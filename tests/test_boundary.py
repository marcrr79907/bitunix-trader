"""R9 contract: the framework-free core (src/) never imports Django.

Stdlib-only on purpose: this test must not import Django itself, otherwise it
could not run in an environment where Django is absent (the exact CI scenario
it protects).
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


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


def test_no_django_import_in_core():
    assert _django_offenders(SRC) == [], (
        f"Django import found in core: {_django_offenders(SRC)}"
    )


def test_scanner_flags_a_django_violation(tmp_path):
    (tmp_path / "leaky.py").write_text("import django.conf\n")
    (tmp_path / "clean.py").write_text("import os\n")
    assert _django_offenders(tmp_path) == [str(tmp_path / "leaky.py")]
