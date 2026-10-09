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

from market.quotes import INTERVALS, get_kline_payload
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

    try:
        payload = get_kline_payload(BitunixClient(), symbol, interval, limit)
    except BitunixError:
        # Upstream rejects the request (API code != 0, e.g. unknown symbol).
        return JsonResponse({"error": "upstream rejected"}, status=400)
    except requests.RequestException:
        # Network failure (timeout, conn refused) — an upstream problem.
        return JsonResponse({"error": "upstream"}, status=502)

    return JsonResponse(payload)


@login_required
@require_http_methods(["GET"])
def chart_js(request: HttpRequest) -> HttpResponse:
    return HttpResponse(
        render(request, "market/chart.js", {"symbols": json.dumps(SYMBOLS)}).content,
        content_type="text/javascript",
    )
