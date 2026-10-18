"""JSON alert-rule transport for the chart bell (F10, R10/R11).

One self-contained CRUD over the frozen ``AlertRule`` model and the frozen
``parse_condition`` engine, mirroring the drawings API (``views.py:411-554``).
Every read routes through ``AlertRule.for_user`` and every write passes
``user=request.user`` explicitly (``for_user`` filters, it does not inject).

A rule is interval-scoped, so GET keys on ``symbol`` AND ``interval``. The
``interval`` MUST be a persisted candle interval (``CANDLE_INTERVALS``): the
worker skips anything else, so a rule outside it would be a permanent no-op.
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from trading.candles import CANDLE_INTERVALS
from trading.models import AlertRule

from src.alert_rules import parse_condition
from src.config import SYMBOLS

_CHAT_ID_MAX = 64


def _row(rule: AlertRule) -> dict:
    """Single row shape shared by every verb (R10)."""
    fired = rule.last_fired_at
    return {
        "id": rule.id,
        "symbol": rule.symbol,
        "interval": rule.interval,
        "condition": rule.condition,
        "is_active": rule.is_active,
        "last_fired_at": int(fired.timestamp()) if fired is not None else None,
        "telegram_chat_id": rule.telegram_chat_id,
    }


def _pair_error(symbol: object, interval: object) -> str | None:
    """Validation steps 1-4; returns the first error message, or ``None``."""
    if not symbol:
        return "symbol required"
    if symbol not in SYMBOLS:
        return "invalid symbol"
    if not interval:
        return "interval required"
    if interval not in CANDLE_INTERVALS:
        return "invalid interval"
    return None


def _post_alert(request: HttpRequest) -> JsonResponse:
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "invalid body"}, status=400)

    symbol = body.get("symbol")
    interval = body.get("interval")
    error = _pair_error(symbol, interval)
    if error is not None:
        return JsonResponse({"error": error}, status=400)

    try:
        condition = parse_condition(body.get("condition"))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    is_active = body.get("is_active", True)
    # ``True`` is an ``int``: require a real bool, not truthiness.
    if not isinstance(is_active, bool):
        return JsonResponse({"error": "is_active must be a boolean"}, status=400)

    chat_id = body.get("telegram_chat_id", "")
    if not isinstance(chat_id, str) or len(chat_id) > _CHAT_ID_MAX:
        return JsonResponse({"error": "invalid telegram_chat_id"}, status=400)

    # for_user filters; it does NOT inject the owner — pass user explicitly.
    rule = AlertRule.for_user(request.user).create(
        user=request.user,
        symbol=symbol,
        interval=interval,
        condition=condition,
        is_active=is_active,
        telegram_chat_id=chat_id,
    )
    return JsonResponse(_row(rule), status=201)


@login_required
@require_http_methods(["GET", "POST"])
def api_alerts(request: HttpRequest) -> JsonResponse:
    """Per-user, pair-scoped alert collection: GET lists, POST creates."""
    if request.method == "POST":
        return _post_alert(request)

    symbol = request.GET.get("symbol", "")
    interval = request.GET.get("interval", "")
    error = _pair_error(symbol, interval)
    if error is not None:
        return JsonResponse({"error": error}, status=400)

    rows = AlertRule.for_user(request.user).filter(symbol=symbol, interval=interval)
    return JsonResponse(
        {
            "symbol": symbol,
            "interval": interval,
            "alerts": [_row(r) for r in rows],
        }
    )


@login_required
@require_http_methods(["PUT", "DELETE"])
def api_alert_detail(request: HttpRequest, id: int) -> HttpResponse:
    """PUT updates / DELETE removes one alert rule by id (R10/R11).

    Both verbs resolve the row through ``AlertRule.for_user(request.user)`` — an
    id-only lookup MUST NOT be used. A miss (including another user's id) is a
    404, so existence is never leaked. PUT is PARTIAL: ``symbol``/``interval``
    are immutable (a differing value → 400, mirroring ``_put_drawing``),
    ``condition`` is re-validated with ``parse_condition`` BEFORE any write, and
    only the provided fields are persisted.
    """
    rule = AlertRule.for_user(request.user).filter(pk=id).first()
    if rule is None:
        return JsonResponse({"error": "not found"}, status=404)
    if request.method == "DELETE":
        rule.delete()
        return HttpResponse(status=204)
    return _put_alert(request, rule)


_UPDATABLE = ("condition", "is_active", "telegram_chat_id")


def _put_alert(request: HttpRequest, rule: AlertRule) -> JsonResponse:
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "invalid body"}, status=400)

    # A rule is pair-scoped: moving it would silently leave the worker's group.
    for field in ("symbol", "interval"):
        if field in body and body[field] != getattr(rule, field):
            return JsonResponse({"error": f"{field} is immutable"}, status=400)

    if not any(field in body for field in _UPDATABLE):
        return JsonResponse({"error": "no updatable field"}, status=400)

    changed = []
    if "condition" in body:
        try:
            rule.condition = parse_condition(body["condition"])
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        changed.append("condition")

    if "is_active" in body:
        # ``True`` is an ``int``: require a real bool, not truthiness.
        if not isinstance(body["is_active"], bool):
            return JsonResponse({"error": "is_active must be a boolean"}, status=400)
        rule.is_active = body["is_active"]
        changed.append("is_active")

    if "telegram_chat_id" in body:
        chat_id = body["telegram_chat_id"]
        if not isinstance(chat_id, str) or len(chat_id) > _CHAT_ID_MAX:
            return JsonResponse({"error": "invalid telegram_chat_id"}, status=400)
        rule.telegram_chat_id = chat_id
        changed.append("telegram_chat_id")

    rule.save(update_fields=changed)
    return JsonResponse(_row(rule))
