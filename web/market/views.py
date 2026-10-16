"""Market chart page, kline JSON endpoint and the page's JS.

All three views are ``@login_required`` + GET-only. ``chart_js`` serves the
page's JavaScript same-origin (no static/collectstatic infra exists in prod;
inline JS would force ``script-src 'unsafe-inline'``).
"""

from __future__ import annotations

import json
import logging

import requests
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from trading.models import AlertRule, ChartLayout, ChartPreference, Drawing

from market.quotes import (
    CHART_TYPES,
    DEFAULT_LAYOUT,
    INTERVALS,
    SCALE_MODES,
    THEMES,
    get_kline_payload,
    get_smc_payload,
    parse_drawing,
    parse_indicators,
    parse_layout_indicators,
    parse_smc,
)
from src.client import BitunixClient, BitunixError
from src.config import SYMBOLS

logger = logging.getLogger(__name__)

MIN_LIMIT, MAX_LIMIT = 1, 200
SIGNALS_LIMIT = 200

# ESM module serving allowlists (R15). Names are matched against these sets —
# never concatenated into a path — so traversal is impossible. Controllers live
# under ``market/controllers/`` and are served by ``market_controller_js``.
MODULE_ALLOWLIST = frozenset(
    {
        "chart-core",
        "chart-types-core",
        "chart-registry-core",
        "theme-core",
        "drawing-core",
        "drawing-interaction-core",
        "drawing-primitive",
        "tool-icons-core",
        "smc-overlay-core",
        "legend-core",
        "indicator-settings-core",
        "add-indicator-core",
        "measure-core",
        "position-core",
        "chart-store",
        "chart-bus",
        "chart-host",
        "chart-host-candles",
        "main",
    }
)
CONTROLLER_ALLOWLIST: frozenset[str] = frozenset(
    {
        "indicators",
        "history",
        "stream",
        "drawings",
        "drawing-interaction",
        "smc",
        "toolbar",
        "legend",
        "draw-toolbar",
        "object-tree",
        "preference",
        "measure",
    }
)


@login_required
@require_http_methods(["GET"])
def market_page(request: HttpRequest) -> HttpResponse:
    return render(request, "market/chart.html", {"symbols": SYMBOLS})


def _rule_state(rules) -> str:
    """Derive a pair's alert state from its rules (S4 precedence).

    ``fired`` (any ``last_fired_at`` set) > ``armed`` (any active) > ``inactive``
    (a rule exists) > ``none`` (no rule).
    """
    if any(rule.last_fired_at is not None for rule in rules):
        return "fired"
    if any(rule.is_active for rule in rules):
        return "armed"
    if rules:
        return "inactive"
    return "none"


@login_required
@require_http_methods(["GET"])
def signals_page(request: HttpRequest) -> HttpResponse:
    """Server-rendered ``/signals/``: caller's rule pairs + frozen SMC setups.

    Pairs come only from the caller's own ``AlertRule.for_user`` rows (R14); each
    pair calls the frozen ``get_smc_payload`` ONCE (no SMC recompute here) and an
    upstream failure degrades to empty setups, never 500. Read-only: no send, no
    ``last_fired_at`` write, no pagination (S5).
    """
    by_pair: dict[tuple[str, str], list] = {}
    for rule in AlertRule.for_user(request.user):
        by_pair.setdefault((rule.symbol, rule.interval), []).append(rule)

    groups = []
    for (symbol, interval), rules in sorted(by_pair.items()):
        try:
            setups = get_smc_payload(BitunixClient(), symbol, interval, SIGNALS_LIMIT)[
                "setups"
            ]
        except (BitunixError, requests.RequestException):
            logger.warning("signals degraded symbol=%s interval=%s", symbol, interval)
            setups = []
        groups.append(
            {
                "symbol": symbol,
                "interval": interval,
                "setups": setups,
                "state": _rule_state(rules),
            }
        )

    return render(request, "market/signals.html", {"groups": groups})


