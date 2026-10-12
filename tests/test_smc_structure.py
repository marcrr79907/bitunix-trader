"""Contract tests for src/smc/structure.py — labels, trend, BOS/CHoCH.

Strict TDD: RED written before implementation. Fixtures are synthetic OHLC
series with hand-traced expectations against the frozen state machine in
design.md. Pure: repeatable, non-mutating, never raises.
"""

from src.smc.structure import (
    LabeledSwing,
    StructureEvent,
    find_structure,
    label_swings,
    trend_state,
)
from src.smc.swings import Swing

# --- fixtures: (highs, lows, closes), left=right=1 ----------------------
# BULL_BOS: seed silently at t=6 (close 9 > H0=8); pivot H1=10@6 confirms at
# t=7; close 11 > 10 at t=10 -> bullish BOS at level 10.
BULL_BOS = (
    [4, 8, 5, 3, 6, 9, 10, 7, 5, 8, 12, 9, 7],
    [1, 3, 2, 0, 2, 5, 6, 3, 2, 4, 8, 5, 4],
    [3, 7, 3, 1, 5, 8, 9, 4, 4, 7, 11, 6, 5],
)
# Same series truncated just after the seed bar -> no event, only seeding.
BULL_SEED = tuple(v[:9] for v in BULL_BOS)
# BULL_CHOCH: bullish BOS at t=10, then new low pivot 2@13 confirms at t=14;
# close 0 < 2 at t=16 -> bearish CHoCH at level 2, trend flips to down.
BULL_CHOCH = (
    [4, 8, 5, 3, 6, 9, 10, 7, 5, 8, 12, 9, 7, 2, 3, 4, 1],
    [1, 3, 2, 0, 2, 5, 6, 3, 2, 4, 8, 5, 4, 0, 1, 2, 1],
    [3, 7, 3, 1, 5, 8, 9, 4, 4, 7, 11, 6, 5, 1, 2, 3, 0],
)
# R7: after the first BOS at level 10, a NEW swing high 12@10 confirms at
# t=11 and a close 14 > 12 at t=16 emits a second BOS (level advanced).
R7_TWO_BOS = (
    [4, 8, 5, 3, 6, 9, 10, 7, 5, 8, 12, 9, 7, 6, 9, 14, 15, 10, 8],
    [1, 3, 2, 0, 2, 5, 6, 3, 2, 4, 8, 5, 4, 3, 5, 9, 10, 6, 5],
    [3, 7, 3, 1, 5, 8, 9, 4, 4, 7, 11, 6, 5, 4, 7, 12, 14, 8, 6],
)
# Close-vs-wick: breakout bar 10 wicks to 12 (> H=10) but closes at 9 (< 10).
CLOSE_WICK = (
    [4, 8, 5, 3, 6, 9, 10, 7, 5, 8, 12, 9, 7],
    [1, 3, 2, 0, 2, 5, 6, 3, 2, 4, 8, 5, 4],
    [3, 7, 3, 1, 5, 8, 9, 4, 4, 7, 9, 6, 5],
)


def _mirror(bundle):
    """Flip a bull fixture into its exact bear mirror.

    Negating prices turns highs into lows and vice versa, so the high and low
    series swap roles; closes merely negate.
    """
    highs, lows, closes = bundle
    return ([-v for v in lows], [-v for v in highs], [-v for v in closes])


# --- find_structure: BOS -------------------------------------------------

BULL_BOS_EVENTS = [StructureEvent("bos", 10, 10, "bullish", "up")]


def test_find_structure_bullish_bos():
    highs, lows, closes = BULL_BOS
    assert find_structure(highs, lows, closes, left=1, right=1) == BULL_BOS_EVENTS


def test_find_structure_bearish_bos():
    highs, lows, closes = _mirror(BULL_BOS)
    assert find_structure(highs, lows, closes, left=1, right=1) == [
        StructureEvent("bos", 10, -10, "bearish", "down")
    ]


# --- find_structure: seeding (R8) ---------------------------------------


def test_find_structure_first_break_seeds_silently():
    highs, lows, closes = BULL_SEED
    assert find_structure(highs, lows, closes, left=1, right=1) == []


# --- find_structure: CHoCH (R6) -----------------------------------------


def test_find_structure_bearish_choch_after_up_trend():
    highs, lows, closes = BULL_CHOCH
    assert find_structure(highs, lows, closes, left=1, right=1) == [
        StructureEvent("bos", 10, 10, "bullish", "up"),
        StructureEvent("choch", 13, 2, "bearish", "down"),
    ]


def test_find_structure_bullish_choch_after_down_trend():
    highs, lows, closes = _mirror(BULL_CHOCH)
    assert find_structure(highs, lows, closes, left=1, right=1) == [
        StructureEvent("bos", 10, -10, "bearish", "down"),
        StructureEvent("choch", 13, -2, "bullish", "up"),
    ]


