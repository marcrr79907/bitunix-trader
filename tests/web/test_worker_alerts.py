"""R5/R7/R8 contract: worker alert-rule evaluation (issue #76, Fase D1).

``run_alert_rules`` reads every user's active rules unscoped (R14.4, trusted
zone), evaluates the pure engine over the persisted candle window, dedups by the
fired bar time (R5), and invokes the ``on_fired`` sink once per fire (R8). A bad
rule is logged and skipped without aborting its peers (R7); the ``run_once``
``(funding, ticker)`` contract is unaffected by an alert failure.
"""

from __future__ import annotations

import pytest
import worker
from trading.models import AlertRule, Candle, FundingSnapshot, TickerSnapshot

BASE_TIME = 1_700_000_000
HOUR = 3600
SYMBOL = "BTCUSDT"
INTERVAL = "1h"
ABOVE_100 = {"type": "price", "op": "above", "level": 100}


def _seed(symbol, interval, closes, start=BASE_TIME):
    """Persist one closed candle per close; ``time`` ascends by ``interval``."""
    span = HOUR if interval == INTERVAL else 60
    Candle.objects.bulk_create(
        [
            Candle(
                symbol=symbol,
                interval=interval,
                time=start + i * span,
                open=close,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                quote_vol=1.0,
            )
            for i, close in enumerate(closes)
        ]
    )


def _rule(user, **overrides):
    kwargs = {
        "user": user,
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "condition": ABOVE_100,
    }
    kwargs.update(overrides)
    return AlertRule.objects.create(**kwargs)


class Recorder:
    """Collects ``(rule, detail)`` sink calls."""

    def __init__(self):
        self.calls = []

    def __call__(self, rule, detail):
        self.calls.append((rule, detail))


# --- R5/R8: fire once per edge, then dedup by the fired bar time -------------


@pytest.mark.django_db
def test_fires_once_per_edge_and_invokes_sink(user_a):
    _seed(SYMBOL, INTERVAL, [99.0, 101.0])
    rule = _rule(user_a)
    sink = Recorder()

    assert worker.run_alert_rules(on_fired_sink=sink) == 1

    assert len(sink.calls) == 1
    fired_rule, detail = sink.calls[0]
    assert fired_rule.pk == rule.pk
    assert detail == {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "edge_time": BASE_TIME + HOUR,
        "condition": ABOVE_100,
    }
    rule.refresh_from_db()
    assert int(rule.last_fired_at.timestamp()) == BASE_TIME + HOUR


@pytest.mark.django_db
def test_same_bar_twice_fires_once(user_a):
    _seed(SYMBOL, INTERVAL, [99.0, 101.0])
    rule = _rule(user_a)
    sink = Recorder()

    assert worker.run_alert_rules(on_fired_sink=sink) == 1
    assert worker.run_alert_rules(on_fired_sink=sink) == 0

    assert len(sink.calls) == 1
    rule.refresh_from_db()
    assert int(rule.last_fired_at.timestamp()) == BASE_TIME + HOUR


@pytest.mark.django_db
def test_restart_does_not_refire_a_stamped_bar(user_a):
    from datetime import UTC, datetime

    _seed(SYMBOL, INTERVAL, [99.0, 101.0])
    rule = _rule(user_a)
    rule.last_fired_at = datetime.fromtimestamp(BASE_TIME + HOUR, tz=UTC)
    rule.save(update_fields=["last_fired_at"])
    sink = Recorder()

    # A fresh worker run over the already-fired bar must stay silent.
    assert worker.run_alert_rules(on_fired_sink=sink) == 0
    assert sink.calls == []


@pytest.mark.django_db
def test_new_edge_after_a_fired_bar_refires(user_a):
    _seed(SYMBOL, INTERVAL, [99.0, 101.0])
    _rule(user_a)
    sink = Recorder()

    assert worker.run_alert_rules(on_fired_sink=sink) == 1
    # A later false->true flip on a NEW bar (T2=99, T3=101) re-arms and fires.
    _seed(SYMBOL, INTERVAL, [99.0, 101.0], start=BASE_TIME + 2 * HOUR)

    assert worker.run_alert_rules(on_fired_sink=sink) == 1
    assert [c[1]["edge_time"] for c in sink.calls] == [
        BASE_TIME + HOUR,
        BASE_TIME + 3 * HOUR,
    ]


# --- R7: skip rules that cannot participate ---------------------------------


@pytest.mark.django_db
def test_inactive_rule_is_skipped(user_a):
    _seed(SYMBOL, INTERVAL, [99.0, 101.0])
    _rule(user_a, is_active=False)
    sink = Recorder()

    assert worker.run_alert_rules(on_fired_sink=sink) == 0
    assert sink.calls == []


