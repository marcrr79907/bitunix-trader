"""Setup capture seam: persisted candles → SMC setups → ``trading.Setup`` rows.

Point-in-time only (spec R3): reads the candle window already persisted by the
worker, never fetches. The SMC composition lives in ``src/smc`` (pure); this
module owns env parsing, the DB read and the idempotent write, mirroring
``candles.persist_candles``. ``market/`` stays read-only: we only call
``_db_rows``, exactly as ``run_alert_rules`` does.
"""

from __future__ import annotations

import os

from market.quotes import _db_rows

from src.smc.config import SMC_ENGINE_VERSION
from src.smc.signals import capture_setups
from trading.candles import CANDLE_INTERVALS
from trading.models import Setup

# ponytail: matches ALERT_CANDLE_WINDOW so the ledger and the alert path see the
# same geometry; deep enough for RANGE_LOOKBACK + swing warm-up.
SETUP_CANDLE_WINDOW = 100
DEFAULT_CAPTURE_INTERVALS = ("1h",)


def capture_intervals() -> tuple[str, ...]:
    """Parse ``SETUP_CAPTURE_INTERVALS``, order-preserving and deduped.

    Raises ``ValueError`` naming every entry that is not a persisted candle
    interval: a quietly narrowed ledger would be worse than a loud failure.
    """
    raw = os.environ.get("SETUP_CAPTURE_INTERVALS", "")
    requested = [part.strip() for part in raw.split(",") if part.strip()]
    intervals = tuple(dict.fromkeys(requested)) or DEFAULT_CAPTURE_INTERVALS

    unknown = [interval for interval in intervals if interval not in CANDLE_INTERVALS]
    if unknown:
        raise ValueError(
            "SETUP_CAPTURE_INTERVALS has unknown interval(s): "
            + ", ".join(unknown)
            + f"; valid: {', '.join(CANDLE_INTERVALS)}"
        )
    return intervals


def _records(symbol: str, interval: str) -> list:
    """Run the pure chain over one persisted window; ``[]`` when too thin."""
    rows = _db_rows(symbol, interval, None, SETUP_CANDLE_WINDOW)
    if len(rows) < 3:
        return []
    return capture_setups(
        [row["open"] for row in rows],
        [row["high"] for row in rows],
        [row["low"] for row in rows],
        [row["close"] for row in rows],
        [row["time"] for row in rows],
    )


def run_setup_capture(symbols) -> int:
    """Capture the current window for each symbol × interval; return rows added.

    ``bulk_create(ignore_conflicts=True)`` returns every attempted object, so
    the inserted count is a row-count delta (same precedent as
    ``persist_candles``). Zero network: only persisted candles are read.
    """
    intervals = capture_intervals()
    staged = []
    for symbol in symbols:
        for interval in intervals:
            for record in _records(symbol, interval):
                if not record.anchor_time:  # defensive: never a half row
                    continue
                staged.append(
                    Setup(
                        symbol=symbol,
                        interval=interval,
                        anchor_time=record.anchor_time,
                        direction=record.direction,
                        entry=record.entry,
                        stop=record.stop,
                        take_profit=record.take_profit,
                        rr=record.rr,
                        score=record.score,
                        atr=record.atr,
                        engine_version=SMC_ENGINE_VERSION,
                    )
                )
    if not staged:
        return 0
    before = Setup.objects.count()
    Setup.objects.bulk_create(staged, ignore_conflicts=True)
    return Setup.objects.count() - before
