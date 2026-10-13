"""Per-user positions and journal pages (Fase 6c, R14).

Both views are read-only (GET) and login-gated. Every read routes through
``for_user(request.user)`` so a user only ever sees their own rows. Business math
is delegated to the pure ``src/`` functions (never reimplemented here); no
secrets, no decryption, no order surface.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from src.analytics import (
    bars_svg,
    calibrate,
    equity_and_drawdown,
    equity_svg,
    group_metrics,
)
from src.journal import metrics as journal_metrics
from src.metrics import equity_curve, expectancy, profit_factor
from src.monitor import liq_distance_pct, margin_state
from trading.analytics import extract_signals
from trading.forms import AlertRuleForm
from trading.models import (
    AccountSnapshot,
    AlertRule,
    PositionSnapshot,
    TickerSnapshot,
    Trade,
)

# Calibration window: a trade matches an SMC signal within one hour (matches the
# hourly signal bar). Hour is caller-supplied UTC: (ctime_ms // 3_600_000) % 24.
CALIBRATION_WINDOW_SECONDS = 3600
HOUR_MS = 3_600_000
_ANALYTICS_DIMENSIONS = ("hour", "symbol")


def _latest_marks(symbols: list[str]) -> dict[str, float | None]:
    """Latest global ticker price per requested symbol (None if absent)."""
    marks: dict[str, float | None] = {}
    for symbol in symbols:
        row = TickerSnapshot.objects.filter(symbol=symbol).order_by("-ts").first()
        marks[symbol] = row.last_price if row else None
    return marks


@login_required
@require_http_methods(["GET"])
def positions(request: HttpRequest) -> HttpResponse:
    user = request.user
    latest = PositionSnapshot.for_user(user).aggregate(ts=Max("ts"))["ts"]
    rows = list(PositionSnapshot.for_user(user).filter(ts=latest)) if latest else []
    marks = _latest_marks([r.symbol for r in rows])

    panel = []
    for r in rows:
        mark = marks.get(r.symbol)
        panel.append(
            {
                "symbol": r.symbol,
                "side": r.side,
                "qty": r.qty,
                "avg_open": r.avg_open,
                "leverage": r.leverage,
                "liq_price": r.liq_price,
                "upnl": r.upnl,
                "margin_rate": r.margin_rate,
                "distance": liq_distance_pct(r.liq_price, mark),
                "margin_state": margin_state(r.margin_rate),
            }
        )
    account = AccountSnapshot.for_user(user).order_by("-ts").first()
    return render(
        request, "trading/positions.html", {"rows": panel, "account": account}
    )


@login_required
@require_http_methods(["GET"])
def journal(request: HttpRequest) -> HttpResponse:
    user = request.user
    rows = [
        {
            "symbol": t.symbol,
            "fee": t.fee or 0.0,
            "realized_pnl": t.realized_pnl or 0.0,
        }
        for t in Trade.for_user(user)
    ]
    nets = [r["realized_pnl"] - r["fee"] for r in rows]
    metrics = journal_metrics(rows)
    return render(
        request,
        "trading/journal.html",
        {
            **metrics,
            "expectancy": expectancy(nets),
            "profit_factor": profit_factor(nets),
            "equity_curve": equity_curve(nets),
            "empty": not rows,
        },
    )


@login_required
@require_http_methods(["GET"])
def analytics_view(request: HttpRequest) -> HttpResponse:
    """Read-only, per-user ``/analytics/`` breakdowns + calibration + inline SVG.

    Every trade read routes through ``Trade.for_user(request.user)`` (R14) — no
    unscoped query. All arithmetic is delegated to the pure ``src/analytics.py``
    (``group_metrics`` the hour/symbol breakdowns, ``calibrate`` the setup join,
    ``equity_and_drawdown``/``*_svg`` the charts); the view only reshapes rows and
    never reimplements a metric or the join. Historical SMC signals come from the
    ``trading.analytics`` seam, which swallows upstream failures (never 500).
    """
    user = request.user
    trades = list(Trade.for_user(user))

    # One net per fill (journal convention: realized PnL minus fee) and the
    # caller-supplied UTC hour (Q4) — the only arithmetic the view does.
    nets: list[float] = []
    rows: list[dict] = []
    trade_rows: list[dict] = []
    ctimes_by_symbol: dict[str, list[int]] = {}
    for t in trades:
        net = (t.realized_pnl or 0.0) - (t.fee or 0.0)
        hour = (t.ctime // HOUR_MS) % 24 if t.ctime is not None else None
        nets.append(net)
        rows.append({"net": net, "hour": hour, "symbol": t.symbol})
        trade_rows.append(
            {
                "net": net,
                "side": t.side,
                "ctime": t.ctime,
                "qty": t.qty or 0.0,
                "symbol": t.symbol,
            }
        )
        if t.ctime is not None:
            ctimes_by_symbol.setdefault(t.symbol, []).append(t.ctime)

    # Historical SMC signals per symbol (frozen seam; degrades to [] on failure).
    signals: list[dict] = []
    for symbol in sorted(ctimes_by_symbol):
        signals.extend(extract_signals(symbol, ctimes_by_symbol[symbol]))

    groups = {dim: group_metrics(rows, dim) for dim in _ANALYTICS_DIMENSIONS}
    calibration = calibrate(
        signals, trade_rows, window_seconds=CALIBRATION_WINDOW_SECONDS
    )

    equity = equity_and_drawdown(nets)
    by_symbol_net: dict[str, float] = {}
    for row in rows:
        by_symbol_net[row["symbol"]] = (
            by_symbol_net.get(row["symbol"], 0.0) + row["net"]
        )
    bars = [
        {"label": symbol, "value": value}
        for symbol, value in sorted(by_symbol_net.items())
    ]

    # Flatten the calibrate setup join into render rows (key + metrics + mean R),
    # so the template needs no dict-index filter (single source stays in src/).
    setup_rows = [
        {"key": key, "metrics": metrics, "risk": calibration["r_by_setup"].get(key)}
        for key, metrics in calibration["by_setup"].items()
    ]

    return render(
        request,
        "trading/analytics.html",
        {
            "groups": groups,
            "calibration": calibration,
            "setup_rows": setup_rows,
            "equity_svg": equity_svg(equity["equity"]),
            "equity_drawdown": equity["max_drawdown"],
            "bars_svg": bars_svg(bars),
            "empty": not trades,
        },
    )


def _get_rule(user, pk: int) -> AlertRule:
    """Fetch the caller's rule by pk; a miss (incl. another user's) -> 404.

    Scoped through ``for_user`` so existence is never leaked (R14/C2).
    """
    rule = AlertRule.for_user(user).filter(pk=pk).first()
    if rule is None:
        raise Http404
    return rule


@login_required
@require_http_methods(["GET"])
def rules(request: HttpRequest) -> HttpResponse:
    """List the caller's alert rules (read-only)."""
    return render(
        request, "trading/rules.html", {"rules": AlertRule.for_user(request.user)}
    )