@login_required
@require_http_methods(["GET"])
def api_kline(request: HttpRequest) -> JsonResponse:
    symbol = request.GET.get("symbol", "")
    interval = request.GET.get("interval", "")
    raw_limit = request.GET.get("limit", "")
    raw_before = request.GET.get("before", "")
    raw_indicators = request.GET.get("indicators", "")

    if interval not in INTERVALS:
        return JsonResponse({"error": "invalid interval"}, status=400)
    if not symbol:
        return JsonResponse({"error": "symbol required"}, status=400)
    try:
        limit = int(raw_limit) if raw_limit else 100
    except ValueError:
        return JsonResponse({"error": "invalid limit"}, status=400)
    if not MIN_LIMIT <= limit <= MAX_LIMIT:
        return JsonResponse({"error": "invalid limit"}, status=400)

    # Validate the indicator selection BEFORE building the payload (R3).
    try:
        indicators = parse_indicators(raw_indicators, request.GET)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    before = None
    if raw_before:
        try:
            before = int(raw_before)
        except ValueError:
            return JsonResponse({"error": "invalid before"}, status=400)
        if before <= 0:
            return JsonResponse({"error": "invalid before"}, status=400)

    try:
        payload = get_kline_payload(
            BitunixClient(), symbol, interval, limit, before, indicators
        )
    except BitunixError:
        # Upstream rejects the request (API code != 0, e.g. unknown symbol).
        return JsonResponse({"error": "upstream rejected"}, status=400)
    except requests.RequestException:
        # Network failure (timeout, conn refused) — an upstream problem.
        return JsonResponse({"error": "upstream"}, status=502)

    return JsonResponse(payload)


@login_required
@require_http_methods(["GET"])
def api_smc(request: HttpRequest) -> JsonResponse:
    """Read-only SMC analysis for one candle window (R12, market-global).

    Validates ``symbol``/``interval``/``limit`` BEFORE any work, then runs the
    frozen ``src/smc/`` chain over the same DB-first window as ``api_kline``.
    SMC is market data — no ``for_user`` scoping, no write. Thin windows degrade
    to empty arrays + ``range:null`` (200); upstream failure mirrors ``api_kline``.
    """
    symbol = request.GET.get("symbol", "")
    interval = request.GET.get("interval", "")
    raw_limit = request.GET.get("limit", "")

    if interval not in INTERVALS:
        return JsonResponse({"error": "invalid interval"}, status=400)
    if not symbol:
        return JsonResponse({"error": "symbol required"}, status=400)
    try:
        limit = int(raw_limit) if raw_limit else 200
    except ValueError:
        return JsonResponse({"error": "invalid limit"}, status=400)
    if not MIN_LIMIT <= limit <= MAX_LIMIT:
        return JsonResponse({"error": "invalid limit"}, status=400)

    try:
        payload = get_smc_payload(BitunixClient(), symbol, interval, limit)
    except BitunixError:
        return JsonResponse({"error": "upstream rejected"}, status=400)
    except requests.RequestException:
        return JsonResponse({"error": "upstream"}, status=502)

    return JsonResponse(payload)


@login_required
@require_http_methods(["GET", "PUT"])
def api_layout(request: HttpRequest) -> JsonResponse:
    """Per-user chart layout (R2/R3): GET reads, PUT upserts, one row per key.

    All access routes through ``ChartLayout.for_user`` — no unscoped query in
    this request path (R14.3). A GET miss returns the built-in default set with
    ``exists:false`` (never 404). A PUT validates the payload BEFORE writing;
    an unknown token or bad param → 400 with no row touched.
    """
    if request.method == "PUT":
        return _put_layout(request)

    symbol = request.GET.get("symbol", "")
    interval = request.GET.get("interval", "")
    if not symbol:
        return JsonResponse({"error": "symbol required"}, status=400)
    if interval not in INTERVALS:
        return JsonResponse({"error": "invalid interval"}, status=400)

    saved = (
        ChartLayout.for_user(request.user)
        .filter(symbol=symbol, interval=interval)
        .first()
    )
    if saved is None:
        return JsonResponse(
            {
                "symbol": symbol,
                "interval": interval,
                "indicators": DEFAULT_LAYOUT,
                "exists": False,
            }
        )
    return JsonResponse(
        {
            "symbol": saved.symbol,
            "interval": saved.interval,
            "indicators": saved.indicators,
            "exists": True,
        }
    )


def _put_layout(request: HttpRequest) -> JsonResponse:
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "invalid body"}, status=400)

    symbol = body.get("symbol", "")
    interval = body.get("interval", "")
    if not symbol:
        return JsonResponse({"error": "symbol required"}, status=400)
    if interval not in INTERVALS:
        return JsonResponse({"error": "invalid interval"}, status=400)
    try:
        indicators = parse_layout_indicators(body.get("indicators"))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    layout, _ = ChartLayout.for_user(request.user).update_or_create(
        user=request.user,
        symbol=symbol,
        interval=interval,
        defaults={"indicators": indicators},
    )
    return JsonResponse(
        {
            "symbol": layout.symbol,
            "interval": layout.interval,
            "indicators": layout.indicators,
            "exists": True,
        }
    )


