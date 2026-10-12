"""Contract tests for src/smc/zones.py — OB, FVG, EQH/EQL, sweeps.

Strict TDD: RED written before implementation. Fixtures are synthetic OHLC
series with hand-traced expectations against the frozen rules in spec.md /
design.md. Pure: repeatable, non-mutating, never raises.
"""

from src.smc.structure import StructureEvent
from src.smc.swings import Swing
from src.smc.zones import (
    FVG,
    EqualLevel,
    OrderBlock,
    Sweep,
    find_equal_highs_lows,
    find_fvg,
    find_liquidity_sweeps,
    find_order_blocks,
)
from tests.smc_fixtures import (
    FVG_BEAR_HIGHS,
    FVG_BEAR_LOWS,
    FVG_BULL_HIGHS,
    FVG_BULL_LOWS,
    FVG_SMALL_HIGHS,
    FVG_SMALL_LOWS,
    OB_BULL,
    OB_DOJI,
    OB_FAR,
    OB_NONE_BULL,
    SWEEP_HIGH_CLOSES,
    SWEEP_HIGH_HIGHS,
    SWEEP_HIGH_LOWS,
    SWEEP_LOW_CLOSES,
    SWEEP_LOW_HIGHS,
    SWEEP_LOW_LOWS,
    mirror_ohlc,
)

# --- order blocks (R1) ---------------------------------------------------

BULL_BOS = [StructureEvent("bos", 5, 14.0, "bullish", "up")]
BEAR_BOS = [StructureEvent("bos", 5, -14.0, "bearish", "down")]


def test_find_order_blocks_bullish_picks_most_recent_opposite_candle():
    opens, highs, lows, closes = OB_BULL
    assert find_order_blocks(opens, highs, lows, closes, BULL_BOS) == [
        OrderBlock("bullish", 4, top=14.0, bottom=9.0, anchor=5)
    ]


def test_find_order_blocks_bearish_mirrors():
    opens, highs, lows, closes = mirror_ohlc(OB_BULL)
    assert find_order_blocks(opens, highs, lows, closes, BEAR_BOS) == [
        OrderBlock("bearish", 4, top=-9.0, bottom=-14.0, anchor=5)
    ]


def test_find_order_blocks_choch_is_not_an_anchor():
    opens, highs, lows, closes = OB_BULL
    choch = [StructureEvent("choch", 5, 14.0, "bullish", "up")]
    assert find_order_blocks(opens, highs, lows, closes, choch) == []


def test_find_order_blocks_no_opposite_candle_returns_empty():
    opens, highs, lows, closes = OB_NONE_BULL
    assert find_order_blocks(opens, highs, lows, closes, BULL_BOS) == []


def test_find_order_blocks_respects_lookback_window():
    opens, highs, lows, closes = OB_FAR
    b = [StructureEvent("bos", 5, 15.0, "bullish", "up")]
    assert find_order_blocks(opens, highs, lows, closes, b, lookback=3) == []
    assert find_order_blocks(opens, highs, lows, closes, b, lookback=6) == [
        OrderBlock("bullish", 0, top=13.0, bottom=9.0, anchor=5)
    ]


def test_find_order_blocks_doji_is_neither_direction_and_is_skipped():
    opens, highs, lows, closes = OB_DOJI
    b = [StructureEvent("bos", 2, 15.0, "bullish", "up")]
    assert find_order_blocks(opens, highs, lows, closes, b) == [
        OrderBlock("bullish", 0, top=12.0, bottom=8.0, anchor=2)
    ]


def test_find_order_blocks_empty_and_mismatched_return_empty():
    assert find_order_blocks([], [], [], [], BULL_BOS) == []
    opens, highs, lows, closes = OB_BULL
    assert find_order_blocks(opens, highs, lows, closes[:-1], BULL_BOS) == []


def test_find_order_blocks_is_ordered_by_index():
    # Two BOS anchors, each finding its own opposite candle -> ordered by index.
    opens = [10, 12, 11, 10, 13, 13, 12, 15]
    highs = [12, 13, 13, 12, 14, 15, 14, 16]
    lows = [9, 9, 8, 7, 9, 10, 8, 11]
    closes = [11, 10, 12, 11, 10, 14, 13, 15]
    events = [
        StructureEvent("bos", 5, 14.0, "bullish", "up"),
        StructureEvent("bos", 7, 15.0, "bullish", "up"),
    ]
    out = find_order_blocks(opens, highs, lows, closes, events)
    assert [ob.index for ob in out] == sorted(ob.index for ob in out)


# --- fair value gaps (R2) ------------------------------------------------


def test_find_fvg_bullish():
    assert find_fvg(FVG_BULL_HIGHS, FVG_BULL_LOWS) == [
        FVG("bullish", 1, top=11.0, bottom=10.0)
    ]


def test_find_fvg_bearish():
    assert find_fvg(FVG_BEAR_HIGHS, FVG_BEAR_LOWS) == [
        FVG("bearish", 1, top=13.0, bottom=8.0)
    ]


def test_find_fvg_gap_below_min_gap_is_skipped():
    assert find_fvg(FVG_SMALL_HIGHS, FVG_SMALL_LOWS, min_gap=0.5) == []


def test_find_fvg_overlapping_candles_are_not_a_gap():
    # highs[0]=10 >= lows[2]=9 and lows[0]=8 <= highs[2]=11 -> neither kind.
    assert find_fvg([10.0, 10.0, 11.0], [8.0, 8.0, 9.0]) == []


