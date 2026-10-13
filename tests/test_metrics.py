"""Contract tests for src/metrics.py — pure PnL math over caller sequences.

Strict TDD: RED was written per function before implementation. No I/O, no
sqlite3/journal imports, stdlib only. Empty input is ``None`` for the scalar
metrics and ``[]`` for the equity curve.
"""

from pytest import approx

from src.metrics import (
    equity_curve,
    expectancy,
    max_drawdown,
    net_pnl,
    profit_factor,
    r_multiple,
    win_rate,
)

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


# --- max_drawdown (R8) --------------------------------------------------


def test_max_drawdown_peak_then_trough():
    assert max_drawdown([10.0, 5.0, 8.0, 2.0]) == -8.0


def test_max_drawdown_monotonic_up_is_zero():
    assert max_drawdown([1.0, 2.0, 3.0]) == 0.0


def test_max_drawdown_single_point_is_zero():
    # Triangulation: one point is its own peak, no decline.
    assert max_drawdown([42.0]) == 0.0


def test_max_drawdown_empty_is_none():
    assert max_drawdown([]) is None


def test_max_drawdown_does_not_mutate_input():
    equity = [10.0, 5.0, 8.0, 2.0]
    max_drawdown(equity)
    assert equity == [10.0, 5.0, 8.0, 2.0]


# --- win_rate (R9) ------------------------------------------------------


def test_win_rate_mixed():
    assert win_rate([10.0, -5.0, 5.0]) == approx(66.6666666667)


def test_win_rate_all_win_is_100():
    assert win_rate([1.0, 2.0]) == 100.0


def test_win_rate_zero_is_not_a_win():
    assert win_rate([0.0, -1.0]) == 0.0


def test_win_rate_empty_is_none():
    assert win_rate([]) is None


def test_win_rate_does_not_mutate_input():
    pnls = [10.0, -5.0, 5.0]
    win_rate(pnls)
    assert pnls == [10.0, -5.0, 5.0]


# --- net_pnl (R10) ------------------------------------------------------


def test_net_pnl_sums_nets():
    assert net_pnl([10.0, -5.0, 5.0]) == 10.0


def test_net_pnl_empty_is_zero():
    assert net_pnl([]) == 0.0


def test_net_pnl_does_not_mutate_input():
    pnls = [10.0, -5.0, 5.0]
    net_pnl(pnls)
    assert pnls == [10.0, -5.0, 5.0]