@login_required
@require_http_methods(["GET", "PUT"])
def api_preference(request: HttpRequest) -> JsonResponse:
    """Per-user, user-global chart preference (R8/R9): GET reads, PUT upserts.

    All access routes through ``ChartPreference.for_user`` — no unscoped query in
    this request path (R14.3). A GET miss returns the defaults with
    ``exists:false`` (never 404). A PUT accepts a PARTIAL body: each present field
    is validated BEFORE any write; an invalid value → 400 with no row touched.
    """
    if request.method == "PUT":
        return _put_preference(request)

    saved = ChartPreference.for_user(request.user).first()
    if saved is None:
        return JsonResponse(_preference_defaults())
    return JsonResponse(_preference_body(saved))


# Absent-preference body: field defaults + ``exists:false``. The single source
# for the "no row" shape returned by GET, an empty PUT and a defaults PUT.
_PREFERENCE_DEFAULTS = {
    "interval": "1m",
    "scale_mode": "linear",
    "chart_type": "candles",
    "theme": "system",
    "smc": {},
}


def _preference_defaults() -> dict:
    return {**_PREFERENCE_DEFAULTS, "exists": False}


def _preference_body(pref) -> dict:
    return {
        "interval": pref.last_interval,
        "scale_mode": pref.scale_mode,
        "chart_type": pref.chart_type,
        "theme": pref.theme,
        "smc": pref.smc,
        "exists": True,
    }


def _put_preference(request: HttpRequest) -> JsonResponse:
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "invalid body"}, status=400)

    # Validate every PRESENT field before any write (per-field 400, no partial
    # write). Absent keys are left untouched (partial body).
    defaults: dict = {}
    if "interval" in body:
        if body["interval"] not in INTERVALS:
            return JsonResponse({"error": "invalid interval"}, status=400)
        defaults["last_interval"] = body["interval"]
    if "scale_mode" in body:
        if body["scale_mode"] not in SCALE_MODES:
            return JsonResponse({"error": "invalid scale_mode"}, status=400)
        defaults["scale_mode"] = body["scale_mode"]
    if "chart_type" in body:
        if body["chart_type"] not in CHART_TYPES:
            return JsonResponse({"error": "invalid chart_type"}, status=400)
        defaults["chart_type"] = body["chart_type"]
    if "theme" in body:
        if body["theme"] not in THEMES:
            return JsonResponse({"error": "invalid theme"}, status=400)
        defaults["theme"] = body["theme"]
    if "smc" in body:
        try:
            defaults["smc"] = parse_smc(body["smc"])
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)

    if not defaults:
        # Nothing to apply: return the current preference (or the defaults)
        # without creating a row.
        saved = ChartPreference.for_user(request.user).first()
        if saved is None:
            return JsonResponse(_preference_defaults())
        return JsonResponse(_preference_body(saved))

    # for_user filters; it does NOT inject the owner (A2 gotcha) — pass user.
    pref, _ = ChartPreference.for_user(request.user).update_or_create(
        user=request.user,
        defaults=defaults,
    )
    return JsonResponse(_preference_body(pref))


@login_required
@require_http_methods(["GET", "POST"])
def api_drawings(request: HttpRequest) -> JsonResponse:
    """Per-user, per-SYMBOL drawing collection (R2): GET lists, POST creates.

    All access routes through ``Drawing.for_user`` — no unscoped query in this
    request path (R14.3). GET keys on ``symbol`` ONLY (no ``interval``; a stray
    query key is ignored) and never 404s (an empty symbol returns ``[]``). POST
    validates the payload BEFORE writing; a bad body → 400 with no row created.
    An incoming ``interval`` key is accepted and ignored (stale clients).
    """
    if request.method == "POST":
        return _post_drawing(request)

    symbol = request.GET.get("symbol", "")
    if not symbol:
        return JsonResponse({"error": "symbol required"}, status=400)

    rows = Drawing.for_user(request.user).filter(symbol=symbol)
    return JsonResponse(
        {
            "symbol": symbol,
            "drawings": [
                {
                    "id": d.id,
                    "kind": d.kind,
                    "points": d.points,
                    "style": d.style,
                    "visible": d.visible,
                    "locked": d.locked,
                }
                for d in rows
            ],
        }
    )


