"""Alerts contract tests.

The antidebounce logic is the non-trivial part: a condition that stays true
must NOT re-alert every poll. Only the transition into the state fires.
"""

from src.alerts import AlertState, funding_alert, margin_alert


def test_funding_alert_threshold():
    assert funding_alert({"funding": 0.001}, 0.0005) is True
    assert funding_alert({"funding": -0.001}, 0.0005) is True  # abs
    assert funding_alert({"funding": 0.0001}, 0.0005) is False


def test_margin_alert_threshold():
    assert margin_alert({"margin_rate": 0.6}, 0.5) is True
    assert margin_alert({"margin_rate": 0.1}, 0.5) is False
    assert margin_alert({"margin_rate": None}, 0.5) is False


def test_antidebounce_fires_only_on_transition():
    st = AlertState()
    # first time true -> fire
    assert st.fire("funding:BTCUSDT", True) is True
    # still true next poll -> no fire
    assert st.fire("funding:BTCUSDT", True) is False
    # back to false -> no fire
    assert st.fire("funding:BTCUSDT", False) is False
    # true again -> fire (new transition)
    assert st.fire("funding:BTCUSDT", True) is True


def test_antidebounce_is_per_key():
    st = AlertState()
    assert st.fire("funding:BTCUSDT", True) is True
    assert st.fire("funding:ETHUSDT", True) is True  # different key, own state


if __name__ == "__main__":
    test_funding_alert_threshold()
    test_margin_alert_threshold()
    test_antidebounce_fires_only_on_transition()
    test_antidebounce_is_per_key()
    print("ok: alert rules work")