# --- find_structure: level re-arm (R7) ----------------------------------
# Note: the CHoCH above also proves no re-fire at t=14/15/16 beyond the
# updated level (armed_low consumed at t=13, re-armed only by the new pivot).
R7_EVENTS = [
    StructureEvent("bos", 10, 10, "bullish", "up"),
    StructureEvent("bos", 16, 12, "bullish", "up"),
]


def test_find_structure_level_advances_to_new_swing():
    highs, lows, closes = R7_TWO_BOS
    assert find_structure(highs, lows, closes, left=1, right=1) == R7_EVENTS


def test_find_structure_does_not_refire_same_level():
    # Truncate at t=11: the first BOS fired at t=10 and the consumed level
    # must not re-fire in the two bars that follow.
    highs, lows, closes = (v[:12] for v in R7_TWO_BOS)
    assert find_structure(highs, lows, closes, left=1, right=1) == [R7_EVENTS[0]]


# --- find_structure: close vs wick (R5) ---------------------------------


def test_find_structure_close_break_by_default():
    highs, lows, closes = CLOSE_WICK
    assert find_structure(highs, lows, closes, left=1, right=1) == []


def test_find_structure_wick_break_when_use_close_false():
    highs, lows, closes = CLOSE_WICK
    assert find_structure(highs, lows, closes, left=1, right=1, use_close=False) == (
        BULL_BOS_EVENTS
    )


# --- find_structure: guard rails (R8/R11) -------------------------------


def test_find_structure_needs_both_a_high_and_a_low_pivot():
    # High pivot at index 1; lows strictly rising -> no low pivot -> [].
    highs = [1, 5, 1, 2, 3, 4, 5, 6]
    lows = [0, 1, 2, 3, 4, 5, 6, 7]
    closes = [2, 4, 2, 4, 5, 6, 7, 8]
    assert find_structure(highs, lows, closes, left=1, right=1) == []


def test_find_structure_low_only_returns_empty():
    # Low pivot at index 1; highs strictly falling -> no high pivot -> [].
    highs = [7, 6, 5, 4, 3, 2, 1, 0]
    lows = [4, 1, 4, 3, 2, 1, 0, -1]
    closes = [5, 2, 5, 4, 3, 2, 1, 0]
    assert find_structure(highs, lows, closes, left=1, right=1) == []


def test_find_structure_empty_returns_empty():
    assert find_structure([], [], [], left=1, right=1) == []


def test_find_structure_mismatched_closes_returns_empty():
    highs, lows, _ = BULL_BOS
    assert find_structure(highs, lows, highs[:-1], left=1, right=1) == []


def test_find_structure_is_deterministic_and_non_mutating():
    highs, lows, closes = BULL_CHOCH
    first = find_structure(highs, lows, closes, left=1, right=1)
    second = find_structure(highs, lows, closes, left=1, right=1)
    assert first == second
    assert highs == BULL_CHOCH[0]
    assert lows == BULL_CHOCH[1]
    assert closes == BULL_CHOCH[2]


# --- label_swings (R3) --------------------------------------------------

LABEL_SWINGS = [
    Swing("high", 0, 5.0),
    Swing("low", 1, 1.0),
    Swing("high", 2, 6.0),
    Swing("low", 3, 2.0),
    Swing("high", 4, 4.0),
    Swing("low", 5, 0.0),
]


def test_label_swings_omits_first_of_each_kind_and_labels_rest():
    assert label_swings(LABEL_SWINGS) == [
        LabeledSwing("high", 2, 6.0, "HH"),
        LabeledSwing("low", 3, 2.0, "HL"),
        LabeledSwing("high", 4, 4.0, "LH"),
        LabeledSwing("low", 5, 0.0, "LL"),
    ]


def test_label_swings_single_swing_per_kind_is_omitted():
    assert label_swings([Swing("high", 0, 5.0), Swing("low", 1, 1.0)]) == []


def test_label_swings_empty_returns_empty():
    assert label_swings([]) == []


def test_label_swings_does_not_mutate_input():
    swings = list(LABEL_SWINGS)
    label_swings(swings)
    assert swings == LABEL_SWINGS


# --- trend_state (R4) ---------------------------------------------------


def test_trend_state_transitions_none_up_range_down():
    labeled = label_swings(LABEL_SWINGS)
    assert trend_state(labeled) == [None, "up", "range", "down"]


def test_trend_state_none_until_both_sides_known():
    assert trend_state([LabeledSwing("high", 0, 6.0, "HH")]) == [None]


def test_trend_state_empty_returns_empty():
    assert trend_state([]) == []
