"""R4 contract: closure rule + closed-candle fetch/persist seam.

``is_closed`` is pure (wall clock passed in), the fetch keeps only candles whose
bucket fully elapsed, and persist is idempotent. No sockets: the client is a
stub returning mapped candles, and ``now`` is fixed.
"""

from __future__ import annotations

import pytest
from trading.candles import (
    CANDLE_INTERVALS,
    INTERVAL_SECONDS,
    fetch_closed_candles,
    is_closed,
    persist_candles,
)
from trading.models import Candle

NOW = 1_700_000_000  # fixed epoch-seconds


@pytest.mark.parametrize("interval", CANDLE_INTERVALS)
def test_is_closed_boundary_per_interval(interval):
    span = INTERVAL_SECONDS[interval]

    assert is_closed(NOW - span, interval, NOW) is True  # bucket ended exactly now
    assert is_closed(NOW - span + 1, interval, NOW) is False  # one second early


def test_one_month_uses_31_days():
    # Design pins 1M to the longest month so a partial monthly candle is never
    # persisted; 30d would wrongly close a 31-day month early.
    assert INTERVAL_SECONDS["1M"] == 2678400
    thirty_days = 30 * 86400
    assert is_closed(NOW - thirty_days, "1M", NOW) is False
    assert is_closed(NOW - 2678400, "1M", NOW) is True


def test_candle_intervals_is_all_eight_and_excludes_1m():
    assert set(CANDLE_INTERVALS) == {
        "5m",
        "15m",
        "1h",
        "2h",
        "4h",
        "1d",
        "1w",
        "1M",
    }
    assert "1m" not in CANDLE_INTERVALS


class StubClient:
    def __init__(self, rows_by_interval):
        self._rows_by_interval = rows_by_interval
        self.calls: list[tuple] = []

    def kline(self, symbol, interval="1m", limit=100, start_time=None, end_time=None):
        self.calls.append((symbol, interval, limit))
        return self._rows_by_interval.get(interval, [])


def test_fetch_closed_candles_drops_forming_and_tags_series():
    closed = {
        "time": NOW - 3600,
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": 1.5,
        "quote_vol": 10.0,
    }
    forming = {
        "time": NOW - 10,
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": 1.5,
        "quote_vol": 10.0,
    }
    client = StubClient({"1h": [forming, closed]})  # newest first, as the API returns

    result = fetch_closed_candles(client, ["BTCUSDT"], now=NOW)

    # only the 1h series has rows; the forming candle is dropped
    assert len(result) == 1
    assert result[0]["time"] == NOW - 3600
    assert result[0]["symbol"] == "BTCUSDT"
    assert result[0]["interval"] == "1h"


def test_fetch_closed_candles_queries_limit_2_every_interval():
    client = StubClient({})

    fetch_closed_candles(client, ["BTCUSDT", "ETHUSDT"], now=NOW)

    assert len(client.calls) == 2 * len(CANDLE_INTERVALS)
    assert all(call[2] == 2 for call in client.calls)


@pytest.mark.django_db
def test_persist_candles_idempotent():
    rows = [
        {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "time": NOW - 3600,
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "quote_vol": 10.0,
        }
    ]

    assert persist_candles(rows) == 1
    assert persist_candles(rows) == 0  # unique (symbol, interval, time)
    assert Candle.objects.count() == 1


@pytest.mark.django_db
def test_persist_candles_empty_is_noop():
    assert persist_candles([]) == 0
    assert Candle.objects.count() == 0
