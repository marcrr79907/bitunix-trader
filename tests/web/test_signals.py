"""S1-S5 contract: the server-rendered ``/signals/`` screen (issue #77, Fase D2).

``/signals/`` is a GET-only, login-gated, server-rendered page. It pairs each of
the caller's own ``AlertRule`` ``(symbol, interval)`` pairs with the frozen
``market.quotes.get_smc_payload`` setups (single source — no SMC recompute in the
view) and renders the rule state (fired/armed/inactive/none). Ownership is
per-user (R14); another user's pairs are never shown. Read-only: the view sends
nothing and writes nothing.
"""

from __future__ import annotations

import re

import pytest
from django.contrib.auth import get_user_model
from trading.models import AlertRule

User = get_user_model()

CONDITION = {"type": "price", "op": "above", "level": 100}


def _rule(user, symbol="BTCUSDT", interval="1h", **overrides):
    kwargs = {
        "user": user,
        "symbol": symbol,
        "interval": interval,
        "condition": CONDITION,
    }
    kwargs.update(overrides)
    return AlertRule.objects.create(**kwargs)


def _setup(direction="long", entry=100.0, stop=95.0, tp=110.0, rr=2.0, score=80.0):
    return {
        "direction": direction,
        "time": 1_700_000_000,
        "entry": entry,
        "stop": stop,
        "take_profit": tp,
        "rr": rr,
        "score": score,
    }


class PayloadRecorder:
    """Stubs ``market.views.get_smc_payload``; records calls, returns setups."""

    def __init__(self, setups_by_pair):
        self._setups = setups_by_pair
        self.calls = []

    def __call__(self, client, symbol, interval, limit):
        self.calls.append((symbol, interval, limit, client))
        return {
            "symbol": symbol,
            "interval": interval,
            "setups": self._setups.get((symbol, interval), []),
        }


@pytest.fixture
def login_a(client, user_a):
    client.force_login(user_a)
    return client


# --- S1: route and auth ------------------------------------------------------


def test_signals_anonymous_redirects_to_login(client):
    response = client.get("/signals/")
    assert response.status_code == 302
    assert response.url.startswith("/login/")


@pytest.mark.django_db
def test_signals_authenticated_renders_html(login_a, monkeypatch):
    from market import views

    monkeypatch.setattr(views, "get_smc_payload", PayloadRecorder({}))

    response = login_a.get("/signals/")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")
    body = response.content.decode()
    assert "<html" in body
    # Extends the base shell (brand + primary nav live there).
    assert "bitunix-trader" in body
    assert 'aria-label="Primary"' in body


# --- S2: per-user pair scoping ----------------------------------------------


