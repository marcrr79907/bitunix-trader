"""Migration 0016 round-trip: the eight F9 kinds join ``Drawing.Kind`` (R1).

Choices-only ``AlterField`` on ``kind`` (deps ``0015_drawing_kind_position``;
mirrors the ``0015`` precedent). No column and no row changes: forward makes the
eight F9 kinds selectable, reverse restores the prior choices, and every
pre-existing row keeps its kind/data either way. This test drives the REAL
migration graph (no fakes): it pins ``trading`` at ``0015``, seeds a row of every
prior kind, walks forward, proves the rows survive and the eight kinds are
selectable, then reverses and proves every row survives.

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

_BEFORE = ("trading", "0015_drawing_kind_position")
_AFTER = ("trading", "0016_drawing_kind_tools")
_PRIOR_KINDS = ("hline", "trendline", "fib", "rect", "text", "position")
_NEW_KINDS = (
    "ray",
    "vline",
    "channel",
    "price",
    "callout",
    "fib_ext",
    "fib_time",
    "fib_zone",
)
_TABLE = "trading_drawing"


def _migrate(targets):
    MigrationExecutor(connection).migrate(targets)


def _down_to_0015():
    """All apps at their leaf, except ``trading`` pinned to 0015."""
    leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()
    _migrate([_BEFORE if app == "trading" else (app, name) for app, name in leaves])


def _up_to_latest():
    _migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())


def _trading_leaf() -> str:
    """Latest APPLIED ``trading`` migration (graph leaves ignore applied state)."""
    applied = MigrationRecorder(connection).applied_migrations()
    return max(name for app, name in applied if app == "trading")


def _seed_row(user_id: int, kind: str) -> None:
    """Insert the pre-0016 shape: one row per prior kind."""
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


def test_0016_adds_eight_kinds_forward_then_reverses_without_data_loss():
    user = get_user_model().objects.create_user(
        email="mig0016@example.com", password="pw-123456"
    )
    try:
        # Pre-state: 0016 is applied. Later additive migrations may exist
        # (0017+), so assert the leaf is AT LEAST 0016, not equal to it.
        _up_to_latest()
        assert _trading_leaf() >= _AFTER[1]

        _down_to_0015()
        assert _trading_leaf() == _BEFORE[1]
        for kind in _PRIOR_KINDS:
            _seed_row(user.pk, kind)

        # Forward: all eight F9 kinds become selectable; no row is touched.
        _up_to_latest()
        for kind in _NEW_KINDS:
            assert kind in Drawing.Kind.values
        assert _kinds() == sorted(_PRIOR_KINDS)

        # Reverse: prior choices only; every row still survives the round-trip.
        _down_to_0015()
        assert _trading_leaf() == _BEFORE[1]
        assert _kinds() == sorted(_PRIOR_KINDS)
    finally:
        _up_to_latest()
