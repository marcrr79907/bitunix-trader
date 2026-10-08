"""Contract tests for src/indicators.py — pure, index-aligned chart math.

Strict TDD: RED was written per function before implementation. Every function
keeps output length == input length, uses leading None for warm-up, and never
mutates its inputs.
"""

from pytest import approx

from src.indicators import atr, ema, rsi, sma, vwap, zscore

# --- sma ----------------------------------------------------------------


def test_sma_known_values():
    assert sma([1, 2, 3, 4], 3) == [None, None, 2.0, 3.0]


def test_sma_window_one_is_identity():
    # Triangulation: different window/inputs exercise the general branch.
    assert sma([5, 7, 9], 1) == [5.0, 7.0, 9.0]


def test_sma_empty_returns_empty():
    assert sma([], 3) == []


def test_sma_window_below_one_all_none():
    assert sma([1, 2, 3], 0) == [None, None, None]


def test_sma_length_preserved():
    assert len(sma([1, 2, 3, 4, 5, 6, 7], 4)) == 7


def test_sma_does_not_mutate_input():
    data = [1, 2, 3, 4]
    sma(data, 3)
    assert data == [1, 2, 3, 4]


# --- ema ----------------------------------------------------------------


def test_ema_seeds_with_sma_and_applies_multiplier():
    # seed at idx 2 = SMA(1,2,3)=2.0; k=2/(3+1)=0.5
    # idx 3 = 2.0 + 0.5*(4-2.0) = 3.0
    assert ema([1, 2, 3, 4], 3) == [None, None, 2.0, 3.0]


def test_ema_window_one_is_identity():
    # Triangulation: window 1 => seed at idx 0, k=1.0, so value == price.
    assert ema([5, 7, 9], 1) == [5.0, 7.0, 9.0]


def test_ema_empty_returns_empty():
    assert ema([], 3) == []


def test_ema_window_below_one_all_none():
    assert ema([1, 2, 3], 0) == [None, None, None]


def test_ema_length_preserved():
    assert len(ema([1, 2, 3, 4, 5, 6], 4)) == 6


def test_ema_does_not_mutate_input():
    data = [1, 2, 3, 4]
    ema(data, 3)
    assert data == [1, 2, 3, 4]


# --- rsi ----------------------------------------------------------------


def test_rsi_wilder_smoothing_known_values():
    # window=2; deltas of [2,1,2,1,2] = [-1,+1,-1,+1]
    # idx2: avg_gain=0.5 avg_loss=0.5 -> 50.0
    # idx3: avg_gain=0.25 avg_loss=0.75 -> 25.0
    # idx4: avg_gain=0.625 avg_loss=0.375 -> 62.5
    out = rsi([2, 1, 2, 1, 2], 2)
    assert out[:2] == [None, None]
    assert out[2] == approx(50.0)
    assert out[3] == approx(25.0)
    assert out[4] == approx(62.5)


def test_rsi_first_valid_index_is_window():
    # non-monotonic so avg_loss != 0 at the first computable index
    out = rsi([1, 2, 3, 2, 4], 3)
    assert out[2] is None
    assert out[3] is not None


def test_rsi_strictly_rising_is_none():
    # avg_loss == 0 for every computable position -> None, never raise.
    assert rsi([1, 2, 3, 4, 5], 3) == [None, None, None, None, None]


def test_rsi_bounded_zero_to_hundred():
    out = rsi([2, 1, 3, 1, 4, 1, 5], 3)
    assert all(v is None or 0.0 <= v <= 100.0 for v in out)


def test_rsi_empty_returns_empty():
    assert rsi([], 3) == []


def test_rsi_window_below_one_all_none():
    assert rsi([1, 2, 3], 0) == [None, None, None]


def test_rsi_does_not_mutate_input():
    data = [2, 1, 2, 1, 2]
    rsi(data, 2)
    assert data == [2, 1, 2, 1, 2]


