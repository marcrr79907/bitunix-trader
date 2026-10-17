"""R3/R4 contract: kline payload seam + auth-gated JSON endpoint.

Two layers:

- Payload: a stub client into ``quotes.get_kline_payload`` (no monkeypatching)
  proves sort/dedupe/gap-omission and indicator alignment against the real
  ``src/indicators.py`` functions.
- Endpoint: contract tests over ``/market/api/kline`` — view errors are
  exercised via a monkeypatched ``market.views.BitunixClient``; anonymous
  redirect and the 200/400/502 matrix.
- Layout: contract tests over ``/market/api/layout`` (R2/R3) — per-user layout
  GET/PUT, default-on-miss, upsert, validation-before-write, CSRF, A≠B.
"""

from __future__ import annotations

import json

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
        "panes": {},
    }


# --- endpoint layer: HTTP contract over the JSON view -----------------------

ANON = Client()
USER = Client()
AUTH_USER = None  # set by the autouse fixture; the user logged into USER


@pytest.fixture(autouse=True)
def _auth_user(db):
    global AUTH_USER
    from django.contrib.auth import get_user_model

    AUTH_USER = get_user_model().objects.create_user(
        email="market@example.com", password="pw-123456"
    )
    USER.force_login(AUTH_USER)


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
    assert set(body) == {"candles", "overlays", "panes"}
    assert set(body["overlays"]) == {"sma20", "ema20", "rsi14"}
    assert body["panes"] == {}
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


def test_endpoint_macd_fast_gte_slow_is_400():
    # Regression: fast>=slow previously raised TypeError -> HTTP 500.
    url = "/market/api/kline?symbol=BTCUSDT&interval=1m&indicators=macd"
    response = USER.get(url + "&macd_fast=30&macd_slow=5")
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
        "panes": {},
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
        "panes": {},
    }


# --- WU2: registry, selection, derived warm-up, volume (R3/R4) --------------

# A long mixed series so every default/selected indicator computes real values.
_MIXED_CLOSES = [
    10,
    11,
    10.5,
    12,
    11.5,
    13,
    12,
    14,
    13,
    15,
    14,
    16,
    15,
    17,
    16,
    18,
    17,
    19,
    18,
    20,
    19,
    21,
    20,
    22,
    21,
    23,
    22,
    24,
    23,
    25,
    24,
    26,
    25,
    27,
    26,
    28,
    27,
    29,
    28,
    30,
]


def _mixed_rows(n=40, with_quote_vol=False):
    rows = []
    for t in range(n):
        c = _MIXED_CLOSES[t % len(_MIXED_CLOSES)]
        if with_quote_vol:
            rows.append(
                _row_with_quote_vol(
                    t * 60, str(c), str(c + 1), str(c - 1), str(c), str(t + 1)
                )
            )
        else:
            rows.append(_row(t * 60, str(c), str(c + 1), str(c - 1), str(c)))
    return rows


def test_payload_default_set_unchanged_and_panes_empty():
    from market.quotes import get_kline_payload

    payload = get_kline_payload(StubClient(_mixed_rows()), "BTCUSDT", "1m", 40)

    assert set(payload) == {"candles", "overlays", "panes"}
    assert set(payload["overlays"]) == {"sma20", "ema20", "rsi14"}
    assert payload["panes"] == {}


def test_payload_selection_returns_requested_panes():
    from market.quotes import get_kline_payload

    payload = get_kline_payload(
        StubClient(_mixed_rows()),
        "BTCUSDT",
        "1m",
        40,
        indicators=[("macd", {}), ("rsi", {})],
    )

    assert set(payload["overlays"]) == set()  # nothing default leaked in
    assert set(payload["panes"]) == {"macd", "rsi"}
    macd = payload["panes"]["macd"]
    assert macd["type"] == "line"
    assert set(macd["series"]) == {"macd", "signal", "histogram"}
    rsi = payload["panes"]["rsi"]
    assert rsi["type"] == "line"
    assert set(rsi["series"]) == {"rsi"}
    assert all(set(p) == {"time", "value"} for p in rsi["series"]["rsi"])


def test_payload_overlays_selection_bollinger_three_lines():
    from market.quotes import get_kline_payload

    payload = get_kline_payload(
        StubClient(_mixed_rows()),
        "BTCUSDT",
        "1m",
        40,
        indicators=[("bollinger", {})],
    )

    assert set(payload["overlays"]) == {
        "bollinger_upper",
        "bollinger_middle",
        "bollinger_lower",
    }
    assert payload["panes"] == {}
    upper = payload["overlays"]["bollinger_upper"]
    lower = payload["overlays"]["bollinger_lower"]
    assert len(upper) == len(lower) > 0
    # Band order per computed point.
    assert all(u["value"] >= lo["value"] for u, lo in zip(upper, lower, strict=False))


def test_payload_derived_warmup_macd_defined_on_first_page_candle():
    from market.quotes import get_kline_payload

    # 40 rows, page = 5. MACD needs 33 warm-up → derived warmup must exceed 20
    # so the first returned candle already has a non-null MACD line.
    payload = get_kline_payload(
        StubClient(_mixed_rows(40)),
        "BTCUSDT",
        "1m",
        5,
        indicators=[("macd", {})],
    )

    page_times = {c["time"] for c in payload["candles"]}
    assert len(page_times) == 5
    macd = payload["panes"]["macd"]["series"]["macd"]
    assert macd, "MACD series must not be empty"
    assert macd[0]["value"] is not None
    assert macd[0]["time"] == payload["candles"][0]["time"]
    assert all(p["time"] in page_times for p in macd)


def test_payload_candles_exactly_five_keys_no_quote_vol_leak():
    from market.quotes import get_kline_payload

    payload = get_kline_payload(
        StubClient(_mixed_rows(with_quote_vol=True)),
        "BTCUSDT",
        "1m",
        40,
        indicators=[("volume", {})],
    )

    assert payload["candles"]
    for c in payload["candles"]:
        assert set(c) == {"time", "open", "high", "low", "close"}
        assert "quote_vol" not in c


def test_payload_volume_pane_uses_quote_vol():
    from market.quotes import get_kline_payload

    rows = _mixed_rows(40, with_quote_vol=True)
    payload = get_kline_payload(
        StubClient(rows), "BTCUSDT", "1m", 40, indicators=[("volume", {})]
    )

    volume = payload["panes"]["volume"]
    assert volume["type"] == "histogram"
    series = volume["series"]["volume"]
    assert series  # non-empty: rows carried quote_vol
    # The page's last candle quote_vol must equal the last volume point.
    assert series[-1]["value"] == rows[-1]["quote_vol"]
    assert series[-1]["time"] == payload["candles"][-1]["time"]


def test_payload_upstream_fetch_clamped_to_200():
    from market.quotes import get_kline_payload

    client = StubClient([])
    # limit 200 + default warm-up 20 = 220 > 200 → upstream asked for 200 max.
    get_kline_payload(client, "BTCUSDT", "1m", 200)

    assert client.calls[0]["limit"] == 200


