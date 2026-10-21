"""Contract for the isolated setup-capture worker step (smc-setup-ledger R6).

Capture runs AFTER the candle cycle and in its OWN ``try``: a failure (including
a bad ``SETUP_CAPTURE_INTERVALS`` parsed at import time) is logged and leaves
funding, ticker, candles, private sync and alerts untouched. The ``run_once``
return contract stays ``(funding, ticker)``.
"""

from __future__ import annotations

import logging

import pytest
import worker
from trading.candles import INTERVAL_SECONDS
from trading.models import Candle, FundingSnapshot, Setup, TickerSnapshot

pytestmark = pytest.mark.django_db

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

NOW_SECONDS = 1_700_000_000
CLOSED_1H = {
    "time": NOW_SECONDS - INTERVAL_SECONDS["1h"],
    "open": 1.0,
    "high": 2.0,
    "low": 0.5,
    "close": 1.5,
    "quote_vol": 10.0,
}


class StubClient:
    def tickers(self, symbols=None):
        return FIXTURE_TICKERS

    def funding_rate_batch(self):
        return FIXTURE_FUNDING

    def kline(self, symbol, interval="1m", limit=100, start_time=None, end_time=None):
        return [CLOSED_1H] if interval == "1h" else []


@pytest.fixture(autouse=True)
def _fixed_cycle(monkeypatch):
    import trading.candles as candles

    monkeypatch.setattr(candles, "_now_seconds", lambda: NOW_SECONDS)
    monkeypatch.setattr(worker, "_last_poll", None, raising=False)
    monkeypatch.delenv("SETUP_CAPTURE_INTERVALS", raising=False)


def test_capture_runs_after_the_candle_cycle(monkeypatch):
    seen = {}
    import trading.setups as setups

    def _record_after_candles(*args, **kwargs):
        # The capture step is only reached once the candle cycle persisted.
        seen["candles"] = Candle.objects.count()
        return 0

    monkeypatch.setattr(setups, "run_setup_capture", _record_after_candles)

    worker.run_once(StubClient(), ["BTCUSDT"])

    assert seen["candles"] == 1


def test_capture_failure_leaves_every_other_step_intact(monkeypatch, caplog):
    import trading.setups as setups

    def _boom(symbols):
        raise RuntimeError("capture exploded")

    monkeypatch.setattr(setups, "run_setup_capture", _boom)
    caplog.set_level(logging.WARNING)

    result = worker.run_once(StubClient(), ["BTCUSDT"])

    assert result == (1, 1)  # return contract unchanged
    assert FundingSnapshot.objects.count() == 1
    assert TickerSnapshot.objects.count() == 1
    assert Candle.objects.count() == 1
    assert Setup.objects.count() == 0
    assert "setup capture failed: capture exploded" in caplog.text


def test_bad_intervals_config_disables_capture_without_touching_ingestion(
    monkeypatch, caplog
):
    monkeypatch.setenv("SETUP_CAPTURE_INTERVALS", "1h,bogus")
    caplog.set_level(logging.WARNING)

    result = worker.run_once(StubClient(), ["BTCUSDT"])

    assert result == (1, 1)
    assert FundingSnapshot.objects.count() == 1
    assert TickerSnapshot.objects.count() == 1
    assert Candle.objects.count() == 1
    assert Setup.objects.count() == 0
    assert "setup capture failed:" in caplog.text
    assert "bogus" in caplog.text
