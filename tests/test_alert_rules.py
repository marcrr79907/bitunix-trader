"""Contract tests for src/alert_rules.py — pure, framework-free alert engine.

Strict TDD: RED written before implementation. The engine turns a validated
``condition`` JSON object plus a window of DB-shaped candle rows (open/high/low/
close/quote_vol/time) into a boolean state and a false->true edge. It is total
(never raises); ``parse_condition`` is the only function that raises
(``ValueError`` on a structural breach) so the worker can log + skip a bad rule.

Deterministic: no clock, no random, inputs never mutated.
"""

from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from src.alert_rules import edge_fired, matches, parse_condition

MODULE = Path(__file__).resolve().parent.parent / "src" / "alert_rules.py"


def _row(time, close, *, high=None, low=None, open_=None, quote_vol=None) -> dict:
    return {
        "time": time,
        "open": close if open_ is None else open_,
        "high": close if high is None else high,
        "low": close if low is None else low,
        "close": close,
        "quote_vol": quote_vol,
    }


def _price_rows(closes: list[float]) -> list[dict]:
    return [_row(i, c) for i, c in enumerate(closes)]


def _scalar_rows(closes: list[float], *, quote_vol: float = 1.0) -> list[dict]:
    return [_row(i, c, quote_vol=quote_vol) for i, c in enumerate(closes)]


def _zigzag_rows() -> list[dict]:
    """48-bar deterministic zigzag exercising the whole frozen SMC chain.

    Six rising peak/trough legs yield confirmed swings, BOS events, order
    blocks, FVGs, a dealing range and one LONG setup (score 3 at bar 44).
    """
    peaks = [110, 112, 116, 118, 124, 126]
    troughs = [100, 102, 104, 108, 110, 112]
    seq = []
    for peak, trough in zip(peaks, troughs, strict=True):
        seq.append((peak, "up"))
        seq.append((trough, "down"))
    rows: list[dict] = []
    prev = 100.0
    i = 0
    for price, direction in seq:
        for s in range(4):
            v = prev + (price - prev) * (s / 4)
            hi, lo = v + 0.5, v - 0.5
            o, c = (hi - 0.1, lo + 0.1) if direction == "down" else (lo + 0.1, hi - 0.1)
            rows.append(_row(i, c, high=hi, low=lo, open_=o))
            i += 1
        prev = price
    return rows


# --- parse_condition: valid shapes ---------------------------------------


def test_parse_price_normalizes():
    assert parse_condition({"type": "price", "op": "above", "level": 100}) == {
        "type": "price",
        "op": "above",
        "level": 100.0,
    }


def test_parse_indicator_fills_default_params():
    assert parse_condition(
        {"type": "indicator", "name": "rsi", "op": "above", "level": 70}
    ) == {
        "type": "indicator",
        "name": "rsi",
        "op": "above",
        "level": 70.0,
        "params": {"rsi_len": 14},
    }


def test_parse_indicator_accepts_explicit_length():
    out = parse_condition(
        {
            "type": "indicator",
            "name": "sma",
            "op": "below",
            "level": 1,
            "params": {"sma_len": 5},
        }
    )
    assert out["params"] == {"sma_len": 5}


def test_parse_smc_defaults_min_score():
    assert parse_condition({"type": "smc_setup", "direction": "any"}) == {
        "type": "smc_setup",
        "direction": "any",
        "min_score": 3,
    }


# --- parse_condition: breaches raise ValueError ---------------------------


