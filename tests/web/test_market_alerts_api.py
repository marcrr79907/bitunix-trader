"""R10/R11 contract: JSON alert-rule transport (F10 S1a, GET + POST).

Mirrors the drawings API tests (``test_market_api.py:1216-1450``): login-gated,
``for_user``-scoped, pair-keyed GET (``symbol`` AND ``interval``), and a POST
that validates in the documented order BEFORE writing. ``condition`` is
normalized by the engine's own ``parse_condition`` (single source), so the bell
can never persist a shape the evaluator would reject.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from django.test import Client
from trading.models import AlertRule

ALERTS_URL = "/market/api/alerts"

ANON = Client()
USER = Client()


@pytest.fixture(autouse=True)
def _auth_user(db):
    global AUTH_USER
    from django.contrib.auth import get_user_model

    AUTH_USER = get_user_model().objects.create_user(
        email="alerts@example.com", password="pw-123456"
    )
    USER.force_login(AUTH_USER)


AUTH_USER = None


def _rule(user, **overrides):
    kwargs = {
        "user": user,
        "symbol": "BTCUSDT",
        "interval": "1h",
        "condition": {"type": "price", "op": "above", "level": 100.0},
    }
    kwargs.update(overrides)
    return AlertRule.objects.create(**kwargs)


# --- GET --------------------------------------------------------------------


def test_alerts_anonymous_get_redirects_to_login():
    response = ANON.get(f"{ALERTS_URL}?symbol=BTCUSDT&interval=1h")
    assert response.status_code == 302
    assert response.url.startswith("/login/")


def test_alerts_get_missing_symbol_is_400():
    response = USER.get(f"{ALERTS_URL}?interval=1h")
    assert response.status_code == 400
    assert "error" in response.json()


def test_alerts_get_missing_interval_is_400():
    response = USER.get(f"{ALERTS_URL}?symbol=BTCUSDT")
    assert response.status_code == 400
    assert "error" in response.json()


def test_alerts_get_invalid_interval_is_400():
    response = USER.get(f"{ALERTS_URL}?symbol=BTCUSDT&interval=1m")
    assert response.status_code == 400
    assert "error" in response.json()


def test_alerts_get_empty_returns_empty_list_not_404():
    response = USER.get(f"{ALERTS_URL}?symbol=BTCUSDT&interval=1h")

    assert response.status_code == 200
    assert response.json() == {"symbol": "BTCUSDT", "interval": "1h", "alerts": []}
    assert AlertRule.objects.count() == 0


def test_alerts_get_lists_only_the_requested_pair():
    _rule(AUTH_USER, interval="1h")
    _rule(AUTH_USER, interval="5m")
    _rule(AUTH_USER, symbol="ETHUSDT", interval="1h")

    body = USER.get(f"{ALERTS_URL}?symbol=BTCUSDT&interval=1h").json()

    assert body["symbol"] == "BTCUSDT"
    assert body["interval"] == "1h"
    assert len(body["alerts"]) == 1
    assert body["alerts"][0]["interval"] == "1h"
    assert body["alerts"][0]["symbol"] == "BTCUSDT"


def test_alerts_get_never_leaks_another_users_rows():
    from django.contrib.auth import get_user_model

    _rule(AUTH_USER)

    b_client = Client()
    b = get_user_model().objects.create_user(
        email="alerts-b@example.com", password="pw-123456"
    )
    b_client.force_login(b)

    body = b_client.get(f"{ALERTS_URL}?symbol=BTCUSDT&interval=1h").json()
    assert body["alerts"] == []


def test_alerts_get_row_shape_and_epoch_last_fired_at():
    rule = _rule(
        AUTH_USER,
        telegram_chat_id="42",
        last_fired_at=datetime.fromtimestamp(1729220400, tz=UTC),
    )

    row = USER.get(f"{ALERTS_URL}?symbol=BTCUSDT&interval=1h").json()["alerts"][0]

    assert row == {
        "id": rule.id,
        "symbol": "BTCUSDT",
        "interval": "1h",
        "condition": {"type": "price", "op": "above", "level": 100.0},
        "is_active": True,
        "last_fired_at": 1729220400,
        "telegram_chat_id": "42",
    }


# --- POST -------------------------------------------------------------------


def _body(**overrides):
    body = {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "condition": {"type": "price", "op": "above", "level": 50000},
    }
    body.update(overrides)
    return body


def _post(client, payload):
    return client.post(
        ALERTS_URL, data=json.dumps(payload), content_type="application/json"
    )


def test_alerts_anonymous_post_redirects_to_login():
    response = _post(ANON, _body())
    assert response.status_code == 302
    assert response.url.startswith("/login/")


def test_alerts_post_requires_csrf():
    enforcing = Client(enforce_csrf_checks=True)
    enforcing.force_login(AUTH_USER)
    response = enforcing.post(
        ALERTS_URL, data=json.dumps(_body()), content_type="application/json"
    )
    assert response.status_code == 403


def test_alerts_post_valid_creates_row_owned_by_caller():
    response = _post(USER, _body(telegram_chat_id="99"))

    assert response.status_code == 201
    row = response.json()
    assert row["symbol"] == "BTCUSDT"
    assert row["interval"] == "1h"
    assert row["condition"] == {"type": "price", "op": "above", "level": 50000.0}
    assert row["is_active"] is True
    assert row["last_fired_at"] is None
    assert row["telegram_chat_id"] == "99"
    assert isinstance(row["id"], int)

    stored = AlertRule.objects.get(pk=row["id"])
    assert stored.user == AUTH_USER
    assert stored.condition == {"type": "price", "op": "above", "level": 50000.0}


def test_alerts_post_normalizes_integer_level_to_float():
    response = _post(
        USER, _body(condition={"type": "price", "op": "below", "level": 100})
    )

    assert response.status_code == 201
    assert response.json()["condition"] == {
        "type": "price",
        "op": "below",
        "level": 100.0,
    }


def test_alerts_post_round_trips_through_get():
    created = _post(USER, _body()).json()

    body = USER.get(f"{ALERTS_URL}?symbol=BTCUSDT&interval=1h").json()
    assert body["alerts"] == [created]


def test_alerts_post_owner_is_never_taken_from_the_body():
    from django.contrib.auth import get_user_model

    other = get_user_model().objects.create_user(
        email="alerts-other@example.com", password="pw-123456"
    )

    response = _post(USER, _body(user=other.id))

    assert response.status_code == 201
    assert AlertRule.objects.get(pk=response.json()["id"]).user == AUTH_USER


def test_alerts_post_invalid_json_is_400():
    response = USER.post(ALERTS_URL, data="not-json", content_type="application/json")
    assert response.status_code == 400
    assert "error" in response.json()
    assert AlertRule.objects.count() == 0


def test_alerts_post_non_object_body_is_400():
    response = _post(USER, [1, 2, 3])
    assert response.status_code == 400
    assert "error" in response.json()
    assert AlertRule.objects.count() == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"symbol": ""},
        {"symbol": "NOTAPAIR"},
        {"interval": ""},
        {"interval": "1m"},
        {"interval": "7m"},
    ],
    ids=["empty-symbol", "unknown-symbol", "empty-interval", "1m", "unknown"],
)
def test_alerts_post_bad_pair_is_400_and_writes_nothing(overrides):
    response = _post(USER, _body(**overrides))
    assert response.status_code == 400
    assert "error" in response.json()
    assert AlertRule.objects.count() == 0


@pytest.mark.parametrize(
    "condition",
    [
        {"type": "magic"},
        {"type": "price", "op": "sideways", "level": 1},
        {"type": "price", "op": "above", "level": "abc"},
        {"type": "price", "op": "above", "level": "100"},
        {"type": "price", "op": "above"},
        "not-an-object",
    ],
    ids=[
        "unknown-type",
        "bad-op",
        "non-numeric",
        "numeric-string",
        "missing-level",
        "not-object",
    ],
)
def test_alerts_post_bad_condition_is_400_and_writes_nothing(condition):
    response = _post(USER, _body(condition=condition))
    assert response.status_code == 400
    assert "error" in response.json()
    assert AlertRule.objects.count() == 0


@pytest.mark.parametrize("is_active", ["true", 1, 0, None, []], ids=str)
def test_alerts_post_non_bool_is_active_is_400(is_active):
    response = _post(USER, _body(is_active=is_active))
    assert response.status_code == 400
    assert response.json() == {"error": "is_active must be a boolean"}
    assert AlertRule.objects.count() == 0


def test_alerts_post_is_active_false_is_accepted():
    response = _post(USER, _body(is_active=False))
    assert response.status_code == 201
    assert response.json()["is_active"] is False


def test_alerts_post_non_str_telegram_chat_id_is_400():
    response = _post(USER, _body(telegram_chat_id=42))
    assert response.status_code == 400
    assert "error" in response.json()
    assert AlertRule.objects.count() == 0


def test_alerts_post_telegram_chat_id_over_64_chars_is_400():
    response = _post(USER, _body(telegram_chat_id="9" * 65))
    assert response.status_code == 400
    assert AlertRule.objects.count() == 0


@pytest.mark.parametrize(
    "interval",
    ["5m", "15m", "1h", "2h", "4h", "1d", "1w", "1M"],
)
def test_alerts_post_accepts_every_evaluable_interval(interval):
    response = _post(USER, _body(interval=interval))
    assert response.status_code == 201
    assert response.json()["interval"] == interval


def test_alerts_post_b_is_invisible_to_a():
    from django.contrib.auth import get_user_model

    b_client = Client()
    b = get_user_model().objects.create_user(
        email="alerts-b2@example.com", password="pw-123456"
    )
    b_client.force_login(b)

    _post(b_client, _body())

    body = USER.get(f"{ALERTS_URL}?symbol=BTCUSDT&interval=1h").json()
    assert body["alerts"] == []


def test_alerts_post_missing_symbol_key_is_400():
    body = _body()
    del body["symbol"]
    response = _post(USER, body)
    assert response.status_code == 400
    assert AlertRule.objects.count() == 0


def test_alerts_post_missing_interval_key_is_400():
    body = _body()
    del body["interval"]
    response = _post(USER, body)
    assert response.status_code == 400
    assert AlertRule.objects.count() == 0
