"""C1-C4 contract: ``AlertRule`` CRUD (issue #77, Fase D2, Slice 3).

Server-rendered, login-gated create / edit / toggle / delete. Every read and
write routes through ``AlertRule.for_user(request.user)`` (R14): a pk that is not
the caller's -> 404 with no existence leak, and ``owner`` is set explicitly on
create. The ``condition`` is validated by the engine's own ``parse_condition``
(single source) and only the normalized dict is persisted. Anonymous -> 302.
"""

from __future__ import annotations

import json
import re

import pytest
from trading.models import AlertRule

RULES_URL = "/rules/"
CREATE_URL = "/rules/new/"

GOOD_PRICE = {"type": "price", "op": "above", "level": 100}
GOOD_INDICATOR = {"type": "indicator", "name": "rsi", "op": "above", "level": 70}


def _payload(condition=GOOD_PRICE, **overrides):
    data = {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "condition": json.dumps(condition),
        "telegram_chat_id": "",
        "is_active": "on",
    }
    data.update(overrides)
    return data


def _rule(user, **overrides):
    kwargs = {
        "user": user,
        "symbol": "BTCUSDT",
        "interval": "1h",
        "condition": GOOD_PRICE,
    }
    kwargs.update(overrides)
    return AlertRule.objects.create(**kwargs)


@pytest.fixture
def login_a(client, user_a):
    client.force_login(user_a)
    return client


@pytest.fixture
def login_b(client, user_b):
    client.force_login(user_b)
    return client


# --- C1: auth + server-rendered ---------------------------------------------


@pytest.mark.parametrize("url", [RULES_URL, CREATE_URL])
def test_anonymous_redirects_to_login(client, url):
    response = client.get(url)
    assert response.status_code == 302
    assert response.url.startswith("/login/")


@pytest.mark.django_db
def test_rules_page_is_csp_safe_html(login_a):
    body = login_a.get(RULES_URL).content.decode()
    assert "<html" in body
    assert re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", body) == []
    assert not re.search(r"\son[a-z]+\s*=", body), "inline handler found"


# --- C2: per-user scoping ----------------------------------------------------


@pytest.mark.django_db
def test_list_shows_only_callers_rules(login_a, user_a, user_b):
    _rule(user_a, symbol="BTCUSDT")
    _rule(user_b, symbol="ETHUSDT")

    body = login_a.get(RULES_URL).content.decode()

    assert "BTCUSDT" in body
    assert "ETHUSDT" not in body


@pytest.mark.django_db
def test_create_sets_the_owner(login_a, user_a):
    response = login_a.post(CREATE_URL, _payload())

    assert response.status_code == 302
    assert response.url == RULES_URL
    rule = AlertRule.for_user(user_a).get()
    assert rule.user == user_a
    assert rule.symbol == "BTCUSDT"
    assert rule.interval == "1h"


@pytest.mark.django_db
def test_edit_and_delete_cross_user_are_404(login_b, user_a):
    rule = _rule(user_a)

    assert login_b.get(f"/rules/{rule.pk}/edit/").status_code == 404
    assert login_b.post(f"/rules/{rule.pk}/edit/", _payload()).status_code == 404
    assert login_b.post(f"/rules/{rule.pk}/toggle/").status_code == 404
    assert login_b.post(f"/rules/{rule.pk}/delete/").status_code == 404

    rule.refresh_from_db()
    assert rule.is_active is True  # untouched by B


# --- C3: condition validated via parse_condition -----------------------------


@pytest.mark.django_db
def test_invalid_condition_is_rejected_and_not_persisted(login_a, user_a):
    response = login_a.post(CREATE_URL, _payload(condition={"type": "nope"}))

    assert response.status_code == 200
    assert AlertRule.for_user(user_a).count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides",
    [{"interval": "1m"}, {"symbol": "NOTASYMBOL"}],
)
def test_out_of_range_symbol_or_interval_rejected(login_a, user_a, overrides):
    response = login_a.post(CREATE_URL, _payload(**overrides))

    assert response.status_code == 200
    assert AlertRule.for_user(user_a).count() == 0


@pytest.mark.django_db
def test_valid_condition_is_normalized_and_persisted(login_a, user_a):
    from src.alert_rules import parse_condition

    login_a.post(CREATE_URL, _payload(condition=GOOD_INDICATOR))

    rule = AlertRule.for_user(user_a).get()
    expected = parse_condition(GOOD_INDICATOR)
    assert rule.condition == expected
    assert rule.condition["params"] == {"rsi_len": 14}  # normalized defaults


@pytest.mark.django_db
def test_create_get_renders_the_form(login_a):
    response = login_a.get(CREATE_URL)

    assert response.status_code == 200
    body = response.content.decode()
    assert "<form" in body
    assert 'name="symbol"' in body


@pytest.mark.django_db
def test_edit_get_renders_the_form(login_a, user_a):
    rule = _rule(user_a)

    response = login_a.get(f"/rules/{rule.pk}/edit/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "<form" in body
    assert 'name="symbol"' in body


@pytest.mark.django_db
def test_edit_invalid_re_renders_form_without_writing(login_a, user_a):
    rule = _rule(user_a, symbol="BTCUSDT")

    response = login_a.post(
        f"/rules/{rule.pk}/edit/", _payload(condition={"type": "nope"})
    )

    assert response.status_code == 200
    rule.refresh_from_db()
    assert rule.symbol == "BTCUSDT"  # unchanged


# --- C4: edit + toggle -------------------------------------------------------


@pytest.mark.django_db
def test_edit_updates_fields_under_the_owner(login_a, user_a):
    rule = _rule(user_a, symbol="BTCUSDT")

    response = login_a.post(
        f"/rules/{rule.pk}/edit/", _payload(symbol="SOLUSDT", interval="4h")
    )

    assert response.status_code == 302
    rule.refresh_from_db()
    assert rule.symbol == "SOLUSDT"
    assert rule.interval == "4h"
    assert rule.user == user_a


@pytest.mark.django_db
def test_toggle_flips_is_active_without_sending(login_a, user_a, monkeypatch):
    from src import alerts

    rule = _rule(user_a, is_active=True)
    sent = []
    monkeypatch.setattr(alerts, "send_telegram", lambda *a, **k: sent.append(a))

    login_a.post(f"/rules/{rule.pk}/toggle/")
    rule.refresh_from_db()
    assert rule.is_active is False

    login_a.post(f"/rules/{rule.pk}/toggle/")
    rule.refresh_from_db()
    assert rule.is_active is True

    assert sent == []  # the config UI never sends


@pytest.mark.django_db
def test_delete_removes_the_rule(login_a, user_a):
    rule = _rule(user_a)

    response = login_a.post(f"/rules/{rule.pk}/delete/")

    assert response.status_code == 302
    assert AlertRule.for_user(user_a).count() == 0
