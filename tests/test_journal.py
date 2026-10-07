"""Journal metrics contract tests.

The money math is the risk-facing part: net PnL discounts fees, win rate
counts only positive net trades. Pinned with pure-function tests.
"""

from src.journal import metrics


def _trade(symbol, pnl, fee):
    return {"symbol": symbol, "realized_pnl": pnl, "fee": fee}


def test_net_pnl_discounts_fee():
    rows = [_trade("BTCUSDT", 10.0, 0.5), _trade("BTCUSDT", -3.0, 0.2)]
    m = metrics(rows)
    # net: 9.5 + (-3.2) = 6.3
    assert round(m["net_pnl"], 2) == 6.3
    assert m["trades"] == 2


def test_win_rate_counts_positive_net():
    rows = [
        _trade("BTCUSDT", 10.0, 0.5),  # win
        _trade("ETHUSDT", -3.0, 0.2),  # loss
        _trade("SOLUSDT", 1.0, 0.5),  # win (net 0.5)
        _trade("SOLUSDT", 0.3, 0.5),  # loss (net -0.2)
    ]
    m = metrics(rows)
    assert m["wins"] == 2
    assert m["trades"] == 4
    assert round(m["win_rate"], 1) == 50.0


def test_per_symbol_net_and_best_worst():
    rows = [
        _trade("BTCUSDT", 10.0, 0.0),
        _trade("BTCUSDT", 5.0, 0.0),
        _trade("ETHUSDT", -4.0, 0.0),
    ]
    m = metrics(rows)
    assert m["per_symbol"]["BTCUSDT"] == 15.0
    assert m["per_symbol"]["ETHUSDT"] == -4.0
    assert m["best"] == ("BTCUSDT", 15.0)
    assert m["worst"] == ("ETHUSDT", -4.0)


def test_empty_is_safe():
    m = metrics([])
    assert m["trades"] == 0
    assert m["net_pnl"] == 0.0
    assert m["win_rate"] == 0.0
    assert m["best"] is None
    assert m["worst"] is None


if __name__ == "__main__":
    test_net_pnl_discounts_fee()
    test_win_rate_counts_positive_net()
    test_per_symbol_net_and_best_worst()
    test_empty_is_safe()
    print("ok: journal metrics work")
