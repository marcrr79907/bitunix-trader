"""Contract tests for src/smc/swings.py — strict fractal pivots over OHLC.

Strict TDD: RED written before implementation. Pivots are strict (equal levels
are never pivots), only fully confirmed bars are emitted (no look-ahead), and
the function never raises.
"""

from src.smc.swings import Swing, find_swings

# --- find_swings: known pivots ------------------------------------------


def test_find_swings_known_high_pivots():
    # Spec R1: highs 1->3->2->4->1, pivots at the two local maxima.
    highs = [1, 3, 2, 4, 1]
    lows = [0, 1, 0, 2, 0]
    picks = [s for s in find_swings(highs, lows, left=1, right=1) if s.kind == "high"]
    assert picks == [Swing("high", 1, 3.0), Swing("high", 3, 4.0)]


def test_find_swings_mirrors_low_pivots():
    # R1 mirror: bar 2 low (0.0) is strictly below both neighbours.
    result = find_swings([1, 3, 2, 4, 1], [0, 1, 0, 2, 0], left=1, right=1)
    assert result == [
        Swing("high", 1, 3.0),
        Swing("low", 2, 0.0),
        Swing("high", 3, 4.0),
    ]


def test_find_swings_equal_levels_are_not_pivots():
    # Strict inequality: the plateau neighbour disqualifies the pivot.
    assert find_swings([2, 2, 1], [1, 1, 0], left=1, right=1) == []


def test_find_swings_trailing_extreme_absent():
    # Local max at the last bar has no right confirmation -> never emitted.
    assert find_swings([1, 2, 5], [0, 1, 2], left=1, right=1) == []


# --- find_swings: parameter edges ---------------------------------------


def test_find_swings_left_zero_uses_only_future_side():
    # left=0 -> empty left window -> immediate right-neighbour pivots.
    assert find_swings([1, 3, 1], [0, 1, 0], left=0, right=1) == [
        Swing("low", 0, 0.0),
        Swing("high", 1, 3.0),
    ]


def test_find_swings_right_zero_uses_only_past_side():
    # right=0 -> empty right window -> immediate left-neighbour pivots.
    assert find_swings([1, 3, 1], [0, 1, 0], left=1, right=0) == [
        Swing("high", 1, 3.0),
        Swing("low", 2, 0.0),
    ]


# --- find_swings: guard rails -------------------------------------------


def test_find_swings_empty_returns_empty():
    assert find_swings([], [], left=1, right=1) == []


def test_find_swings_mismatched_length_returns_empty():
    assert find_swings([1, 2, 3], [0, 1], left=1, right=1) == []


def test_find_swings_negative_left_returns_empty():
    assert find_swings([1, 2, 1], [0, 1, 0], left=-1, right=1) == []


def test_find_swings_negative_right_returns_empty():
    assert find_swings([1, 2, 1], [0, 1, 0], left=1, right=-1) == []


# --- find_swings: shape and purity --------------------------------------


def test_find_swings_ascending_order_and_unpacking():
    result = find_swings([1, 3, 1, 4, 1], [0, 1, 0, 2, 0], left=1, right=1)
    assert [s.index for s in result] == sorted(s.index for s in result)
    kind, index, price = result[0]
    assert (kind, index, price) == ("high", 1, 3.0)


def test_find_swings_same_index_high_first():
    # Both a high and a low pivot land on index 1 -> high sorts first.
    result = find_swings([1, 3, 2], [1, 0, 2], left=0, right=1)
    assert result == [Swing("high", 1, 3.0), Swing("low", 1, 0.0)]


def test_find_swings_is_deterministic_and_non_mutating():
    highs = [1, 3, 1, 4, 1]
    lows = [0, 1, 0, 2, 0]
    first = find_swings(highs, lows, left=1, right=1)
    second = find_swings(highs, lows, left=1, right=1)
    assert first == second
    assert highs == [1, 3, 1, 4, 1]
    assert lows == [0, 1, 0, 2, 0]
