"""Migration 0017 contract (F11-B): additive, creates only the template table.

Mirrors ``test_migration_0014.py``: it inspects the migration *source* (no DB
round-trip) so the guarantee is about the operation set, not about a particular
database state.
"""

from __future__ import annotations

import ast
from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[2] / "web/trading/migrations/0017_charttemplate.py"
)


def _tree():
    return ast.parse(MIGRATION.read_text(encoding="utf-8"))


def test_migration_creates_only_the_charttemplate_model():
    tree = _tree()
    created = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", None) == "CreateModel"
    ]

    assert len(created) == 1
    model_names = [
        kw.value.value for node in created for kw in node.keywords if kw.arg == "name"
    ]
    assert model_names == ["ChartTemplate"]


def test_migration_is_additive_no_alter_or_delete():
    tree = _tree()
    forbidden = {"DeleteModel", "RemoveField", "AlterField", "RenameModel"}

    used = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and hasattr(node.func, "attr")
    }

    assert used & forbidden == set()


def test_migration_depends_on_the_previous_one():
    assert "0016_drawing_kind_tools" in MIGRATION.read_text(encoding="utf-8")