# --- atr ----------------------------------------------------------------


def test_atr_wilder_smoothing_known_values():
    # tr[1]=3, tr[2]=2 -> atr[2]=2.5; tr[3]=3 -> atr[3]=2.75
    highs = [10, 12, 11, 13]
    lows = [8, 9, 9, 10]
    closes = [9, 11, 10, 12]
    out = atr(highs, lows, closes, 2)
    assert out[:2] == [None, None]
    assert out[2] == approx(2.5)
    assert out[3] == approx(2.75)


def test_atr_first_valid_index_is_window():
    out = atr([10, 11, 12], [8, 9, 10], [9, 10, 11], 2)
    assert out[1] is None
    assert out[2] is not None


def test_atr_non_negative():
    out = atr([10, 11, 12], [8, 9, 10], [9, 10, 11], 2)
    assert all(v is None or v >= 0.0 for v in out)


def test_atr_empty_returns_empty():
    assert atr([], [], [], 3) == []


def test_atr_window_below_one_all_none():
    assert atr([10, 11], [8, 9], [9, 10], 0) == [None, None]


def test_atr_does_not_mutate_inputs():
    highs, lows, closes = [10, 12, 11], [8, 9, 9], [9, 11, 10]
    atr(highs, lows, closes, 2)
    assert highs == [10, 12, 11]
    assert lows == [8, 9, 9]
    assert closes == [9, 11, 10]


# --- vwap ---------------------------------------------------------------


def test_vwap_single_bar_uses_typical_price():
    # tp = (3+1+2)/3 = 2.0; v=10 -> 20/10 = 2.0
    assert vwap([3], [1], [2], [10]) == [2.0]


def test_vwap_cumulative_weighting():
    # bar0: tp=2, v=10 -> 20/10 = 2.0
    # bar1: tp=(5+3+4)/3=4, v=10 -> (20+40)/20 = 3.0
    assert vwap([3, 5], [1, 3], [2, 4], [10, 10]) == [2.0, 3.0]


def test_vwap_zero_cumulative_volume_is_none():
    assert vwap([3], [1], [2], [0]) == [None]


def test_vwap_empty_returns_empty():
    assert vwap([], [], [], []) == []


def test_vwap_does_not_mutate_inputs():
    highs, lows, closes, vols = [3], [1], [2], [10]
    vwap(highs, lows, closes, vols)
    assert (highs, lows, closes, vols) == ([3], [1], [2], [10])


# --- zscore -------------------------------------------------------------


def test_zscore_rolling_known_values():
    # window=2: idx1 mean=1.5 pstdev=0.5 -> (2-1.5)/0.5 = 1.0
    #           idx2 mean=2.5 pstdev=0.5 -> (3-2.5)/0.5 = 1.0
    assert zscore([1, 2, 3], 2) == [None, 1.0, 1.0]


def test_zscore_flat_window_is_none():
    # pstdev == 0 -> None, never raise.
    assert zscore([5, 5, 5], 2) == [None, None, None]


def test_zscore_full_series_only_last_position():
    out = zscore([1, 2, 3], 3)
    assert out[0] is None
    assert out[1] is None
    assert out[2] == approx(1.224744871, abs=1e-6)


def test_zscore_empty_returns_empty():
    assert zscore([], 3) == []


def test_zscore_window_below_one_all_none():
    assert zscore([1, 2, 3], 0) == [None, None, None]


def test_zscore_does_not_mutate_input():
    data = [1, 2, 3]
    zscore(data, 2)
    assert data == [1, 2, 3]


# --- pure-function contract over all six --------------------------------


def test_no_mutation_across_all_indicators():
    series = [1.0, 2.0, 3.0, 4.0, 5.0]
    snapshot = list(series)
    sma(series, 3)
    ema(series, 3)
    rsi(series, 3)
    atr(series, series, series, 3)
    vwap(series, series, series, series)
    zscore(series, 3)
    assert series == snapshot
