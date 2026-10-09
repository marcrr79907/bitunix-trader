"""R3/R4 contract: kline payload seam + auth-gated JSON endpoint.

Two layers:

- Payload: a stub client into ``quotes.get_kline_payload`` (no monkeypatching)
  proves sort/dedupe/gap-omission and indicator alignment against the real
  ``src/indicators.py`` functions.
- Endpoint: contract tests over ``/market/api/kline`` — view errors are
  exercised via a monkeypatched ``market.views.BitunixClient``; anonymous
  redirect and the 200/400/502 matrix.
"""

from __future__ import annotations

import pytest
import requests
from django.test import Client

# --- payload layer: pure-ish seam with a stub client ------------------------


class StubClient:
    """Read-only double whose ``kline()`` returns MAPPED candles.

    Mirrors ``BitunixClient.kline()`` output: int unix-seconds ``time``,
    float prices — the mapping seam lives in the client, not here.
    """

    def __init__(self, rows):
        self._rows = rows

    def kline(self, symbol, interval="1m", limit=100):
        return self._rows


def _row(t, o, h, lo, c):
    return {
        "time": int(t),
        "open": float(o),
        "high": float(h),
        "low": float(lo),
        "close": float(c),
    }


def test_payload_dedupes_and_sorts_ascending_last_wins():
    from market.quotes import get_kline_payload

    rows = [
        _row(1700000060, "1", "1", "1", "2"),
        _row(1700000000, "10", "10", "10", "10"),
        _row(1700000000, "50", "50", "50", "50"),  # duplicate time: last wins
    ]

    payload = get_kline_payload(StubClient(rows), "BTCUSDT", "1m", 100)

    times = [c["time"] for c in payload["candles"]]
    assert times == [1700000000, 1700000060]  # ascending, unique
    assert payload["candles"][0]["close"] == 50.0  # LAST duplicate wins


def test_payload_overlays_are_time_value_pairs_without_nulls():
    from market.quotes import get_kline_payload

    # 25 candles → sma20 has N-w+1 = 6 points; rsi14 needs 15 deltas.
    rows = [_row(t * 60, str(t), str(t + 1), str(t - 1), str(t)) for t in range(25)]

    payload = get_kline_payload(StubClient(rows), "BTCUSDT", "1m", 25)

    sma20 = payload["overlays"]["sma20"]
    assert len(sma20) == 25 - 20 + 1  # N−w+1 points
    assert all(set(p) == {"time", "value"} and p["value"] is not None for p in sma20)
    # Aligned with the LAST sma20 input positions.
    assert sma20[0]["time"] == 19 * 60
    assert sma20[-1]["time"] == 24 * 60

    ema20 = payload["overlays"]["ema20"]
    assert len(ema20) == 25 - 20 + 1

    rsi14 = payload["overlays"]["rsi14"]
    # Rising series → avg_loss == 0 → RSI undefined → points omitted entirely.
    assert rsi14 == []
    assert all("null" not in str(p) for p in sma20 + ema20 + rsi14)


def test_payload_rsi_bounded_or_omitted():
    from market.quotes import get_kline_payload

    # Mixed series so RSI computes real values (bounded [0, 100]).
    closes = [10, 11, 10.5, 12, 11.5, 13, 12, 14, 13, 15, 14, 16, 15, 17, 16, 18]
    rows = [_row(t * 60, str(c), str(c), str(c), str(c)) for t, c in enumerate(closes)]

    payload = get_kline_payload(StubClient(rows), "BTCUSDT", "1m", len(rows))

    rsi14 = payload["overlays"]["rsi14"]
    assert len(rsi14) > 0  # real values exist for this series
    assert all(0 <= p["value"] <= 100 for p in rsi14)


def test_payload_empty_upstream_is_200_empty_arrays():
    from market.quotes import get_kline_payload

    payload = get_kline_payload(StubClient([]), "BTCUSDT", "1m", 100)

    assert payload == {
        "candles": [],
        "overlays": {"sma20": [], "ema20": [], "rsi14": []},
    }


# --- endpoint layer: HTTP contract over the JSON view -----------------------

ANON = Client()
USER = Client()


@pytest.fixture(autouse=True)
def _auth_user(db):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user(
        email="market@example.com", password="pw-123456"
    )
    USER.force_login(user)


def _upstream_rows(n=30):
    return [_row(t * 60, str(t), str(t + 1), str(t - 1), str(t)) for t in range(n)]


def test_endpoint_anonymous_redirects_to_login():
    response = ANON.get("/market/api/kline?symbol=BTCUSDT&interval=1m")
    assert response.status_code == 302
    assert response.url.startswith("/login/")


def test_endpoint_200_exact_shape(monkeypatch):
    from market import views

    monkeypatch.setattr(views, "BitunixClient", lambda: StubClient(_upstream_rows(30)))

    response = USER.get("/market/api/kline?symbol=BTCUSDT&interval=1m")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"candles", "overlays"}
    assert set(body["overlays"]) == {"sma20", "ema20", "rsi14"}
    candle = body["candles"][0]
    assert set(candle) == {"time", "open", "high", "low", "close"}
    assert isinstance(candle["time"], int)
    times = [c["time"] for c in body["candles"]]
    assert times == sorted(times) and len(set(times)) == len(times)


def test_endpoint_invalid_interval_is_400():
    response = USER.get("/market/api/kline?symbol=BTCUSDT&interval=2s")
    assert response.status_code == 400
    assert "error" in response.json()


def test_endpoint_missing_symbol_is_400():
    response = USER.get("/market/api/kline?interval=1m")
    assert response.status_code == 400
    assert "error" in response.json()


def test_endpoint_limit_outside_range_is_400():
    url = "/market/api/kline?symbol=BTCUSDT&interval=1m&limit={}"
    assert USER.get(url.format(0)).status_code == 400
    assert USER.get(url.format(201)).status_code == 400
    assert USER.get(url.format("abc")).status_code == 400


def test_endpoint_upstream_api_reject_is_400(monkeypatch):
    from market import views

    from src.client import BitunixError

    def reject():
        raise BitunixError(70014, "symbol not exist")

    monkeypatch.setattr(views, "BitunixClient", lambda: (_ for _ in ()).throw(reject()))

    response = USER.get("/market/api/kline?symbol=NOSUCHUSDT&interval=1m")
    assert response.status_code == 400
    assert "error" in response.json()


def test_endpoint_network_failure_is_502_upstream(monkeypatch):
    from market import views

    def refused():
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(
        views, "BitunixClient", lambda: (_ for _ in ()).throw(refused())
    )

    response = USER.get("/market/api/kline?symbol=BTCUSDT&interval=1m")
    assert response.status_code == 502
    assert response.json() == {"error": "upstream"}


def test_endpoint_empty_upstream_is_200_empty(monkeypatch):
    from market import views

    monkeypatch.setattr(views, "BitunixClient", lambda: StubClient([]))

    response = USER.get("/market/api/kline?symbol=BTCUSDT&interval=1m")

    assert response.status_code == 200
    assert response.json() == {
        "candles": [],
        "overlays": {"sma20": [], "ema20": [], "rsi14": []},
    }
