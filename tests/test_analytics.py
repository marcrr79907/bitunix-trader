"""Contract tests for src/analytics.py — pure grouping, calibration, SVG.

Strict TDD: RED was written before the implementation. Framework-free, stdlib
only, deterministic, never raises on empty/short/mismatched input, and never
mutates its inputs.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET

from pytest import approx

from src.analytics import (
    bars_svg,
    calibrate,
    equity_and_drawdown,
    equity_svg,
    group_metrics,
    summarize,
)

# --- summarize (A1) -----------------------------------------------------


def test_summarize_known_bucket():
    assert summarize([10.0, -5.0, 5.0]) == {
        "trades": 3,
        "wins": 2,
        "win_rate": approx(66.6666666667),
        "net_pnl": 10.0,
        "expectancy": approx(3.3333333333),
        "profit_factor": 3.0,
        "max_drawdown": -5.0,
    }


def test_summarize_empty_bucket():
    assert summarize([]) == {
        "trades": 0,
        "wins": 0,
        "win_rate": None,
        "net_pnl": 0.0,
        "expectancy": None,
        "profit_factor": None,
        "max_drawdown": None,
    }


def test_summarize_all_wins_has_no_losses():
    out = summarize([1.0, 2.0])
    assert out["wins"] == 2
    assert out["win_rate"] == 100.0
    assert out["profit_factor"] is None


def test_summarize_all_losses():
    out = summarize([-1.0, -2.0])
    assert out["wins"] == 0
    assert out["win_rate"] == 0.0
    assert out["net_pnl"] == -3.0


def test_summarize_does_not_mutate_input():
    pnls = [10.0, -5.0, 5.0]
    summarize(pnls)
    assert pnls == [10.0, -5.0, 5.0]


# --- group_metrics (A2) -------------------------------------------------


def _rows():
    return [
        {"net": 10.0, "setup": "long:score4", "hour": 14, "symbol": "BTCUSDT"},
        {"net": -5.0, "setup": "short:score3", "hour": 14, "symbol": "ETHUSDT"},
        {"net": 5.0, "setup": None, "hour": None, "symbol": "BTCUSDT"},
    ]


def test_group_by_setup_keys_sorted():
    groups = group_metrics(_rows(), "setup")
    assert list(groups) == ["long:score4", "short:score3", "unmatched"]
    assert groups["long:score4"]["net_pnl"] == 10.0
    assert groups["short:score3"]["net_pnl"] == -5.0
    assert groups["unmatched"]["net_pnl"] == 5.0


def test_group_by_hour_none_buckets_as_unknown():
    groups = group_metrics(_rows(), "hour")
    assert set(groups) == {14, "unknown"}
    assert groups[14]["trades"] == 2
    assert groups["unknown"]["trades"] == 1


def test_group_by_symbol():
    groups = group_metrics(_rows(), "symbol")
    assert list(groups) == ["BTCUSDT", "ETHUSDT"]
    assert groups["BTCUSDT"]["trades"] == 2


def test_group_empty_rows_is_empty():
    assert group_metrics([], "setup") == {}


def test_group_unknown_dimension_is_empty():
    assert group_metrics(_rows(), "nope") == {}


def test_group_does_not_mutate_rows():
    rows = _rows()
    snapshot = copy.deepcopy(rows)
    group_metrics(rows, "setup")
    assert rows == snapshot


def test_group_skips_malformed_row():
    rows = [{"net": 5.0, "setup": "long:score4"}, {"nope": 1}]
    groups = group_metrics(rows, "setup")
    assert groups["long:score4"]["trades"] == 1


# --- equity_and_drawdown (A3) -------------------------------------------


def test_equity_and_drawdown_one_call():
    assert equity_and_drawdown([5.0, -2.0, 3.0]) == {
        "equity": [5.0, 3.0, 6.0],
        "max_drawdown": -2.0,
    }


def test_equity_and_drawdown_empty():
    assert equity_and_drawdown([]) == {"equity": [], "max_drawdown": None}


# --- calibrate (A4) -----------------------------------------------------


def _signal(**over):
    base = {
        "symbol": "BTCUSDT",
        "time": 1_699_999_999,
        "direction": "long",
        "entry": 100.0,
        "stop": 90.0,
        "score": 4,
    }
    base.update(over)
    return base


def _trade(**over):
    base = {
        "net": 20.0,
        "side": "BUY",
        "ctime": 1_700_000_000_000,
        "qty": 1.0,
        "symbol": "BTCUSDT",
    }
    base.update(over)
    return base


def test_calibrate_output_shape():
    out = calibrate([], [], window_seconds=3600)
    assert set(out) == {"matched", "unmatched", "by_setup", "r_by_setup"}
    assert out["by_setup"] == {}
    assert out["r_by_setup"] == {}
    assert out["matched"]["trades"] == 0
    assert out["unmatched"]["trades"] == 0


def test_calibrate_nearest_within_window_matches():
    out = calibrate([_signal()], [_trade()], window_seconds=3600)
    assert out["matched"]["trades"] == 1
    assert out["unmatched"]["trades"] == 0
    assert out["by_setup"]["long:score4"]["net_pnl"] == 20.0
    assert out["r_by_setup"]["long:score4"] == 2.0


def test_calibrate_se_sell_maps_to_short():
    signal = _signal(direction="short", entry=100.0, stop=110.0)
    trade = _trade(side="SELL")
    out = calibrate([signal], [trade], window_seconds=3600)
    assert out["matched"]["trades"] == 1
    assert "short:score4" in out["by_setup"]


def test_calibrate_outside_window_is_unmatched():
    signal = _signal(time=1_690_000_000)
    out = calibrate([signal], [_trade()], window_seconds=3600)
    assert out["matched"]["trades"] == 0
    assert out["unmatched"]["trades"] == 1
    assert out["by_setup"] == {}


def test_calibrate_direction_mismatch_is_unmatched():
    out = calibrate([_signal()], [_trade(side="SELL")], window_seconds=3600)
    assert out["unmatched"]["trades"] == 1
    assert out["by_setup"] == {}


def test_calibrate_nearest_delta_wins():
    far = _signal(time=1_699_999_900, score=3)  # delta 100
    near = _signal(time=1_699_999_950, score=4)  # delta 50
    out = calibrate([far, near], [_trade()], window_seconds=3600)
    assert "long:score4" in out["by_setup"]
    assert "long:score3" not in out["by_setup"]


def test_calibrate_equal_delta_picks_earlier_time():
    earlier = _signal(time=1_699_999_950, score=4)  # delta 50
    later = _signal(time=1_700_000_050, score=3)  # delta 50
    out = calibrate([later, earlier], [_trade()], window_seconds=3600)
    assert "long:score4" in out["by_setup"]
    assert "long:score3" not in out["by_setup"]


def test_calibrate_zero_risk_yields_none_r():
    signal = _signal(entry=100.0, stop=100.0)
    out = calibrate([signal], [_trade()], window_seconds=3600)
    assert out["matched"]["trades"] == 1
    assert out["r_by_setup"]["long:score4"] is None


def test_calibrate_r_by_setup_is_mean_of_non_none():
    # Two long:score4 signals: one zero-risk (R None) and one normal (R 2.0).
    # Each trade sits nearest its own signal, so both match long:score4.
    zero = _signal(time=1_699_999_990, entry=100.0, stop=100.0)
    normal = _signal(time=1_699_999_000, entry=100.0, stop=90.0)
    trades = [
        _trade(ctime=1_700_000_000_000, net=20.0),  # nearest -> zero, R None
        _trade(ctime=1_699_999_010_000, net=20.0),  # nearest -> normal, R 2.0
    ]
    out = calibrate([zero, normal], trades, window_seconds=3600)
    assert out["matched"]["trades"] == 2
    assert out["r_by_setup"]["long:score4"] == approx(2.0)


def test_calibrate_window_non_positive_all_unmatched():
    out = calibrate([_signal()], [_trade()], window_seconds=0)
    assert out["matched"]["trades"] == 0
    assert out["unmatched"]["trades"] == 1


def test_calibrate_does_not_mutate_inputs():
    signals = [_signal()]
    trades = [_trade()]
    signals_snapshot = copy.deepcopy(signals)
    trades_snapshot = copy.deepcopy(trades)
    calibrate(signals, trades, window_seconds=3600)
    assert signals == signals_snapshot
    assert trades == trades_snapshot


def test_calibrate_is_deterministic():
    signals = [_signal(time=1_699_999_900), _signal(time=1_699_999_950)]
    trades = [_trade()]
    assert calibrate(signals, trades, window_seconds=3600) == calibrate(
        signals, trades, window_seconds=3600
    )


def test_calibrate_symbol_mismatch_is_unmatched():
    out = calibrate([_signal(symbol="ETHUSDT")], [_trade()], window_seconds=3600)
    assert out["unmatched"]["trades"] == 1


def test_calibrate_skips_malformed_trade():
    out = calibrate([_signal()], [{"nope": 1}], window_seconds=3600)
    assert out["matched"]["trades"] == 0
    assert out["unmatched"]["trades"] == 0


def test_calibrate_skips_malformed_signal():
    out = calibrate([{"symbol": "BTCUSDT"}], [_trade()], window_seconds=3600)
    assert out["unmatched"]["trades"] == 1


def test_calibrate_unknown_side_is_unmatched():
    out = calibrate([_signal()], [_trade(side="HOLD")], window_seconds=3600)
    assert out["unmatched"]["trades"] == 1


# --- equity_svg / bars_svg (A5 / AS4) -----------------------------------


def test_equity_svg_is_deterministic():
    points = [0.0, 5.0, 3.0, 6.0]
    first = equity_svg(points, width=200, height=50)
    second = equity_svg(points, width=200, height=50)
    assert first == second


def test_equity_svg_is_well_formed():
    svg = equity_svg([0.0, 5.0, 3.0, 6.0], width=200, height=50)
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")


def test_equity_svg_empty_is_fixed_empty_state():
    svg = equity_svg([], width=200, height=50)
    assert svg == equity_svg([], width=200, height=50)
    ET.fromstring(svg)
    assert "<svg" in svg


def test_bars_svg_is_deterministic_and_well_formed():
    items = [
        {"label": "long:score4", "value": 3.0},
        {"label": "short:score3", "value": -5.0},
    ]
    first = bars_svg(items, width=200, height=50)
    assert first == bars_svg(items, width=200, height=50)
    root = ET.fromstring(first)
    assert root.tag.endswith("svg")


def test_bars_svg_escapes_labels():
    svg = bars_svg([{"label": "<b>&", "value": 1.0}], width=200, height=50)
    assert "&lt;b&gt;&amp;" in svg
    assert "<b>" not in svg


def test_bars_svg_empty_is_fixed_empty_state():
    svg = bars_svg([], width=200, height=50)
    assert svg == bars_svg([], width=200, height=50)
    ET.fromstring(svg)
    assert "<svg" in svg


def test_bars_svg_does_not_mutate_input():
    items = [{"label": "long:score4", "value": 3.0}]
    snapshot = copy.deepcopy(items)
    bars_svg(items, width=200, height=50)
    assert items == snapshot


def test_bars_svg_skips_malformed_row():
    svg = bars_svg([{"label": "ok", "value": 1.0}, {"nope": 1}], width=200, height=50)
    ET.fromstring(svg)
    assert "ok" in svg
