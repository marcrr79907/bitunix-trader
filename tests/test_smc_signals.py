"""Contract tests for src/smc/signals.py — confluence scoring + Setup derivation.

Strict TDD: RED written before implementation. Fixtures are synthetic OHLC
series with hand-traced expectations against the frozen rules in
``specs/smc-signals/spec.md`` and ``design.md``. Pure: repeatable,
non-mutating, never raises.
"""

from __future__ import annotations

import copy

from src.smc.range import DealingRange
from src.smc.signals import Setup, find_setups
from src.smc.structure import StructureEvent
from tests.smc_fixtures import OB_BULL, OB_NONE_BULL, mirror_ohlc

# --- fixtures ------------------------------------------------------------
# Full-confluence LONG bundle (opens, highs, lows, closes):
#   - bullish BOS at bar 7; the OB candle is the bearish bar 5
#     (open 110, high 110, low 100, close 105) -> zone [bottom 100, top 110].
#   - bullish FVGs at bars 1 and 6.
FULL_LONG = (
    [100.0, 101.0, 103.0, 105.0, 107.0, 110.0, 105.0, 112.0],
    [102.0, 103.0, 106.0, 108.0, 112.0, 110.0, 115.0, 118.0],
    [99.0, 100.0, 104.0, 103.0, 105.0, 100.0, 104.0, 111.0],
    [101.0, 102.0, 105.0, 107.0, 109.0, 105.0, 112.0, 117.0],
)
FULL_LONG_BOS = [StructureEvent("bos", 7, 112.0, "bullish", "up")]

# close 117 < equilibrium 125 -> discount -> PD component aligned.
RANGE_DISCOUNT = DealingRange(high=150.0, low=100.0, equilibrium=125.0, index=7)
# close 117 > equilibrium 115 -> premium -> PD component NOT aligned.
RANGE_PREMIUM = DealingRange(high=150.0, low=80.0, equilibrium=115.0, index=7)
# structural high 120 yields rr 1.0 < min_rr -> fixed-R fallback target.
RANGE_LOW_TP = DealingRange(high=120.0, low=100.0, equilibrium=110.0, index=7)

# Exact bear mirror of FULL_LONG / RANGE_DISCOUNT / the BOS event.
FULL_SHORT = mirror_ohlc(FULL_LONG)
FULL_SHORT_BOS = [StructureEvent("bos", 7, -112.0, "bearish", "down")]
RANGE_SHORT = DealingRange(high=-100.0, low=-150.0, equilibrium=-125.0, index=7)

# No OB anywhere (every candle is bullish), only a bullish FVG at bar 1.
FVG_ONLY_LONG = (
    [10.0, 10.5, 13.0],
    [11.0, 12.0, 15.0],
    [9.5, 10.2, 13.0],
    [10.5, 11.5, 14.0],
)
FVG_ONLY_BOS = [StructureEvent("bos", 2, 11.0, "bullish", "up")]
FVG_ONLY_RANGE = DealingRange(high=100.0, low=0.0, equilibrium=50.0, index=2)

# 14 bars: one bullish FVG at bars 1-2, then only bullish bars (no OB), and a
# BOS anchored at bar 13 -> every zone is older than OB_LOOKBACK (10).
STALE_LONG = (
    [
        10.0,
        10.5,
        13.0,
        14.0,
        15.0,
        16.0,
        17.0,
        18.0,
        19.0,
        20.0,
        21.0,
        22.0,
        23.0,
        24.0,
    ],
    [
        11.0,
        12.0,
        15.0,
        16.0,
        17.0,
        18.0,
        19.0,
        20.0,
        21.0,
        22.0,
        23.0,
        24.0,
        25.0,
        26.0,
    ],
    [9.5, 10.2, 13.0, 13.5, 14.5, 15.5, 16.5, 17.5, 18.5, 19.5, 20.5, 21.5, 22.5, 23.5],
    [
        10.5,
        11.5,
        14.0,
        15.0,
        16.0,
        17.0,
        18.0,
        19.0,
        20.0,
        21.0,
        22.0,
        23.0,
        24.0,
        25.0,
    ],
)
STALE_BOS = [StructureEvent("bos", 13, 25.0, "bullish", "up")]


# --- R2: confluence score / gate -----------------------------------------


def test_find_setups_full_confluence_long_scores_four():
    out = find_setups(*FULL_LONG, [], FULL_LONG_BOS, range_=RANGE_DISCOUNT)
    assert out == [Setup("long", 110.0, 100.0, 150.0, 4.0, 4, 7)]


def test_find_setups_missing_pd_component_drops_score_to_three():
    # Same zones, but price is in premium -> the PD component is 0.
    out = find_setups(*FULL_LONG, [], FULL_LONG_BOS, range_=RANGE_PREMIUM)
    assert out == [Setup("long", 110.0, 100.0, 150.0, 4.0, 3, 7)]


def test_find_setups_below_min_confluence_is_suppressed():
    # OB_BULL: bullish BOS + OB, no FVG, price in premium -> score 2 < 3.
    opens, highs, lows, closes = OB_BULL
    bos = [StructureEvent("bos", 5, 14.0, "bullish", "up")]
    premium = DealingRange(high=20.0, low=10.0, equilibrium=13.0, index=5)
    assert find_setups(opens, highs, lows, closes, [], bos, range_=premium) == []


def test_find_setups_at_threshold_emits_using_same_fixture():
    # Companion to the suppression test: identical zones, price in discount
    # -> score 3 -> emitted with the fixed-R target.
    opens, highs, lows, closes = OB_BULL
    bos = [StructureEvent("bos", 5, 14.0, "bullish", "up")]
    discount = DealingRange(high=20.0, low=10.0, equilibrium=15.0, index=5)
    out = find_setups(opens, highs, lows, closes, [], bos, range_=discount)
    assert out == [Setup("long", 14.0, 9.0, 29.0, 3.0, 3, 5)]


