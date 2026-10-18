"""R4 contract: worker candle cycle + tick isolation.

``run_once`` must persist closed candles AFTER funding/ticker ingestion, and
any candle failure MUST leave the tick counts and the loop intact. The stub
client serves both the tick/funding endpoints and ``kline``.
"""

from __future__ import annotations

import pytest
import worker
from trading.candles import INTERVAL_SECONDS
from trading.models import Candle, FundingSnapshot, TickerSnapshot

FIXTURE_TICKERS = [
    {
        "symbol": "BTCUSDT",
        "lastPrice": "50000.5",
        "high": "51000",
        "low": "49000",
        "quoteVol": "123456",
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
]

# A closed 1h candle and a forming one, relative to the fixed run instant.
NOW_MS = 1_700_000_000_000
CLOSED_1H = {
    "time": NOW_MS // 1000 - INTERVAL_SECONDS["1h"],
    "open": 1.0,
    "high": 2.0,
    "low": 0.5,
    "close": 1.5,
    "quote_vol": 10.0,
}
FORMING_1H = {
    "time": NOW_MS // 1000 - 60,
    "open": 1.0,
    "high": 2.0,
    "low": 0.5,
    "close": 1.5,
    "quote_vol": 10.0,
}


class StubClient:
    """Serves ticks/funding and kline; optionally raises on kline."""

    def __init__(self, kline_error: Exception | None = None):
        self._kline_error = kline_error

    def tickers(self, symbols=None):
        return FIXTURE_TICKERS

    def funding_rate_batch(self):
        return FIXTURE_FUNDING

    def kline(self, symbol, interval="1m", limit=100, start_time=None, end_time=None):
        if self._kline_error is not None:
            raise self._kline_error
        # Only the 1h series returns rows; the newest is forming.
        if interval == "1h":
            return [FORMING_1H, CLOSED_1H]
        return []


@pytest.fixture(autouse=True)
def _freeze_now(monkeypatch):
    # Deterministic closure without freezing time module-wide in production.
    import trading.candles as candles

    monkeypatch.setattr(candles, "_now_seconds", lambda: NOW_MS // 1000, raising=False)
    # F11: the worker owns a module-global _last_poll. Reset it per test so the
    # due-interval state never leaks across tests (order-independence).
    monkeypatch.setattr(worker, "_last_poll", None, raising=False)


@pytest.mark.django_db
def test_run_once_persists_closed_candle_and_keeps_tick_counts():
    result = worker.run_once(StubClient(), ["BTCUSDT"])

    assert result == (1, 1)  # existing (funding, ticker) contract preserved
    assert FundingSnapshot.objects.count() == 1
    assert TickerSnapshot.objects.count() == 1
    # Only the closed candle persisted, tagged to its series.
    assert Candle.objects.count() == 1
    row = Candle.objects.get()
    assert row.interval == "1h"
    assert row.time == CLOSED_1H["time"]


@pytest.mark.django_db
def test_run_once_candle_failure_does_not_break_ticks():
    from src.client import BitunixError

    result = worker.run_once(
        StubClient(kline_error=BitunixError(500, "boom")), ["BTCUSDT"]
    )

    # Ticks still persisted; candle failure swallowed.
    assert result == (1, 1)
    assert FundingSnapshot.objects.count() == 1
    assert TickerSnapshot.objects.count() == 1
    assert Candle.objects.count() == 0


@pytest.mark.django_db
def test_run_once_unexpected_candle_error_is_isolated():
    # Broad `except Exception` is deliberate: a candle bug MUST never kill ticks.
    result = worker.run_once(
        StubClient(kline_error=ValueError("unexpected")), ["BTCUSDT"]
    )

    assert result == (1, 1)
    assert TickerSnapshot.objects.count() == 1
    assert Candle.objects.count() == 0


@pytest.mark.django_db
def test_run_loop_survives_candle_failure():
    class SleepRecorder:
        def __init__(self):
            self.calls = []

        def __call__(self, seconds):
            self.calls.append(seconds)

    sleep = SleepRecorder()
    from src.client import BitunixError

    result = worker.run_loop(
        StubClient(kline_error=BitunixError(500, "boom")),
        ["BTCUSDT"],
        iterations=1,
        sleep=sleep,
    )

    assert result == 0
    assert TickerSnapshot.objects.count() == 1


# --- F11 A-S3: due-interval scheduling and the watchlist union --------------

from trading.candles import CANDLE_INTERVALS, due_intervals  # noqa: E402


def test_due_intervals_same_bucket_omits_the_interval():
    # 1h bucket: 0 and 3599 are the same bucket (5m/15m DO roll over).
    assert "1h" not in due_intervals(3599, 0)
    assert "1d" not in due_intervals(3599, 0)


def test_due_intervals_boundary_includes_the_rolled_interval():
    assert "1h" in due_intervals(3600, 3599)


def test_due_intervals_fresh_process_returns_every_interval():
    assert due_intervals(1_700_000_000, None) == CANDLE_INTERVALS


def test_due_intervals_is_pure_and_deterministic():
    assert due_intervals(100, 0) == due_intervals(100, 0)


def test_fetch_closed_candles_honours_the_intervals_argument():
    import trading.candles as candles

    class Recorder:
        def __init__(self):
            self.calls = []

        def kline(
            self, symbol, interval="1m", limit=100, start_time=None, end_time=None
        ):
            self.calls.append(interval)
            return []

    recorder = Recorder()
    candles.fetch_closed_candles(recorder, ["BTCUSDT"], intervals=("1h",))

    assert recorder.calls == ["1h"]


def test_fetch_closed_candles_isolates_one_failing_interval():
    import trading.candles as candles

    from src.client import BitunixError

    class Flaky:
        def __init__(self):
            self.calls = []

        def kline(
            self, symbol, interval="1m", limit=100, start_time=None, end_time=None
        ):
            self.calls.append(interval)
            if interval == "1h":
                raise BitunixError(500, "boom")
            return []

    flaky = Flaky()
    result = candles.fetch_closed_candles(
        flaky, ["BTCUSDT"], intervals=("1h", "1d"), now=10**9
    )

    # The 1h failure did not stop the 1d request.
    assert flaky.calls == ["1h", "1d"]
    assert result == []


# --- worker: union ingest set ----------------------------------------------


@pytest.mark.django_db
def test_ingest_symbols_puts_defaults_first_then_sorted_watchlist(
    monkeypatch,
):
    from django.contrib.auth import get_user_model
    from trading.models import Watchlist

    monkeypatch.setattr(worker.config, "SYMBOLS", ["BTCUSDT"])
    user = get_user_model().objects.create_user(
        email="w@example.com", password="pw-123456"
    )
    Watchlist.objects.create(user=user, symbol="SOLUSDT")
    Watchlist.objects.create(user=user, symbol="ETHUSDT")

    assert worker.ingest_symbols() == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


@pytest.mark.django_db
def test_ingest_symbols_caps_and_never_starves_defaults(monkeypatch):
    from django.contrib.auth import get_user_model
    from trading.models import Watchlist

    monkeypatch.setattr(worker.config, "SYMBOLS", ["AAAUSDT", "BBBUSDT"])
    monkeypatch.setattr(worker.config, "MAX_WATCHLIST_SYMBOLS", 5)
    user = get_user_model().objects.create_user(
        email="w2@example.com", password="pw-123456"
    )
    Watchlist.objects.bulk_create(
        [Watchlist(user=user, symbol=f"SYM{i:02d}USDT") for i in range(10)]
    )

    result = worker.ingest_symbols()

    assert len(result) == 5
    assert result[0] == "AAAUSDT" and result[1] == "BBBUSDT"


@pytest.mark.django_db
def test_ingest_symbols_dedups_a_default_that_is_also_watched(monkeypatch):
    from django.contrib.auth import get_user_model
    from trading.models import Watchlist

    monkeypatch.setattr(worker.config, "SYMBOLS", ["BTCUSDT"])
    user = get_user_model().objects.create_user(
        email="w3@example.com", password="pw-123456"
    )
    Watchlist.objects.create(user=user, symbol="BTCUSDT")

    assert worker.ingest_symbols() == ["BTCUSDT"]


@pytest.mark.django_db
def test_last_poll_advances_only_after_a_successful_cycle(monkeypatch):
    import trading.candles as candles

    monkeypatch.setattr(worker, "_last_poll", None)
    monkeypatch.setattr(candles, "_now_seconds", lambda: 1000, raising=False)

    worker.run_once(StubClient(), ["BTCUSDT"])

    assert worker._last_poll is not None


@pytest.mark.django_db
def test_run_loop_uses_the_ingest_set_when_symbols_is_none(monkeypatch):
    from django.contrib.auth import get_user_model
    from trading.models import Watchlist

    calls = []
    monkeypatch.setattr(worker.config, "SYMBOLS", ["BTCUSDT"])
    monkeypatch.setattr(
        worker, "run_once", lambda client, symbols: (calls.append(symbols), (0, 0))[1]
    )
    user = get_user_model().objects.create_user(
        email="loop@example.com", password="pw-123456"
    )
    Watchlist.objects.create(user=user, symbol="ETHUSDT")

    worker.run_loop(None, symbols=None, iterations=1, sleep=lambda s: None)

    assert calls == [["BTCUSDT", "ETHUSDT"]]


@pytest.mark.django_db
def test_run_loop_keeps_an_explicit_symbol_list(monkeypatch):
    calls = []
    monkeypatch.setattr(worker.config, "SYMBOLS", ["BTCUSDT"])
    monkeypatch.setattr(
        worker, "ingest_symbols", lambda: (_ for _ in ()).throw(AssertionError("no"))
    )
    monkeypatch.setattr(
        worker, "run_once", lambda client, symbols: (calls.append(symbols), (0, 0))[1]
    )

    worker.run_loop(None, symbols=["SOLUSDT"], iterations=1, sleep=lambda s: None)

    assert calls == [["SOLUSDT"]]
