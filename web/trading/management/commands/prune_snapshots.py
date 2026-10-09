"""Bounded retention for the 30s tick tables (R1).

Deletes ``FundingSnapshot`` and ``TickerSnapshot`` rows older than an injected
``cutoff``, in pk-batches to bound each transaction's lock. ``Candle`` is
deliberately out of scope: the store has indefinite retention.

The loop lives in the module-level ``run()`` seam (mirrors ``backfill_candles``)
so tests inject the ``cutoff`` and an ``out`` sink; ``handle`` only parses CLI
args, derives ``cutoff = now(UTC) - timedelta(days=older_than)`` and delegates.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from django.core.management.base import BaseCommand

from trading.models import FundingSnapshot, TickerSnapshot

DEFAULT_BATCH_SIZE = 5000


def run(cutoff, batch_size, dry_run, out) -> int:
    """Delete tick rows with ``ts < cutoff``; return the total deleted."""
    total = 0
    for model in (FundingSnapshot, TickerSnapshot):
        qs = model.objects.filter(ts__lt=cutoff)
        if dry_run:
            n = qs.count()
            out(f"{model.__name__}: would_delete={n}")
        else:
            n = 0
            while True:
                pks = list(qs.values_list("pk", flat=True)[:batch_size])
                if not pks:
                    break
                n += model.objects.filter(pk__in=pks).delete()[0]
            out(f"{model.__name__}: deleted={n}")
        total += n
    out(f"prune done cutoff={cutoff.isoformat()} total={total}")
    return total


class Command(BaseCommand):
    help = "Prune snapshots older than --older-than days (Candle untouched)."

    def add_arguments(self, parser):
        parser.add_argument("--older-than", type=int, required=True, dest="older_than")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)

    def handle(self, *args, **options):
        cutoff = datetime.now(UTC) - timedelta(days=options["older_than"])
        run(
            cutoff,
            options["batch_size"],
            options["dry_run"],
            self.stdout.write,
        )