@pytest.mark.parametrize(
    "condition",
    [
        None,
        [],
        "price",
        42,
        {},
        {"type": "magic"},
        {"type": "price"},
        {"type": "price", "op": "sideways", "level": 1},
        {"type": "price", "op": "above"},
        {"type": "price", "op": "above", "level": "high"},
        {"type": "price", "op": "above", "level": True},
        {"type": "indicator", "name": "macd", "op": "above", "level": 1},
        {"type": "indicator", "name": "bollinger", "op": "above", "level": 1},
        {"type": "indicator", "name": "stochastic", "op": "above", "level": 1},
        {"type": "indicator", "name": "unknown", "op": "above", "level": 1},
        {"type": "indicator", "name": "rsi", "op": "sideways", "level": 1},
        {"type": "indicator", "name": "rsi", "op": "above", "level": "x"},
        {
            "type": "indicator",
            "name": "vwap",
            "op": "above",
            "level": 1,
            "params": {"sma_len": 5},
        },
        {"type": "indicator", "name": "rsi", "op": "above", "level": 1, "params": 5},
        {
            "type": "indicator",
            "name": "rsi",
            "op": "above",
            "level": 1,
            "params": {"sma_len": 20},
        },
        {
            "type": "indicator",
            "name": "rsi",
            "op": "above",
            "level": 1,
            "params": {"rsi_len": 0},
        },
        {
            "type": "indicator",
            "name": "rsi",
            "op": "above",
            "level": 1,
            "params": {"rsi_len": "x"},
        },
        {"type": "smc_setup"},
        {"type": "smc_setup", "direction": "up"},
        {"type": "smc_setup", "direction": "any", "min_score": "3"},
        {"type": "smc_setup", "direction": "any", "min_score": True},
    ],
)
def test_parse_condition_breach_raises(condition):
    with pytest.raises(ValueError):
        parse_condition(condition)


# --- matches: price ------------------------------------------------------


def test_price_above_fires():
    assert (
        matches({"type": "price", "op": "above", "level": 100}, _price_rows([101]))
        is True
    )


def test_price_above_below_level_is_false():
    assert (
        matches({"type": "price", "op": "above", "level": 100}, _price_rows([99]))
        is False
    )


def test_price_below_fires():
    assert (
        matches({"type": "price", "op": "below", "level": 100}, _price_rows([99]))
        is True
    )


def test_price_op_is_strict_at_the_level():
    assert (
        matches({"type": "price", "op": "above", "level": 100}, _price_rows([100]))
        is False
    )
    assert (
        matches({"type": "price", "op": "below", "level": 100}, _price_rows([100]))
        is False
    )


def test_price_index_slicing():
    rows = _price_rows([10, 20, 30])
    cond = {"type": "price", "op": "above", "level": 15}
    assert matches(cond, rows, index=-1) is True  # latest close 30
    assert matches(cond, rows, index=-2) is True  # previous close 20
    assert matches(cond, rows, index=-3) is False  # first close 10


def test_price_positive_index_slices_from_start():
    rows = _price_rows([10, 20, 30])
    cond = {"type": "price", "op": "above", "level": 15}
    assert matches(cond, rows, index=0) is False  # close 10
    assert matches(cond, rows, index=1) is True  # close 20
    assert matches(cond, rows, index=2) is True  # close 30


# --- matches: indicator --------------------------------------------------


def test_sma_fires_and_not():
    rows = _scalar_rows([1, 2, 3])  # sma(2)[-1] = 2.5
    cond = {
        "type": "indicator",
        "name": "sma",
        "op": "above",
        "level": 2,
        "params": {"sma_len": 2},
    }
    assert matches(cond, rows) is True
    cond_below = {**cond, "level": 3}
    assert matches(cond_below, rows) is False


def test_ema_fires():
    rows = _scalar_rows([1, 2, 3, 4])  # ema(3)[-1] = 3.0
    cond = {
        "type": "indicator",
        "name": "ema",
        "op": "above",
        "level": 2,
        "params": {"ema_len": 3},
    }
    assert matches(cond, rows) is True


def test_rsi_warms_up_to_none_and_is_false():
    rows = _scalar_rows([2, 1])  # rsi(3) all None -> warm-up
    cond = {"type": "indicator", "name": "rsi", "op": "above", "level": 10}
    assert matches(cond, rows) is False


def test_atr_fires():
    rows = [
        _row(0, 9, high=10, low=8),
        _row(1, 11, high=12, low=9),
        _row(2, 10, high=11, low=9),
        _row(3, 12, high=13, low=10),
    ]  # atr(2)[-1] = 2.75
    cond = {
        "type": "indicator",
        "name": "atr",
        "op": "above",
        "level": 2,
        "params": {"atr_len": 2},
    }
    assert matches(cond, rows) is True


def test_vwap_fires():
    rows = [_row(0, 9, high=10, low=8, quote_vol=5.0)]  # vwap = 9.0
    cond = {"type": "indicator", "name": "vwap", "op": "above", "level": 8}
    assert matches(cond, rows) is True


def test_vwap_zero_volume_is_none_and_false():
    rows = [_row(0, 9, high=10, low=8, quote_vol=0.0)]
    cond = {"type": "indicator", "name": "vwap", "op": "above", "level": 8}
    assert matches(cond, rows) is False