@pytest.mark.django_db
def test_only_callers_pairs_are_shown(login_a, user_a, user_b, monkeypatch):
    from market import views

    _rule(user_a, "BTCUSDT", "1h")
    _rule(user_b, "ETHUSDT", "4h")
    recorder = PayloadRecorder({})
    monkeypatch.setattr(views, "get_smc_payload", recorder)

    response = login_a.get("/signals/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "BTCUSDT" in body
    assert "ETHUSDT" not in body
    # ONE call per pair, fixed limit 200 (S5/C1).
    assert [(c[0], c[1], c[2]) for c in recorder.calls] == [("BTCUSDT", "1h", 200)]


@pytest.mark.django_db
def test_no_rules_renders_empty_page(login_a, monkeypatch):
    from market import views

    recorder = PayloadRecorder({})
    monkeypatch.setattr(views, "get_smc_payload", recorder)

    response = login_a.get("/signals/")

    assert response.status_code == 200
    assert recorder.calls == []  # no pairs -> no upstream work
    assert b"No alert rules" in response.content


# --- S3: single-sourced setups ----------------------------------------------


@pytest.mark.django_db
def test_setups_come_from_get_smc_payload(login_a, user_a, monkeypatch):
    from market import views

    _rule(user_a, "BTCUSDT", "1h")
    setups = [_setup(direction="long", entry=101.5, tp=250.25, rr=3.5)]
    recorder = PayloadRecorder({("BTCUSDT", "1h"): setups})
    monkeypatch.setattr(views, "get_smc_payload", recorder)

    response = login_a.get("/signals/")

    assert response.status_code == 200
    body = response.content.decode()
    # Every rendered field mirrors the frozen payload record (single source).
    assert "long" in body
    assert "101.5" in body
    assert "250.25" in body
    assert "3.5" in body
    # ONE call per pair into the frozen seam.
    assert len(recorder.calls) == 1
    assert recorder.calls[0][0] == "BTCUSDT"
    assert recorder.calls[0][1] == "1h"


@pytest.mark.django_db
def test_empty_setups_renders_without_error(login_a, user_a, monkeypatch):
    from market import views

    _rule(user_a, "BTCUSDT", "1h")
    monkeypatch.setattr(views, "get_smc_payload", PayloadRecorder({}))

    response = login_a.get("/signals/")

    assert response.status_code == 200
    assert b"BTCUSDT" in response.content


@pytest.mark.django_db
def test_upstream_error_degrades_to_empty_not_500(login_a, user_a, monkeypatch):
    from market import views

    from src.client import BitunixError

    _rule(user_a, "BTCUSDT", "1h")

    def explode(client, symbol, interval, limit):
        raise BitunixError(70014, "symbol not exist")

    monkeypatch.setattr(views, "get_smc_payload", explode)

    response = login_a.get("/signals/")

    assert response.status_code == 200
    assert b"BTCUSDT" in response.content


# --- S4: alert-state rendering ----------------------------------------------


@pytest.mark.django_db
def test_state_fired_armed_and_inactive(login_a, user_a, monkeypatch):
    from datetime import UTC, datetime

    from market import views

    _rule(user_a, "BTCUSDT", "1h", last_fired_at=datetime.fromtimestamp(1, tz=UTC))
    _rule(user_a, "ETHUSDT", "4h")
    _rule(user_a, "SOLUSDT", "1d", is_active=False)
    monkeypatch.setattr(views, "get_smc_payload", PayloadRecorder({}))

    response = login_a.get("/signals/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "fired" in body
    assert "armed" in body
    assert "inactive" in body


@pytest.mark.django_db
def test_fired_takes_precedence_over_armed(login_a, user_a, monkeypatch):
    from datetime import UTC, datetime

    from market import views

    _rule(user_a, "BTCUSDT", "1h", last_fired_at=datetime.fromtimestamp(1, tz=UTC))
    _rule(user_a, "BTCUSDT", "1h")  # active, not fired
    monkeypatch.setattr(views, "get_smc_payload", PayloadRecorder({}))

    response = login_a.get("/signals/")

    body = response.content.decode()
    assert "state-fired" in body
    assert "state-armed" not in body


def test_rule_state_none_when_no_rules():
    from market.views import _rule_state

    assert _rule_state([]) == "none"


@pytest.mark.django_db
def test_read_only_no_send_and_no_write(login_a, user_a, monkeypatch):
    from datetime import UTC, datetime

    from market import views

    from src import alerts

    stamped = datetime.fromtimestamp(1, tz=UTC)
    rule = _rule(user_a, "BTCUSDT", "1h", last_fired_at=stamped)
    monkeypatch.setattr(views, "get_smc_payload", PayloadRecorder({}))

    sent = []

    def fake_send(*args, **kwargs):
        sent.append((args, kwargs))
        return True

    monkeypatch.setattr(alerts, "send_telegram", fake_send)

    response = login_a.get("/signals/")

    assert response.status_code == 200
    assert sent == []  # the view never sends
    rule.refresh_from_db()
    assert rule.last_fired_at == stamped  # the view never writes


# --- S5: CSP-safe / server-rendered / no pagination -------------------------


@pytest.mark.django_db
def test_no_inline_script_or_handler(login_a, user_a, monkeypatch):
    from market import views

    _rule(user_a, "BTCUSDT", "1h")
    monkeypatch.setattr(views, "get_smc_payload", PayloadRecorder({}))

    body = login_a.get("/signals/").content.decode()

    assert re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", body) == []
    assert not re.search(r"\son[a-z]+\s*=", body), "inline handler found"


@pytest.mark.django_db
def test_no_pagination_controls(login_a, user_a, monkeypatch):
    from market import views

    for i in range(30):
        _rule(user_a, f"SYM{i}USDT", "1h")
    monkeypatch.setattr(views, "get_smc_payload", PayloadRecorder({}))

    body = login_a.get("/signals/").content.decode()

    assert 'rel="next"' not in body
    assert "page=" not in body
    assert "SYM29USDT" in body  # all pairs on one GET
