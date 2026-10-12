"""Contract tests for src/smc/range.py — dealing range + PD classification.

Strict TDD: RED written before implementation. Series are small and
hand-traced against the frozen rules in specs/smc-range/spec.md and design.md.
Pure: repeatable, non-mutating, never raises.
"""

from src.smc.range import DealingRange, classify_price, dealing_range

# --- dealing_range (R1) --------------------------------------------------


def test_dealing_range_over_last_n_bars():
    out = dealing_range([1.0, 5.0, 3.0], [0.0, 2.0, 1.0], lookback=3)
    assert out == DealingRange(high=5.0, low=0.0, equilibrium=2.5, index=2)
    assert isinstance(out, tuple)  # stdlib NamedTuple (R3)


def test_dealing_range_truncates_to_lookback():
    # Only the last 2 bars count: high=max(5,3)=5, low=min(4,1)=1.
    out = dealing_range([9.0, 1.0, 5.0, 3.0], [8.0, 0.0, 4.0, 1.0], lookback=2)
    assert out == DealingRange(high=5.0, low=1.0, equilibrium=3.0, index=3)


def test_dealing_range_lookback_larger_than_series_uses_whole_series():
    out = dealing_range([2.0, 4.0], [1.0, 3.0], lookback=10)
    assert out == DealingRange(high=4.0, low=1.0, equilibrium=2.5, index=1)


def test_dealing_range_flat_market_equilibrium_equals_extremes():
    out = dealing_range([5.0, 5.0, 5.0], [5.0, 5.0, 5.0], lookback=3)
    assert out == DealingRange(high=5.0, low=5.0, equilibrium=5.0, index=2)


def test_dealing_range_empty_returns_none():
    assert dealing_range([], []) is None


def test_dealing_range_mismatched_lengths_return_none():
    assert dealing_range([1.0, 2.0], [1.0]) is None


def test_dealing_range_non_positive_lookback_returns_none():
    assert dealing_range([1.0, 2.0], [1.0, 2.0], lookback=0) is None
    assert dealing_range([1.0, 2.0], [1.0, 2.0], lookback=-1) is None


def test_dealing_range_deterministic_and_non_mutating():
    highs, lows = [1.0, 5.0, 3.0], [0.0, 2.0, 1.0]
    first = dealing_range(highs, lows, lookback=3)
    second = dealing_range(highs, lows, lookback=3)
    assert first == second
    assert (highs, lows) == ([1.0, 5.0, 3.0], [0.0, 2.0, 1.0])


# --- classify_price (R2) -------------------------------------------------

EQ100 = DealingRange(high=110.0, low=90.0, equilibrium=100.0, index=4)


def test_classify_price_above_equilibrium_is_premium():
    assert classify_price(101.0, EQ100) == "premium"


def test_classify_price_below_equilibrium_is_discount():
    assert classify_price(99.0, EQ100) == "discount"


def test_classify_price_at_equilibrium_is_equilibrium():
    assert classify_price(100.0, EQ100) == "equilibrium"


def test_classify_price_none_range_is_equilibrium():
    # Never raises: a missing range degrades to neutral.
    assert classify_price(101.0, None) == "equilibrium"
