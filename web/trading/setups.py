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
from trading.candles import CANDLE_INTERVALS, INTERVAL_SECONDS
from trading.models import Setup

# ponytail: parity with every consumer of the same setups — the chart's
# SIGNALS_LIMIT, MAX_LIMIT and the analytics LIMIT are all 200, and
# find_structure is path-dependent (it seeds its trend at the first break in
# the window), so a shorter window yields a DIFFERENT signal, not a suffix.
SMC_WINDOW = 200
DEFAULT_CAPTURE_INTERVALS = ("1h",)


def engine_stamp() -> str:
    """Engine version fingerprinted with the window geometry.

    find_structure is path-dependent, so the same engine over a different
    window is a different engine. Encoding the window in the stamp keeps the
    unique constraint from swallowing rows derived under new geometry —
    without it, widening the window would silently collide with old rows.
    """
    return f"{SMC_ENGINE_VERSION}:w{SMC_WINDOW}"


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
    """Run the pure chain over one persisted window; ``[]`` when too thin.

    A gappy window is consumed as-is, but a gap shifts every index and
    re-seeds structure differently, so a window with holes must not be
    mistaken for a contiguous one.
    """
    rows = _db_rows(symbol, interval, None, SMC_WINDOW)
    if len(rows) < 3:
        return []
    span = rows[-1]["time"] - rows[0]["time"]
    if span != (len(rows) - 1) * INTERVAL_SECONDS[interval]:
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
    stamp = engine_stamp()
    staged = []
    for symbol in symbols:
        for interval in intervals:
            for record in _records(symbol, interval):
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
                        engine_version=stamp,
                    )
                )
    if not staged:
        return 0
    # bulk_create(ignore_conflicts=True) cannot report what actually inserted,
    # so the honest count is a delta. The pre-scan runs only when there is
    # something to insert (rare: about once per closed candle), not on every
    # no-op cycle.
    before = Setup.objects.count()
    Setup.objects.bulk_create(staged, ignore_conflicts=True)
    return Setup.objects.count() - before
