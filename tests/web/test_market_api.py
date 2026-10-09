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
    float prices — the mapping seam lives in the client, not here. Records
    every call so tests can assert the DB-first short-circuit and the
    gap-fill ``end_time``; an optional ``error`` makes it raise instead.
    """

    def __init__(self, rows, error=None):
        self._rows = rows
        self._error = error
        self.calls: list[dict] = []

    def kline(self, symbol, interval="1m", limit=100, start_time=None, end_time=None):
        self.calls.append(
            {
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
                "start_time": start_time,
                "end_time": end_time,
            }
        )
        if self._error is not None:
            raise self._error
        return self._rows


def _row(t, o, h, lo, c):
    return {
        "time": int(t),
        "open": float(o),
        "high": float(h),
        "low": float(lo),
        "close": float(c),
    }


def _row_with_quote_vol(t, o, h, lo, c, qv):
    """Upstream now carries quoteVol; the payload seam must strip it."""
    return {**_row(t, o, h, lo, c), "quote_vol": float(qv)}


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


def test_payload_strips_quote_vol_to_exactly_five_keys():
    from market.quotes import get_kline_payload

    rows = [
        _row_with_quote_vol(1700000000, "10", "10", "10", "10", "123456"),
        _row_with_quote_vol(1700000060, "1", "1", "1", "2", "999"),
    ]

    payload = get_kline_payload(StubClient(rows), "BTCUSDT", "1m", 100)

    assert payload["candles"] == [
        {"time": 1700000000, "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0},
        {"time": 1700000060, "open": 1.0, "high": 1.0, "low": 1.0, "close": 2.0},
    ]
    assert all("quote_vol" not in c for c in payload["candles"])


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
    # Upstream carries quoteVol; the endpoint must strip it to five keys.
    return [
        _row_with_quote_vol(t * 60, str(t), str(t + 1), str(t - 1), str(t), str(t))
        for t in range(n)
    ]


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


# --- WU1: DB-first pagination, warm-up, degradation (R3/R4) -----------------

# A persisted interval (``CANDLE_INTERVALS``) routes reads through the DB;
# ``1m`` stays unpersisted and must keep hitting upstream directly.
PERSISTED = "1h"


def _seed_series(n, interval=PERSISTED, step=1000, symbol="BTCUSDT"):
    """Seed ``n`` ascending candles starting at ``step`` seconds."""
    from trading.models import Candle

    times = [step * (i + 1) for i in range(n)]
    Candle.objects.bulk_create(
        [
            Candle(
                symbol=symbol,
                interval=interval,
                time=t,
                open=float(t),
                high=float(t),
                low=float(t),
                close=float(t),
                quote_vol=None,
            )
            for t in times
        ]
    )
    return times


# --- 1.1 pagination ---------------------------------------------------------


def test_payload_before_returns_newest_limit_older_than_cursor():
    from market.quotes import get_kline_payload

    times = _seed_series(25)
    client = StubClient([])

    payload = get_kline_payload(client, "BTCUSDT", PERSISTED, 3, before=25000)

    page = [c["time"] for c in payload["candles"]]
    assert page == times[-4:-1]  # 22000/23000/24000, strictly < 25000
    assert all(t < 25000 for t in page)
    assert client.calls == []  # full page: DB suffices


def test_payload_before_omitted_returns_latest_page():
    from market.quotes import get_kline_payload

    times = _seed_series(25)
    client = StubClient([])

    payload = get_kline_payload(client, "BTCUSDT", PERSISTED, 3)

    assert [c["time"] for c in payload["candles"]] == times[-3:]
    assert client.calls == []


# --- 1.2 DB-first short-circuit --------------------------------------------


def test_payload_full_db_page_never_calls_bitunix():
    from market.quotes import get_kline_payload

    _seed_series(25)
    client = StubClient([_row(1, "1", "1", "1", "1")])

    payload = get_kline_payload(client, "BTCUSDT", PERSISTED, 5)

    assert client.calls == []  # DB held the full limit+WARMUP window
    assert len(payload["candles"]) == 5


# --- 1.3 gap-fill + merge ---------------------------------------------------


def test_payload_short_db_gapfills_with_end_time_and_db_wins_dedupe():
    from market.quotes import get_kline_payload
    from trading.models import Candle

    # One durable row at t=30000 (close 999) that upstream will also return.
    Candle.objects.create(
        symbol="BTCUSDT",
        interval=PERSISTED,
        time=30000,
        open=999.0,
        high=999.0,
        low=999.0,
        close=999.0,
        quote_vol=None,
    )
    upstream = [
        _row(30000, "1", "1", "1", "111"),  # duplicate: DB must win
        _row(31000, "1", "1", "1", "1"),
        _row(32000, "1", "1", "1", "1"),
    ]
    client = StubClient(upstream)

    payload = get_kline_payload(client, "BTCUSDT", PERSISTED, 5, before=1700000000)

    assert client.calls == [
        {
            "symbol": "BTCUSDT",
            "interval": PERSISTED,
            "limit": 25,  # limit + WARMUP
            "start_time": None,
            "end_time": 1700000000 * 1000,
        }
    ]
    by_time = {c["time"]: c for c in payload["candles"]}
    assert by_time[30000]["close"] == 999.0  # durable record wins
    times = [c["time"] for c in payload["candles"]]
    assert times == sorted(times) and len(set(times)) == len(times)


# --- 1.4 warm-up overlay slice ---------------------------------------------


def test_payload_warmup_makes_first_page_candle_have_sma20():
    from market.quotes import get_kline_payload

    times = _seed_series(25)  # 25 rows == limit + WARMUP
    payload = get_kline_payload(StubClient([]), "BTCUSDT", PERSISTED, 5)

    sma20 = payload["overlays"]["sma20"]
    ema20 = payload["overlays"]["ema20"]
    assert sma20[0]["time"] == times[20]  # 20 prior candles → defined
    assert sma20[0]["value"] is not None
    assert ema20[0]["value"] is not None
    assert all(p["value"] is not None for p in sma20 + ema20)


def test_payload_series_floor_omits_leading_warmup_no_nulls():
    from market.quotes import get_kline_payload

    times = _seed_series(22)  # only 22 rows: window starts short of warm-up
    payload = get_kline_payload(StubClient([]), "BTCUSDT", PERSISTED, 20)

    sma20 = payload["overlays"]["sma20"]
    # First definable index is 19 (needs 20 candles); page starts at index 2.
    assert sma20[0]["time"] == times[19]
    assert all(p["value"] is not None for p in sma20)
    page_times = {c["time"] for c in payload["candles"]}
    assert all(p["time"] in page_times for p in sma20)


# --- 1.5 degradation matrix -------------------------------------------------


def test_payload_db_rows_survive_upstream_failure():
    import requests
    from market.quotes import get_kline_payload

    _seed_series(3)
    client = StubClient([], error=requests.ConnectionError("boom"))

    payload = get_kline_payload(client, "BTCUSDT", PERSISTED, 5)

    assert len(payload["candles"]) == 3  # degraded: serve what the DB has


def test_payload_empty_db_reraises_upstream_failure():
    import requests
    from market.quotes import get_kline_payload

    client = StubClient([], error=requests.ConnectionError("boom"))

    with pytest.raises(requests.ConnectionError):
        get_kline_payload(client, "BTCUSDT", PERSISTED, 5)


def test_endpoint_invalid_before_is_400():
    for raw in ("abc", "0", "-1"):
        url = f"/market/api/kline?symbol=BTCUSDT&interval=1m&before={raw}"
        response = USER.get(url)
        assert response.status_code == 400
        assert "error" in response.json()


def test_endpoint_degraded_db_rows_with_upstream_failure_is_200(monkeypatch):
    import requests
    from market import views

    _seed_series(3)
    client = StubClient([], error=requests.ConnectionError("connection refused"))
    monkeypatch.setattr(views, "BitunixClient", lambda: client)

    response = USER.get(f"/market/api/kline?symbol=BTCUSDT&interval={PERSISTED}")

    assert response.status_code == 200
    assert len(response.json()["candles"]) == 3


def test_endpoint_empty_db_with_upstream_failure_is_502(monkeypatch):
    import requests
    from market import views

    client = StubClient([], error=requests.ConnectionError("connection refused"))
    monkeypatch.setattr(views, "BitunixClient", lambda: client)

    response = USER.get(f"/market/api/kline?symbol=BTCUSDT&interval={PERSISTED}")

    assert response.status_code == 502
    assert response.json() == {"error": "upstream"}


def test_endpoint_empty_db_with_upstream_ok_is_200(monkeypatch):
    from market import views

    monkeypatch.setattr(views, "BitunixClient", lambda: StubClient(_upstream_rows(30)))

    response = USER.get(f"/market/api/kline?symbol=BTCUSDT&interval={PERSISTED}")

    assert response.status_code == 200
    assert len(response.json()["candles"]) > 0


def test_endpoint_empty_cursor_is_200_empty(monkeypatch):
    from market import views

    monkeypatch.setattr(views, "BitunixClient", lambda: StubClient([]))

    response = USER.get(
        f"/market/api/kline?symbol=BTCUSDT&interval={PERSISTED}&before=1700000000"
    )

    assert response.status_code == 200
    assert response.json() == {
        "candles": [],
        "overlays": {"sma20": [], "ema20": [], "rsi14": []},
    }
