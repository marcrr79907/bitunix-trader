"""Contract for the global ``Setup`` ledger row (smc-setup-ledger R1/R2).

A setup is a market-derived observation, byte-identical for every user: no
owner FK, not ``UserOwnedModel``, absent from ``OWNED_MODELS``. The migration
is additive and only creates ``setups``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.core.exceptions import FieldDoesNotExist
from trading.models import Setup, UserOwnedModel

MIGRATION = Path(__file__).resolve().parents[2] / "web/trading/migrations/0018_setup.py"
GUARD = Path(__file__).resolve().parent / "test_owned_model_guard.py"


# --- model shape ---------------------------------------------------------


def test_setup_is_global_not_owned():
    assert not issubclass(Setup, UserOwnedModel)
    with pytest.raises(FieldDoesNotExist):
        Setup._meta.get_field("user")


def test_setup_is_absent_from_owned_models():
    tree = ast.parse(GUARD.read_text(encoding="utf-8"))
    owned = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "OWNED_MODELS" for t in node.targets)
    )
    names = {
        elt.value
        for elt in ast.walk(owned.value)
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
    }
    assert "Setup" not in names


def test_unique_constraint_fields_include_engine_version():
    constraints = {
        tuple(c.fields): c for c in Setup._meta.constraints if hasattr(c, "fields")
    }
    key = ("symbol", "interval", "anchor_time", "engine_version")
    assert key in constraints


def test_symbol_interval_anchor_index_exists():
    indexes = {tuple(i.fields) for i in Setup._meta.indexes}
    assert ("symbol", "interval", "anchor_time") in indexes


@pytest.mark.parametrize(
    "field",
    ["zone_top", "zone_bottom", "range_high", "range_low", "has_ob", "has_fvg"],
)
def test_excluded_fields_are_absent(field):
    with pytest.raises(FieldDoesNotExist):
        Setup._meta.get_field(field)


def test_engine_version_and_atr_columns():
    assert Setup._meta.get_field("engine_version").max_length == 16
    assert Setup._meta.get_field("atr").null is True
    assert Setup._meta.get_field("created_at").auto_now_add is True


# --- migration source ----------------------------------------------------


def _tree():
    return ast.parse(MIGRATION.read_text(encoding="utf-8"))


def test_migration_creates_only_the_setup_model():
    created = [
        node
        for node in ast.walk(_tree())
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", None) == "CreateModel"
    ]

    assert len(created) == 1
    names = [
        kw.value.value for node in created for kw in node.keywords if kw.arg == "name"
    ]
    assert names == ["Setup"]


def test_migration_is_additive_no_alter_or_delete():
    forbidden = {"DeleteModel", "RemoveField", "AlterField", "RenameModel"}
    used = {
        node.func.attr
        for node in ast.walk(_tree())
        if isinstance(node, ast.Call) and hasattr(node.func, "attr")
    }
    assert used & forbidden == set()


def test_migration_depends_on_0017():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "'0017_charttemplate'" in text or '"0017_charttemplate"' in text


@pytest.mark.django_db
def test_trading_leaf_is_at_least_0018():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()
    trading_leaf = next(name for app, name in leaves if app == "trading")
    assert trading_leaf >= "0018"
