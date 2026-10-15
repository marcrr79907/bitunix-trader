"""Migration 0012 round-trip: drawings keyed per SYMBOL, lossy reverse (R1).

The first destructive migration in the tree. This test drives the REAL
migration graph (no fakes): it walks ``0012`` down, seeds two drawings that
differ only by ``interval`` (the pre-0012 shape), walks it forward, and proves
both rows survive as distinct per-symbol drawings (keep-all, NO dedupe) with the
new ``(user, symbol)`` index. It then reverses and proves the documented lossy
contract: every row comes back with ``interval="1m"`` and the per-interval split
is gone.

``transaction=True`` is required to run schema-changing DDL inside the test; the
schema is restored to the latest leaf in a ``finally`` so later tests are
unaffected.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)

_BEFORE = ("trading", "0011_chartpreference_theme")
_AFTER = ("trading", "0012_drawing_per_symbol")
_TABLE = "trading_drawing"


def _migrate(targets):
    MigrationExecutor(connection).migrate(targets)


def _down_to_0011():
    """All apps at their leaf, except ``trading`` pinned to 0011."""
    leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()
    _migrate([_BEFORE if app == "trading" else (app, name) for app, name in leaves])


def _up_to_latest():
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())


def _columns(table: str) -> set[str]:
    with connection.cursor() as cursor:
        return {
            col.name
            for col in connection.introspection.get_table_description(cursor, table)
        }


def _indexes(table: str) -> set[str]:
    with connection.cursor() as cursor:
        return set(connection.introspection.get_constraints(cursor, table))


def _seed_two_intervals(user_id: int) -> None:
    """Insert the pre-0012 shape: same symbol, differing only by ``interval``."""
    with connection.cursor() as cursor:
        for interval, price in (("1m", 1.0), ("1h", 2.0)):
            cursor.execute(
                f"INSERT INTO {_TABLE} "
                "(symbol, interval, kind, points, style, created_at, user_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                [
                    "BTCUSDT",
                    interval,
                    "hline",
                    json.dumps({"price": price}),
                    "{}",
                    "2026-10-15 00:00:00",
                    user_id,
                ],
            )


def test_0012_keeps_all_rows_forward_then_reverses_lossily():
    user = get_user_model().objects.create_user(
        email="mig0012@example.com", password="pw-123456"
    )
    try:
        # Pre-state: interval column present, two rows differing only by interval.
        _down_to_0011()
        assert "interval" in _columns(_TABLE)
        _seed_two_intervals(user.pk)

        # Forward: interval dropped, both rows survive distinct (no dedupe).
        _up_to_latest()
        cols = _columns(_TABLE)
        assert "interval" not in cols
        assert "ix_drawing_user_symbol" in _indexes(_TABLE)
        assert "ix_drawing_user_sym_interval" not in _indexes(_TABLE)
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) FROM {_TABLE} WHERE symbol = %s", ["BTCUSDT"]
            )
            assert cursor.fetchone()[0] == 2

        # Reverse: LOSSY — every row re-adds interval="1m"; split unrecoverable.
        _down_to_0011()
        assert "interval" in _columns(_TABLE)
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT interval FROM {_TABLE} ORDER BY id")
            assert [row[0] for row in cursor.fetchall()] == ["1m", "1m"]
    finally:
        _up_to_latest()
