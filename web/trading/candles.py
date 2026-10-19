"""Closed-candle ingestion seam (R4).

Owns the interval→seconds mapping used to decide when a candle bucket has
closed, and the idempotent persistence helper. ``ingest.py`` stays
snapshot-focused; candles are a real second concern with their own deep module.

``INTERVAL_SECONDS`` values are pinned by design: 1w is exactly 7d (UTC epoch,
DST-free) and 1M is 31d — the longest month — which guarantees the bucket ended
for every month, never persisting a partial candle (cost: a ≤3 day delay on
shorter months; backfill covers history).
"""

from __future__ import annotations

import logging
import time

import requests

from src.client import BitunixError
from trading.models import Candle

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = {
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
    "1M": 2678400,
}

CANDLE_INTERVALS = tuple(INTERVAL_SECONDS)


def _now_seconds() -> int:
    """Wall clock in UNIX seconds (seam for deterministic tests)."""
    return int(time.time())


def is_closed(candle_time: int, interval: str, now: int) -> bool:
    """True when the candle's bucket window has fully elapsed.

    ``candle_time`` is the bucket OPEN in UNIX seconds. A fixed interval is
    closed once ``now`` reaches open + span, so the still-forming candle is
    never persisted.
    """
    return now >= candle_time + INTERVAL_SECONDS[interval]


def due_intervals(now: int, last_poll: int | None) -> tuple[str, ...]:
    """Intervals whose bucket rolled over since ``last_poll`` (F11 A-S3).

    Pure: no clock read, no I/O. A fresh process (``last_poll is None``) returns
    every interval once, which is the documented restart burst; the worker's
    cycle throttle absorbs it. Without this guard a 50-symbol watchlist would
    request 8 intervals each cycle (~13 req/s, over the exchange's 10 req/s).
    """
    if last_poll is None:
        return CANDLE_INTERVALS
    return tuple(
        name
        for name, span in INTERVAL_SECONDS.items()
        if now // span != last_poll // span
    )


def fetch_closed_candles(client, symbols, now=None, intervals=None) -> list[dict]:
    """Fetch the just-closed candle per symbol × interval.

    ``limit=2`` returns the forming candle plus the one that just closed; only
    closed buckets are kept. Each row is tagged with its ``symbol``/``interval``
    so the flat list is directly persistable.

    ``intervals`` defaults to every ``CANDLE_INTERVALS`` entry (back-compat). A
    per-(symbol, interval) failure is logged and skipped so one bad pair can
    never abort the whole cycle (F11 spec R7).
    """
    now = _now_seconds() if now is None else now
    interval_names = CANDLE_INTERVALS if intervals is None else tuple(intervals)
    closed: list[dict] = []
    for symbol in symbols:
        for interval in interval_names:
            try:
                rows = client.kline(symbol, interval, 2)
            except (BitunixError, requests.RequestException):
                logger.warning(
                    "candle fetch failed symbol=%s interval=%s", symbol, interval
                )
                continue
            for row in rows:
                if is_closed(row["time"], interval, now):
                    closed.append(
                        {
                            "symbol": symbol,
                            "interval": interval,
                            "time": row["time"],
                            "open": row["open"],
                            "high": row["high"],
                            "low": row["low"],
                            "close": row["close"],
                            "quote_vol": row["quote_vol"],
                        }
                    )
    return closed


def persist_candles(rows) -> int:
    """Persist candle dicts, swallowing duplicate (symbol, interval, time).

    ``bulk_create(ignore_conflicts=True)`` returns every attempted object, not
    the inserted ones, so the count comes from a row-count delta.
    """
    if not rows:
        return 0
    before = Candle.objects.count()
    Candle.objects.bulk_create([Candle(**row) for row in rows], ignore_conflicts=True)
    return Candle.objects.count() - before
