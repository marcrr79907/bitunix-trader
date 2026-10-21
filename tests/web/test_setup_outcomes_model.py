"""Contract for the global ``SetupOutcome`` row (smc-setup-outcomes R1).

One resolution per setup: global, owner-less like ``Setup`` — no ``user`` FK,
not ``UserOwnedModel``, absent from ``OWNED_MODELS`` — linked one-to-one with
``related_name="outcome"``. The migration is additive: only ``setup_outcomes``
is created, on top of the ``0018`` leaf.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.core.exceptions import FieldDoesNotExist
from django.db import IntegrityError, transaction
from trading.models import Setup, SetupOutcome, UserOwnedModel

MIGRATION = (
    Path(__file__).resolve().parents[2] / "web/trading/migrations/0019_setupoutcome.py"
)
GUARD = Path(__file__).resolve().parent / "test_owned_model_guard.py"


# --- model shape ---------------------------------------------------------


def test_setup_outcome_is_global_not_owned():
    assert not issubclass(SetupOutcome, UserOwnedModel)
    with pytest.raises(FieldDoesNotExist):
        SetupOutcome._meta.get_field("user")


def test_setup_outcome_is_absent_from_owned_models():
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
    assert "SetupOutcome" not in names


def test_setup_link_is_one_to_one_cascade_with_outcome_related_name():
    field = SetupOutcome._meta.get_field("setup")
    assert field.get_internal_type() == "OneToOneField"
    assert field.remote_field.model is Setup
    assert field.remote_field.on_delete.__name__ == "CASCADE"
    assert field.remote_field.related_name == "outcome"


@pytest.mark.parametrize(
    ("name", "internal_type"),
    [
        ("status", "CharField"),
        ("resolved_time", "BigIntegerField"),
        ("bars_to_resolution", "IntegerField"),
        ("mfe_r", "FloatField"),
        ("mae_r", "FloatField"),
        ("sl_then_tp", "BooleanField"),
        ("horizon_bars", "IntegerField"),
        ("engine_version", "CharField"),
        ("evaluated_at", "DateTimeField"),
    ],
)
def test_column_contract(name, internal_type):
    assert SetupOutcome._meta.get_field(name).get_internal_type() == internal_type


def test_char_columns_are_sized_per_spec():
    assert SetupOutcome._meta.get_field("status").max_length == 16
    assert SetupOutcome._meta.get_field("engine_version").max_length == 16


def test_status_has_the_five_frozen_choices():
    choices = dict(SetupOutcome._meta.get_field("status").choices)
    assert set(choices) == {
        "take_profit",
        "stop_loss",
        "ambiguous",
        "expired",
        "not_triggered",
    }


def test_nullability_contract():
    nullable = {
        field.name
        for field in SetupOutcome._meta.fields
        if field.null and not field.primary_key
    }
    assert nullable == {
        "resolved_time",
        "bars_to_resolution",
        "mfe_r",
        "mae_r",
        "sl_then_tp",
    }


def test_evaluated_at_changes_on_every_save():
    assert SetupOutcome._meta.get_field("evaluated_at").auto_now is True
    assert SetupOutcome._meta.get_field("evaluated_at").auto_now_add is False


@pytest.mark.django_db
def test_uniqueness_is_the_one_to_one_setup_link():
    setup = Setup.objects.create(
        symbol="BTCUSDT",
        interval="1h",
        anchor_time=1_700_000_000,
        direction="long",
        entry=100.0,
        stop=90.0,
        take_profit=110.0,
        rr=1.0,
        score=3,
        engine_version="1:w200",
    )
    SetupOutcome.objects.create(
        setup=setup,
        status="expired",
        horizon_bars=200,
        engine_version=setup.engine_version,
    )

    # A second outcome for the same setup must fail: the OneToOne unique
    # index IS the idempotency key. Inside the test's atomic block the
    # IntegrityError must be contained or the connection is poisoned, so
    # this runs in a savepoint (Django's atomiccontext for assertRaises).
    with pytest.raises(IntegrityError), transaction.atomic():
        SetupOutcome.objects.create(
            setup=setup,
            status="take_profit",
            horizon_bars=100,
            engine_version=setup.engine_version,
        )

    setup.refresh_from_db()
    assert SetupOutcome.objects.count() == 1
    assert setup.outcome.status == "expired"


# --- migration source ----------------------------------------------------


def _tree():
    return ast.parse(MIGRATION.read_text(encoding="utf-8"))


def test_migration_creates_only_the_setup_outcome_model():
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
    assert names == ["SetupOutcome"]


def test_migration_is_additive_no_alter_or_delete():
    forbidden = {"DeleteModel", "RemoveField", "AlterField", "RenameModel"}
    used = {
        node.func.attr
        for node in ast.walk(_tree())
        if isinstance(node, ast.Call) and hasattr(node.func, "attr")
    }
    assert used & forbidden == set()


def test_migration_depends_on_0018():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "'0018_setup'" in text or '"0018_setup"' in text


@pytest.mark.django_db
def test_trading_leaf_is_at_least_0019():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()
    trading_leaf = next(name for app, name in leaves if app == "trading")
    assert trading_leaf >= "0019"