def test_endpoint_selected_panes_shape(monkeypatch):
    from market import views

    monkeypatch.setattr(views, "BitunixClient", lambda: StubClient(_mixed_rows(40)))

    response = USER.get(
        "/market/api/kline?symbol=BTCUSDT&interval=1m&limit=40&indicators=macd,rsi"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["panes"]["macd"]["type"] == "line"
    assert set(body["panes"]["macd"]["series"]) == {"macd", "signal", "histogram"}
    assert set(body["panes"]["rsi"]["series"]) == {"rsi"}
    assert body["overlays"] == {}


def test_endpoint_unknown_indicator_is_400(monkeypatch):
    from market import views

    monkeypatch.setattr(views, "BitunixClient", lambda: StubClient(_mixed_rows(40)))

    response = USER.get(
        "/market/api/kline?symbol=BTCUSDT&interval=1m&indicators=notreal"
    )

    assert response.status_code == 400
    assert "error" in response.json()


def test_endpoint_bad_indicator_param_is_400(monkeypatch):
    from market import views

    monkeypatch.setattr(views, "BitunixClient", lambda: StubClient(_mixed_rows(40)))

    response = USER.get(
        "/market/api/kline?symbol=BTCUSDT&interval=1m&indicators=rsi&rsi_len=abc"
    )

    assert response.status_code == 400
    assert "error" in response.json()


def test_endpoint_volume_indicator_never_leaks_quote_vol(monkeypatch):
    from market import views

    monkeypatch.setattr(
        views, "BitunixClient", lambda: StubClient(_mixed_rows(40, with_quote_vol=True))
    )

    response = USER.get(
        "/market/api/kline?symbol=BTCUSDT&interval=1m&limit=40&indicators=volume"
    )

    assert response.status_code == 200
    body = response.json()
    assert all(
        set(c) == {"time", "open", "high", "low", "close"} for c in body["candles"]
    )
    assert body["panes"]["volume"]["series"]["volume"]


def test_payload_param_driven_overlays_sma_ema_vwap():
    from market.quotes import get_kline_payload

    payload = get_kline_payload(
        StubClient(_mixed_rows(40, with_quote_vol=True)),
        "BTCUSDT",
        "1m",
        40,
        indicators=[("sma", {"sma_len": 5}), ("ema", {"ema_len": 5}), ("vwap", {})],
    )

    assert set(payload["overlays"]) == {"sma", "ema", "vwap"}
    assert payload["panes"] == {}
    assert all(p["value"] is not None for p in payload["overlays"]["sma"])
    assert all(p["value"] is not None for p in payload["overlays"]["ema"])
    assert payload["overlays"]["vwap"]  # quote_vol present → VWAP defined


def test_payload_stochastic_and_atr_panes():
    from market.quotes import get_kline_payload

    payload = get_kline_payload(
        StubClient(_mixed_rows(40)),
        "BTCUSDT",
        "1m",
        40,
        indicators=[("stochastic", {}), ("atr", {})],
    )

    assert set(payload["panes"]) == {"stochastic", "atr"}
    assert set(payload["panes"]["stochastic"]["series"]) == {"k", "d"}
    assert payload["panes"]["stochastic"]["series"]["k"]
    assert set(payload["panes"]["atr"]["series"]) == {"atr"}
    assert payload["panes"]["atr"]["series"]["atr"]


def test_payload_vwap_with_null_quote_vol_treated_as_zero():
    from market.quotes import get_kline_payload

    # quote_vol all None → cumulative volume stays 0 → VWAP undefined → omitted.
    payload = get_kline_payload(
        StubClient(_mixed_rows(40)), "BTCUSDT", "1m", 40, indicators=[("vwap", {})]
    )

    assert payload["overlays"]["vwap"] == []


def test_endpoint_int_param_below_one_is_400(monkeypatch):
    from market import views

    monkeypatch.setattr(views, "BitunixClient", lambda: StubClient(_mixed_rows(40)))

    response = USER.get(
        "/market/api/kline?symbol=BTCUSDT&interval=1m&indicators=rsi&rsi_len=0"
    )
    assert response.status_code == 400
    assert "error" in response.json()


def test_endpoint_float_param_invalid_is_400(monkeypatch):
    from market import views

    monkeypatch.setattr(views, "BitunixClient", lambda: StubClient(_mixed_rows(40)))

    bad = USER.get(
        "/market/api/kline?symbol=BTCUSDT&interval=1m&indicators=bollinger&bb_std=abc"
    )
    assert bad.status_code == 400
    zero = USER.get(
        "/market/api/kline?symbol=BTCUSDT&interval=1m&indicators=bollinger&bb_std=0"
    )
    assert zero.status_code == 400


def test_endpoint_param_overrides_reach_the_builder(monkeypatch):
    from market import views

    monkeypatch.setattr(views, "BitunixClient", lambda: StubClient(_mixed_rows(40)))

    response = USER.get(
        "/market/api/kline?symbol=BTCUSDT&interval=1m&limit=40&indicators=sma&sma_len=5"
    )

    assert response.status_code == 200
    sma = response.json()["overlays"]["sma"]
    assert sma and all(p["value"] is not None for p in sma)


# --- WU2: chart layout endpoint (R2/R3) -------------------------------------

LAYOUT_URL = "/market/api/layout"
DEFAULT_LAYOUT = [
    {"token": "sma"},
    {"token": "ema"},
    {"token": "rsi"},
]


def _put_layout(client, payload):
    return client.put(
        LAYOUT_URL, data=json.dumps(payload), content_type="application/json"
    )


def test_layout_anonymous_get_redirects_to_login():
    response = ANON.get(f"{LAYOUT_URL}?symbol=BTCUSDT&interval=1m")
    assert response.status_code == 302
    assert response.url.startswith("/login/")


def test_layout_anonymous_put_redirects_to_login():
    response = _put_layout(
        ANON,
        {"symbol": "BTCUSDT", "interval": "1m", "indicators": DEFAULT_LAYOUT},
    )
    assert response.status_code == 302
    assert response.url.startswith("/login/")


def test_layout_get_without_row_returns_default_not_404():
    response = USER.get(f"{LAYOUT_URL}?symbol=BTCUSDT&interval=1m")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "BTCUSDT"
    assert body["interval"] == "1m"
    assert body["indicators"] == DEFAULT_LAYOUT
    assert body["exists"] is False


def test_layout_put_then_get_returns_saved_set():
    indicators = [
        {"token": "sma", "params": {"sma_len": 50}},
        {"token": "macd"},
    ]
    put = _put_layout(
        USER, {"symbol": "BTCUSDT", "interval": "1m", "indicators": indicators}
    )
    assert put.status_code == 200
    assert put.json()["exists"] is True

    body = USER.get(f"{LAYOUT_URL}?symbol=BTCUSDT&interval=1m").json()
    assert body["indicators"] == indicators
    assert body["exists"] is True


def test_layout_put_upserts_one_row_for_the_same_key():
    from trading.models import ChartLayout

    _put_layout(
        USER, {"symbol": "BTCUSDT", "interval": "1m", "indicators": DEFAULT_LAYOUT}
    )
    _put_layout(
        USER,
        {"symbol": "BTCUSDT", "interval": "1m", "indicators": [{"token": "volume"}]},
    )

    rows = list(ChartLayout.for_user(AUTH_USER))
    assert len(rows) == 1
    assert rows[0].indicators == [{"token": "volume"}]


def test_layout_put_invalid_token_is_400_and_writes_nothing():
    from trading.models import ChartLayout

    response = _put_layout(
        USER,
        {"symbol": "BTCUSDT", "interval": "1m", "indicators": [{"token": "notreal"}]},
    )

    assert response.status_code == 400
    assert "error" in response.json()
    assert ChartLayout.objects.count() == 0


def test_layout_put_invalid_param_is_400_and_writes_nothing():
    from trading.models import ChartLayout

    response = _put_layout(
        USER,
        {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "indicators": [{"token": "rsi", "params": {"rsi_len": "abc"}}],
        },
    )

    assert response.status_code == 400
    assert "error" in response.json()
    assert ChartLayout.objects.count() == 0


def test_layout_get_missing_symbol_is_400():
    assert USER.get(f"{LAYOUT_URL}?interval=1m").status_code == 400


def test_layout_get_invalid_interval_is_400():
    assert USER.get(f"{LAYOUT_URL}?symbol=BTCUSDT&interval=2s").status_code == 400


def test_layout_put_missing_symbol_is_400():
    response = _put_layout(USER, {"interval": "1m", "indicators": []})
    assert response.status_code == 400


def test_layout_put_invalid_interval_is_400():
    response = _put_layout(
        USER, {"symbol": "BTCUSDT", "interval": "2s", "indicators": []}
    )
    assert response.status_code == 400


def test_layout_put_requires_csrf():
    # A CSRF-enforcing client (no token) MUST reject the write with 403.
    enforcing = Client(enforce_csrf_checks=True)
    enforcing.force_login(AUTH_USER)
    response = enforcing.put(
        LAYOUT_URL,
        data=json.dumps(
            {"symbol": "BTCUSDT", "interval": "1m", "indicators": DEFAULT_LAYOUT}
        ),
        content_type="application/json",
    )
    assert response.status_code == 403


def test_layout_isolation_b_get_never_sees_a():
    from trading.models import ChartLayout

    ChartLayout.objects.create(
        user=AUTH_USER,
        symbol="BTCUSDT",
        interval="1m",
        indicators=[{"token": "volume"}],
    )

    from django.contrib.auth import get_user_model

    b_client = Client()
    b = get_user_model().objects.create_user(
        email="b@example.com", password="pw-123456"
    )
    b_client.force_login(b)

    body = b_client.get(f"{LAYOUT_URL}?symbol=BTCUSDT&interval=1m").json()
    assert body["indicators"] == DEFAULT_LAYOUT
    assert body["exists"] is False


def test_layout_isolation_b_put_does_not_touch_a_row():
    from trading.models import ChartLayout

    a_row = ChartLayout.objects.create(
        user=AUTH_USER,
        symbol="BTCUSDT",
        interval="1m",
        indicators=[{"token": "volume"}],
    )

    from django.contrib.auth import get_user_model

    b_client = Client()
    b = get_user_model().objects.create_user(
        email="b2@example.com", password="pw-123456"
    )
    b_client.force_login(b)

    _put_layout(
        b_client,
        {"symbol": "BTCUSDT", "interval": "1m", "indicators": [{"token": "rsi"}]},
    )

    a_row.refresh_from_db()
    assert a_row.indicators == [{"token": "volume"}]  # A untouched
    assert ChartLayout.for_user(b).count() == 1  # B owns its own row
    assert ChartLayout.for_user(AUTH_USER).count() == 1


def test_layout_put_invalid_json_is_400():
    response = USER.put(LAYOUT_URL, data="not-json", content_type="application/json")
    assert response.status_code == 400
    assert "error" in response.json()


def test_layout_put_non_object_body_is_400():
    response = USER.put(LAYOUT_URL, data="[1, 2]", content_type="application/json")
    assert response.status_code == 400
    assert "error" in response.json()


# --- parse_layout_indicators: pure validation seam (R2) ---------------------


def test_parse_layout_indicators_preserves_shape_and_validates_params():
    from market.quotes import parse_layout_indicators

    out = parse_layout_indicators(
        [
            {"token": "sma", "params": {"sma_len": 50}},
            {"token": "bollinger", "params": {"bb_len": 20, "bb_std": 2.5}},
            {"token": "macd", "params": {"macd_fast": 12, "macd_slow": 26}},
        ]
    )

    assert out == [
        {"token": "sma", "params": {"sma_len": 50}},
        {"token": "bollinger", "params": {"bb_len": 20, "bb_std": 2.5}},
        {"token": "macd", "params": {"macd_fast": 12, "macd_slow": 26}},
    ]


def test_parse_layout_indicators_drops_duplicate_tokens():
    from market.quotes import parse_layout_indicators

    out = parse_layout_indicators([{"token": "rsi"}, {"token": "rsi"}])
    assert out == [{"token": "rsi"}]


@pytest.mark.parametrize(
    "bad",
    [
        "sma",  # not a list
        [123],  # entry not a dict
        [{"token": "notreal"}],  # unknown token
        [{"token": "sma", "params": "x"}],  # params not a dict
        [{"token": "sma", "params": {"nope": 1}}],  # unknown param key
        [{"token": "sma", "params": {"sma_len": 0}}],  # below range
        [{"token": "sma", "params": {"sma_len": True}}],  # bool is not an int
        [{"token": "bollinger", "params": {"bb_std": 0}}],  # float <= 0
        [{"token": "macd", "params": {"macd_fast": 30, "macd_slow": 5}}],  # fast>=slow
    ],
)
def test_parse_layout_indicators_rejects_bad_input(bad):
    from market.quotes import parse_layout_indicators

    with pytest.raises(ValueError):
        parse_layout_indicators(bad)


# --- parse_layout_indicators: style preservation (F2.7 / R2 delta) -----------


def test_layout_put_then_get_round_trips_style_verbatim():
    # The parser no longer drops ``style``; the frozen shape
    # {color,lineWidth,precision} survives PUT -> GET byte-for-byte.
    indicators = [
        {
            "token": "sma",
            "params": {"sma_len": 50},
            "style": {"color": "#ff0000", "lineWidth": 2, "precision": 4},
        },
        {"token": "macd"},
    ]
    put = _put_layout(
        USER, {"symbol": "BTCUSDT", "interval": "1m", "indicators": indicators}
    )
    assert put.status_code == 200

    body = USER.get(f"{LAYOUT_URL}?symbol=BTCUSDT&interval=1m").json()
    assert body["indicators"] == indicators


def test_parse_layout_indicators_preserves_partial_style_verbatim():
    from market.quotes import parse_layout_indicators

    out = parse_layout_indicators(
        [{"token": "sma", "style": {"lineWidth": 3, "color": "#00ff00"}}]
    )
    # Stored verbatim: no defaults injected, key order preserved.
    assert out == [{"token": "sma", "style": {"lineWidth": 3, "color": "#00ff00"}}]


@pytest.mark.parametrize(
    "bad_style",
    [
        "notadict",
        {"lineWidth": 9},  # above 1..4
        {"lineWidth": 0},  # below 1..4
        {"lineWidth": True},  # bool is not an int
        {"precision": 20},  # above 0..8
        {"precision": -1},  # below 0..8
        {"color": "red"},  # not #rrggbb
        {"color": "#zzz"},  # not #rrggbb
        {"foo": 1},  # unknown key
    ],
)
def test_parse_layout_indicators_rejects_bad_style(bad_style):
    from market.quotes import parse_layout_indicators

    with pytest.raises(ValueError):
        parse_layout_indicators([{"token": "sma", "style": bad_style}])


# --- parse_layout_indicators: visible preservation (F5 S3 / F2.7 delta) ------


def test_parse_layout_indicators_preserves_visible_verbatim():
    from market.quotes import parse_layout_indicators

    out = parse_layout_indicators([{"token": "sma", "visible": False}])
    # Preserved verbatim (no default injected); key order preserved.
    assert out == [{"token": "sma", "visible": False}]

    out_true = parse_layout_indicators([{"token": "ema", "visible": True}])
    assert out_true == [{"token": "ema", "visible": True}]


def test_parse_layout_indicators_absent_visible_is_not_injected():
    from market.quotes import parse_layout_indicators

    # Absent = true at read time; the parser MUST NOT inject a default key.
    out = parse_layout_indicators([{"token": "rsi"}])
    assert out == [{"token": "rsi"}]
    assert "visible" not in out[0]


@pytest.mark.parametrize("bad", ["yes", 1, 0, None, []])
def test_parse_layout_indicators_non_bool_visible_is_400(bad):
    from market.quotes import parse_layout_indicators

    with pytest.raises(ValueError):
        parse_layout_indicators([{"token": "sma", "visible": bad}])


def test_layout_put_then_get_round_trips_visible_verbatim():
    indicators = [
        {"token": "sma", "params": {"sma_len": 50}, "visible": False},
        {"token": "macd"},
    ]
    put = _put_layout(
        USER, {"symbol": "BTCUSDT", "interval": "1m", "indicators": indicators}
    )
    assert put.status_code == 200

    body = USER.get(f"{LAYOUT_URL}?symbol=BTCUSDT&interval=1m").json()
    assert body["indicators"] == indicators


def test_layout_put_non_bool_visible_is_400_and_writes_nothing():
    from trading.models import ChartLayout

    response = _put_layout(
        USER,
        {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "indicators": [{"token": "sma", "visible": "yes"}],
        },
    )
    assert response.status_code == 400
    assert "error" in response.json()
    assert ChartLayout.objects.count() == 0


# --- WU2: drawings CRUD endpoint (R2/R3/R4/R5) ------------------------------

DRAWINGS_URL = "/market/api/drawings"


def _post_drawing(client, payload):
    return client.post(
        DRAWINGS_URL, data=json.dumps(payload), content_type="application/json"
    )


def _put_drawing(client, drawing_id, payload):
    return client.put(
        f"{DRAWINGS_URL}/{drawing_id}",
        data=json.dumps(payload),
        content_type="application/json",
    )


def _drawing_body(**overrides):
    # Per SYMBOL (R1): no ``interval`` in the canonical body. A stale client may
    # still send one; POST accepts and ignores it (see the stale-interval test).
    body = {
        "symbol": "BTCUSDT",
        "kind": "hline",
        "points": {"price": 50000.0},
        "style": {"color": "#f00", "lineWidth": 1},
    }
    body.update(overrides)
    return body


def test_drawings_anonymous_get_redirects_to_login():
    response = ANON.get(f"{DRAWINGS_URL}?symbol=BTCUSDT")
    assert response.status_code == 302
    assert response.url.startswith("/login/")


def test_drawings_anonymous_post_redirects_to_login():
    response = _post_drawing(ANON, _drawing_body())
    assert response.status_code == 302
    assert response.url.startswith("/login/")


def test_drawings_anonymous_delete_redirects_to_login():
    response = ANON.delete(f"{DRAWINGS_URL}/1")
    assert response.status_code == 302
    assert response.url.startswith("/login/")


def test_drawings_get_empty_returns_empty_list_not_404():
    from trading.models import Drawing

    response = USER.get(f"{DRAWINGS_URL}?symbol=BTCUSDT")

    assert response.status_code == 200
    assert response.json() == {"symbol": "BTCUSDT", "drawings": []}
    assert Drawing.objects.count() == 0


def test_drawings_get_missing_symbol_is_400():
    assert USER.get(DRAWINGS_URL).status_code == 400


def test_drawings_get_ignores_any_interval_query_param():
    # R2: GET is per SYMBOL only; a stray ``interval`` query key is ignored.
    assert USER.get(f"{DRAWINGS_URL}?symbol=BTCUSDT&interval=2s").status_code == 200
    assert USER.get(f"{DRAWINGS_URL}?symbol=BTCUSDT").json()["drawings"] == []


def test_drawings_post_then_get_lists_the_row_with_id():
    response = _post_drawing(USER, _drawing_body())

    assert response.status_code == 201
    created = response.json()
    assert created["kind"] == "hline"
    assert created["points"] == {"price": 50000.0}
    assert created["style"] == {"color": "#f00", "lineWidth": 1}
    assert isinstance(created["id"], int)

    body = USER.get(f"{DRAWINGS_URL}?symbol=BTCUSDT").json()
    assert body["drawings"] == [
        {
            "id": created["id"],
            "kind": "hline",
            "points": {"price": 50000.0},
            "style": {"color": "#f00", "lineWidth": 1},
            "visible": True,
            "locked": False,
        }
    ]


def test_drawings_post_accepts_and_ignores_stale_interval():
    # R4: an incoming ``interval`` (stale client) is accepted and ignored —
    # never 400 — and the row is stored per SYMBOL.
    response = _post_drawing(USER, _drawing_body(interval="7m"))

    assert response.status_code == 201
    assert isinstance(response.json()["id"], int)

    body = USER.get(f"{DRAWINGS_URL}?symbol=BTCUSDT").json()
    assert len(body["drawings"]) == 1


def test_drawings_get_lists_only_the_requested_symbol():
    _post_drawing(USER, _drawing_body())
    _post_drawing(
        USER,
        _drawing_body(
            kind="trendline",
            points={
                "p1": {"time": 1, "price": 1.0},
                "p2": {"time": 2, "price": 2.0},
            },
        ),
    )
    _post_drawing(USER, _drawing_body(symbol="ETHUSDT"))

    body = USER.get(f"{DRAWINGS_URL}?symbol=BTCUSDT").json()
    assert len(body["drawings"]) == 2
    assert {d["kind"] for d in body["drawings"]} == {"hline", "trendline"}


def test_drawings_get_same_row_after_interval_only_conceptual_switch():
    # R7: a drawing is per SYMBOL, so it survives an interval-only switch — a
    # GET without the (dropped) interval key still lists it.
    created = _post_drawing(USER, _drawing_body()).json()

    body = USER.get(f"{DRAWINGS_URL}?symbol=BTCUSDT").json()
    assert [d["id"] for d in body["drawings"]] == [created["id"]]


def test_drawings_many_per_symbol_coexist_without_unique_violation():
    from trading.models import Drawing

    first = _post_drawing(USER, _drawing_body())
    second = _post_drawing(USER, _drawing_body())

    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert Drawing.objects.count() == 2


@pytest.mark.parametrize(
    "payload",
    [
        _drawing_body(kind="notreal"),  # kind outside DRAWING_KINDS
        _drawing_body(symbol=""),  # empty symbol
        _drawing_body(points={"nope": 1}),  # malformed point (missing price)
        _drawing_body(kind="trendline", points={"p1": {"time": 1, "price": 1.0}}),
        _drawing_body(
            kind="trendline",
            points={
                "p1": {"time": 1, "price": 1.0},
                "p2": {"time": 2, "price": 2.0},
                "p3": {"time": 3, "price": 3.0},
            },
        ),
        _drawing_body(style="not-an-object"),  # style not an object
        _drawing_body(kind="text", points={"time": 1, "price": 1.0}),  # no label
    ],
)
def test_drawings_post_invalid_payload_is_400_and_writes_nothing(payload):
    from trading.models import Drawing

    response = _post_drawing(USER, payload)

    assert response.status_code == 400
    assert "error" in response.json()
    assert Drawing.objects.count() == 0


def test_drawings_post_invalid_json_is_400():
    response = USER.post(DRAWINGS_URL, data="not-json", content_type="application/json")
    assert response.status_code == 400
    assert "error" in response.json()


def test_drawings_post_requires_csrf():
    enforcing = Client(enforce_csrf_checks=True)
    enforcing.force_login(AUTH_USER)
    response = enforcing.post(
        DRAWINGS_URL,
        data=json.dumps(_drawing_body()),
        content_type="application/json",
    )
    assert response.status_code == 403


def test_drawings_delete_own_removes_the_row():
    created = _post_drawing(USER, _drawing_body()).json()

    response = USER.delete(f"{DRAWINGS_URL}/{created['id']}")
    assert response.status_code in (200, 204)

    body = USER.get(f"{DRAWINGS_URL}?symbol=BTCUSDT").json()
    assert body["drawings"] == []


def test_drawings_delete_miss_is_404():
    assert USER.delete(f"{DRAWINGS_URL}/999999").status_code == 404


def test_drawings_delete_requires_csrf():
    created = _post_drawing(USER, _drawing_body()).json()
    enforcing = Client(enforce_csrf_checks=True)
    enforcing.force_login(AUTH_USER)
    response = enforcing.delete(f"{DRAWINGS_URL}/{created['id']}")
    assert response.status_code == 403


def test_drawings_isolation_b_get_never_sees_a():
    from django.contrib.auth import get_user_model

    _post_drawing(USER, _drawing_body())

    b_client = Client()
    b = get_user_model().objects.create_user(
        email="db@example.com", password="pw-123456"
    )
    b_client.force_login(b)

    body = b_client.get(f"{DRAWINGS_URL}?symbol=BTCUSDT").json()
    assert body["drawings"] == []


def test_drawings_isolation_b_delete_of_a_id_is_404_and_a_unchanged():
    from django.contrib.auth import get_user_model
    from trading.models import Drawing

    created = _post_drawing(USER, _drawing_body()).json()
    a_row = Drawing.objects.get(pk=created["id"])

    b_client = Client()
    b = get_user_model().objects.create_user(
        email="db2@example.com", password="pw-123456"
    )
    b_client.force_login(b)

    response = b_client.delete(f"{DRAWINGS_URL}/{created['id']}")
    assert response.status_code == 404
    assert Drawing.objects.filter(pk=a_row.pk).exists()  # A's row untouched


# --- WU2: drawings PUT update path (R2 modified / R14.6) --------------------


def _trendline_body(**overrides):
    """A valid ``trendline`` create body (two fully-specified anchors)."""
    body = _drawing_body(
        kind="trendline",
        points={"p1": {"time": 1, "price": 1.0}, "p2": {"time": 2, "price": 2.0}},
    )
    body.update(overrides)
    return body


def test_drawings_anonymous_put_redirects_to_login():
    response = _put_drawing(ANON, 1, {"points": {"price": 1.0}})
    assert response.status_code == 302
    assert response.url.startswith("/login/")


def test_drawings_put_updates_points_round_trip():
    created = _post_drawing(USER, _trendline_body()).json()

    new_points = {
        "p1": {"time": 10, "price": 9.5},
        "p2": {"time": 20, "price": 11.5},
    }
    response = _put_drawing(USER, created["id"], {"points": new_points})

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["kind"] == "trendline"
    assert body["points"] == new_points
    # Persisted (not just echoed): a fresh GET reflects the update.
    listed = USER.get(f"{DRAWINGS_URL}?symbol=BTCUSDT").json()["drawings"]
    assert listed[0]["points"] == new_points


def test_drawings_put_updates_style_round_trip():
    created = _post_drawing(USER, _trendline_body()).json()

    new_style = {"color": "#00ff00", "lineWidth": 3}
    response = _put_drawing(USER, created["id"], {"style": new_style})

    assert response.status_code == 200
    assert response.json()["style"] == new_style
    listed = USER.get(f"{DRAWINGS_URL}?symbol=BTCUSDT").json()["drawings"]
    assert listed[0]["style"] == new_style


def test_drawings_put_partial_points_only_keeps_style():
    created = _post_drawing(USER, _trendline_body()).json()
    original_style = created["style"]

    response = _put_drawing(
        USER,
        created["id"],
        {"points": {"p1": {"time": 5, "price": 5.0}, "p2": {"time": 6, "price": 6.0}}},
    )

    assert response.status_code == 200
    assert response.json()["style"] == original_style  # untouched
    listed = USER.get(f"{DRAWINGS_URL}?symbol=BTCUSDT").json()["drawings"]
    assert listed[0]["style"] == original_style


def test_drawings_put_partial_style_only_keeps_points():
    created = _post_drawing(USER, _trendline_body()).json()
    original_points = created["points"]

    response = _put_drawing(USER, created["id"], {"style": {"lineWidth": 4}})

    assert response.status_code == 200
    assert response.json()["points"] == original_points  # untouched


def test_drawings_put_kind_immutable_differing_is_400_and_no_write():
    from trading.models import Drawing

    created = _post_drawing(USER, _trendline_body()).json()
    a_row = Drawing.objects.get(pk=created["id"])

    response = _put_drawing(
        USER,
        created["id"],
        {"kind": "hline", "points": {"price": 9.0}},
    )

    assert response.status_code == 400
    assert "error" in response.json()
    a_row.refresh_from_db()
    assert a_row.kind == "trendline"
    assert a_row.points == created["points"]  # no write at all


def test_drawings_put_equal_kind_is_accepted_and_ignored():
    created = _post_drawing(USER, _trendline_body()).json()

    response = _put_drawing(
        USER, created["id"], {"kind": "trendline", "style": {"lineWidth": 2}}
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "trendline"
    assert response.json()["style"] == {"lineWidth": 2}


@pytest.mark.parametrize(
    "points",
    [
        {"nope": 1},  # malformed for trendline (missing p1/p2)
        {"p1": {"time": 1, "price": 1.0}},  # only one anchor
        {"p1": {"time": "x", "price": 1.0}, "p2": {"time": 2, "price": 2.0}},  # bad
    ],
)
def test_drawings_put_invalid_points_is_400_and_writes_nothing(points):
    from trading.models import Drawing

    created = _post_drawing(USER, _trendline_body()).json()
    a_row = Drawing.objects.get(pk=created["id"])

    response = _put_drawing(USER, created["id"], {"points": points})

    assert response.status_code == 400
    assert "error" in response.json()
    a_row.refresh_from_db()
    assert a_row.points == created["points"]  # unchanged


def test_drawings_put_invalid_style_is_400_and_writes_nothing():
    from trading.models import Drawing

    created = _post_drawing(USER, _trendline_body()).json()
    a_row = Drawing.objects.get(pk=created["id"])

    response = _put_drawing(USER, created["id"], {"style": "not-an-object"})

    assert response.status_code == 400
    assert "error" in response.json()
    a_row.refresh_from_db()
    assert a_row.style == created["style"]


def test_drawings_put_invalid_json_is_400():
    created = _post_drawing(USER, _trendline_body()).json()

    response = USER.put(
        f"{DRAWINGS_URL}/{created['id']}",
        data="not-json",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "error" in response.json()


def test_drawings_put_non_object_body_is_400():
    created = _post_drawing(USER, _trendline_body()).json()

    response = USER.put(
        f"{DRAWINGS_URL}/{created['id']}",
        data="[1, 2]",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "error" in response.json()


def test_drawings_put_miss_is_404():
    response = _put_drawing(USER, 999999, {"style": {"lineWidth": 2}})
    assert response.status_code == 404
    assert "error" in response.json()


def test_drawings_put_requires_csrf():
    created = _post_drawing(USER, _trendline_body()).json()
    enforcing = Client(enforce_csrf_checks=True)
    enforcing.force_login(AUTH_USER)
    response = enforcing.put(
        f"{DRAWINGS_URL}/{created['id']}",
        data=json.dumps({"style": {"lineWidth": 2}}),
        content_type="application/json",
    )
    assert response.status_code == 403


def test_drawings_isolation_b_put_of_a_id_is_404_and_a_unchanged():
    # R14.6: cross-user update denied — for_user resolves nothing for B, so the
    # PUT is a 404 with no existence leak and A's row is untouched.
    from django.contrib.auth import get_user_model
    from trading.models import Drawing

    created = _post_drawing(USER, _trendline_body()).json()
    a_row = Drawing.objects.get(pk=created["id"])

    b_client = Client()
    b = get_user_model().objects.create_user(
        email="putb@example.com", password="pw-123456"
    )
    b_client.force_login(b)

    response = _put_drawing(
        b_client,
        created["id"],
        {"points": {"p1": {"time": 9, "price": 9.0}, "p2": {"time": 9, "price": 9.0}}},
    )

    assert response.status_code == 404
    a_row.refresh_from_db()
    assert a_row.points == created["points"]  # A unchanged
    assert a_row.style == created["style"]


# --- F5 S1: drawing visible/locked flags (R2 delta) --------------------------


def test_drawings_post_defaults_absent_flags():
    response = _post_drawing(USER, _drawing_body())

    assert response.status_code == 201
    body = response.json()
    assert body["visible"] is True
    assert body["locked"] is False


def test_drawings_post_carries_explicit_flags_and_get_lists_them():
    response = _post_drawing(USER, _drawing_body(visible=False, locked=True))

    assert response.status_code == 201
    created = response.json()
    assert created["visible"] is False
    assert created["locked"] is True

    listed = USER.get(f"{DRAWINGS_URL}?symbol=BTCUSDT").json()["drawings"]
    assert listed[0]["visible"] is False
    assert listed[0]["locked"] is True


@pytest.mark.parametrize("key", ["visible", "locked"])
@pytest.mark.parametrize("bad", ["yes", 1, 0, None])
def test_drawings_post_non_bool_flag_is_400_and_writes_nothing(key, bad):
    from trading.models import Drawing

    response = _post_drawing(USER, _drawing_body(**{key: bad}))

    assert response.status_code == 400
    assert "error" in response.json()
    assert Drawing.objects.count() == 0


def test_drawings_put_updates_both_flags_round_trip():
    created = _post_drawing(USER, _drawing_body()).json()

    response = _put_drawing(USER, created["id"], {"visible": False, "locked": True})

    assert response.status_code == 200
    assert response.json()["visible"] is False
    assert response.json()["locked"] is True
    listed = USER.get(f"{DRAWINGS_URL}?symbol=BTCUSDT").json()["drawings"]
    assert listed[0]["visible"] is False
    assert listed[0]["locked"] is True


def test_drawings_put_partial_visible_only_keeps_locked_and_points():
    created = _post_drawing(USER, _drawing_body(locked=True)).json()
    original_points = created["points"]

    response = _put_drawing(USER, created["id"], {"visible": False})

    assert response.status_code == 200
    body = response.json()
    assert body["visible"] is False
    assert body["locked"] is True  # kept from the stored row
    assert body["points"] == original_points


@pytest.mark.parametrize("key", ["visible", "locked"])
@pytest.mark.parametrize("bad", ["yes", 1, 0, None])
def test_drawings_put_non_bool_flag_is_400_and_writes_nothing(key, bad):
    from trading.models import Drawing

    created = _post_drawing(USER, _drawing_body()).json()
    a_row = Drawing.objects.get(pk=created["id"])

    response = _put_drawing(USER, created["id"], {key: bad})

    assert response.status_code == 400
    assert "error" in response.json()
    a_row.refresh_from_db()
    assert a_row.visible is True and a_row.locked is False  # unchanged


def test_drawings_put_stale_interval_key_still_ignored():
    # R2: an ``interval`` key in a PUT body MUST NOT 400 (accepted and ignored).
    created = _post_drawing(USER, _drawing_body()).json()
    response = _put_drawing(USER, created["id"], {"interval": "1m", "visible": False})
    assert response.status_code == 200
    assert response.json()["visible"] is False


# --- F9 S2: eight new drawing kinds (R1/R4/R5) ------------------------------

_P1 = {"time": 1, "price": 1.0}
_P2 = {"time": 2, "price": 2.0}
_P3 = {"time": 3, "price": 3.0}

# One canonical valid ``points`` object per F9 kind (R5 schema table).
_F9_VALID_POINTS = {
    "ray": {"p1": _P1, "p2": _P2},
    "vline": {"time": 1700000000},
    "channel": {"p1": _P1, "p2": _P2, "p3": _P3},
    "price": {"price": 50000.0},
    "callout": {"p1": _P1, "p2": _P2, "text": "note"},
    "fib_ext": {"p1": _P1, "p2": _P2, "p3": _P3},
    "fib_time": {"p1": _P1, "p2": _P2},
    "fib_zone": {"p1": _P1, "p2": _P2},
}

# Malformed variants per kind: (kind, points) — every one MUST 400 with no write.
_F9_INVALID_POINTS = [
    ("ray", {"p1": _P1}),  # one anchor
    ("ray", {"p1": _P1, "p2": _P2, "p3": _P3}),  # extra key
    ("ray", {"p1": {"time": "x", "price": 1.0}, "p2": _P2}),  # non-int time
    ("ray", {"p1": {"time": 1, "price": "x"}, "p2": _P2}),  # non-num price
    ("ray", {"p1": {"time": 1, "price": True}, "p2": _P2}),  # bool price
    ("vline", {"time": 1, "price": 1.0}),  # vline carries no price key
    ("vline", {"time": "x"}),  # non-int time
    ("vline", {}),  # missing time
    ("channel", {"p1": _P1, "p2": _P2}),  # two anchors
    ("channel", {"p1": _P1, "p2": _P2, "p3": _P3, "p4": _P1}),  # four anchors
    ("channel", {"p1": _P1, "p2": _P2, "p3": {"time": 3}}),  # p3 missing price
    ("price", {"time": 1, "price": 1.0}),  # price carries price only
    ("price", {"price": "x"}),  # non-num price
    ("price", {"price": True}),  # bool price
    ("price", {}),  # missing price
    ("callout", {"p1": _P1, "p2": _P2}),  # missing text
    ("callout", {"p1": _P1, "p2": _P2, "text": "  "}),  # blank text
    ("callout", {"p1": _P1, "p2": _P2, "text": 1}),  # non-str text
    ("fib_ext", {"p1": _P1, "p2": _P2}),  # two anchors
    ("fib_ext", {"p1": _P1, "p2": _P2, "p3": _P3, "p4": _P1}),  # extra key
    ("fib_time", {"p1": _P1}),  # one anchor
    ("fib_time", {"p1": _P1, "p2": _P2, "p3": _P3}),  # three anchors
    ("fib_zone", {"p1": _P1}),  # one anchor
    ("fib_zone", {"p1": _P1, "p2": {"time": 2}}),  # p2 missing price
]


@pytest.mark.parametrize("kind", sorted(_F9_VALID_POINTS))
def test_drawings_f9_kind_post_get_put_round_trip(kind):
    points = _F9_VALID_POINTS[kind]
    created = _post_drawing(USER, _drawing_body(kind=kind, points=points))

    assert created.status_code == 201, created.json()
    body = created.json()
    assert body["kind"] == kind
    assert body["points"] == points
    assert isinstance(body["id"], int)

    listed = USER.get(f"{DRAWINGS_URL}?symbol=BTCUSDT").json()["drawings"]
    assert listed[0]["kind"] == kind
    assert listed[0]["points"] == points

    moved = _put_drawing(USER, body["id"], {"points": points})
    assert moved.status_code == 200
    assert moved.json()["points"] == points


@pytest.mark.parametrize(("kind", "points"), _F9_INVALID_POINTS)
def test_drawings_f9_invalid_points_is_400_and_writes_nothing(kind, points):
    from trading.models import Drawing

    response = _post_drawing(USER, _drawing_body(kind=kind, points=points))

    assert response.status_code == 400, (kind, response.json())
    assert "error" in response.json()
    assert Drawing.objects.count() == 0


@pytest.mark.parametrize("kind", sorted(_F9_VALID_POINTS))
def test_parse_drawing_accepts_each_f9_kind(kind):
    from market.quotes import parse_drawing

    points = _F9_VALID_POINTS[kind]
    out = parse_drawing(kind, points, {})
    assert out[0] == points


def test_f9_kinds_are_members_of_drawing_kinds():
    # R1: DRAWING_KINDS (quotes.py) auto-includes the eight F9 kinds.
    from market.quotes import DRAWING_KINDS

    assert set(_F9_VALID_POINTS) <= DRAWING_KINDS


def test_drawings_f9_interval_key_ignored_not_400():
    # R4: an incoming ``interval`` is accepted and ignored for a new kind too.
    response = _post_drawing(
        USER, _drawing_body(kind="ray", points=_F9_VALID_POINTS["ray"], interval="7m")
    )
    assert response.status_code == 201


def test_drawings_f9_isolation_b_put_of_a_id_is_404():
    from django.contrib.auth import get_user_model

    created = _post_drawing(
        USER, _drawing_body(kind="fib_ext", points=_F9_VALID_POINTS["fib_ext"])
    ).json()

    b_client = Client()
    b = get_user_model().objects.create_user(
        email="f9b@example.com", password="pw-123456"
    )
    b_client.force_login(b)

    response = _put_drawing(
        b_client, created["id"], {"points": _F9_VALID_POINTS["fib_ext"]}
    )
    assert response.status_code == 404


# --- parse_drawing: pure validation seam (R4/R5) ----------------------------


@pytest.mark.parametrize(
    ("kind", "points", "style"),
    [
        ("hline", {"price": 50000.0}, {"color": "#f00", "lineWidth": 1}),
        (
            "trendline",
            {"p1": {"time": 1, "price": 1.0}, "p2": {"time": 2, "price": 2.0}},
            {"color": "#0f0", "lineWidth": 2},
        ),
        (
            "fib",
            {"p1": {"time": 1, "price": 1.0}, "p2": {"time": 2, "price": 2.0}},
            {"color": "#00f", "lineWidth": 1, "levels": [0.382, 0.618]},
        ),
        (
            "rect",
            {"p1": {"time": 1, "price": 1.0}, "p2": {"time": 2, "price": 2.0}},
            {"color": "#ff0", "lineWidth": 1, "fill": "#ff04"},
        ),
        ("text", {"time": 1, "price": 1.0, "text": "hello"}, {"color": "#fff"}),
    ],
)
def test_parse_drawing_accepts_each_kind(kind, points, style):
    from market.quotes import parse_drawing

    out_points, out_style, out_visible, out_locked = parse_drawing(kind, points, style)
    assert out_points == points
    assert out_style == style
    # Absent flags default to True/False (R2).
    assert out_visible is True
    assert out_locked is False


def test_parse_drawing_carries_real_bool_flags():
    from market.quotes import parse_drawing

    out_points, out_style, out_visible, out_locked = parse_drawing(
        "hline", {"price": 1.0}, {}, visible=False, locked=True
    )
    assert out_points == {"price": 1.0}
    assert out_style == {}
    assert out_visible is False
    assert out_locked is True


@pytest.mark.parametrize(
    "flags",
    [
        {"visible": "yes"},  # str
        {"visible": 1},  # int (int is not bool)
        {"visible": None},  # None where a bool is expected
        {"locked": "no"},  # str
        {"locked": 0},  # int
        {"locked": None},  # None
    ],
)
def test_parse_drawing_rejects_non_bool_flags(flags):
    from market.quotes import parse_drawing

    with pytest.raises(ValueError):
        parse_drawing("hline", {"price": 1.0}, {}, **flags)


@pytest.mark.parametrize(
    ("kind", "points", "style"),
    [
        ("notreal", {"price": 1.0}, {}),  # kind outside DRAWING_KINDS
        ("hline", {}, {}),  # missing price
        ("hline", {"price": "x"}, {}),  # price not numeric
        ("trendline", {"p1": {"time": 1, "price": 1.0}}, {}),  # one point
        (
            "trendline",
            {"p1": {"time": 1, "price": 1.0}, "p2": {"time": 2}},  # p2 missing price
            {},
        ),
        (
            "trendline",
            {"p1": "x", "p2": {"time": 2, "price": 2.0}},
            {},
        ),  # point not obj
        (
            "trendline",
            {"p1": {"time": "x", "price": 1.0}, "p2": {"time": 2, "price": 2.0}},
            {},
        ),  # time not int
        (
            "fib",
            {"p1": {"time": 1, "price": 1.0}},  # one point
            {},
        ),
        ("rect", {"p1": {"time": 1, "price": 1.0}}, {}),  # one point
        ("text", {"time": 1, "price": 1.0}, {}),  # no label
        ("text", {"time": 1, "price": 1.0, "text": ""}, {}),  # empty label
        ("text", {"time": "x", "price": 1.0, "text": "hi"}, {}),  # time not int
        ("text", {"time": 1, "price": "x", "text": "hi"}, {}),  # price not numeric
        ("hline", {"price": 1.0}, "not-an-object"),  # style not an object
        ("hline", "not-an-object", {}),  # points not an object
    ],
)
def test_parse_drawing_rejects_bad_input(kind, points, style):
    from market.quotes import parse_drawing

    with pytest.raises(ValueError):
        parse_drawing(kind, points, style)


def test_drawings_post_non_object_body_is_400():
    response = USER.post(DRAWINGS_URL, data="[1, 2]", content_type="application/json")
    assert response.status_code == 400
    assert "error" in response.json()


# --- R12: SMC overlay endpoint + payload seam (Slice 1) ---------------------

SMC_URL = "/market/api/smc"

# Top-level keys are frozen by the spec (no ``index`` anywhere).
SMC_KEYS = {
    "symbol",
    "interval",
    "swings",
    "structure",
    "order_blocks",
    "fvgs",
    "range",
    "setups",
}


def _smc_rows():
    """Deterministic zigzag (48 bars) exercising the whole frozen chain.

    Six rising peak/trough legs (4 bars each) yield confirmed swings, HH/HL
    labels, BOS events, order blocks, FVGs, a dealing range and one long setup.
    """
    peaks = [110, 112, 116, 118, 124, 126]
    troughs = [100, 102, 104, 108, 110, 112]
    seq = []
    for peak, trough in zip(peaks, troughs, strict=True):
        seq.append((peak, "up"))
        seq.append((trough, "down"))
    rows = []
    prev = 100.0
    t = 0
    for price, direction in seq:
        for s in range(4):
            v = prev + (price - prev) * (s / 4)
            hi, lo = v + 0.5, v - 0.5
            o, c = (hi - 0.1, lo + 0.1) if direction == "down" else (lo + 0.1, hi - 0.1)
            rows.append(_row(t * 60, o, hi, lo, c))
            t += 1
        prev = price
    return rows


def _all_keys(obj):
    """Every dict key anywhere in a nested payload (for leak checks)."""
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _all_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _all_keys(item)
    return keys


# --- payload layer: get_smc_payload with a stub client ----------------------


def test_smc_payload_exact_top_level_shape():
    from market.quotes import get_smc_payload

    payload = get_smc_payload(StubClient(_smc_rows()), "BTCUSDT", "1m", 48)

    assert set(payload) == SMC_KEYS
    assert payload["symbol"] == "BTCUSDT"
    assert payload["interval"] == "1m"
    assert isinstance(payload["range"], dict)


def test_smc_payload_no_index_or_anchor_key_leaks():
    from market.quotes import get_smc_payload

    payload = get_smc_payload(StubClient(_smc_rows()), "BTCUSDT", "1m", 48)

    keys = _all_keys(payload)
    assert "index" not in keys
    assert "anchor" not in keys  # only ``anchor_time`` is emitted
    assert "anchor_time" in keys


def test_smc_payload_times_are_window_members():
    from market.quotes import get_smc_payload

    rows = _smc_rows()
    payload = get_smc_payload(StubClient(rows), "BTCUSDT", "1m", 48)
    times = {c["time"] for c in rows}

    emitted = (
        [r["time"] for r in payload["swings"]]
        + [r["time"] for r in payload["structure"]]
        + [r["time"] for r in payload["order_blocks"]]
        + [r["anchor_time"] for r in payload["order_blocks"]]
        + [r["time"] for r in payload["fvgs"]]
        + [r["time"] for r in payload["setups"]]
        + [payload["range"]["time"]]
    )
    assert emitted
    assert all(t in times for t in emitted)


def test_smc_payload_index_resolved_to_candle_time():
    from market.quotes import get_smc_payload

    rows = _smc_rows()
    payload = get_smc_payload(StubClient(rows), "BTCUSDT", "1m", 48)

    # First BOS is at bar 19 (-> time 1140) anchored on OB at bar 15 (-> 900).
    assert payload["structure"][0] == {
        "kind": "bos",
        "time": 19 * 60,
        "price": 112.5,
        "direction": "bullish",
        "trend": "up",
    }
    ob = payload["order_blocks"][0]
    assert ob == {
        "kind": "bullish",
        "time": 15 * 60,
        "top": 105.0,
        "bottom": 104.0,
        "anchor_time": 19 * 60,
    }


def test_smc_payload_label_null_for_first_of_each_kind():
    from market.quotes import get_smc_payload

    payload = get_smc_payload(StubClient(_smc_rows()), "BTCUSDT", "1m", 48)

    first_high = next(s for s in payload["swings"] if s["kind"] == "high")
    first_low = next(s for s in payload["swings"] if s["kind"] == "low")
    assert first_high["label"] is None  # first-of-kind: label_swings omits it
    assert first_low["label"] is None
    labels = {s["label"] for s in payload["swings"]}
    assert {"HH", "HL"} <= labels


def test_smc_payload_swing_shape_exact():
    from market.quotes import get_smc_payload

    payload = get_smc_payload(StubClient(_smc_rows()), "BTCUSDT", "1m", 48)

    assert payload["swings"]
    assert all(set(s) == {"kind", "time", "price", "label"} for s in payload["swings"])
    assert all(s["kind"] in ("high", "low") for s in payload["swings"])


def test_smc_payload_setup_shape_and_fields():
    from market.quotes import get_smc_payload

    payload = get_smc_payload(StubClient(_smc_rows()), "BTCUSDT", "1m", 48)

    assert payload["setups"]
    setup = payload["setups"][-1]
    assert set(setup) == {
        "direction",
        "time",
        "entry",
        "stop",
        "take_profit",
        "rr",
        "score",
    }
    assert setup["direction"] == "long"
    assert setup["time"] == 44 * 60


def test_smc_payload_empty_window_is_empty_arrays_and_null_range():
    from market.quotes import get_smc_payload

    payload = get_smc_payload(StubClient([]), "BTCUSDT", "1m", 48)

    assert payload == {
        "symbol": "BTCUSDT",
        "interval": "1m",
        "swings": [],
        "structure": [],
        "order_blocks": [],
        "fvgs": [],
        "range": None,
        "setups": [],
    }


def test_smc_payload_fewer_than_three_candles_stays_empty():
    from market.quotes import get_smc_payload

    payload = get_smc_payload(StubClient(_smc_rows()[:2]), "BTCUSDT", "1m", 48)

    assert payload["swings"] == []
    assert payload["range"] is None


def test_smc_payload_want_equals_limit_without_warmup():
    from market.quotes import get_smc_payload

    client = StubClient(_smc_rows())

    get_smc_payload(client, "BTCUSDT", "1m", 30)

    assert client.calls[0]["limit"] == 30  # SMC asks for exactly ``limit``


def test_smc_payload_full_db_window_never_calls_upstream():
    from market.quotes import get_smc_payload

    _seed_series(20)
    client = StubClient([_row(1, "1", "1", "1", "1")])

    payload = get_smc_payload(client, "BTCUSDT", PERSISTED, 10)

    assert client.calls == []
    assert set(payload) == SMC_KEYS


def test_smc_payload_db_rows_survive_upstream_failure():
    import requests
    from market.quotes import get_smc_payload

    _seed_series(5)
    client = StubClient([], error=requests.ConnectionError("boom"))

    payload = get_smc_payload(client, "BTCUSDT", PERSISTED, 10)

    assert set(payload) == SMC_KEYS  # degraded, never raised


def test_smc_payload_empty_db_reraises_upstream_failure():
    import requests
    from market.quotes import get_smc_payload

    client = StubClient([], error=requests.ConnectionError("boom"))

    with pytest.raises(requests.ConnectionError):
        get_smc_payload(client, "BTCUSDT", PERSISTED, 10)


# --- endpoint layer: /market/api/smc contract -------------------------------


def test_smc_endpoint_anonymous_redirects_to_login():
    response = ANON.get(f"{SMC_URL}?symbol=BTCUSDT&interval=1m")
    assert response.status_code == 302
    assert response.url.startswith("/login/")


def test_smc_endpoint_missing_symbol_is_400():
    response = USER.get(f"{SMC_URL}?interval=1m")
    assert response.status_code == 400
    assert "error" in response.json()


def test_smc_endpoint_invalid_interval_is_400():
    response = USER.get(f"{SMC_URL}?symbol=BTCUSDT&interval=2s")
    assert response.status_code == 400
    assert "error" in response.json()


def test_smc_endpoint_limit_outside_range_is_400():
    url = f"{SMC_URL}?symbol=BTCUSDT&interval=1m&limit={{}}"
    assert USER.get(url.format(0)).status_code == 400
    assert USER.get(url.format(201)).status_code == 400
    assert USER.get(url.format("abc")).status_code == 400


def test_smc_endpoint_default_limit_is_200(monkeypatch):
    from market import views

    captured = {}

    def _fake(client, symbol, interval, limit):
        captured.update(symbol=symbol, interval=interval, limit=limit)
        return {"symbol": symbol, "interval": interval}

    monkeypatch.setattr(views, "get_smc_payload", _fake)

    response = USER.get(f"{SMC_URL}?symbol=BTCUSDT&interval=1m")

    assert response.status_code == 200
    assert captured["limit"] == 200


def test_smc_endpoint_200_exact_shape(monkeypatch):
    from market import views

    monkeypatch.setattr(views, "BitunixClient", lambda: StubClient(_smc_rows()))

    response = USER.get(f"{SMC_URL}?symbol=BTCUSDT&interval=1m&limit=48")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == SMC_KEYS
    assert "index" not in _all_keys(body)


def test_smc_endpoint_upstream_reject_without_db_is_400(monkeypatch):
    from market import views

    from src.client import BitunixError

    def reject():
        raise BitunixError(70014, "symbol not exist")

    monkeypatch.setattr(views, "BitunixClient", lambda: (_ for _ in ()).throw(reject()))

    response = USER.get(f"{SMC_URL}?symbol=NOSUCHUSDT&interval=1m")
    assert response.status_code == 400
    assert response.json() == {"error": "upstream rejected"}


def test_smc_endpoint_empty_db_transport_fail_is_502(monkeypatch):
    import requests
    from market import views

    client = StubClient([], error=requests.ConnectionError("connection refused"))
    monkeypatch.setattr(views, "BitunixClient", lambda: client)

    response = USER.get(f"{SMC_URL}?symbol=BTCUSDT&interval={PERSISTED}")

    assert response.status_code == 502
    assert response.json() == {"error": "upstream"}


def test_smc_endpoint_db_rows_with_transport_fail_is_200(monkeypatch):
    import requests
    from market import views

    _seed_series(5)
    client = StubClient([], error=requests.ConnectionError("connection refused"))
    monkeypatch.setattr(views, "BitunixClient", lambda: client)

    response = USER.get(f"{SMC_URL}?symbol=BTCUSDT&interval={PERSISTED}&limit=10")

    assert response.status_code == 200
    assert set(response.json()) == SMC_KEYS


def test_smc_endpoint_unknown_symbol_with_db_rows_is_200(monkeypatch):
    from market import views

    from src.client import BitunixError

    _seed_series(5)
    client = StubClient([], error=BitunixError(70014, "symbol not exist"))
    monkeypatch.setattr(views, "BitunixClient", lambda: client)

    response = USER.get(f"{SMC_URL}?symbol=BTCUSDT&interval={PERSISTED}&limit=10")

    assert response.status_code == 200  # degraded over the DB rows, never 5xx


def test_smc_endpoint_is_market_global_not_per_user(monkeypatch):
    from django.contrib.auth import get_user_model
    from market import views

    monkeypatch.setattr(views, "BitunixClient", lambda: StubClient(_smc_rows()))

    url = f"{SMC_URL}?symbol=BTCUSDT&interval=1m&limit=48"
    body_a = USER.get(url).json()

    b_client = Client()
    b = get_user_model().objects.create_user(
        email="smc-b@example.com", password="pw-123456"
    )
    b_client.force_login(b)
    body_b = b_client.get(url).json()

    assert body_a == body_b  # R5: no per-user scoping/filtering


# --- AS5 (Slice 2): get_smc_payload(*, before=None) additive cursor ---------


def test_smc_payload_before_bounds_the_window():
    from market.quotes import get_smc_payload

    # Persisted series at 1000s steps; before=25000 selects candles < 25000.
    times = _seed_series(25)
    client = StubClient([])

    payload = get_smc_payload(client, "BTCUSDT", PERSISTED, 10, before=25000)

    assert set(payload) == SMC_KEYS
    emitted = payload["swings"] + payload["structure"]
    assert all(r["time"] in times for r in emitted)
    assert all(r["time"] < 25000 for r in emitted)
    assert client.calls == []  # DB held the window; no upstream needed


def test_smc_payload_before_omitted_is_newest_window():
    from market.quotes import get_smc_payload

    _seed_series(25)
    client = StubClient([])

    payload = get_smc_payload(client, "BTCUSDT", PERSISTED, 10)

    # Omitted ``before`` keeps today's behavior: newest rows, no upstream.
    assert set(payload) == SMC_KEYS
    assert client.calls == []


def test_smc_payload_before_forwards_to_upstream_end_time():
    from market.quotes import get_smc_payload

    client = StubClient(_smc_rows())
    get_smc_payload(client, "BTCUSDT", "1m", 10, before=1700000000)

    # ``before`` reaches the shared seam as the exclusive upstream end_time.
    assert client.calls[0]["end_time"] == 1700000000 * 1000


# --- Slice 2: interval preference endpoint (R8/R9/R11) ----------------------

PREF_URL = "/market/api/preference"


def _put_pref(client, payload):
    return client.put(
        PREF_URL, data=json.dumps(payload), content_type="application/json"
    )


def test_preference_anonymous_get_redirects_to_login():
    response = ANON.get(PREF_URL)
    assert response.status_code == 302
    assert response.url.startswith("/login/")


def test_preference_anonymous_put_redirects_to_login():
    response = _put_pref(ANON, {"interval": "1h"})
    assert response.status_code == 302
    assert response.url.startswith("/login/")


def test_preference_get_default_when_absent():
    from trading.models import ChartPreference

    response = USER.get(PREF_URL)

    assert response.status_code == 200
    assert response.json() == {
        "interval": "1m",
        "scale_mode": "linear",
        "chart_type": "candles",
        "theme": "system",
        "smc": {},
        "exists": False,
    }
    assert ChartPreference.objects.count() == 0


def test_preference_put_then_get_round_trip():
    put = _put_pref(USER, {"interval": "1h"})
    assert put.status_code == 200
    assert put.json() == {
        "interval": "1h",
        "scale_mode": "linear",
        "chart_type": "candles",
        "theme": "system",
        "smc": {},
        "exists": True,
    }

    body = USER.get(PREF_URL).json()
    assert body == {
        "interval": "1h",
        "scale_mode": "linear",
        "chart_type": "candles",
        "theme": "system",
        "smc": {},
        "exists": True,
    }


def test_preference_put_upserts_one_row_for_the_user():
    from trading.models import ChartPreference

    _put_pref(USER, {"interval": "1h"})
    _put_pref(USER, {"interval": "4h"})

    rows = list(ChartPreference.for_user(AUTH_USER))
    assert len(rows) == 1
    assert rows[0].last_interval == "4h"


def test_preference_put_invalid_interval_is_400_and_writes_nothing():
    from trading.models import ChartPreference

    response = _put_pref(USER, {"interval": "7m"})

    assert response.status_code == 400
    assert "error" in response.json()
    assert ChartPreference.objects.count() == 0


def test_preference_put_empty_body_writes_nothing_and_returns_defaults():
    from trading.models import ChartPreference

    response = _put_pref(USER, {})

    assert response.status_code == 200
    assert response.json() == {
        "interval": "1m",
        "scale_mode": "linear",
        "chart_type": "candles",
        "theme": "system",
        "smc": {},
        "exists": False,
    }
    assert ChartPreference.objects.count() == 0


def test_preference_put_empty_body_returns_saved_when_present():
    from trading.models import ChartPreference

    _put_pref(USER, {"interval": "2h", "scale_mode": "log", "chart_type": "area"})
    response = _put_pref(USER, {})

    assert response.status_code == 200
    assert response.json() == {
        "interval": "2h",
        "scale_mode": "log",
        "chart_type": "area",
        "theme": "system",
        "smc": {},
        "exists": True,
    }
    assert ChartPreference.for_user(AUTH_USER).count() == 1


def test_preference_put_invalid_json_is_400():
    response = USER.put(PREF_URL, data="not-json", content_type="application/json")
    assert response.status_code == 400
    assert "error" in response.json()


def test_preference_put_non_object_body_is_400():
    response = USER.put(PREF_URL, data="[1, 2]", content_type="application/json")
    assert response.status_code == 400
    assert "error" in response.json()


def test_preference_put_requires_csrf():
    enforcing = Client(enforce_csrf_checks=True)
    enforcing.force_login(AUTH_USER)
    response = enforcing.put(
        PREF_URL,
        data=json.dumps({"interval": "1h"}),
        content_type="application/json",
    )
    assert response.status_code == 403


def test_preference_isolation_b_get_never_sees_a():
    from django.contrib.auth import get_user_model
    from trading.models import ChartPreference

    ChartPreference.objects.create(user=AUTH_USER, last_interval="4h")

    b_client = Client()
    b = get_user_model().objects.create_user(
        email="pref-b@example.com", password="pw-123456"
    )
    b_client.force_login(b)

    assert b_client.get(PREF_URL).json() == {
        "interval": "1m",
        "scale_mode": "linear",
        "chart_type": "candles",
        "theme": "system",
        "smc": {},
        "exists": False,
    }


def test_preference_isolation_b_put_does_not_touch_a_row():
    from django.contrib.auth import get_user_model
    from trading.models import ChartPreference

    a_row = ChartPreference.objects.create(user=AUTH_USER, last_interval="4h")

    b_client = Client()
    b = get_user_model().objects.create_user(
        email="pref-b2@example.com", password="pw-123456"
    )
    b_client.force_login(b)

    _put_pref(b_client, {"interval": "1h"})

    a_row.refresh_from_db()
    assert a_row.last_interval == "4h"  # A untouched
    assert ChartPreference.for_user(b).get().last_interval == "1h"
    assert ChartPreference.for_user(AUTH_USER).count() == 1


def test_preference_get_is_not_scoped_to_interval_query_param():
    # A preference is user-global: the GET carries no symbol/interval input.
    from trading.models import ChartPreference

    ChartPreference.objects.create(user=AUTH_USER, last_interval="12h")
    assert USER.get(PREF_URL).json() == {
        "interval": "12h",
        "scale_mode": "linear",
        "chart_type": "candles",
        "theme": "system",
        "smc": {},
        "exists": True,
    }


# --- Slice 3: chart type + scale persistence (R8/R9/R12) ---------------------


def test_preference_put_scale_then_get_round_trip():
    put = _put_pref(USER, {"scale_mode": "log"})
    assert put.status_code == 200
    assert put.json() == {
        "interval": "1m",
        "scale_mode": "log",
        "chart_type": "candles",
        "theme": "system",
        "smc": {},
        "exists": True,
    }
    assert USER.get(PREF_URL).json()["scale_mode"] == "log"


def test_preference_put_chart_type_then_get_round_trip():
    put = _put_pref(USER, {"chart_type": "heikin-ashi"})
    assert put.status_code == 200
    assert put.json() == {
        "interval": "1m",
        "scale_mode": "linear",
        "chart_type": "heikin-ashi",
        "theme": "system",
        "smc": {},
        "exists": True,
    }
    assert USER.get(PREF_URL).json()["chart_type"] == "heikin-ashi"


def test_preference_partial_put_updates_only_present_key():
    from trading.models import ChartPreference

    _put_pref(USER, {"interval": "1h", "scale_mode": "log", "chart_type": "area"})
    response = _put_pref(USER, {"chart_type": "line"})

    assert response.status_code == 200
    assert response.json() == {
        "interval": "1h",
        "scale_mode": "log",
        "chart_type": "line",
        "theme": "system",
        "smc": {},
        "exists": True,
    }
    row = ChartPreference.for_user(AUTH_USER).get()
    assert (row.last_interval, row.scale_mode, row.chart_type) == ("1h", "log", "line")


def test_preference_put_invalid_scale_mode_is_400_and_writes_nothing():
    from trading.models import ChartPreference

    response = _put_pref(USER, {"scale_mode": "bogus"})

    assert response.status_code == 400
    assert "error" in response.json()
    assert ChartPreference.objects.count() == 0


def test_preference_put_invalid_chart_type_is_400_and_writes_nothing():
    from trading.models import ChartPreference

    response = _put_pref(USER, {"chart_type": "notreal"})

    assert response.status_code == 400
    assert "error" in response.json()
    assert ChartPreference.objects.count() == 0


def test_preference_invalid_field_on_partial_put_writes_no_partial_change():
    from trading.models import ChartPreference

    _put_pref(USER, {"interval": "1h", "scale_mode": "log", "chart_type": "area"})
    response = _put_pref(USER, {"interval": "4h", "scale_mode": "bogus"})

    assert response.status_code == 400
    row = ChartPreference.for_user(AUTH_USER).get()
    # No partial write: the valid interval in the same body is NOT applied.
    assert (row.last_interval, row.scale_mode, row.chart_type) == ("1h", "log", "area")


def test_preference_isolation_b_never_sees_a_scale_or_type():
    from django.contrib.auth import get_user_model
    from trading.models import ChartPreference

    ChartPreference.objects.create(
        user=AUTH_USER,
        last_interval="4h",
        scale_mode="percentage",
        chart_type="heikin-ashi",
    )

    b_client = Client()
    b = get_user_model().objects.create_user(
        email="pref-b3@example.com", password="pw-123456"
    )
    b_client.force_login(b)

    assert b_client.get(PREF_URL).json() == {
        "interval": "1m",
        "scale_mode": "linear",
        "chart_type": "candles",
        "theme": "system",
        "smc": {},
        "exists": False,
    }


# --- Slice 2 (chart-theme): theme preference endpoint (R8/R9/R13) ------------


def test_preference_theme_vocabulary_is_frozen():
    # R13: quotes.THEMES is the sole validator for the theme field.
    from market import quotes

    assert quotes.THEMES == ("light", "dark", "system")


def test_preference_get_default_includes_system_theme():
    from trading.models import ChartPreference

    response = USER.get(PREF_URL)

    assert response.status_code == 200
    assert response.json() == {
        "interval": "1m",
        "scale_mode": "linear",
        "chart_type": "candles",
        "theme": "system",
        "smc": {},
        "exists": False,
    }
    assert ChartPreference.objects.count() == 0


def test_preference_put_theme_then_get_round_trip():
    put = _put_pref(USER, {"theme": "light"})
    assert put.status_code == 200
    assert put.json() == {
        "interval": "1m",
        "scale_mode": "linear",
        "chart_type": "candles",
        "theme": "light",
        "smc": {},
        "exists": True,
    }
    assert USER.get(PREF_URL).json()["theme"] == "light"


def test_preference_partial_put_theme_applies_only_theme():
    from trading.models import ChartPreference

    _put_pref(USER, {"interval": "1h", "scale_mode": "log", "chart_type": "area"})
    response = _put_pref(USER, {"theme": "dark"})

    assert response.status_code == 200
    assert response.json() == {
        "interval": "1h",
        "scale_mode": "log",
        "chart_type": "area",
        "theme": "dark",
        "smc": {},
        "exists": True,
    }
    row = ChartPreference.for_user(AUTH_USER).get()
    assert (row.last_interval, row.scale_mode, row.chart_type, row.theme) == (
        "1h",
        "log",
        "area",
        "dark",
    )


def test_preference_put_invalid_theme_is_400_and_writes_nothing():
    from trading.models import ChartPreference

    response = _put_pref(USER, {"theme": "bogus"})

    assert response.status_code == 400
    assert "error" in response.json()
    assert ChartPreference.objects.count() == 0


def test_preference_theme_round_trip_across_reload():
    # CT6: a saved theme persists and is returned by a later GET (round-trip).
    _put_pref(USER, {"theme": "dark"})
    assert USER.get(PREF_URL).json()["theme"] == "dark"
    _put_pref(USER, {"theme": "system"})
    assert USER.get(PREF_URL).json()["theme"] == "system"


def test_preference_isolation_b_never_sees_a_theme():
    from django.contrib.auth import get_user_model
    from trading.models import ChartPreference

    ChartPreference.objects.create(user=AUTH_USER, last_interval="4h", theme="dark")

    b_client = Client()
    b = get_user_model().objects.create_user(
        email="pref-theme-b@example.com", password="pw-123456"
    )
    b_client.force_login(b)

    body = b_client.get(PREF_URL).json()
    assert body["theme"] == "system"
    assert body["exists"] is False


# --- Slice 2 (persistence-foundation): SMC toggles persistence (R7/R8/R9) -----


def test_parse_smc_family_vocabulary_is_frozen():
    # R7: quotes.SMC_FAMILIES mirrors the six JS SMC families (single vocabulary).
    from market import quotes

    assert quotes.SMC_FAMILIES == (
        "swings",
        "structure",
        "order_blocks",
        "fvg",
        "range",
        "setups",
    )


def test_parse_smc_accepts_known_families_and_returns_verbatim():
    from market.quotes import parse_smc

    saved = {"range": False, "fvg": True}
    assert parse_smc(saved) == saved
    # `{}` (all ON) is a valid payload and round-trips unchanged.
    assert parse_smc({}) == {}


def test_parse_smc_rejects_non_dict():
    from market.quotes import parse_smc

    for bad in ("notanobject", [], 3, None):
        with pytest.raises(ValueError):
            parse_smc(bad)


def test_parse_smc_rejects_unknown_family():
    from market.quotes import parse_smc

    with pytest.raises(ValueError):
        parse_smc({"bogus": True})


def test_parse_smc_rejects_non_bool_value():
    from market.quotes import parse_smc

    for bad in ("no", 1, 0, None):
        with pytest.raises(ValueError):
            parse_smc({"range": bad})


def test_preference_get_default_includes_empty_smc():
    from trading.models import ChartPreference

    response = USER.get(PREF_URL)

    assert response.status_code == 200
    assert response.json() == {
        "interval": "1m",
        "scale_mode": "linear",
        "chart_type": "candles",
        "theme": "system",
        "smc": {},
        "exists": False,
    }
    assert ChartPreference.objects.count() == 0


def test_preference_put_smc_then_get_round_trip():
    put = _put_pref(USER, {"smc": {"range": False, "fvg": True}})
    assert put.status_code == 200
    assert put.json()["smc"] == {"range": False, "fvg": True}

    body = USER.get(PREF_URL).json()
    assert body["smc"] == {"range": False, "fvg": True}
    assert body["exists"] is True


def test_preference_partial_put_smc_applies_only_smc():
    from trading.models import ChartPreference

    _put_pref(USER, {"interval": "1h", "scale_mode": "log", "chart_type": "area"})
    response = _put_pref(USER, {"smc": {"setups": False}})

    assert response.status_code == 200
    assert response.json() == {
        "interval": "1h",
        "scale_mode": "log",
        "chart_type": "area",
        "theme": "system",
        "smc": {"setups": False},
        "exists": True,
    }
    row = ChartPreference.for_user(AUTH_USER).get()
    assert row.smc == {"setups": False}
    assert (row.last_interval, row.scale_mode, row.chart_type) == ("1h", "log", "area")


def test_preference_put_invalid_smc_non_object_is_400_and_writes_nothing():
    from trading.models import ChartPreference

    response = _put_pref(USER, {"smc": "notanobject"})

    assert response.status_code == 400
    assert "error" in response.json()
    assert ChartPreference.objects.count() == 0


def test_preference_put_invalid_smc_family_is_400_and_writes_nothing():
    from trading.models import ChartPreference

    response = _put_pref(USER, {"smc": {"bogus": True}})

    assert response.status_code == 400
    assert "error" in response.json()
    assert ChartPreference.objects.count() == 0


def test_preference_put_invalid_smc_value_is_400_and_writes_nothing():
    from trading.models import ChartPreference

    response = _put_pref(USER, {"smc": {"range": "no"}})

    assert response.status_code == 400
    assert "error" in response.json()
    assert ChartPreference.objects.count() == 0


def test_preference_smc_field_round_trips_json():
    from trading.models import ChartPreference

    pref = ChartPreference.objects.create(user=AUTH_USER, smc={"range": False})
    reread = ChartPreference.for_user(AUTH_USER).get(pk=pref.pk)
    assert reread.smc == {"range": False}
    # Default is the empty object (all families ON).
    assert ChartPreference().smc == {}


def test_preference_isolation_b_never_sees_a_smc():
    from django.contrib.auth import get_user_model
    from trading.models import ChartPreference

    ChartPreference.objects.create(
        user=AUTH_USER, last_interval="4h", smc={"range": False}
    )

    b_client = Client()
    b = get_user_model().objects.create_user(
        email="pref-smc-b@example.com", password="pw-123456"
    )
    b_client.force_login(b)

    body = b_client.get(PREF_URL).json()
    assert body["smc"] == {}
    assert body["exists"] is False


# --- F6 S2: position drawing kind (R1/R5/R14) --------------------------------


def _position_body(**overrides):
    """A valid ``position`` create body (entry anchor + SL/TP levels)."""
    body = _drawing_body(
        kind="position",
        points={
            "entry": {"time": 1700000000, "price": 50000.0},
            "stop": 49000.0,
            "take_profit": 52000.0,
        },
    )
    body.update(overrides)
    return body


def test_position_kind_is_a_member_of_drawing_kinds():
    from market.quotes import DRAWING_KINDS

    assert "position" in DRAWING_KINDS


def test_drawings_position_post_get_put_round_trip():
    points = {
        "entry": {"time": 1700000000, "price": 50000.0},
        "stop": 49000.0,
        "take_profit": 52000.0,
    }
    response = _post_drawing(USER, _position_body())

    assert response.status_code == 201
    created = response.json()
    assert created["kind"] == "position"
    assert created["points"] == points

    listed = USER.get(f"{DRAWINGS_URL}?symbol=BTCUSDT").json()["drawings"]
    assert listed[0]["points"] == points
    assert listed[0]["kind"] == "position"

    new_points = {
        "entry": {"time": 1700000060, "price": 51000.0},
        "stop": 50000.0,
        "take_profit": 53000.0,
    }
    updated = _put_drawing(USER, created["id"], {"points": new_points})

    assert updated.status_code == 200
    assert updated.json()["points"] == new_points
    listed = USER.get(f"{DRAWINGS_URL}?symbol=BTCUSDT").json()["drawings"]
    assert listed[0]["points"] == new_points


def test_drawings_position_post_accepts_and_ignores_stale_interval():
    response = _post_drawing(USER, _position_body(interval="7m"))

    assert response.status_code == 201
    assert len(USER.get(f"{DRAWINGS_URL}?symbol=BTCUSDT").json()["drawings"]) == 1


@pytest.mark.parametrize(
    "points",
    [
        {"entry": {"time": 1700000000, "price": 50000.0}, "stop": 49000.0},  # no tp
        {"entry": {"time": 1700000000, "price": 50000.0}, "take_profit": 52000.0},
        # extra key
        {
            "entry": {"time": 1700000000, "price": 50000.0},
            "stop": 49000.0,
            "take_profit": 52000.0,
            "extra": 1,
        },
        "not-an-object",  # points not an object
        {
            "entry": {"time": 1700000000, "price": 50000.0},
            "stop": 49000.0,
            "take_profit": 52000.0,
            "entry_price": 50000.0,
        },  # noqa: E501
        # entry not a dict
        {"entry": 50000.0, "stop": 49000.0, "take_profit": 52000.0},
        # entry missing time
        {"entry": {"price": 50000.0}, "stop": 49000.0, "take_profit": 52000.0},
        # entry time non-int
        {
            "entry": {"time": "x", "price": 50000.0},
            "stop": 49000.0,
            "take_profit": 52000.0,
        },  # noqa: E501
        # entry price non-numeric
        {
            "entry": {"time": 1700000000, "price": "x"},
            "stop": 49000.0,
            "take_profit": 52000.0,
        },  # noqa: E501
        # non-numeric / bool stop
        {
            "entry": {"time": 1700000000, "price": 50000.0},
            "stop": "x",
            "take_profit": 52000.0,
        },  # noqa: E501
        {
            "entry": {"time": 1700000000, "price": 50000.0},
            "stop": True,
            "take_profit": 52000.0,
        },  # noqa: E501
        # non-numeric / bool take_profit
        {
            "entry": {"time": 1700000000, "price": 50000.0},
            "stop": 49000.0,
            "take_profit": "x",
        },  # noqa: E501
        {
            "entry": {"time": 1700000000, "price": 50000.0},
            "stop": 49000.0,
            "take_profit": False,
        },  # noqa: E501
        # degenerate entry.price == stop
        {
            "entry": {"time": 1700000000, "price": 50000.0},
            "stop": 50000.0,
            "take_profit": 52000.0,
        },  # noqa: E501
    ],
)
def test_drawings_position_post_invalid_points_is_400_and_writes_nothing(points):
    from trading.models import Drawing

    response = _post_drawing(USER, _position_body(points=points))

    assert response.status_code == 400
    assert "error" in response.json()
    assert Drawing.objects.count() == 0


def test_drawings_position_put_invalid_points_is_400_and_writes_nothing():
    from trading.models import Drawing

    created = _post_drawing(USER, _position_body()).json()
    a_row = Drawing.objects.get(pk=created["id"])

    response = _put_drawing(
        USER,
        created["id"],
        {
            "points": {
                "entry": {"time": 1700000000, "price": 50000.0},
                "stop": 50000.0,  # degenerate
                "take_profit": 52000.0,
            }
        },
    )

    assert response.status_code == 400
    assert "error" in response.json()
    a_row.refresh_from_db()
    assert a_row.points == created["points"]


def test_drawings_position_isolation_b_get_never_sees_a():
    from django.contrib.auth import get_user_model

    _post_drawing(USER, _position_body())

    b_client = Client()
    b = get_user_model().objects.create_user(
        email="posb@example.com", password="pw-123456"
    )
    b_client.force_login(b)

    assert b_client.get(f"{DRAWINGS_URL}?symbol=BTCUSDT").json()["drawings"] == []


def test_drawings_position_isolation_b_put_of_a_id_is_404_and_a_unchanged():
    from django.contrib.auth import get_user_model
    from trading.models import Drawing

    created = _post_drawing(USER, _position_body()).json()
    a_row = Drawing.objects.get(pk=created["id"])

    b_client = Client()
    b = get_user_model().objects.create_user(
        email="posputb@example.com", password="pw-123456"
    )
    b_client.force_login(b)

    response = _put_drawing(
        b_client,
        created["id"],
        {
            "points": {
                "entry": {"time": 1, "price": 1.0},
                "stop": 2.0,
                "take_profit": 3.0,
            }
        },
    )

    assert response.status_code == 404
    a_row.refresh_from_db()
    assert a_row.points == created["points"]
