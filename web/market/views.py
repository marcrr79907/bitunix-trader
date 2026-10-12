"""Market chart page, kline JSON endpoint and the page's JS.

All three views are ``@login_required`` + GET-only. ``chart_js`` serves the
page's JavaScript same-origin (no static/collectstatic infra exists in prod;
inline JS would force ``script-src 'unsafe-inline'``).
"""

from __future__ import annotations

import json

import requests
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from trading.models import ChartLayout, Drawing

from market.quotes import (
    DEFAULT_LAYOUT,
    INTERVALS,
    get_kline_payload,
    parse_drawing,
    parse_indicators,
    parse_layout_indicators,
)
from src.client import BitunixClient, BitunixError
from src.config import SYMBOLS

MIN_LIMIT, MAX_LIMIT = 1, 200


@login_required
@require_http_methods(["GET"])
def market_page(request: HttpRequest) -> HttpResponse:
    return render(request, "market/chart.html", {"symbols": SYMBOLS})


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
@require_http_methods(["GET", "POST"])
def api_drawings(request: HttpRequest) -> JsonResponse:
    """Per-user drawing collection (R2): GET lists, POST creates.

    All access routes through ``Drawing.for_user`` — no unscoped query in this
    request path (R14.3). GET never 404s (an empty key returns ``[]``). POST
    validates the payload BEFORE writing; a bad body → 400 with no row created.
    """
    if request.method == "POST":
        return _post_drawing(request)

    symbol = request.GET.get("symbol", "")
    interval = request.GET.get("interval", "")
    if not symbol:
        return JsonResponse({"error": "symbol required"}, status=400)
    if interval not in INTERVALS:
        return JsonResponse({"error": "invalid interval"}, status=400)

    rows = Drawing.for_user(request.user).filter(symbol=symbol, interval=interval)
    return JsonResponse(
        {
            "symbol": symbol,
            "interval": interval,
            "drawings": [
                {"id": d.id, "kind": d.kind, "points": d.points, "style": d.style}
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
    interval = body.get("interval", "")
    if not symbol:
        return JsonResponse({"error": "symbol required"}, status=400)
    if interval not in INTERVALS:
        return JsonResponse({"error": "invalid interval"}, status=400)
    try:
        points, style = parse_drawing(
            body.get("kind"), body.get("points"), body.get("style")
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    # for_user filters; it does NOT inject the owner (A2 gotcha) — pass user.
    drawing = Drawing.for_user(request.user).create(
        user=request.user,
        symbol=symbol,
        interval=interval,
        kind=body["kind"],
        points=points,
        style=style,
    )
    return JsonResponse(
        {
            "id": drawing.id,
            "kind": drawing.kind,
            "points": drawing.points,
            "style": drawing.style,
        },
        status=201,
    )


@login_required
@require_http_methods(["DELETE"])
def api_drawing_detail(request: HttpRequest, id: int) -> HttpResponse:
    """DELETE one drawing by id (R2/R3): scoped via ``for_user``.

    A miss — including another user's id — resolves to nothing → 404, so
    existence is never leaked (no id-only lookup).
    """
    drawing = Drawing.for_user(request.user).filter(pk=id).first()
    if drawing is None:
        return JsonResponse({"error": "not found"}, status=404)
    drawing.delete()
    return HttpResponse(status=204)


@login_required
@require_http_methods(["GET"])
def chart_js(request: HttpRequest) -> HttpResponse:
    return HttpResponse(
        render(request, "market/chart.js", {"symbols": json.dumps(SYMBOLS)}).content,
        content_type="text/javascript",
    )


@require_http_methods(["GET"])
def chart_core_js(request: HttpRequest) -> HttpResponse:
    """Serve the pure chart core same-origin (no state; not auth-gated)."""
    return HttpResponse(
        render(request, "market/chart-core.js").content,
        content_type="text/javascript",
    )