def test_find_fvg_short_and_mismatched_returns_empty():
    assert find_fvg([10.0, 11.0], [8.0, 9.0]) == []
    assert find_fvg(FVG_BULL_HIGHS, FVG_BULL_LOWS[:-1]) == []


def test_find_fvg_empty_returns_empty():
    assert find_fvg([], []) == []


# --- equal highs / lows (R3) ---------------------------------------------

SWINGS_EQH = [
    Swing("high", 1, 100.0),
    Swing("low", 3, 90.0),
    Swing("high", 5, 100.2),
]
SWINGS_EQL = [
    Swing("high", 1, 110.0),
    Swing("low", 3, 90.0),
    Swing("low", 7, 90.1),
]
SWINGS_NOT_CONSECUTIVE = [
    Swing("high", 0, 5.0),
    Swing("low", 1, 1.0),
    Swing("high", 2, 6.0),
]


def test_find_equal_highs_within_tolerance():
    assert find_equal_highs_lows(SWINGS_EQH, tolerance=0.5) == [
        EqualLevel("eqh", 5, 100.2, twin=1)
    ]


def test_find_equal_lows_within_tolerance():
    assert find_equal_highs_lows(SWINGS_EQL, tolerance=0.5) == [
        EqualLevel("eql", 7, 90.1, twin=3)
    ]


def test_find_equal_highs_zero_tolerance_requires_exact():
    assert find_equal_highs_lows(SWINGS_EQH, tolerance=0.0) == []


def test_find_equal_highs_non_consecutive_not_paired():
    assert find_equal_highs_lows(SWINGS_NOT_CONSECUTIVE, tolerance=0.5) == []


def test_find_equal_levels_empty_returns_empty():
    assert find_equal_highs_lows([]) == []


# --- liquidity sweeps (R4) -----------------------------------------------


def test_find_liquidity_sweeps_bullish_low():
    swings = [Swing("low", 2, 100.0)]
    assert find_liquidity_sweeps(
        SWEEP_LOW_HIGHS, SWEEP_LOW_LOWS, SWEEP_LOW_CLOSES, swings, lookback=5
    ) == [Sweep("low", 5, 100.0, "bullish")]


def test_find_liquidity_sweeps_bearish_high():
    swings = [Swing("high", 2, 110.0)]
    assert find_liquidity_sweeps(
        SWEEP_HIGH_HIGHS, SWEEP_HIGH_LOWS, SWEEP_HIGH_CLOSES, swings, lookback=5
    ) == [Sweep("high", 5, 110.0, "bearish")]


def test_find_liquidity_sweeps_no_close_back_inside_returns_empty():
    swings = [Swing("low", 2, 100.0)]
    closes = [104.5, 103.5, 101.0, 101.5, 102.5, 99.0]  # closes below level
    assert (
        find_liquidity_sweeps(
            SWEEP_LOW_HIGHS, SWEEP_LOW_LOWS, closes, swings, lookback=5
        )
        == []
    )


def test_find_liquidity_sweeps_stale_level_outside_lookback():
    swings = [Swing("low", 2, 100.0)]
    assert (
        find_liquidity_sweeps(
            SWEEP_LOW_HIGHS, SWEEP_LOW_LOWS, SWEEP_LOW_CLOSES, swings, lookback=2
        )
        == []
    )


def test_find_liquidity_sweeps_most_recent_qualifying_swing_wins():
    # Two swept lows; the most recent (index 3) MUST be the one reported.
    swings = [Swing("low", 1, 100.0), Swing("low", 3, 101.0)]
    highs = [105.0, 104.0, 103.0, 102.0, 103.0, 103.0]
    lows = [104.0, 103.0, 100.0, 101.0, 102.0, 99.5]
    closes = [104.5, 103.5, 101.0, 101.5, 102.5, 101.5]
    assert find_liquidity_sweeps(highs, lows, closes, swings, lookback=5) == [
        Sweep("low", 5, 101.0, "bullish")
    ]


def test_find_liquidity_sweeps_empty_and_mismatched_return_empty():
    swings = [Swing("low", 2, 100.0)]
    assert find_liquidity_sweeps([], [], [], swings) == []
    assert (
        find_liquidity_sweeps(
            SWEEP_LOW_HIGHS, SWEEP_LOW_LOWS[:-1], SWEEP_LOW_CLOSES, swings
        )
        == []
    )


# --- purity / determinism (R5) -------------------------------------------


def test_finders_are_deterministic_and_do_not_mutate_inputs():
    opens, highs, lows, closes = OB_BULL
    first = find_order_blocks(opens, highs, lows, closes, BULL_BOS)
    second = find_order_blocks(opens, highs, lows, closes, BULL_BOS)
    assert first == second
    assert (opens, highs, lows, closes) == OB_BULL

    highs_f, lows_f = list(FVG_BULL_HIGHS), list(FVG_BULL_LOWS)
    find_fvg(highs_f, lows_f)
    assert highs_f == FVG_BULL_HIGHS and lows_f == FVG_BULL_LOWS

    swings = list(SWINGS_EQH)
    find_equal_highs_lows(swings, tolerance=0.5)
    assert swings == SWINGS_EQH


def test_finds_return_empty_never_raise_on_empty_input():
    assert find_order_blocks([], [], [], [], []) == []
    assert find_fvg([], []) == []
    assert find_equal_highs_lows([]) == []
    assert find_liquidity_sweeps([], [], [], []) == []
