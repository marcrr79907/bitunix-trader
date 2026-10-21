"""Resolve every fully-horizoned setup into a ``SetupOutcome`` row (R6/R7).

Reads only ``Setup`` + ``Candle``, writes only ``SetupOutcome`` — zero
network, zero orders. A setup is eligible only when the FULL horizon of
candles is available: ``now >= anchor_time + horizon_bars * interval_seconds``
(the canonical mapping from ``trading.candles``); ineligible setups are
skipped without a write. Resolution math lives in the pure ``resolve_setup``
(``src/smc``); persistence is an idempotent ``update_or_create`` keyed by the
OneToOne, so re-runs overwrite instead of duplicating.

The loop lives in the module-level ``run()`` seam (mirrors
``backfill_candles``/``prune_snapshots``) with ``now`` injected ONCE so no
wall clock enters the loop; ``handle`` only parses CLI flags and reads it.
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from src.smc.signals import resolve_setup
from trading.candles import INTERVAL_SECONDS
from trading.models import Candle, Setup, SetupOutcome

DEFAULT_HORIZON = 200


def _eligible(setup, horizon_bars: int, now: int) -> bool:
    """True when the full horizon window exists for this setup."""
    return now >= setup.anchor_time + horizon_bars * INTERVAL_SECONDS[setup.interval]


def run(
    now,
    interval=None,
    horizon_bars=DEFAULT_HORIZON,
    max_setups=None,
    dry_run=False,
    out=print,
) -> int:
    """Evaluate eligible setups in ascending-anchor order; return rows written.

    ``now`` is injected (epoch seconds) and read once by the caller. ``interval``
    filters the ledger when given (absent → every interval); an unknown value
    raises ``ValueError`` naming it — a quietly narrowed run is worse than a
    loud failure. ``max_setups`` bounds how many setups are processed per run.
    ``dry_run`` computes and reports but writes nothing.
    """
    if interval is not None and interval not in INTERVAL_SECONDS:
        raise ValueError(
            f"unknown interval: {interval}; valid: {', '.join(INTERVAL_SECONDS)}"
        )

    setups = Setup.objects.order_by("anchor_time", "id")
    if interval is not None:
        setups = setups.filter(interval=interval)
    if max_setups is not None:
        setups = setups[:max_setups]

    evaluated = skipped = 0
    for setup in setups:
        if not _eligible(setup, horizon_bars, now):
            skipped += 1
            out(f"{setup.symbol} {setup.interval}: skipped (horizon incomplete)")
            continue
        candles = list(
            Candle.objects.filter(
                symbol=setup.symbol,
                interval=setup.interval,
                time__gt=setup.anchor_time,
            )
            .order_by("time")
            .values_list("time", "high", "low")[:horizon_bars]
        )
        record = resolve_setup(
            setup.direction,
            setup.entry,
            setup.stop,
            setup.take_profit,
            candles,
            horizon_bars=horizon_bars,
        )
        label = f"{setup.symbol} {setup.interval}"
        if dry_run:
            out(f"{label}: would_write={record.status}")
        else:
            SetupOutcome.objects.update_or_create(
                setup=setup,
                defaults={
                    "status": record.status,
                    "resolved_time": record.resolved_time,
                    "bars_to_resolution": record.bars_to_resolution,
                    "mfe_r": record.mfe_r,
                    "mae_r": record.mae_r,
                    "sl_then_tp": record.sl_then_tp,
                    "horizon_bars": horizon_bars,
                    # The stamp is copied verbatim (R8): re-evaluation never
                    # rewrites it — it belongs to the setup, not the outcome.
                    "engine_version": setup.engine_version,
                },
            )
            out(f"{label}: {record.status}")
        evaluated += 1
    out(f"evaluate done: evaluated={evaluated} skipped={skipped}")
    return evaluated


class Command(BaseCommand):
    help = (
        "Resolve setups whose full candle horizon is available into "
        "SetupOutcome rows (idempotent, zero network)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--interval", default=None)
        parser.add_argument(
            "--horizon-bars", type=int, default=DEFAULT_HORIZON, dest="horizon_bars"
        )
        parser.add_argument("--max-setups", type=int, default=None, dest="max_setups")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        run(
            int(time.time()),
            interval=options["interval"],
            horizon_bars=options["horizon_bars"],
            max_setups=options["max_setups"],
            dry_run=options["dry_run"],
            out=self.stdout.write,
        )
