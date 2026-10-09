"""Resumable historical candle backfill (R3).

Paginates BACKWARD via ``endTime`` per (symbol, interval) until BitUnix depth
is exhausted or ``--start`` is reached. Idempotent by the unique
``(symbol, interval, time)`` key and resumable from the oldest stored ``time``,
so a partial run is always safe to re-run.

The loop lives in the module-level ``run()`` seam (mirrors ``worker.run_loop``)
so tests inject a stub client, ``sleep`` and ``out``; ``Command.handle`` only
parses CLI args and delegates.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import requests
from django.core.management.base import BaseCommand
from django.db.models import Min

from src.client import BitunixClient, BitunixError
from src.config import SYMBOLS
from trading.candles import CANDLE_INTERVALS, persist_candles
from trading.models import Candle

PAGE_LIMIT = 200
DEFAULT_SLEEP = 0.15


def _to_ms(value: str | None) -> int | None:
    """Parse a ``YYYY-MM-DD`` date (UTC midnight) to epoch ms."""
    if not value:
        return None
    midnight = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    return int(midnight.timestamp() * 1000)


def _now_ms() -> int:
    return int(time.time() * 1000)


def run(
    client,
    symbols,
    intervals,
    start,
    end,
    dry_run,
    sleep,
    out,
    delay=DEFAULT_SLEEP,
    max_pages=None,
) -> int:
    """Backfill every (symbol, interval); return the number of rows persisted.

    ``max_pages`` caps pages fetched across ALL series (one shared budget). A
    bounded run stops mid-series and returns what it persisted; the next run
    resumes from ``Min(time)`` and converges. ``None`` (default) is unlimited.
    """
    start_ms = _to_ms(start)
    end_ms = _to_ms(end)
    total = 0
    used = 0
    for symbol in symbols:
        for interval in intervals:
            remaining = None if max_pages is None else max_pages - used
            if remaining is not None and remaining <= 0:
                out("budget exhausted")
                return total
            persisted, spent = _backfill_series(
                client,
                symbol,
                interval,
                start_ms,
                end_ms,
                dry_run,
                sleep,
                out,
                delay,
                remaining,
            )
            total += persisted
            used += spent
    return total


def _backfill_series(
    client,
    symbol,
    interval,
    start_ms,
    end_ms,
    dry_run,
    throttle,
    out,
    delay,
    page_budget,
) -> tuple[int, int]:
    series = f"{symbol} {interval}"
    oldest = Candle.objects.filter(symbol=symbol, interval=interval).aggregate(
        Min("time")
    )["time__min"]
    if oldest is not None:
        cursor = oldest * 1000 - 1  # resume from oldest stored candle
    else:
        cursor = end_ms if end_ms is not None else _now_ms()

    persisted = 0
    pages = 0
    while True:
        if page_budget is not None and pages >= page_budget:
            out(f"{series}: budget exhausted after {pages} pages")
            break
        try:
            rows = client.kline(symbol, interval, PAGE_LIMIT, end_time=cursor)
        except (BitunixError, requests.RequestException) as exc:
            # Abort this series only; a re-run resumes from what was stored.
            out(f"{series}: aborted ({exc})")
            break
        if not rows:
            break
        pages += 1
        if start_ms is not None:
            rows = [r for r in rows if r["time"] * 1000 >= start_ms]
            if not rows:
                break
        if not dry_run:
            persisted += persist_candles(
                [
                    {
                        "symbol": symbol,
                        "interval": interval,
                        "time": r["time"],
                        "open": r["open"],
                        "high": r["high"],
                        "low": r["low"],
                        "close": r["close"],
                        "quote_vol": r["quote_vol"],
                    }
                    for r in rows
                ]
            )
        oldest_time = min(r["time"] for r in rows)
        out(f"{series}: page={len(rows)} oldest={oldest_time}")
        new_cursor = oldest_time * 1000 - 1
        if new_cursor >= cursor:
            # Defensive: if upstream ignored endTime the page did not advance;
            # stop instead of hammering the API in an infinite loop.
            out(f"{series}: no progress (cursor stuck at {cursor}); stopping")
            break
        cursor = new_cursor
        if start_ms is not None and oldest_time * 1000 <= start_ms:
            break
        throttle(delay)
    out(f"{series}: done persisted={persisted}")
    return persisted, pages


class Command(BaseCommand):
    help = "Backfill historical candles per symbol × interval (resumable)."

    def add_arguments(self, parser):
        parser.add_argument("--symbol", action="append", dest="symbols", default=None)
        parser.add_argument(
            "--interval", action="append", dest="intervals", default=None
        )
        parser.add_argument("--start", default=None)
        parser.add_argument("--end", default=None)
        parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--max-pages", type=int, default=None, dest="max_pages")

    def handle(self, *args, **options):
        symbols = options["symbols"] or SYMBOLS
        intervals = options["intervals"] or list(CANDLE_INTERVALS)
        total = run(
            BitunixClient(),
            symbols=symbols,
            intervals=intervals,
            start=options["start"],
            end=options["end"],
            dry_run=options["dry_run"],
            sleep=time.sleep,
            out=self.stdout.write,
            delay=options["sleep"],
            max_pages=options["max_pages"],
        )
        self.stdout.write(f"backfill done: {total} rows")
