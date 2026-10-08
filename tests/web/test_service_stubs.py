"""R4/R5 contract: real worker loop + scheduler stub.

The worker loop is driven with an injected stub market client, an injectable
``stop`` flag and a recording ``sleep``, so every branch (cycle, backoff, stop)
runs without sockets or real sleeps. ``redis.Redis.ping`` is mocked so the
scheduler stays a boot-only stub that needs no broker.
"""

from __future__ import annotations

import signal

import pytest
import redis
import requests
import scheduler
import worker
from trading.models import FundingSnapshot, TickerSnapshot

from src.client import BitunixError

FIXTURE_TICKERS = [
    {
        "symbol": "BTCUSDT",
        "lastPrice": "50000.5",
        "high": "51000",
        "low": "49000",
        "quoteVol": "123456",
    },
    {
        "symbol": "ETHUSDT",
        "lastPrice": "3000.25",
        "high": "3100",
        "low": "2900",
        "quoteVol": "654321",
    },
]

FIXTURE_FUNDING = [
    {
        "symbol": "BTCUSDT",
        "fundingRate": "0.0001",
        "fundingInterval": "8",
        "nextFundingTime": "1700000000000",
        "markPrice": "50001",
        "indexPrice": "50000",
    },
    {
        "symbol": "ETHUSDT",
        "fundingRate": "-0.0002",
        "fundingInterval": "4",
        "nextFundingTime": "1700000001000",
        "markPrice": "3001",
        "indexPrice": "3000",
    },
]


class StubClient:
    """Read-only double; raises ``error`` on the first ``fail_times`` calls."""

    def __init__(self, fail_times: int = 0, error: Exception | None = None):
        self._fail_times = fail_times
        self._error = error or BitunixError(500, "boom")

    def tickers(self, symbols=None):
        if self._fail_times > 0:
            self._fail_times -= 1
            raise self._error
        return FIXTURE_TICKERS

    def funding_rate_batch(self):
        return FIXTURE_FUNDING


class SleepRecorder:
    """Injectable ``sleep`` that records the backoff it was asked to wait."""

    def __init__(self):
        self.calls: list[float] = []

    def __call__(self, seconds):
        self.calls.append(seconds)


@pytest.fixture
def fake_redis(monkeypatch):
    """Redis that never connects: ping is a no-op returning True."""
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(redis.Redis, "ping", lambda self: True)


@pytest.mark.django_db
def test_worker_one_cycle_ingests_and_returns_zero():
    sleep = SleepRecorder()

    result = worker.run_loop(
        StubClient(), ["BTCUSDT", "ETHUSDT"], iterations=1, sleep=sleep
    )

    assert result == 0
    assert FundingSnapshot.objects.count() == 2
    assert TickerSnapshot.objects.count() == 2
    btc = FundingSnapshot.objects.get(symbol="BTCUSDT")
    assert btc.next_funding_time == 1_700_000_000_000
    # One poll delay after the successful cycle, then exit.
    assert sleep.calls == [worker.INGEST_POLL_SECONDS]


@pytest.mark.django_db
def test_worker_backs_off_on_bitunix_error_then_recovers():
    sleep = SleepRecorder()

    result = worker.run_loop(
        StubClient(fail_times=1), ["BTCUSDT"], iterations=2, sleep=sleep
    )

    assert result == 0
    # First cycle failed → backoff doubles; second cycle succeeded → reset.
    assert sleep.calls == [
        worker.INGEST_POLL_SECONDS * 2,
        worker.INGEST_POLL_SECONDS,
    ]
    assert FundingSnapshot.objects.count() == 1
    assert TickerSnapshot.objects.count() == 1


@pytest.mark.django_db
def test_worker_backs_off_on_request_exception_then_recovers():
    # Triangulation: the other caught error type takes the same backoff branch.
    sleep = SleepRecorder()
    client = StubClient(fail_times=1, error=requests.RequestException("timeout"))

    result = worker.run_loop(client, ["BTCUSDT"], iterations=2, sleep=sleep)

    assert result == 0
    assert sleep.calls == [
        worker.INGEST_POLL_SECONDS * 2,
        worker.INGEST_POLL_SECONDS,
    ]
    assert FundingSnapshot.objects.count() == 1


@pytest.mark.django_db
def test_worker_backoff_is_capped_at_300_seconds():
    # Successive failures keep doubling but never exceed the 300s ceiling.
    sleep = SleepRecorder()
    client = StubClient(fail_times=5)

    result = worker.run_loop(client, ["BTCUSDT"], iterations=5, sleep=sleep)

    assert result == 0
    assert sleep.calls == [60, 120, 240, 300, 300]
    assert FundingSnapshot.objects.count() == 0


@pytest.mark.django_db
def test_worker_stop_exits_between_cycles():
    sleep = SleepRecorder()
    stop_signals = iter([False, True])

    result = worker.run_loop(
        StubClient(),
        ["BTCUSDT"],
        iterations=None,
        stop=lambda: next(stop_signals),
        sleep=sleep,
    )

    assert result == 0
    # Exactly one cycle ran before the stop flag flipped true.
    assert FundingSnapshot.objects.count() == 1
    assert TickerSnapshot.objects.count() == 1
    assert sleep.calls == [worker.INGEST_POLL_SECONDS]


@pytest.mark.django_db
def test_worker_stop_set_before_first_cycle_ingests_nothing():
    sleep = SleepRecorder()

    result = worker.run_loop(
        StubClient(), ["BTCUSDT"], iterations=None, stop=lambda: True, sleep=sleep
    )

    assert result == 0
    assert FundingSnapshot.objects.count() == 0
    assert TickerSnapshot.objects.count() == 0
    assert sleep.calls == []


@pytest.mark.django_db
def test_worker_main_boots_one_iteration():
    sleep = SleepRecorder()

    result = worker.main(
        iterations=1,
        client=StubClient(),
        symbols=["BTCUSDT"],
        stop=lambda: False,
        sleep=sleep,
    )

    assert result == 0
    assert FundingSnapshot.objects.count() == 1
    assert TickerSnapshot.objects.count() == 1


def test_install_signal_handlers_returns_unset_event():
    stop = worker._install_signal_handlers()
    assert not stop.is_set()


def test_signal_handler_sets_stop_event():
    # The installed handler flips the event; invoke it directly (no real signal).
    original = signal.getsignal(signal.SIGTERM)
    try:
        stop = worker._install_signal_handlers()
        handler = signal.getsignal(signal.SIGTERM)
        handler(signal.SIGTERM, None)
        assert stop.is_set()
    finally:
        signal.signal(signal.SIGTERM, original)


def test_scheduler_boots_one_iteration(fake_redis):
    # Scheduler stays a boot-only stub sharing worker.idle_loop.
    assert scheduler.main(iterations=1) == 0
