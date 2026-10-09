"""R3 contract: resumable, throttled historical candle backfill.

The command paginates BACKWARD via ``endTime``. Tests drive the module-level
``run()`` seam with a stub client and a recording ``sleep`` (no real delays,
no sockets), then prove the ``call_command`` wiring. A stub returns descending
pages keyed by the requested cursor.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import requests
from django.core.management import call_command
from trading.models import Candle

from src.client import BitunixError

EPOCH_DAY = int(datetime(2023, 11, 15, tzinfo=UTC).timestamp())


def _ts(day: int, hour: int = 0) -> int:
    """Epoch-seconds for 2023-11-<day> hour:00 UTC."""
    return int(datetime(2023, 11, day, hour, tzinfo=UTC).timestamp())


class SeriesClient:
    """Stub client: serves descending candles strictly below the end_time cursor."""

    def __init__(self, series: dict[tuple[str, str], list[int]]):
        self._series = series
        self.calls: list[tuple[str, str, int, int | None]] = []

    def kline(
        self, symbol, interval, limit=100, start_time=None, end_time=None
    ) -> list[dict]:
        self.calls.append((symbol, interval, limit, end_time))
        times = self._series.get((symbol, interval), [])
        upper = end_time // 1000 if end_time is not None else 10**12
        chosen = sorted((t for t in times if t <= upper), reverse=True)[:limit]
        return [
            {
                "time": t,
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "quote_vol": None,
            }
            for t in chosen
        ]


class SleepRecorder:
    def __init__(self):
        self.calls: list[float] = []

    def __call__(self, seconds):
        self.calls.append(seconds)


class OutRecorder:
    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, message):
        self.lines.append(str(message))


def _run(client, series_intervals=("5m",), **overrides):
    from trading.management.commands.backfill_candles import run

    sleep, out = SleepRecorder(), OutRecorder()
    persisted = run(
        client,
        symbols=overrides.get("symbols", ["BTCUSDT"]),
        intervals=list(series_intervals),
        start=overrides.get("start"),
        end=overrides.get("end", "2023-11-15"),
        dry_run=overrides.get("dry_run", False),
        sleep=sleep,
        out=out,
    )
    return persisted, sleep, out


@pytest.mark.django_db
def test_backfill_persists_all_rows_and_logs_pages():
    client = SeriesClient({("BTCUSDT", "5m"): [_ts(14), _ts(14, 1), _ts(14, 2)]})

    persisted, sleep, out = _run(client)

    assert persisted == 3
    assert Candle.objects.count() == 3
    assert Candle.objects.filter(symbol="BTCUSDT", interval="5m").count() == 3
    # One sleep between the data page and the terminating empty page.
    assert len(sleep.calls) == 1
    assert any("5m" in line for line in out.lines)


@pytest.mark.django_db
def test_backfill_advances_cursor_from_oldest_row():
    client = SeriesClient({("BTCUSDT", "5m"): [_ts(14), _ts(14, 1)]})

    _run(client)

    # Second call must ask from oldest(1440)-1s in ms, not the original end.
    assert client.calls[0][3] == EPOCH_DAY * 1000
    assert client.calls[1][3] == _ts(14) * 1000 - 1


@pytest.mark.django_db
def test_backfill_rerun_is_idempotent():
    client = SeriesClient({("BTCUSDT", "5m"): [_ts(14), _ts(14, 1), _ts(14, 2)]})

    first, _, _ = _run(client)
    second, _, _ = _run(client)

    assert first == 3
    assert second == 0
    assert Candle.objects.count() == 3


@pytest.mark.django_db
def test_backfill_resumes_from_oldest_stored_time():
    Candle.objects.create(
        symbol="BTCUSDT",
        interval="5m",
        time=_ts(14),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
    )
    client = SeriesClient({("BTCUSDT", "5m"): [_ts(14), _ts(13)]})

    _run(client)

    # First request resumes from Min(time)-1ms, not from `end`.
    assert client.calls[0][3] == _ts(14) * 1000 - 1


@pytest.mark.django_db
def test_backfill_dry_run_persists_nothing():
    client = SeriesClient({("BTCUSDT", "5m"): [_ts(14), _ts(14, 1)]})

    persisted, _, _ = _run(client, dry_run=True)

    assert persisted == 0
    assert Candle.objects.count() == 0


@pytest.mark.django_db
def test_backfill_empty_page_stops_series_without_error():
    client = SeriesClient({})

    persisted, sleep, _ = _run(client)

    assert persisted == 0
    assert Candle.objects.count() == 0
    assert sleep.calls == []  # empty first page → no throttle


@pytest.mark.django_db
def test_backfill_start_bounds_earliest_candle():
    # Series spans three days; --start cuts at day 14.
    client = SeriesClient({("BTCUSDT", "5m"): [_ts(13), _ts(14), _ts(14, 1)]})

    _run(client, start="2023-11-14")

    times = sorted(Candle.objects.values_list("time", flat=True))
    assert times == [_ts(14), _ts(14, 1)]
    assert all(
        t * 1000 >= int(datetime(2023, 11, 14, tzinfo=UTC).timestamp()) * 1000
        for t in times
    )


@pytest.mark.django_db
def test_backfill_start_after_all_data_persists_nothing():
    # Whole page is older than --start -> filtered to empty -> break, no persist.
    client = SeriesClient({("BTCUSDT", "5m"): [_ts(13), _ts(14)]})

    persisted, _, _ = _run(client, start="2023-11-20", end="2023-11-21")

    assert persisted == 0
    assert Candle.objects.count() == 0


@pytest.mark.django_db
def test_backfill_stops_when_upstream_ignores_endtime():
    # Defensive: a client that never advances the cursor would loop forever.
    class StuckClient(SeriesClient):
        def kline(self, symbol, interval, limit=100, start_time=None, end_time=None):
            return super().kline(symbol, interval, limit, start_time, end_time=None)

    client = StuckClient({("BTCUSDT", "5m"): [_ts(14), _ts(14, 1)]})

    persisted, _, out = _run(client, end="2023-11-20")

    assert any("no progress" in line for line in out.lines)
    assert persisted <= 2  # bounded: does not spin


@pytest.mark.django_db
def test_backfill_error_aborts_series_but_continues_next():
    class FlakyClient(SeriesClient):
        def kline(self, symbol, interval, limit=100, start_time=None, end_time=None):
            if interval == "5m":
                raise BitunixError(500, "boom")
            return super().kline(symbol, interval, limit, start_time, end_time)

    client = FlakyClient({("BTCUSDT", "1h"): [_ts(14)]})

    persisted, _, out = _run(client, series_intervals=("5m", "1h"))

    assert persisted == 1  # 5m aborted, 1h persisted
    assert Candle.objects.filter(interval="1h").count() == 1
    assert any("aborted" in line for line in out.lines)


@pytest.mark.django_db
def test_backfill_request_exception_also_aborts_series():
    class RefusedClient(SeriesClient):
        def kline(self, symbol, interval, limit=100, start_time=None, end_time=None):
            raise requests.ConnectionError("refused")

    persisted, _, out = _run(RefusedClient({}))

    assert persisted == 0
    assert any("aborted" in line for line in out.lines)


@pytest.mark.django_db
def test_backfill_defaults_end_to_now():
    client = SeriesClient({("BTCUSDT", "5m"): []})

    _run(client, end=None)

    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    assert abs(client.calls[0][3] - now_ms) < 60_000


@pytest.mark.django_db
def test_call_command_wires_bitunix_client(monkeypatch):
    from trading.management.commands import backfill_candles

    client = SeriesClient({("BTCUSDT", "5m"): [_ts(14), _ts(14, 1)]})
    monkeypatch.setattr(backfill_candles, "BitunixClient", lambda: client)

    call_command(
        "backfill_candles",
        symbols=["BTCUSDT"],
        intervals=["5m"],
        end="2023-11-15",
        sleep=0,
    )

    assert Candle.objects.count() == 2
    assert client.calls[0][0] == "BTCUSDT"
    assert client.calls[0][1] == "5m"
    # CLI defaults the page limit to the command constant.
    assert client.calls[0][2] == backfill_candles.PAGE_LIMIT
