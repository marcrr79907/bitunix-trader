"""R4 contract: worker candle cycle + tick isolation.

``run_once`` must persist closed candles AFTER funding/ticker ingestion, and
any candle failure MUST leave the tick counts and the loop intact. The stub
client serves both the tick/funding endpoints and ``kline``.
"""

from __future__ import annotations

import pytest
import worker
from trading.candles import INTERVAL_SECONDS
from trading.models import Candle, FundingSnapshot, TickerSnapshot

FIXTURE_TICKERS = [
    {
        "symbol": "BTCUSDT",
        "lastPrice": "50000.5",
        "high": "51000",
        "low": "49000",
        "quoteVol": "123456",
    },
]

FIXTURE_FUNDING = [
    {
        "symbol": "BTCUSDT",
        "fundingRate": "0.0001",
        "fundingInterval": "8",
        "nextFundingTime": "1700000000000",
        "markPrice": "50001",
        "indexPrice": "50000",
    },
]

# A closed 1h candle and a forming one, relative to the fixed run instant.
NOW_MS = 1_700_000_000_000
CLOSED_1H = {
    "time": NOW_MS // 1000 - INTERVAL_SECONDS["1h"],
    "open": 1.0,
    "high": 2.0,
    "low": 0.5,
    "close": 1.5,
    "quote_vol": 10.0,
}
FORMING_1H = {
    "time": NOW_MS // 1000 - 60,
    "open": 1.0,
    "high": 2.0,
    "low": 0.5,
    "close": 1.5,
    "quote_vol": 10.0,
}


class StubClient:
    """Serves ticks/funding and kline; optionally raises on kline."""

    def __init__(self, kline_error: Exception | None = None):
        self._kline_error = kline_error

    def tickers(self, symbols=None):
        return FIXTURE_TICKERS

    def funding_rate_batch(self):
        return FIXTURE_FUNDING

    def kline(self, symbol, interval="1m", limit=100, start_time=None, end_time=None):
        if self._kline_error is not None:
            raise self._kline_error
        # Only the 1h series returns rows; the newest is forming.
        if interval == "1h":
            return [FORMING_1H, CLOSED_1H]
        return []


@pytest.fixture(autouse=True)
def _freeze_now(monkeypatch):
    # Deterministic closure without freezing time module-wide in production.
    import trading.candles as candles

    monkeypatch.setattr(candles, "_now_seconds", lambda: NOW_MS // 1000, raising=False)


@pytest.mark.django_db
def test_run_once_persists_closed_candle_and_keeps_tick_counts():
    result = worker.run_once(StubClient(), ["BTCUSDT"])

    assert result == (1, 1)  # existing (funding, ticker) contract preserved
    assert FundingSnapshot.objects.count() == 1
    assert TickerSnapshot.objects.count() == 1
    # Only the closed candle persisted, tagged to its series.
    assert Candle.objects.count() == 1
    row = Candle.objects.get()
    assert row.interval == "1h"
    assert row.time == CLOSED_1H["time"]


@pytest.mark.django_db
def test_run_once_candle_failure_does_not_break_ticks():
    from src.client import BitunixError

    result = worker.run_once(
        StubClient(kline_error=BitunixError(500, "boom")), ["BTCUSDT"]
    )

    # Ticks still persisted; candle failure swallowed.
    assert result == (1, 1)
    assert FundingSnapshot.objects.count() == 1
    assert TickerSnapshot.objects.count() == 1
    assert Candle.objects.count() == 0


@pytest.mark.django_db
def test_run_once_unexpected_candle_error_is_isolated():
    # Broad `except Exception` is deliberate: a candle bug MUST never kill ticks.
    result = worker.run_once(
        StubClient(kline_error=ValueError("unexpected")), ["BTCUSDT"]
    )

    assert result == (1, 1)
    assert TickerSnapshot.objects.count() == 1
    assert Candle.objects.count() == 0


@pytest.mark.django_db
def test_run_loop_survives_candle_failure():
    class SleepRecorder:
        def __init__(self):
            self.calls = []

        def __call__(self, seconds):
            self.calls.append(seconds)

    sleep = SleepRecorder()
    from src.client import BitunixError

    result = worker.run_loop(
        StubClient(kline_error=BitunixError(500, "boom")),
        ["BTCUSDT"],
        iterations=1,
        sleep=sleep,
    )

    assert result == 0
    assert TickerSnapshot.objects.count() == 1