def test_tuple_indicator_is_false_without_raising():
    rows = _scalar_rows([1, 2, 3, 4, 5])
    assert (
        matches({"type": "indicator", "name": "macd", "op": "above", "level": 1}, rows)
        is False
    )


# --- matches: smc_setup --------------------------------------------------


def test_smc_setup_long_fires():
    rows = _zigzag_rows()
    cond = {"type": "smc_setup", "direction": "long", "min_score": 3}
    assert matches(cond, rows) is True


def test_smc_setup_direction_mismatch_is_false():
    rows = _zigzag_rows()
    assert (
        matches({"type": "smc_setup", "direction": "short", "min_score": 1}, rows)
        is False
    )


def test_smc_setup_any_direction_fires():
    rows = _zigzag_rows()
    assert (
        matches({"type": "smc_setup", "direction": "any", "min_score": 3}, rows) is True
    )


def test_smc_setup_min_score_above_actual_is_false():
    rows = _zigzag_rows()  # setup score = 3
    assert (
        matches({"type": "smc_setup", "direction": "long", "min_score": 4}, rows)
        is False
    )


def test_smc_setup_short_window_is_false():
    assert (
        matches({"type": "smc_setup", "direction": "any"}, _zigzag_rows()[:5]) is False
    )


# --- matches: totality ---------------------------------------------------


def test_unknown_type_and_op_are_false_without_raising():
    rows = _price_rows([1, 2, 3])
    assert matches({"type": "magic"}, rows) is False
    assert matches({"type": "price", "op": "sideways", "level": 1}, rows) is False


@pytest.mark.parametrize("candles", [[], None, 42, "nope"])
def test_empty_or_malformed_window_is_false(candles):
    assert matches({"type": "price", "op": "above", "level": 1}, candles) is False


def test_missing_row_key_is_false_not_raise():
    rows = [{"time": 0, "open": 1, "high": 1, "close": 1}]  # no "low" -> atr raises
    cond = {
        "type": "indicator",
        "name": "atr",
        "op": "above",
        "level": 0,
        "params": {"atr_len": 1},
    }
    assert matches(cond, rows) is False


def test_matches_does_not_mutate_candles():
    rows = _price_rows([1, 2, 3])
    snapshot = copy.deepcopy(rows)
    matches({"type": "price", "op": "above", "level": 2}, rows)
    assert rows == snapshot


def test_matches_is_deterministic():
    rows = _zigzag_rows()
    cond = {"type": "smc_setup", "direction": "long", "min_score": 3}
    assert matches(cond, rows) == matches(cond, rows)


# --- edge_fired ----------------------------------------------------------


def test_edge_false_to_true_fires():
    rows = _price_rows([99, 101])
    assert edge_fired({"type": "price", "op": "above", "level": 100}, rows) is True


def test_edge_true_to_true_does_not_fire():
    rows = _price_rows([101, 102])
    assert edge_fired({"type": "price", "op": "above", "level": 100}, rows) is False


def test_edge_true_to_false_does_not_fire():
    rows = _price_rows([101, 99])
    assert edge_fired({"type": "price", "op": "above", "level": 100}, rows) is False


def test_edge_false_to_false_does_not_fire():
    rows = _price_rows([98, 99])
    assert edge_fired({"type": "price", "op": "above", "level": 100}, rows) is False


@pytest.mark.parametrize("rows", [[], _price_rows([100]), 42, None])
def test_edge_fewer_than_two_bars_is_false(rows):
    assert edge_fired({"type": "price", "op": "above", "level": 100}, rows) is False


def test_edge_unknown_condition_is_false():
    assert edge_fired({"type": "magic"}, _price_rows([1, 2])) is False


def test_edge_is_deterministic_and_non_mutating():
    rows = _price_rows([99, 101])
    snapshot = copy.deepcopy(rows)
    cond = {"type": "price", "op": "above", "level": 100}
    assert edge_fired(cond, rows) == edge_fired(cond, rows)
    assert rows == snapshot


# --- purity: no clock / random imports -----------------------------------


def test_engine_imports_no_clock_or_random():
    tree = ast.parse(MODULE.read_text(), filename=str(MODULE))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert roots.isdisjoint({"time", "datetime", "random"})