@pytest.mark.django_db
def test_unsupported_interval_is_skipped(user_a):
    # "1m" is not in CANDLE_INTERVALS: never persisted closed, never evaluated.
    _seed(SYMBOL, "1m", [99.0, 101.0])
    _rule(user_a, interval="1m")
    sink = Recorder()

    assert worker.run_alert_rules(on_fired_sink=sink) == 0
    assert sink.calls == []


# --- R7: per-rule isolation --------------------------------------------------


@pytest.mark.django_db
def test_bad_condition_rule_is_skipped_but_peer_fires(user_a):
    _seed(SYMBOL, INTERVAL, [99.0, 101.0])
    _rule(user_a, condition={"type": "magic"})  # parse_condition raises ValueError
    peer = _rule(user_a)
    sink = Recorder()

    assert worker.run_alert_rules(on_fired_sink=sink) == 1
    assert [c[0].pk for c in sink.calls] == [peer.pk]


@pytest.mark.django_db
def test_engine_valueerror_does_not_abort_peers(user_a):
    _seed(SYMBOL, INTERVAL, [99.0, 101.0])
    _rule(user_a, condition={"type": "indicator", "name": "macd", "op": "above"})
    peer = _rule(user_a)
    sink = Recorder()

    assert worker.run_alert_rules(on_fired_sink=sink) == 1
    assert [c[0].pk for c in sink.calls] == [peer.pk]


@pytest.mark.django_db
def test_default_sink_handles_a_fire(user_a):
    # No sink injected: the module-level ``on_fired`` logger stub is the default.
    _seed(SYMBOL, INTERVAL, [99.0, 101.0])
    rule = _rule(user_a)

    assert worker.run_alert_rules() == 1
    rule.refresh_from_db()
    assert int(rule.last_fired_at.timestamp()) == BASE_TIME + HOUR


@pytest.mark.django_db
def test_unexpected_rule_error_is_isolated(user_a, monkeypatch):
    # A non-editor error (not swallowed by the total engine) must be caught by
    # the worker's per-rule guard, logged, and skip only the offending rule.
    _seed(SYMBOL, INTERVAL, [99.0, 101.0])
    bad = _rule(user_a, condition={"type": "price", "op": "above", "level": 1})
    peer = _rule(user_a)
    sink = Recorder()

    def exploding(condition, candles):
        if condition == {"type": "price", "op": "above", "level": 1}:
            raise RuntimeError("engine exploded")
        return condition["level"] < candles[-1]["close"]

    from src import alert_rules

    monkeypatch.setattr(alert_rules, "edge_fired", exploding)

    assert worker.run_alert_rules(on_fired_sink=sink) == 1
    assert [c[0].pk for c in sink.calls] == [peer.pk]
    assert bad.last_fired_at is None


# --- R14.4: unscoped read across users --------------------------------------


@pytest.mark.django_db
def test_rules_of_all_users_are_evaluated_unscoped(user_a, user_b):
    _seed(SYMBOL, INTERVAL, [99.0, 101.0])
    rule_a = _rule(user_a)
    rule_b = _rule(user_b)
    sink = Recorder()

    assert worker.run_alert_rules(on_fired_sink=sink) == 2
    assert {c[0].pk for c in sink.calls} == {rule_a.pk, rule_b.pk}


# --- R7: run_once isolation --------------------------------------------------


FIXTURE_TICKERS = [
    {
        "symbol": SYMBOL,
        "lastPrice": "50000.5",
        "high": "51000",
        "low": "49000",
        "quoteVol": "123456",
    }
]
FIXTURE_FUNDING = [
    {
        "symbol": SYMBOL,
        "fundingRate": "0.0001",
        "fundingInterval": "8",
        "nextFundingTime": "1700000000000",
        "markPrice": "50001",
        "indexPrice": "50000",
    }
]


class MarketStub:
    def tickers(self, symbols=None):
        return FIXTURE_TICKERS

    def funding_rate_batch(self):
        return FIXTURE_FUNDING

    def kline(self, symbol, interval="1m", limit=100, start_time=None, end_time=None):
        return []


@pytest.mark.django_db
def test_run_once_survives_alert_failure(monkeypatch):
    def boom(on_fired_sink=None):
        raise RuntimeError("alert boom")

    monkeypatch.setattr(worker, "run_alert_rules", boom)

    # Tick/private persistence still completes and no exception escapes.
    assert worker.run_once(MarketStub(), [SYMBOL]) == (1, 1)
    assert FundingSnapshot.objects.count() == 1
    assert TickerSnapshot.objects.count() == 1
