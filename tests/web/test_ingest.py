"""R1-R3 contract: global market snapshots + idempotent ingestion service.

No sockets: a stub client exposes ``tickers()``/``funding_rate_batch()`` so
``fetch_market`` exercises the real ``src.monitor.fetch_rows`` parser, and
``persist_market`` proves the unique ``(symbol, ts)`` idempotency at the DB
layer (fetch_rows stamps ``ts`` via the wall clock).
"""

from __future__ import annotations

from datetime import UTC, timedelta

import pytest
from django.db import IntegrityError, transaction
from trading.ingest import fetch_market, persist_market
from trading.models import FundingSnapshot, TickerSnapshot, UserOwnedModel

TS_MS = 1_700_000_000_000  # raw epoch-ms fixture (nextFundingTime)

FIXTURE_TICKERS = [
    {
        "symbol": "BTCUSDT",
        "lastPrice": "50000.5",
        "high": "51000",
        "low": "49000",
        "quoteVol": "123456",
    },
    {
        "symbol": "ETHUSDT",
        "lastPrice": "3000.25",
        "high": "3100",
        "low": "2900",
        "quoteVol": "654321",
    },
]

FIXTURE_FUNDING = [
    {
        "symbol": "BTCUSDT",
        "fundingRate": "0.0001",
        "fundingInterval": "8",
        "nextFundingTime": str(TS_MS),
        "markPrice": "50001",
        "indexPrice": "50000",
    },
    {
        "symbol": "ETHUSDT",
        "fundingRate": "-0.0002",
        "fundingInterval": "4",
        "nextFundingTime": str(TS_MS + 1000),
        "markPrice": "3001",
        "indexPrice": "3000",
    },
]


class StubClient:
    """Read-only double: returns fixtures, never opens a socket."""

    def __init__(self, tickers, funding):
        self._tickers = tickers
        self._funding = funding

    def tickers(self, symbols=None):
        return self._tickers

    def funding_rate_batch(self):
        return self._funding


def _stub():
    return StubClient(FIXTURE_TICKERS, FIXTURE_FUNDING)


def test_fetch_market_splits_and_maps_two_symbols():
    market = fetch_market(_stub(), ["BTCUSDT", "ETHUSDT"])

    assert len(market["funding"]) == 2
    assert len(market["tickers"]) == 2

    funding = market["funding"][0]
    # ts is stamped by fetch_rows' wall clock, converted to aware UTC.
    assert funding["ts"].tzinfo is not None
    assert funding["ts"].utcoffset() == timedelta(0)
    assert funding == {
        "symbol": "BTCUSDT",
        "ts": funding["ts"],
        "funding_rate": 0.0001,
        "mark_price": 50001.0,
        "index_price": 50000.0,
        "next_funding_time": TS_MS,
        "funding_interval": 8,
    }

    ticker = market["tickers"][0]
    assert ticker == {
        "symbol": "BTCUSDT",
        "ts": funding["ts"],
        "last_price": 50000.5,
        "high": 51000.0,
        "low": 49000.0,
        "quote_vol": 123456.0,
    }

    # Same instant shared by both rows, converted once at the boundary.
    assert funding["ts"] == ticker["ts"]


def test_fetch_market_maps_second_symbol():
    market = fetch_market(_stub(), ["BTCUSDT", "ETHUSDT"])

    funding = market["funding"][1]
    ticker = market["tickers"][1]
    assert funding["symbol"] == "ETHUSDT"
    assert funding["funding_rate"] == -0.0002
    assert funding["funding_interval"] == 4
    assert funding["next_funding_time"] == TS_MS + 1000
    assert ticker["last_price"] == 3000.25
    assert ticker["quote_vol"] == 654321.0


@pytest.mark.django_db
def test_persist_market_round_trip():
    market = fetch_market(_stub(), ["BTCUSDT", "ETHUSDT"])
    n_funding, n_tickers = persist_market(market["funding"], market["tickers"])

    assert (n_funding, n_tickers) == (2, 2)
    assert FundingSnapshot.objects.count() == 2
    assert TickerSnapshot.objects.count() == 2

    row = FundingSnapshot.objects.get(symbol="BTCUSDT")
    assert row.funding_rate == 0.0001
    assert row.mark_price == 50001.0
    assert row.index_price == 50000.0
    assert row.funding_interval == 8
    # next_funding_time stays a raw epoch-ms int, never a datetime.
    assert row.next_funding_time == TS_MS
    assert isinstance(row.next_funding_time, int)
    # ts is persisted UTC-aware.
    assert row.ts.tzinfo is not None
    assert row.ts.utcoffset() == timedelta(0)
    assert row.ts == market["funding"][0]["ts"]

    ticker = TickerSnapshot.objects.get(symbol="ETHUSDT")
    assert ticker.last_price == 3000.25
    assert ticker.high == 3100.0
    assert ticker.low == 2900.0