def _post_drawing(request: HttpRequest) -> JsonResponse:
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "invalid body"}, status=400)

    symbol = body.get("symbol", "")
    if not symbol:
        return JsonResponse({"error": "symbol required"}, status=400)
    # ``interval`` is deliberately NOT read: the key is per SYMBOL now. A stale
    # client may still send one — accept-and-ignore, never 400 (R4).
    try:
        points, style, visible, locked = parse_drawing(
            body.get("kind"),
            body.get("points"),
            body.get("style"),
            body.get("visible", True),
            body.get("locked", False),
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    # for_user filters; it does NOT inject the owner (A2 gotcha) — pass user.
    drawing = Drawing.for_user(request.user).create(
        user=request.user,
        symbol=symbol,
        kind=body["kind"],
        points=points,
        style=style,
        visible=visible,
        locked=locked,
    )
    return JsonResponse(
        {
            "id": drawing.id,
            "kind": drawing.kind,
            "points": drawing.points,
            "style": drawing.style,
            "visible": drawing.visible,
            "locked": drawing.locked,
        },
        status=201,
    )


@login_required
@require_http_methods(["PUT", "DELETE"])
def api_drawing_detail(request: HttpRequest, id: int) -> HttpResponse:
    """PUT updates / DELETE removes one drawing by id (R2/R3/R14.6).

    Both verbs resolve the row through ``Drawing.for_user(request.user)`` — an
    id-only lookup MUST NOT be used. A miss (including another user's id) is a
    404, so existence is never leaked. PUT accepts a PARTIAL ``{points?, style?}``
    body: ``kind`` is immutable (a differing value → 400), validation runs via
    ``parse_drawing`` BEFORE any write (a bad payload → 400 with no row touched),
    and only the provided fields are persisted.
    """
    drawing = Drawing.for_user(request.user).filter(pk=id).first()
    if drawing is None:
        return JsonResponse({"error": "not found"}, status=404)
    if request.method == "DELETE":
        drawing.delete()
        return HttpResponse(status=204)
    return _put_drawing(request, drawing)


def _put_drawing(request: HttpRequest, drawing: Drawing) -> JsonResponse:
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "invalid body"}, status=400)

    # ``kind`` is immutable (D9): a differing value is rejected. An equal value
    # is accepted and ignored (mirrors the stale-``interval`` precedent).
    if "kind" in body and body["kind"] != drawing.kind:
        return JsonResponse({"error": "kind is immutable"}, status=400)

    # Partial body: each absent field keeps the stored value. Validation runs
    # BEFORE any write, so a bad payload leaves the row untouched.
    try:
        points, style, visible, locked = parse_drawing(
            drawing.kind,
            body.get("points", drawing.points),
            body.get("style", drawing.style),
            body.get("visible", drawing.visible),
            body.get("locked", drawing.locked),
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    drawing.points, drawing.style = points, style
    drawing.visible, drawing.locked = visible, locked
    drawing.save(update_fields=["points", "style", "visible", "locked"])
    return JsonResponse(
        {
            "id": drawing.id,
            "kind": drawing.kind,
            "points": drawing.points,
            "style": drawing.style,
            "visible": drawing.visible,
            "locked": drawing.locked,
        }
    )


@login_required
@require_http_methods(["GET"])
def chart_js(request: HttpRequest) -> HttpResponse:
    return HttpResponse(
        render(request, "market/chart.js", {"symbols": json.dumps(SYMBOLS)}).content,
        content_type="text/javascript",
    )


@require_http_methods(["GET"])
def market_chart_module_js(request: HttpRequest, name: str) -> HttpResponse:
    """Serve an allowlisted ESM chart module same-origin (no state, no auth).

    The allowlist (not a filesystem path) blocks traversal: any name outside
    ``MODULE_ALLOWLIST`` is a 404. Modules are plain JS, so ``text/javascript``.
    """
    return _serve_allowlisted(request, name, MODULE_ALLOWLIST, "")


@require_http_methods(["GET"])
def market_controller_js(request: HttpRequest, name: str) -> HttpResponse:
    """Serve an allowlisted controller module from ``market/controllers/``.

    Same allowlist discipline as ``market_chart_module_js``; the allowlist is
    populated as controllers ship.
    """
    return _serve_allowlisted(request, name, CONTROLLER_ALLOWLIST, "controllers/")


def _serve_allowlisted(
    request: HttpRequest, name: str, allowlist: frozenset[str], subdir: str
) -> HttpResponse:
    if name not in allowlist:
        raise Http404("unknown module")
    return HttpResponse(
        render(request, f"market/{subdir}{name}.js").content,
        content_type="text/javascript",
    )