@login_required
@require_http_methods(["GET", "POST"])
def rule_create(request: HttpRequest) -> HttpResponse:
    """Create a rule; ``owner`` is set explicitly (``for_user`` only filters)."""
    if request.method == "POST":
        form = AlertRuleForm(request.POST)
        if form.is_valid():
            rule = form.save(commit=False)
            rule.user = request.user
            rule.save()
            return redirect("rules")
    else:
        form = AlertRuleForm()
    return render(request, "trading/rules.html", {"form": form, "creating": True})


@login_required
@require_http_methods(["GET", "POST"])
def rule_edit(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit the caller's rule (scoped fetch -> 404 on a foreign pk)."""
    rule = _get_rule(request.user, pk)
    if request.method == "POST":
        form = AlertRuleForm(request.POST, instance=rule)
        if form.is_valid():
            form.save()
            return redirect("rules")
    else:
        form = AlertRuleForm(instance=rule)
    return render(request, "trading/rules.html", {"form": form, "editing": rule})


@login_required
@require_http_methods(["POST"])
def rule_toggle(request: HttpRequest, pk: int) -> HttpResponse:
    """Flip ``is_active``; the config UI never evaluates or sends (C4)."""
    rule = _get_rule(request.user, pk)
    rule.is_active = not rule.is_active
    rule.save(update_fields=["is_active"])
    return redirect("rules")


@login_required
@require_http_methods(["POST"])
def rule_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete the caller's rule (scoped fetch -> 404 on a foreign pk)."""
    _get_rule(request.user, pk).delete()
    return redirect("rules")
