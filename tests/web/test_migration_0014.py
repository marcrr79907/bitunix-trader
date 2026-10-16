"""Migration 0014 round-trip: drawings gain ``visible``/``locked`` additively (R1).

Purely additive ``AddField`` pair (mirrors ``0013_chartpreference_smc.py:17-21``):
forward adds ``visible`` (default True) and ``locked`` (default False); reverse
drops both with zero row loss. This test drives the REAL migration graph (no
fakes): it pins ``trading`` at ``0013``, seeds rows (the pre-0014 shape), walks
forward, proves the columns appear with their defaults on EXISTING rows, then
reverses and proves every row survives the column drop.

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

_BEFORE = ("trading", "0013_chartpreference_smc")
_AFTER = ("trading", "0014_drawing_visible_locked")
_TABLE = "trading_drawing"


def _migrate(targets):
    MigrationExecutor(connection).migrate(targets)


def _down_to_0013():
    """All apps at their leaf, except ``trading`` pinned to 0013."""
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


def _seed_row(user_id: int, symbol: str) -> None:
    """Insert the pre-0014 shape: no ``visible``/``locked`` columns exist."""
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {_TABLE} "
            "(symbol, kind, points, style, created_at, user_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            [
                symbol,
                "hline",
                json.dumps({"price": 1.0}),
                "{}",
                "2026-10-16 00:00:00",
                user_id,
            ],
        )


def test_0014_adds_two_fields_forward_then_reverses_without_data_loss():
    user = get_user_model().objects.create_user(
        email="mig0014@example.com", password="pw-123456"
    )
    try:
        # Pre-state: neither column exists; two rows seeded.
        _down_to_0013()
        cols = _columns(_TABLE)
        assert "visible" not in cols
        assert "locked" not in cols
        _seed_row(user.pk, "BTCUSDT")
        _seed_row(user.pk, "ETHUSDT")

        # Forward: both columns appear; the EXISTING rows take the defaults.
        _up_to_latest()
        cols = _columns(_TABLE)
        assert "visible" in cols
        assert "locked" in cols
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT symbol, visible, locked FROM {_TABLE} ORDER BY symbol"
            )
            rows = cursor.fetchall()
        # SQLite stores booleans as 0/1; both pre-existing rows get the defaults.
        assert rows == [("BTCUSDT", 1, 0), ("ETHUSDT", 1, 0)]

        # Reverse: both columns drop; every row survives the drop.
        _down_to_0013()
        cols = _columns(_TABLE)
        assert "visible" not in cols
        assert "locked" not in cols
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {_TABLE}")
            assert cursor.fetchone()[0] == 2
    finally:
        _up_to_latest()
