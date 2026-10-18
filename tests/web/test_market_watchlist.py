"""market-watchlist contract: CRUD transport, virtual default, cap (F11 A-S2).

R14.8/R14.9/R14.10 of
``openspec/changes/f11-symbol-universe/specs/market-watchlist``. Every access is
``for_user``-scoped; an empty list falls back VIRTUALLY to ``config.SYMBOLS`` and
never writes. The catalog is stubbed so no test touches the network.
"""

from __future__ import annotations

import json

import market.catalog as catalog
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from trading.models import Watchlist

from src.config import MAX_WATCHLIST_SYMBOLS, SYMBOLS

WATCHLIST_URL = "/market/api/watchlist"


class StubClient:
    def __init__(self, symbols):
        self._symbols = list(symbols)

    def tickers(self, symbols=None):
        return [{"symbol": s} for s in self._symbols]


@pytest.fixture(autouse=True)
def _warm_catalog():
    catalog.reset_cache()
    catalog.list_symbols(client=StubClient(["BTCUSDT", "ETHUSDT", "SOLUSDT"]))
    yield
    catalog.reset_cache()


@pytest.fixture
def user_a(db):
    return get_user_model().objects.create_user(
        email="wl-a@example.com", password="pw-123456"
    )


@pytest.fixture
def user_b(db):
    return get_user_model().objects.create_user(
        email="wl-b@example.com", password="pw-123456"
    )


@pytest.fixture
def client_a(user_a):
    client = Client()
    client.force_login(user_a)
    return client


@pytest.fixture
def client_b(user_b):
    client = Client()
    client.force_login(user_b)
    return client


def _post(client, payload):
    return client.post(
        WATCHLIST_URL,
        data=json.dumps(payload),
        content_type="application/json",
    )


# --- R14.9: virtual default ---------------------------------------------------


def test_get_empty_returns_config_symbols_without_seeding(client_a, user_a):
    response = client_a.get(WATCHLIST_URL)

    assert response.status_code == 200
    assert response.json() == {"symbols": list(SYMBOLS), "default": True}
    assert Watchlist.objects.count() == 0


def test_get_populated_is_sorted_and_explicit(client_a, user_a):
    Watchlist.objects.create(user=user_a, symbol="SOLUSDT")
    Watchlist.objects.create(user=user_a, symbol="BTCUSDT")

    body = client_a.get(WATCHLIST_URL).json()

    assert body == {"symbols": ["BTCUSDT", "SOLUSDT"], "default": False}


def test_default_follows_the_environment(client_a, monkeypatch):
    client_a.get(WATCHLIST_URL)
    monkeypatch.setattr("market.watchlist.SYMBOLS", ["NEWUSDT"])

    assert client_a.get(WATCHLIST_URL).json()["symbols"] == ["NEWUSDT"]


# --- R14.8: isolation and owner ----------------------------------------------


def test_isolation_b_never_sees_or_deletes_a_rows(client_a, client_b, user_a, user_b):
    Watchlist.objects.create(user=user_a, symbol="BTCUSDT")
    Watchlist.objects.create(user=user_b, symbol="ETHUSDT")

    assert client_b.get(WATCHLIST_URL).json()["symbols"] == ["ETHUSDT"]

    response = client_b.delete(f"{WATCHLIST_URL}/BTCUSDT")

    assert response.status_code == 204
    assert Watchlist.for_user(user_a).filter(symbol="BTCUSDT").exists()


def test_owner_is_never_taken_from_the_body(client_a, user_a, user_b):
    client_a.post(
        WATCHLIST_URL,
        data=json.dumps({"symbol": "BTCUSDT", "user": user_b.pk}),
        content_type="application/json",
    )

    row = Watchlist.objects.get(symbol="BTCUSDT")
    assert row.user_id == user_a.pk


def test_anonymous_is_redirected(client, db):
    response = client.get(WATCHLIST_URL)

    assert response.status_code == 302
    assert response.url.startswith("/login/")


def test_post_requires_csrf(user_a):
    enforcing = Client(enforce_csrf_checks=True)
    enforcing.force_login(user_a)
    response = enforcing.post(
        WATCHLIST_URL,
        data=json.dumps({"symbol": "BTCUSDT"}),
        content_type="application/json",
    )

    assert response.status_code == 403


# --- R14.10: validation, idempotency, cap ------------------------------------


def test_post_adds_a_catalog_symbol(client_a, user_a):
    response = _post(client_a, {"symbol": "ETHUSDT"})

    assert response.status_code == 201
    assert Watchlist.for_user(user_a).filter(symbol="ETHUSDT").exists()


def test_post_unknown_when_warm_is_400(client_a):
    response = _post(client_a, {"symbol": "FAKEUSDT"})

    assert response.status_code == 400
    assert Watchlist.objects.count() == 0


@pytest.mark.parametrize("symbol", ["btc/usdt", "A", "", "btc usdt", "x" * 25])
def test_post_malformed_symbol_is_400(client_a, symbol):
    response = _post(client_a, {"symbol": symbol})

    assert response.status_code == 400
    assert Watchlist.objects.count() == 0


def test_post_duplicate_is_idempotent(client_a, user_a):
    _post(client_a, {"symbol": "BTCUSDT"})
    response = _post(client_a, {"symbol": "BTCUSDT"})

    assert response.status_code == 201
    assert Watchlist.for_user(user_a).filter(symbol="BTCUSDT").count() == 1


def test_post_rejects_when_at_cap(client_a, user_a):
    Watchlist.objects.bulk_create(
        [
            Watchlist(user=user_a, symbol=f"SYM{i:02d}USDT")
            for i in range(MAX_WATCHLIST_SYMBOLS)
        ]
    )

    response = _post(client_a, {"symbol": "BTCUSDT"})

    assert response.status_code == 400
    assert Watchlist.for_user(user_a).count() == MAX_WATCHLIST_SYMBOLS


def test_post_rejects_invalid_json(client_a):
    response = client_a.post(
        WATCHLIST_URL,
        data="{not json",
        content_type="application/json",
    )

    assert response.status_code == 400


def test_delete_is_idempotent(client_a, user_a):
    _post(client_a, {"symbol": "BTCUSDT"})

    first = client_a.delete(f"{WATCHLIST_URL}/BTCUSDT")
    second = client_a.delete(f"{WATCHLIST_URL}/BTCUSDT")

    assert (first.status_code, second.status_code) == (204, 204)
    assert not Watchlist.for_user(user_a).exists()


def test_post_fails_open_when_the_catalog_is_cold(client_a, user_a, monkeypatch):
    catalog.reset_cache()

    import requests

    def boom(client=None, *, now=None):
        raise requests.RequestException("upstream down")

    monkeypatch.setattr(catalog, "list_symbols", boom)

    response = _post(client_a, {"symbol": "ARBUSDT"})

    assert response.status_code == 201
    assert Watchlist.for_user(user_a).filter(symbol="ARBUSDT").exists()


def test_post_rejects_a_non_object_body(client_a):
    response = client_a.post(
        WATCHLIST_URL, data="[1,2]", content_type="application/json"
    )

    assert response.status_code == 400


def test_post_rejects_a_non_string_symbol(client_a):
    response = _post(client_a, {"symbol": 123})

    assert response.status_code == 400
    assert Watchlist.objects.count() == 0
