"""Per-user positions and journal pages (Fase 6c, R14).

Both views are read-only (GET) and login-gated. Every read routes through
``for_user(request.user)`` so a user only ever sees their own rows. Business math
is delegated to the pure ``src/`` functions (never reimplemented here); no
secrets, no decryption, no order surface.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from src.journal import metrics as journal_metrics
from src.metrics import equity_curve, expectancy, profit_factor
from src.monitor import liq_distance_pct, margin_state
from trading.models import AccountSnapshot, PositionSnapshot, TickerSnapshot, Trade


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
