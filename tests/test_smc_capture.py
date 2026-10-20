"""Contract tests for the enriched SMC capture helper (smc-signals R6/R7).

Strict TDD: RED written before implementation. The helper is additive: it
composes the frozen chain exactly as ``get_smc_payload`` does and enriches the
result with the anchor bar time and ATR. ``Setup`` / ``find_setups`` stay
untouched.
"""

from __future__ import annotations

import copy

from src.indicators import atr
from src.smc.config import SMC_ENGINE_VERSION
from src.smc.range import DealingRange, dealing_range
from src.smc.signals import Setup, capture_setups, find_setups
from src.smc.structure import find_structure
from src.smc.swings import find_swings


def test_engine_version_is_a_non_empty_string():
    assert isinstance(SMC_ENGINE_VERSION, str)
    assert SMC_ENGINE_VERSION.strip()


def test_capture_setups_is_callable():
    assert callable(capture_setups)


# --- fixtures -------------------------------------------------------------
# 24-bar zigzag: confirmed swings, one bullish BOS at index 20, one long setup
# with a full score when the range is resolved. Same generator shape as the
# payload fixture in ``test_market_api``.
def _zigzag(peaks, troughs):
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
TIMES = [1_700_000_000 + i * 3600 for i in range(len(ROWS))]


def test_capture_matches_the_frozen_setup_fields():
    # RED: the helper must expose exactly the frozen Setup's fields plus the
    # anchor time and ATR; the chain is the payload's chain.
    frozen = find_setups(
        OPENS,
        HIGHS,
        LOWS,
        CLOSES,
        find_swings(HIGHS, LOWS),
        find_structure(HIGHS, LOWS, CLOSES),
        range_=dealing_range(HIGHS, LOWS),
    )
    assert frozen, "fixture must produce a setup"

    out = capture_setups(OPENS, HIGHS, LOWS, CLOSES, TIMES)

    assert len(out) == len(frozen)
    record = out[0]
    setup = frozen[0]
    assert (
        record.direction,
        record.entry,
        record.stop,
        record.take_profit,
        record.rr,
        record.score,
        record.index,
    ) == (
        setup.direction,
        setup.entry,
        setup.stop,
        setup.take_profit,
        setup.rr,
        setup.score,
        setup.index,
    )


def test_anchor_time_resolves_from_times():
    out = capture_setups(OPENS, HIGHS, LOWS, CLOSES, TIMES)

    assert out[0].anchor_time == TIMES[out[0].index]


def test_atr_is_anchored_at_the_setup_index():
    out = capture_setups(OPENS, HIGHS, LOWS, CLOSES, TIMES)

    expected = atr(HIGHS, LOWS, CLOSES, 14)[out[0].index]
    assert expected is not None
    assert out[0].atr == expected


def test_atr_is_none_inside_the_warm_up():
    # window 100 > 24 bars -> every ATR entry is None.
    out = capture_setups(OPENS, HIGHS, LOWS, CLOSES, TIMES, atr_window=100)

    assert out and out[0].atr is None


def test_range_override_wins_over_the_internal_dealing_range():
    # A range whose high yields rr < min_rr forces the fixed-R fallback in the
    # frozen chain; the helper must pass it through unchanged.
    override = DealingRange(high=110.0, low=100.0, equilibrium=105.0, index=23)
    default = capture_setups(OPENS, HIGHS, LOWS, CLOSES, TIMES)
    custom = capture_setups(OPENS, HIGHS, LOWS, CLOSES, TIMES, range_=override)

    assert default[0].take_profit == 114.5
    assert custom[0].take_profit == 110.0


def test_empty_and_mismatched_ohlc_return_empty():
    assert capture_setups([], [], [], [], []) == []
    assert capture_setups(OPENS, HIGHS, LOWS, CLOSES[:-1], TIMES) == []


def test_mismatched_times_return_empty():
    assert capture_setups(OPENS, HIGHS, LOWS, CLOSES, TIMES[:-1]) == []


def test_no_structure_returns_empty():
    # 8 bars have no confirmed swing pair -> no structure event.
    rows = _zigzag([110], [100])
    assert (
        capture_setups(
            [r[0] for r in rows],
            [r[1] for r in rows],
            [r[2] for r in rows],
            [r[3] for r in rows],
            [i for i in range(len(rows))],
        )
        == []
    )


def test_out_of_bounds_index_skips_the_record(monkeypatch):
    import src.smc.signals as signals

    beyond = Setup("long", 10.0, 9.0, 12.0, 2.0, 3, 999)
    monkeypatch.setattr(signals, "find_setups", lambda *a, **kw: [beyond])

    assert capture_setups(OPENS, HIGHS, LOWS, CLOSES, TIMES) == []


def test_capture_is_deterministic_and_does_not_mutate_inputs():
    first = capture_setups(OPENS, HIGHS, LOWS, CLOSES, TIMES)
    second = capture_setups(OPENS, HIGHS, LOWS, CLOSES, TIMES)
    assert first == second

    opens, highs, lows, closes, times = (
        copy.deepcopy(OPENS),
        copy.deepcopy(HIGHS),
        copy.deepcopy(LOWS),
        copy.deepcopy(CLOSES),
        copy.deepcopy(TIMES),
    )
    capture_setups(opens, highs, lows, closes, times)
    assert (opens, highs, lows, closes, times) == (OPENS, HIGHS, LOWS, CLOSES, TIMES)


def test_capture_record_shape_is_the_frozen_seven_plus_enrichment():
    out = capture_setups(OPENS, HIGHS, LOWS, CLOSES, TIMES)

    assert out[0]._fields == (
        "direction",
        "entry",
        "stop",
        "take_profit",
        "rr",
        "score",
        "index",
        "anchor_time",
        "atr",
    )
