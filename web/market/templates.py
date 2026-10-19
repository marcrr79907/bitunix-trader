"""JSON layout-template transport for the chart (F11-B, T2/T3).

Mirrors ``market/alerts.py`` and ``market/watchlist.py``: a self-contained JSON
API over an owned model, every access routed through
``ChartTemplate.for_user`` (R14), the owner never taken from the body.

A template stores the EXACT list shape ``ChartLayout`` stores, so
``quotes.parse_layout_indicators`` is the single validation point for both — no
second schema, no second set of rules. Validation runs before any write.
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods
from trading.models import ChartTemplate

from market.quotes import parse_layout_indicators


def _row(template: ChartTemplate) -> dict:
    return {
        "id": template.id,
        "name": template.name,
        "indicators": template.indicators,
    }


@login_required
@require_http_methods(["GET", "POST"])
def api_templates(request: HttpRequest) -> JsonResponse:
    owned = ChartTemplate.for_user(request.user)

    if request.method == "GET":
        return JsonResponse(
            {"templates": [_row(t) for t in owned.all()]}  # Meta.ordering: name
        )

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "invalid body"}, status=400)

    raw_name = body.get("name")
    if not isinstance(raw_name, str):
        return JsonResponse({"error": "invalid name"}, status=400)
    name = raw_name.strip()
    if not name or len(name) > ChartTemplate.NAME_MAX:
        return JsonResponse({"error": "invalid name"}, status=400)

    try:
        indicators = parse_layout_indicators(body.get("indicators"))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    # Pre-check so a duplicate is a clean 400 instead of an IntegrityError; the
    # unique constraint remains the backstop.
    if owned.filter(name=name).exists():
        return JsonResponse({"error": "template exists"}, status=400)

    # ``for_user`` is the scoping seam the owned-model guard recognises (R14).
    # It filters rather than injecting, so the owner is passed explicitly — the
    # same shape as ``ChartPreference`` in views.py:428.
    template = ChartTemplate.for_user(request.user).create(
        user=request.user, name=name, indicators=indicators
    )
    return JsonResponse(_row(template), status=201)


@login_required
@require_http_methods(["DELETE"])
def api_template_detail(request: HttpRequest, id: int) -> JsonResponse:
    """Delete one template. A foreign or absent id is a 404 with no leak."""
    deleted, _ = ChartTemplate.for_user(request.user).filter(pk=id).delete()
    if not deleted:
        return JsonResponse({"error": "not found"}, status=404)
    return JsonResponse({}, status=204)
