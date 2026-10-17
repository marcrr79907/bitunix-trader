"""Migration 0015 round-trip: ``position`` joins ``Drawing.Kind`` choices (R1).

Choices-only ``AlterField`` on ``kind`` (deps ``0014_drawing_visible_locked``; the
``0014`` additive precedent). No column and no row changes: forward makes
``"position"`` a selectable kind, reverse restores the prior choices, and every
pre-existing row keeps its kind/data either way. This test drives the REAL
migration graph (no fakes): it pins ``trading`` at ``0014``, seeds a row of every
prior kind, walks forward, proves the rows survive and ``position`` is selectable,
then reverses and proves every row survives.

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
from django.db.migrations.recorder import MigrationRecorder
from trading.models import Drawing

pytestmark = pytest.mark.django_db(transaction=True)

_BEFORE = ("trading", "0014_drawing_visible_locked")
_AFTER = ("trading", "0015_drawing_kind_position")
_PRIOR_KINDS = ("hline", "trendline", "fib", "rect", "text")
_TABLE = "trading_drawing"


def _migrate(targets):
    MigrationExecutor(connection).migrate(targets)


def _down_to_0014():
    """All apps at their leaf, except ``trading`` pinned to 0014."""
    leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()
    _migrate([_BEFORE if app == "trading" else (app, name) for app, name in leaves])


def _up_to_latest():
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())


def _up_to_0015():
    """All apps at their leaf, except ``trading`` pinned to 0015 (the migration
    under test). ``0016`` landed after it, so "latest" no longer means 0015."""
    leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()
    _migrate([_AFTER if app == "trading" else (app, name) for app, name in leaves])


def _trading_leaf() -> str:
    """Latest APPLIED ``trading`` migration (graph leaves ignore applied state)."""
    applied = MigrationRecorder(connection).applied_migrations()
    return max(name for app, name in applied if app == "trading")


def _seed_row(user_id: int, kind: str) -> None:
    """Insert the pre-0015 shape: one row per prior kind (visible/locked exist)."""
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {_TABLE} "
            "(symbol, kind, points, style, created_at, user_id, visible, locked) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            [
                "BTCUSDT",
                kind,
                json.dumps({"price": 1.0}),
                "{}",
                "2026-10-16 00:00:00",
                user_id,
                1,
                0,
            ],
        )


def _kinds() -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT kind FROM {_TABLE} ORDER BY kind")
        return [row[0] for row in cursor.fetchall()]


def test_0015_adds_position_choice_forward_then_reverses_without_data_loss():
    user = get_user_model().objects.create_user(
        email="mig0015@example.com", password="pw-123456"
    )
    try:
        # Pre-state: the migration under test is applied; every prior kind seeded.
        _up_to_0015()
        assert _trading_leaf() == _AFTER[1]

        _down_to_0014()
        assert _trading_leaf() == _BEFORE[1]
        for kind in _PRIOR_KINDS:
            _seed_row(user.pk, kind)

        # Forward: ``position`` becomes a selectable kind; no row is touched.
        _up_to_0015()
        assert "position" in Drawing.Kind.values
        assert _kinds() == sorted(_PRIOR_KINDS)

        # Reverse: prior choices only; every row still survives the round-trip.
        _down_to_0014()
        assert _trading_leaf() == _BEFORE[1]
        assert _kinds() == sorted(_PRIOR_KINDS)
    finally:
        _up_to_latest()