def test_find_setups_no_entry_zone_returns_empty():
    # OB_NONE_BULL: all bullish candles -> no OB; and no FVG -> no zone.
    opens, highs, lows, closes = OB_NONE_BULL
    bos = [StructureEvent("bos", 5, 14.0, "bullish", "up")]
    assert find_setups(opens, highs, lows, closes, [], bos) == []


# --- R3: entry / stop / take-profit derivation ---------------------------


def test_find_setups_structural_target_clears_the_gate():
    out = find_setups(*FULL_LONG, [], FULL_LONG_BOS, range_=RANGE_DISCOUNT)
    assert out[0].take_profit == 150.0  # range_.high, not the fallback
    assert out[0].rr == 4.0


def test_find_setups_falls_back_to_fixed_r_when_structural_rr_too_low():
    # range_.high 120 -> rr 1.0 < 2.0 -> fallback entry + 3 * (entry - stop).
    out = find_setups(*FULL_LONG, [], FULL_LONG_BOS, range_=RANGE_LOW_TP)
    assert out == [Setup("long", 110.0, 100.0, 140.0, 3.0, 3, 7)]


def test_find_setups_without_range_uses_fixed_r_fallback():
    out = find_setups(*FULL_LONG, [], FULL_LONG_BOS, range_=None)
    assert out == [Setup("long", 110.0, 100.0, 140.0, 3.0, 3, 7)]


def test_find_setups_rr_below_gate_is_suppressed():
    # Fixed-R rr is 3.0; a min_rr of 4.0 must suppress it.
    assert find_setups(*FULL_LONG, [], FULL_LONG_BOS, min_rr=4.0) == []
    # Companion: at min_rr 3.0 the same candidate clears the gate.
    out = find_setups(*FULL_LONG, [], FULL_LONG_BOS, min_rr=3.0)
    assert out == [Setup("long", 110.0, 100.0, 140.0, 3.0, 3, 7)]


def test_find_setups_degenerate_entry_equals_stop_is_skipped():
    # sl_buffer chosen so bottom - sl_buffer == top (100 - (-10) == 110).
    assert find_setups(*FULL_LONG, [], FULL_LONG_BOS, sl_buffer=-10.0) == []


# --- direction, fallback zone, recency ------------------------------------


def test_find_setups_bearish_mirror_scores_four():
    out = find_setups(*FULL_SHORT, [], FULL_SHORT_BOS, range_=RANGE_SHORT)
    assert out == [Setup("short", -110.0, -100.0, -150.0, 4.0, 4, 7)]


def test_find_setups_direction_follows_the_latest_event():
    # A bullish event followed by a bearish one -> the candidate is short.
    mixed = [
        StructureEvent("bos", 1, -99.0, "bullish", "up"),
        StructureEvent("bos", 7, -112.0, "bearish", "down"),
    ]
    out = find_setups(*FULL_SHORT, [], mixed, range_=RANGE_SHORT)
    assert out == [Setup("short", -110.0, -100.0, -150.0, 4.0, 4, 7)]


def test_find_setups_uses_fvg_when_no_order_block_exists():
    # No OB (all bullish) -> the bullish FVG provides the entry zone. The
    # entry/stop follow the frozen pseudo-code (`entry = zone.top`); for a
    # bullish FVG the field assignment puts `top` below `bottom`.
    out = find_setups(*FVG_ONLY_LONG, [], FVG_ONLY_BOS, range_=FVG_ONLY_RANGE)
    assert out == [Setup("long", 11.0, 13.0, 5.0, 3.0, 3, 2)]


def test_find_setups_stale_zones_outside_lookback_are_ignored():
    assert find_setups(*STALE_LONG, [], STALE_BOS) == []


# --- R1/R5: never-raise, purity, output shape -----------------------------


def test_find_setups_no_structure_event_returns_empty():
    assert find_setups(*FULL_LONG, [], []) == []


def test_find_setups_empty_and_mismatched_return_empty():
    assert find_setups([], [], [], [], [], []) == []
    opens, highs, lows, closes = FULL_LONG
    assert find_setups(opens, highs, lows, closes[:-1], [], FULL_LONG_BOS) == []


def test_find_setups_is_deterministic_and_does_not_mutate_inputs():
    assert find_setups(*FULL_LONG, [], FULL_LONG_BOS, range_=RANGE_DISCOUNT) == (
        find_setups(*FULL_LONG, [], FULL_LONG_BOS, range_=RANGE_DISCOUNT)
    )

    opens, highs, lows, closes = copy.deepcopy(FULL_LONG)
    structure = copy.deepcopy(FULL_LONG_BOS)
    find_setups(opens, highs, lows, closes, [], structure, range_=RANGE_DISCOUNT)
    assert [opens, highs, lows, closes] == list(FULL_LONG)
    assert structure == FULL_LONG_BOS


def test_find_setups_output_unpacks_as_the_frozen_seven_tuple():
    out = find_setups(*FULL_LONG, [], FULL_LONG_BOS, range_=RANGE_DISCOUNT)
    assert len(out) == 1
    assert isinstance(out[0], tuple)
    direction, entry, stop, take_profit, rr, score, index = out[0]
    assert (direction, entry, stop, take_profit, rr, score, index) == (
        "long",
        110.0,
        100.0,
        150.0,
        4.0,
        4,
        7,
    )
    assert [s.index for s in out] == sorted(s.index for s in out)
