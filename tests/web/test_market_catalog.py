"""symbol-catalog contract: universe fetch, TTL cache, and the read-only API.

R1/R2/R3/R4 of ``openspec/changes/f11-symbol-universe/specs/symbol-catalog``.
No sockets: every test injects a stub client and an explicit ``now``, so the
cache boundaries are exercised deterministically (mirrors the stub pattern in
``tests/web/test_ingest.py:60``).
"""

from __future__ import annotations

import market.catalog as catalog
import pytest
from django.contrib.auth import get_user_model

SYMBOLS_URL = "/market/api/symbols"


class StubClient:
    """Minimal public client: records calls, returns canned tickers or raises."""

    def __init__(self, symbols=(), error=None):
        self._symbols = list(symbols)
        self._error = error
        self.calls = []

    def tickers(self, symbols=None):
        self.calls.append(symbols)
        if self._error is not None:
            raise self._error
        return [{"symbol": s, "lastPrice": "1.0"} for s in self._symbols]


@pytest.fixture(autouse=True)
def _reset_cache():
    catalog.reset_cache()
    yield
    catalog.reset_cache()


@pytest.fixture
def logged_in(db):
    from django.test import Client

    user = get_user_model().objects.create_user(
        email="catalog@example.com", password="pw-123456"
    )
    client = Client()
    client.force_login(user)
    return client


# --- R1: fetch and projection -------------------------------------------------


def test_list_symbols_projects_sorts_and_dedups():
    stub = StubClient(["ETHUSDT", "BTCUSDT", "BTCUSDT"])

    assert catalog.list_symbols(client=stub, now=0) == ["BTCUSDT", "ETHUSDT"]
    # No ``symbols`` argument: the no-arg call is what returns the universe.
    assert stub.calls == [None]


def test_list_symbols_returns_only_strings():
    stub = StubClient(["ETHUSDT"])

    result = catalog.list_symbols(client=stub, now=0)

    assert all(isinstance(s, str) for s in result)


def test_catalog_module_imports_no_django_model():
    """R1 framework boundary: parsed imports never reach Django or the views."""
    import ast

    source = open(catalog.__file__, encoding="utf-8").read()
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert not any(name.startswith("django") for name in imported)
    assert "trading.models" not in imported
    assert "market.views" not in imported


# --- R2: TTL cache ------------------------------------------------------------


def test_warm_cache_does_not_call_upstream():
    stub = StubClient(["BTCUSDT"])
    catalog.list_symbols(client=stub, now=0)

    assert catalog.list_symbols(client=stub, now=59) == ["BTCUSDT"]
    assert len(stub.calls) == 1


def test_expired_entry_refetches():
    stub = StubClient(["BTCUSDT"])
    catalog.list_symbols(client=stub, now=0)
    stub._symbols = ["BTCUSDT", "SOLUSDT"]

    assert catalog.list_symbols(client=stub, now=61) == ["BTCUSDT", "SOLUSDT"]
    assert len(stub.calls) == 2


def test_fetch_failure_propagates_and_keeps_the_cached_value():
    class Boom(Exception):
        pass

    warm = StubClient(["BTCUSDT"])
    catalog.list_symbols(client=warm, now=0)
    failing = StubClient(error=Boom("upstream down"))

    with pytest.raises(Boom):
        catalog.list_symbols(client=failing, now=61)

    # A failure must not clear or replace the cached list.
    assert catalog.list_symbols(client=warm, now=62) == ["BTCUSDT"]


# --- R4: warm membership check ------------------------------------------------


def test_symbol_exists_is_offline_when_warm():
    # Warm with the REAL clock: ``symbol_exists`` takes no ``now`` (spec R4).
    catalog.list_symbols(client=StubClient(["BTCUSDT"]))

    class Raising:
        def tickers(self, symbols=None):
            raise AssertionError("upstream must not be called on a warm cache")

    assert catalog.symbol_exists("BTCUSDT", client=Raising()) is True


def test_symbol_exists_false_for_unknown():
    catalog.list_symbols(client=StubClient(["BTCUSDT"]))

    assert catalog.symbol_exists("DOGEUSDT") is False


# --- R3: endpoint -------------------------------------------------------------


def test_symbols_endpoint_returns_the_universe(logged_in):
    catalog.list_symbols(client=StubClient(["BTCUSDT", "ETHUSDT"]))

    response = logged_in.get(SYMBOLS_URL)

    assert response.status_code == 200
    assert response.json() == {"symbols": ["BTCUSDT", "ETHUSDT"]}


def test_symbols_endpoint_anonymous_redirects(client, db):
    response = client.get(SYMBOLS_URL)

    assert response.status_code == 302
    assert response.url.startswith("/login/")


def test_symbols_endpoint_rejects_post(logged_in):
    response = logged_in.post(SYMBOLS_URL)

    assert response.status_code == 405


def test_symbols_endpoint_maps_upstream_request_error_to_502(logged_in, monkeypatch):
    import requests

    def boom(client=None, *, now=None):
        raise requests.RequestException("network down")

    monkeypatch.setattr(catalog, "list_symbols", boom)

    response = logged_in.get(SYMBOLS_URL)

    assert response.status_code == 502
    assert response.json() == {"error": "upstream"}
