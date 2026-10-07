"""Positions parsing contract tests.

The math here is the risk-facing part: distance to liquidation and margin
state drive the warnings, so we pin it with pure-function tests.
"""

from src.monitor import liq_distance_pct, margin_state, position_row


def test_liq_distance_pct_long():
    # mark 30000, liq 22209 -> ~25.97%
    assert round(liq_distance_pct(22209.0, 30000.0), 2) == 25.97


def test_liq_distance_pct_short_above_mark():
    # magnitude matters regardless of side
    assert round(liq_distance_pct(35000.0, 30000.0), 2) == 16.67


def test_liq_distance_pct_no_liquidation():
    # liqPrice <= 0 means low risk, no liquidation price
    assert liq_distance_pct(0.0, 30000.0) is None
    assert liq_distance_pct(None, 30000.0) is None
    assert liq_distance_pct(22209.0, None) is None


def test_margin_state():
    assert margin_state(0.01) == "ok"
    assert margin_state(0.6) == "danger"
    assert margin_state(None) == "ok"


def test_position_row_from_api_shape():
    raw = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "leverage": 10,
        "qty": "0.5",
        "avgOpenPrice": "30000",
        "unrealizedPNL": "1.5",
        "liqPrice": "22209",
        "marginRate": "0.01",
    }
    row = position_row(raw, mark=30000.0)
    assert row["symbol"] == "BTCUSDT"
    assert row["side"] == "LONG"
    assert row["leverage"] == 10
    assert round(row["distance"], 2) == 25.97
    assert row["margin_state"] == "ok"


def test_position_row_normalizes_buy_sell():
    """Real API returns BUY/SELL even though docs say LONG/SHORT."""
    buy = position_row({"symbol": "X", "side": "BUY", "marginRate": "0.01"}, 100.0)
    sell = position_row({"symbol": "Y", "side": "SELL", "marginRate": "0.7"}, 100.0)
    assert buy["side"] == "LONG"
    assert sell["side"] == "SHORT"
    assert sell["margin_state"] == "danger"


if __name__ == "__main__":
    test_liq_distance_pct_long()
    test_liq_distance_pct_short_above_mark()
    test_liq_distance_pct_no_liquidation()
    test_margin_state()
    test_position_row_from_api_shape()
    test_position_row_normalizes_buy_sell()
    print("ok: positions parsing works")
