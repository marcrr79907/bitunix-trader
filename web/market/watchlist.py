"""JSON watchlist transport for the chart's symbol picker (F11 A-S2, R14.8-R14.10).

Mirrors ``market/alerts.py``: a self-contained JSON API over an owned model, with
every read and write routed through ``Watchlist.for_user`` (R14). The owner is
never taken from the body.

An empty list falls back VIRTUALLY to ``config.SYMBOLS`` with ``default: true``:
GET stays a read (no seeding), and a later ``BITUNIX_SYMBOLS`` change stays
visible to users who never curated a list.

Symbol validation is shared with the catalog and the worker through
``catalog.SYMBOL_RE``. The catalog lookup only runs for a well-formed symbol, so
an unknown-when-warm symbol is rejected while a cold catalog fails open (the
alerts path makes the same choice — see ``symbol-catalog`` R4).
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods
from trading.models import Watchlist

from market import catalog
from src.config import MAX_WATCHLIST_SYMBOLS, SYMBOLS


def _symbols_body(user) -> dict:
    """The caller's list, sorted; virtual default when they have none."""
    symbols = list(
        Watchlist.for_user(user).order_by("symbol").values_list("symbol", flat=True)
    )
    if not symbols:
        return {"symbols": list(SYMBOLS), "default": True}
    return {"symbols": symbols, "default": False}


def _known(symbol: str) -> bool | None:
    """Catalog membership: ``True``/``False`` warm, ``None`` when unavailable."""
    try:
        return catalog.symbol_exists(symbol)
    except Exception:  # ponytail: any upstream failure means "cold", same as alerts
        return None


@login_required
@require_http_methods(["GET", "POST"])
def api_watchlist(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse(_symbols_body(request.user))

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "invalid body"}, status=400)

    symbol = body.get("symbol", "")
    if not isinstance(symbol, str) or not catalog.SYMBOL_RE.match(symbol):
        return JsonResponse({"error": "invalid symbol"}, status=400)

    if _known(symbol) is False:
        return JsonResponse({"error": "invalid symbol"}, status=400)

    owned = Watchlist.for_user(request.user)
    if not owned.filter(symbol=symbol).exists():
        if owned.count() >= MAX_WATCHLIST_SYMBOLS:
            return JsonResponse(
                {"error": f"watchlist limited to {MAX_WATCHLIST_SYMBOLS} symbols"},
                status=400,
            )
        owned.get_or_create(user=request.user, symbol=symbol)

    return JsonResponse({"symbol": symbol, **_symbols_body(request.user)}, status=201)


@login_required
@require_http_methods(["DELETE"])
def api_watchlist_detail(request: HttpRequest, symbol: str) -> JsonResponse:
    Watchlist.for_user(request.user).filter(symbol=symbol).delete()
    return JsonResponse({}, status=204)
