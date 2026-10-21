"""Contract for the setup capture seam (smc-setup-ledger R5/R6, design D2/D3).

The seam reads only persisted candles (``market.quotes._db_rows``), runs the
pure ``capture_setups`` chain, stamps ``SMC_ENGINE_VERSION`` and persists with
``bulk_create(ignore_conflicts=True)``. Zero network, zero SMC math here.
"""

from __future__ import annotations

import pytest
from trading.candles import CANDLE_INTERVALS
from trading.models import Candle, Setup

from src.indicators import atr
from src.smc.config import SMC_ENGINE_VERSION
from src.smc.signals import capture_setups

pytestmark = pytest.mark.django_db

SYMBOL = "BTCUSDT"
INTERVAL = "1h"
BASE_TIME = 1_700_000_000
HOUR = 3600


def _zigzag(peaks, troughs):
    """24-bar zigzag: one long setup (index 20) with full confluence."""
    seq = []
    for peak, trough in zip(peaks, troughs, strict=True):
        seq.append((peak, "up"))
        seq.append((trough, "down"))
    rows = []
    prev = 100.0
    for price, direction in seq:
        for step in range(4):
            value = prev + (price - prev) * (step / 4)
            high, low = value + 0.5, value - 0.5
            if direction == "down":
                open_, close = high - 0.1, low + 0.1
            else:
                open_, close = low + 0.1, high - 0.1
            rows.append((open_, high, low, close))
        prev = price
    return rows


ROWS = _zigzag([110, 112, 114], [100, 102, 104])
OPENS = [r[0] for r in ROWS]
HIGHS = [r[1] for r in ROWS]
LOWS = [r[2] for r in ROWS]
CLOSES = [r[3] for r in ROWS]
TIMES = [BASE_TIME + i * HOUR for i in range(len(ROWS))]


def _seed(rows=ROWS, times=TIMES, symbol=SYMBOL, interval=INTERVAL):
    Candle.objects.bulk_create(
        [
            Candle(
                symbol=symbol,
                interval=interval,
                time=time,
                open=row[0],
                high=row[1],
                low=row[2],
                close=row[3],
                quote_vol=1.0,
            )
            for row, time in zip(rows, times, strict=True)
        ]
    )


@pytest.fixture
def setups():
    import trading.setups as module

    return module


# --- capture_intervals ----------------------------------------------------


def test_intervals_default_to_1h(setups, monkeypatch):
    monkeypatch.delenv("SETUP_CAPTURE_INTERVALS", raising=False)

    assert setups.capture_intervals() == ("1h",)


def test_intervals_preserve_order_and_dedupe(setups, monkeypatch):
    monkeypatch.setenv("SETUP_CAPTURE_INTERVALS", "1d,1h,1d")

    assert setups.capture_intervals() == ("1d", "1h")


def test_bad_interval_raises_and_names_the_offender(setups, monkeypatch):
    monkeypatch.setenv("SETUP_CAPTURE_INTERVALS", "1h,bogus")

    with pytest.raises(ValueError, match="bogus"):
        setups.capture_intervals()


# --- run_setup_capture ----------------------------------------------------


def test_capture_persists_one_matching_row(setups):
    _seed()

    inserted = setups.run_setup_capture([SYMBOL])

    assert inserted == 1
    record = capture_setups(OPENS, HIGHS, LOWS, CLOSES, TIMES)[0]
    row = Setup.objects.get()
    assert row.symbol == SYMBOL
    assert row.interval == INTERVAL
    assert row.anchor_time == record.anchor_time
    assert row.direction == record.direction
    assert row.entry == record.entry
    assert row.stop == record.stop
    assert row.take_profit == record.take_profit
    assert row.rr == record.rr
    assert row.score == record.score
    assert row.engine_version == SMC_ENGINE_VERSION


def test_capture_is_idempotent(setups):
    _seed()

    assert setups.run_setup_capture([SYMBOL]) == 1
    assert setups.run_setup_capture([SYMBOL]) == 0
    assert Setup.objects.count() == 1


def test_capture_stores_atr_at_the_anchor(setups):
    _seed()

    setups.run_setup_capture([SYMBOL])

    record = capture_setups(OPENS, HIGHS, LOWS, CLOSES, TIMES)[0]
    assert Setup.objects.get().atr == atr(HIGHS, LOWS, CLOSES, 14)[record.index]


def test_version_bump_inserts_a_new_row_and_keeps_the_old(setups, monkeypatch):
    _seed()
    assert setups.run_setup_capture([SYMBOL]) == 1

    monkeypatch.setattr(setups, "SMC_ENGINE_VERSION", "2")
    assert setups.run_setup_capture([SYMBOL]) == 1

    versions = sorted(Setup.objects.values_list("engine_version", flat=True))
    assert versions == ["1", "2"]


def test_thin_window_inserts_nothing_and_does_not_raise(setups):
    _seed(rows=ROWS[:2], times=TIMES[:2])

    assert setups.run_setup_capture([SYMBOL]) == 0
    assert Setup.objects.count() == 0


def test_no_candles_inserts_nothing_and_does_not_raise(setups):
    assert setups.run_setup_capture([SYMBOL]) == 0
    assert Setup.objects.count() == 0


def test_capture_reads_only_persisted_candles_no_network(setups, monkeypatch):
    import market.quotes as quotes

    class _NoNetwork:
        def __init__(self, *args, **kwargs):
            raise AssertionError("capture must not construct a client")

        def __getattr__(self, name):
            raise AssertionError(f"capture must not call client.{name}")

    def _no_network(*args, **kwargs):
        raise AssertionError("capture must not fetch upstream")

    monkeypatch.setattr("src.client.BitunixClient", _NoNetwork)
    monkeypatch.setattr(quotes, "_fetch_window", _no_network)
    _seed()

    assert setups.run_setup_capture([SYMBOL]) == 1


def test_capture_uses_configured_intervals(setups, monkeypatch):
    # Only 1d is configured: a 1h-only window must yield nothing.
    monkeypatch.setenv("SETUP_CAPTURE_INTERVALS", "1d")
    _seed()

    assert setups.run_setup_capture([SYMBOL]) == 0
    assert Setup.objects.count() == 0


def test_default_capture_interval_is_a_persisted_candle_interval(setups):
    # Guards the contract, not the constant: whatever DEFAULT_CAPTURE_INTERVALS
    # says, every entry must be an interval the worker actually persists.
    assert set(setups.DEFAULT_CAPTURE_INTERVALS) <= set(CANDLE_INTERVALS)


def test_bad_intervals_names_every_offender(setups, monkeypatch):
    monkeypatch.setenv("SETUP_CAPTURE_INTERVALS", "bogus,xx,1h")
    with pytest.raises(ValueError) as excinfo:
        setups.capture_intervals()

    message = str(excinfo.value)
    assert "bogus" in message
    assert "xx" in message
