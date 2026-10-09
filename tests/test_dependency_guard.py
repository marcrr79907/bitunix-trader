"""R7 contract: runtime code imports only stdlib, declared deps or local modules.

Stdlib-only on purpose (mirrors ``tests/test_boundary.py``): the guard must run
where the declared dependencies are absent, so it parses source with ``ast``
instead of importing anything.

Scan roots are ``web/**/*.py`` and ``src/**/*.py``; the allowlist is derived
from ``sys.stdlib_module_names`` + ``requirements.txt`` import-roots + local
packages, so a new first-party module cannot cause a false positive and a new
third-party import cannot slip in unnoticed.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
SRC = ROOT / "src"
REQUIREMENTS = ROOT / "requirements.txt"
THIS_FILE = Path(__file__).resolve()

# Distribution name (normalized, extras/version/markers stripped) -> import root.
# Extend this map whenever a runtime dependency is added to requirements.txt;
# ``test_requirements_sync`` fails otherwise.
DIST_TO_ROOT = {
    "psycopg": "psycopg",
    "dj-database-url": "dj_database_url",
    "requests": "requests",
    "rich": "rich",
    "django": "django",
    "gunicorn": "gunicorn",
    "redis": "redis",
    "cryptography": "cryptography",
}


def _dist_name(spec: str) -> str:
    """Normalize a requirement line to its bare distribution name."""
    name = spec.split(";")[0].strip()  # environment markers
    name = name.split("[")[0].strip()  # extras, e.g. psycopg[binary]
    for sep in (">=", "<=", "==", "!=", "~=", "===", ">", "<"):
        name = name.split(sep)[0].strip()
    return name.lower()


def _declared_dists() -> list[str]:
    lines = REQUIREMENTS.read_text().splitlines()
    return [
        _dist_name(line)
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def _declared_import_roots() -> set[str]:
    return {DIST_TO_ROOT[dist] for dist in _declared_dists()}


def _local_roots() -> set[str]:
    """First-party import roots: web packages, flat modules and ``src``."""
    roots = {pkg.parent.name for pkg in WEB.glob("*/__init__.py")}
    roots.update(mod.stem for mod in WEB.glob("*.py"))
    roots.add(SRC.name)
    return roots


def _allowlist() -> set[str]:
    return set(sys.stdlib_module_names) | _declared_import_roots() | _local_roots()


def _imported_roots(tree: ast.AST) -> set[str]:
    """Top-level import roots, excluding relative imports and ``__future__``."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    roots.discard("__future__")
    return roots


def _offenders(roots: list[Path], allowlist: set[str]) -> list[tuple[str, list[str]]]:
    """Files importing a top-level root outside the allowlist, sorted by path."""
    findings: list[tuple[str, list[str]]] = []
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts or path.resolve() == THIS_FILE:
                continue
            tree = ast.parse(path.read_text(), filename=str(path))
            # ponytail: TYPE_CHECKING-guarded imports are not excluded — the
            # current tree has none; add a guard here if one appears.
            unknown = sorted(
                name for name in _imported_roots(tree) if name not in allowlist
            )
            if unknown:
                findings.append((str(path), unknown))
    return findings


# --- Positive control: the real tree --------------------------------------


def test_guard_passes_real_tree():
    assert _offenders([WEB, SRC], _allowlist()) == []


# --- Allowed roots are not flagged ----------------------------------------


def test_guard_ignores_stdlib_declared_local_and_relative(tmp_path):
    (tmp_path / "module.py").write_text(
        "import os\n"
        "import django\n"
        "from src.client import BitunixClient\n"
        "from cryptography.fernet import Fernet\n"
        "from . import sibling\n"
        "from .mod import helper\n"
    )
    assert _offenders([tmp_path], _allowlist()) == []


# --- Negative control: an unknown import is reported ----------------------


def test_guard_flags_unknown_import(tmp_path):
    (tmp_path / "leaky.py").write_text("import pandas\n")
    (tmp_path / "clean.py").write_text("import os\n")
    expected = [(str(tmp_path / "leaky.py"), ["pandas"])]
    assert _offenders([tmp_path], _allowlist()) == expected


def test_guard_reports_each_unknown_root(tmp_path):
    (tmp_path / "leaky.py").write_text("import pandas\nfrom numpy import array\n")
    offenders = _offenders([tmp_path], _allowlist())
    assert offenders == [(str(tmp_path / "leaky.py"), ["numpy", "pandas"])]


# --- Manifest / guard sync ------------------------------------------------


def test_requirements_sync():
    declared = _declared_dists()
    assert declared, "requirements.txt declared no dependencies"
    unmapped = [dist for dist in declared if dist not in DIST_TO_ROOT]
    assert unmapped == [], f"declared dist without import-root mapping: {unmapped}"
    allow = _allowlist()
    missing = [dist for dist in declared if DIST_TO_ROOT[dist] not in allow]
    assert missing == [], f"mapped import-root absent from allowlist: {missing}"
