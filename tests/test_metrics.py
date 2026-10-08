"""Contract tests for src/metrics.py — pure PnL math over caller sequences.

Strict TDD: RED was written per function before implementation. No I/O, no
sqlite3/journal imports, stdlib only. Empty input is ``None`` for the scalar
metrics and ``[]`` for the equity curve.
"""

from pytest import approx

from src.metrics import equity_curve, expectancy, profit_factor, r_multiple

# --- expectancy ---------------------------------------------------------


def test_expectancy_mean_of_pnl():
    assert expectancy([10.0, -5.0, 5.0]) == approx(3.3333333333)


def test_expectancy_single_trade():
    # Triangulation: a one-element list must return that element.
    assert expectancy([7.5]) == 7.5


def test_expectancy_empty_is_none():
    assert expectancy([]) is None


def test_expectancy_does_not_mutate_input():
    pnls = [10.0, -5.0, 5.0]
    expectancy(pnls)
    assert pnls == [10.0, -5.0, 5.0]


# --- profit_factor ------------------------------------------------------


def test_profit_factor_normal_ratio():
    assert profit_factor([10.0, -5.0, 20.0]) == 6.0


def test_profit_factor_no_losses_is_none():
    assert profit_factor([10.0, 20.0]) is None


def test_profit_factor_empty_is_none():
    assert profit_factor([]) is None


def test_profit_factor_all_losses_is_zero():
    # gross_profit=0 -> 0.0, a real number (loss side defined).
    assert profit_factor([-5.0, -15.0]) == 0.0


def test_profit_factor_does_not_mutate_input():
    pnls = [10.0, -5.0, 20.0]
    profit_factor(pnls)
    assert pnls == [10.0, -5.0, 20.0]


# --- r_multiple ---------------------------------------------------------


def test_r_multiple_winning_trade():
    assert r_multiple(30.0, 10.0) == 3.0


def test_r_multiple_losing_trade():
    # Triangulation: negative pnl -> negative multiple.
    assert r_multiple(-15.0, 10.0) == -1.5


def test_r_multiple_zero_risk_is_none():
    assert r_multiple(30.0, 0.0) is None


# --- equity_curve -------------------------------------------------------


def test_equity_curve_running_sum():
    assert equity_curve([5.0, -2.0, 3.0]) == [5.0, 3.0, 6.0]


def test_equity_curve_length_preserved():
    assert len(equity_curve([1.0, 2.0, 3.0, 4.0, 5.0])) == 5


def test_equity_curve_empty_is_empty():
    assert equity_curve([]) == []


def test_equity_curve_does_not_mutate_input():
    pnls = [5.0, -2.0, 3.0]
    equity_curve(pnls)
    assert pnls == [5.0, -2.0, 3.0]
