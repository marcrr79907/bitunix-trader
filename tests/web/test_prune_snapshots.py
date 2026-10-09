"""R1 contract: bounded tick-table retention via ``prune_snapshots``.

The core loop is the module-level ``run(cutoff, batch_size, dry_run, out)``
seam: ``cutoff`` is injected so no wall clock enters the tested path. Every
test stamps rows relative to a fixed ``CUTOFF`` and asserts row survival, never
query counts. ``Candle`` MUST be out of scope — a surviving row and a source
scan both prove it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from trading.models import Candle, FundingSnapshot, TickerSnapshot

CUTOFF = datetime(2024, 1, 10, tzinfo=UTC)
OLD = CUTOFF - timedelta(days=1)
NEW = CUTOFF + timedelta(days=1)


class OutRecorder:
    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, message):
        self.lines.append(str(message))


def _funding(symbol, ts, rate=0.0001):
    return FundingSnapshot.objects.create(symbol=symbol, ts=ts, funding_rate=rate)


def _ticker(symbol, ts, price=1.0):
    return TickerSnapshot.objects.create(symbol=symbol, ts=ts, last_price=price)


def _run(cutoff=CUTOFF, batch_size=5000, dry_run=False):
    from trading.management.commands.prune_snapshots import run

    out = OutRecorder()
    total = run(cutoff, batch_size, dry_run, out)
    return total, out


@pytest.mark.django_db
def test_prune_deletes_old_keeps_new_both_tables():
    _funding("BTCUSDT", OLD)
    _funding("ETHUSDT", NEW)
    _funding("SOLUSDT", CUTOFF)  # exactly at cutoff: ts < cutoff is strict
    _ticker("BTCUSDT", OLD)
    _ticker("ETHUSDT", NEW)

    total, out = _run()

    assert total == 2  # one per table
    assert list(FundingSnapshot.objects.values_list("symbol", flat=True)) == [
        "ETHUSDT",
        "SOLUSDT",
    ]
    assert list(TickerSnapshot.objects.values_list("symbol", flat=True)) == ["ETHUSDT"]
    assert any("FundingSnapshot" in line for line in out.lines)
    assert any("TickerSnapshot" in line for line in out.lines)


@pytest.mark.django_db
def test_dry_run_reports_count_and_deletes_nothing():
    _funding("BTCUSDT", OLD)
    _funding("ETHUSDT", OLD)
    _ticker("BTCUSDT", OLD)

    total, out = _run(dry_run=True)

    assert total == 3
    assert FundingSnapshot.objects.count() == 2
    assert TickerSnapshot.objects.count() == 1
    assert any("would_delete=2" in line for line in out.lines)
    assert any("would_delete=1" in line for line in out.lines)


@pytest.mark.django_db
def test_second_run_with_same_cutoff_deletes_nothing():
    _funding("BTCUSDT", OLD)
    _ticker("BTCUSDT", OLD)

    first, _ = _run()
    second, out = _run()

    assert first == 2
    assert second == 0
    assert any("deleted=0" in line for line in out.lines)


@pytest.mark.django_db
def test_candle_rows_survive_regardless_of_time():
    Candle.objects.create(
        symbol="BTCUSDT",
        interval="5m",
        time=int(OLD.timestamp()),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
    )
    _funding("BTCUSDT", OLD)

    _run()

    assert Candle.objects.count() == 1
    assert FundingSnapshot.objects.count() == 0


def test_source_never_references_candle():
    # AST-level guard: the module must not name `Candle` in code or imports.
    # Prose in the docstring is allowed; an identifier reference is not.
    import ast
    import inspect

    from trading.management.commands import prune_snapshots

    tree = ast.parse(inspect.getsource(prune_snapshots))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {
        alias.name
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom)
        for alias in n.names
    }
    assert "Candle" not in names


@pytest.mark.django_db
def test_batch_size_smaller_than_backlog_deletes_all():
    for i in range(5):
        _funding(f"SYM{i}", OLD)

    total, _ = _run(batch_size=2)

    assert total == 5
    assert FundingSnapshot.objects.count() == 0


@pytest.mark.django_db
def test_run_uses_injected_cutoff_not_wall_clock():
    # A row dated 2025 is "old" to a real 2026 clock, but the injected 2020
    # cutoff must govern: ts(2025) < cutoff(2020) is false, so it survives.
    # If run() read the wall clock this row would be deleted.
    _funding("BTCUSDT", datetime(2025, 1, 1, tzinfo=UTC))

    total, _ = _run(cutoff=datetime(2020, 1, 1, tzinfo=UTC))

    assert total == 0
    assert FundingSnapshot.objects.count() == 1


@pytest.mark.django_db
def test_call_command_wires_older_than_and_prunes():
    old = datetime.now(UTC) - timedelta(days=8)
    new = datetime.now(UTC) - timedelta(days=1)
    _funding("BTCUSDT", old)
    _funding("ETHUSDT", new)
    _ticker("BTCUSDT", old)

    call_command("prune_snapshots", older_than=7)

    assert list(FundingSnapshot.objects.values_list("symbol", flat=True)) == ["ETHUSDT"]
    assert TickerSnapshot.objects.count() == 0


@pytest.mark.django_db
def test_call_command_dry_run_keeps_rows():
    _funding("BTCUSDT", datetime.now(UTC) - timedelta(days=8))

    call_command("prune_snapshots", older_than=7, dry_run=True)

    assert FundingSnapshot.objects.count() == 1


def test_older_than_is_required():
    with pytest.raises(CommandError):
        call_command("prune_snapshots")