@pytest.mark.django_db
def test_persist_market_twice_is_a_noop():
    market = fetch_market(_stub(), ["BTCUSDT", "ETHUSDT"])

    assert persist_market(market["funding"], market["tickers"]) == (2, 2)
    # Identical rows: the unique (symbol, ts) constraint swallows them.
    assert persist_market(market["funding"], market["tickers"]) == (0, 0)
    assert FundingSnapshot.objects.count() == 2
    assert TickerSnapshot.objects.count() == 2


@pytest.mark.django_db
def test_persist_market_empty_input_is_a_noop():
    assert persist_market([], []) == (0, 0)
    assert FundingSnapshot.objects.count() == 0
    assert TickerSnapshot.objects.count() == 0


@pytest.mark.django_db
def test_fetch_market_empty_symbols_yields_nothing():
    # No symbols requested → the parser emits no rows → nothing persists.
    market = fetch_market(_stub(), [])
    assert market == {"funding": [], "tickers": []}
    assert persist_market(market["funding"], market["tickers"]) == (0, 0)


# --- R3 empty API response: fetch_rows fabricates a default row per symbol; ---
# --- the ingestion layer must drop rows carrying no real market data.       ---


def test_fetch_market_empty_api_response_yields_nothing():
    market = fetch_market(StubClient([], []), ["BTCUSDT", "ETHUSDT"])

    assert market == {"funding": [], "tickers": []}


@pytest.mark.django_db
def test_persist_market_empty_api_response_is_a_noop():
    market = fetch_market(StubClient([], []), ["BTCUSDT", "ETHUSDT"])

    assert persist_market(market["funding"], market["tickers"]) == (0, 0)
    assert FundingSnapshot.objects.count() == 0
    assert TickerSnapshot.objects.count() == 0


def test_fetch_market_keeps_legit_zero_funding_with_present_prices():
    # funding == 0.0 is legitimate; presence of ANY price field must keep the
    # row. This is the over-filtering guard: the skip signal is None prices,
    # never a zero funding rate.
    tickers = [
        {
            "symbol": "BTCUSDT",
            "lastPrice": "50000",
            "high": "51000",
            "low": "49000",
            "quoteVol": "1",
        },
    ]
    funding = [
        {
            "symbol": "BTCUSDT",
            "fundingRate": "0",
            "fundingInterval": "8",
            "nextFundingTime": str(TS_MS),
            "markPrice": "50001",
            "indexPrice": "50000",
        },
    ]

    market = fetch_market(StubClient(tickers, funding), ["BTCUSDT"])

    assert len(market["funding"]) == 1
    assert len(market["tickers"]) == 1
    assert market["funding"][0]["funding_rate"] == 0.0
    assert market["tickers"][0]["last_price"] == 50000.0


def test_fetch_market_keeps_ticker_only_row():
    # No funding payload at all, but a live ticker price → the row survives.
    tickers = [
        {
            "symbol": "BTCUSDT",
            "lastPrice": "50000",
            "high": "51000",
            "low": "49000",
            "quoteVol": "1",
        }
    ]

    market = fetch_market(StubClient(tickers, []), ["BTCUSDT"])

    assert len(market["tickers"]) == 1
    assert market["tickers"][0]["last_price"] == 50000.0
    # funding dict is still emitted for the row (matches 1:1 mapping); its
    # funding_rate defaults to 0.0 because the caller maps every kept row.
    assert len(market["funding"]) == 1


def test_fetch_market_keeps_mark_price_only_row():
    # Only a funding payload with mark/index present → row survives.
    funding = [
        {
            "symbol": "BTCUSDT",
            "fundingRate": "0.0001",
            "fundingInterval": "8",
            "nextFundingTime": str(TS_MS),
            "markPrice": "50001",
            "indexPrice": "50000",
        },
    ]

    market = fetch_market(StubClient([], funding), ["BTCUSDT"])

    assert len(market["funding"]) == 1
    assert market["funding"][0]["mark_price"] == 50001.0


@pytest.mark.django_db
def test_duplicate_symbol_ts_rejected():
    from datetime import datetime

    ts = datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
    FundingSnapshot.objects.create(symbol="BTCUSDT", ts=ts, funding_rate=0.0001)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            FundingSnapshot.objects.create(symbol="BTCUSDT", ts=ts, funding_rate=0.0002)

    TickerSnapshot.objects.create(symbol="BTCUSDT", ts=ts, last_price=50000.0)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            TickerSnapshot.objects.create(symbol="BTCUSDT", ts=ts, last_price=50000.0)


def test_global_snapshots_have_no_owner():
    from django.core.exceptions import FieldDoesNotExist

    for model in (FundingSnapshot, TickerSnapshot):
        assert not issubclass(model, UserOwnedModel)
        with pytest.raises(FieldDoesNotExist):
            model._meta.get_field("user")
