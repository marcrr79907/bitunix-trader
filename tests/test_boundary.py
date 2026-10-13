"""R9 contract: the framework-free core (src/) never imports Django.

Stdlib-only on purpose: this test must not import Django itself, otherwise it
could not run in an environment where Django is absent (the exact CI scenario
it protects).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

# Pure, framework-free modules: they may import ONLY the standard library.
# Extend this set as new pure domain modules are added.
PURE_MODULES = (
    "indicators.py",
    "metrics.py",
    "analytics.py",
    "alert_rules.py",
    "smc/config.py",
    "smc/swings.py",
    "smc/structure.py",
    "smc/zones.py",
    "smc/range.py",
    "smc/signals.py",
)


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _django_offenders(root: Path) -> list[str]:
    offenders = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        if "django" in _imported_roots(tree):
            offenders.append(str(path))
    return offenders


def _non_stdlib_imports(path: Path) -> set[str]:
    """Top-level imports that are neither stdlib nor local (``src``)."""
    tree = ast.parse(path.read_text(), filename=str(path))
    return {
        name
        for name in _imported_roots(tree)
        if name != "src" and name not in sys.stdlib_module_names
    }


def test_no_django_import_in_core():
    assert _django_offenders(SRC) == [], (
        f"Django import found in core: {_django_offenders(SRC)}"
    )


def test_scanner_flags_a_django_violation(tmp_path):
    (tmp_path / "leaky.py").write_text("import django.conf\n")
    (tmp_path / "clean.py").write_text("import os\n")
    assert _django_offenders(tmp_path) == [str(tmp_path / "leaky.py")]


def test_pure_modules_are_stdlib_only():
    # R8: indicators/metrics (and future pure modules) must import stdlib only
    # (e.g. no requests, rich, django). Only files that exist are checked, so
    # this grows with the module set without a test edit per module.
    offenders = {
        name: sorted(_non_stdlib_imports(SRC / name))
        for name in PURE_MODULES
        if (SRC / name).exists() and _non_stdlib_imports(SRC / name)
    }
    assert offenders == {}, f"non-stdlib import in pure module: {offenders}"


def test_pure_module_scanner_flags_a_violation(tmp_path):
    (tmp_path / "metrics.py").write_text("import requests\n")
    assert _non_stdlib_imports(tmp_path / "metrics.py") == {"requests"}
