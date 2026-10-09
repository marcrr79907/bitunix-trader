"""Kline payload seam: candles + server-side overlays.

DB-first cursor page (R3/R4): read ``Candle`` for ``symbol/interval/time <
before`` newest-first, call BitUnix ONLY when the DB cannot fill
``limit + WARMUP`` (or the interval is unpersisted), merge DB-wins, compute
``src/indicators.py`` over the warm window and slice to the newest ``limit``.

Pure-ish (accepts any client with ``kline()``, so tests stub it without
monkeypatching). Indicator math lives ONLY in ``src/indicators.py`` — the
single source of truth; the browser never recomputes it.
"""

from __future__ import annotations

import logging
import time

import requests
from trading.candles import CANDLE_INTERVALS
from trading.models import Candle

from src import indicators
from src.client import BitunixError

logger = logging.getLogger(__name__)

INTERVALS = (
    "1m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1M",
)


CHART_KEYS = ("time", "open", "high", "low", "close")

# Extra candles fetched before the page boundary so every page-edge overlay
# (sma20/ema20 seed, rsi14) is defined, not omitted (delta R4).
WARMUP = 20


def _now_seconds() -> int:
    """Wall clock in UNIX seconds (seam for deterministic tests)."""
    return int(time.time())


def _db_rows(symbol: str, interval: str, before: int | None, want: int) -> list[dict]:
    """Newest ``want`` persisted rows ``< before`` (ascending), or ``[]``.

    Skips intervals the worker never persists (``CANDLE_INTERVALS``), so the
    endpoint still serves 1m/30m/6h/8h/12h/3d directly from upstream.
    """
    if interval not in CANDLE_INTERVALS:
        return []
    qs = Candle.objects.filter(symbol=symbol, interval=interval)
    if before is not None:
        qs = qs.filter(time__lt=before)
    newest_first = qs.order_by("-time")[:want]
    return [
        {
            "time": row.time,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
        }
        for row in reversed(newest_first)  # ascending for the merge/slice
    ]


def get_kline_payload(
    client, symbol: str, interval: str, limit: int, before: int | None = None
) -> dict:
    want = limit + WARMUP
    db = _db_rows(symbol, interval, before, want)

    upstream: list[dict] = []
    if len(db) < want:
        end_ms = (before if before is not None else _now_seconds()) * 1000
        try:
            upstream = client.kline(symbol, interval, want, end_time=end_ms)
        except (BitunixError, requests.RequestException):
            if not db:
                raise  # view maps: BitunixError -> 400, RequestException -> 502
            logger.warning("kline degraded symbol=%s interval=%s", symbol, interval)
            upstream = []

    # Merge, DB wins on duplicate ``time`` (the durable record is authoritative).
    merged = {c["time"]: c for c in upstream}
    merged.update({c["time"]: c for c in db})
    rows = sorted(merged.values(), key=lambda c: c["time"])[-want:]
    # Strip to exactly the chart's five keys: quote_vol must never reach the
    # response (delta R3).
    rows = [{k: c[k] for k in CHART_KEYS} for c in rows]

    times = [c["time"] for c in rows]
    closes = [c["close"] for c in rows]
    return {
        "candles": rows[-limit:],
        "overlays": {
            "sma20": _zip(times[-limit:], indicators.sma(closes, 20)[-limit:]),
            "ema20": _zip(times[-limit:], indicators.ema(closes, 20)[-limit:]),
            "rsi14": _zip(times[-limit:], indicators.rsi(closes, 14)[-limit:]),
        },
    }


def _zip(times, values):
    # Gaps omitted: Lightweight Charts series arrays must never contain null.
    # strict=False: indicator tails are intentionally shorter than `times`.
    return [
        {"time": t, "value": v}
        for t, v in zip(times, values, strict=False)
        if v is not None
    ]
