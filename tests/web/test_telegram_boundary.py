"""R15 contract: the Telegram secret stays confined to the worker trust zone.

``src.alerts`` (and therefore the Telegram token/chat secret) MUST be imported
and called ONLY from ``web/worker.py``. Request-serving code under ``web/trading``,
``web/market``, and the top-level ``web/`` request modules MUST NOT import
``src.alerts``, reference ``send_telegram``, or read ``TELEGRAM_TOKEN`` /
``TELEGRAM_CHAT_ID``. Scans code via AST; self-excludes the scanner file and
``__pycache__``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent.parent / "web"
# Worker trust zone (R15): the ONLY place the Telegram transport may live.
WORKER_FILE = WEB / "worker.py"
SCANNER_FILE = Path(__file__).resolve()

# Request-serving surface: the web apps plus top-level web request modules.
REQUEST_PATH = (
    WEB / "config",
    WEB / "accounts",
    WEB / "trading",
    WEB / "market",
)

FORBIDDEN_NAMES = frozenset({"send_telegram", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"})


def _is_alerts_import(node: ast.AST) -> bool:
    """True for any form importing the ``src.alerts`` module."""
    if isinstance(node, ast.Import):
        return any(
            a.name == "src.alerts" or a.name.startswith("src.alerts.")
            for a in node.names
        )
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if module == "src.alerts" or module.startswith("src.alerts."):
            return True
        return module == "src" and any(a.name == "alerts" for a in node.names)
    return False


def _telegram_offenders(root: Path) -> list[str]:
    """Files referencing the Telegram transport outside the worker zone."""
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts or path.resolve() in (SCANNER_FILE, WORKER_FILE):
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if _is_alerts_import(node):
                offenders.append(str(path))
                break
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
                offenders.append(str(path))
                break
            if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
                offenders.append(str(path))
                break
    return offenders


def test_request_path_has_no_telegram_transport():
    # R15: the real request tree must be clean today.
    offenders = [f for root in REQUEST_PATH for f in _telegram_offenders(root)]
    assert offenders == [], f"Telegram transport in the request path: {offenders}"


def test_top_level_web_request_modules_are_clean():
    # Top-level ``web/*.py`` request modules (scheduler, credentials, manage) must
    # not carry the transport either — scanning the tree minus the worker.
    modules = [
        p
        for p in sorted(WEB.glob("*.py"))
        if p.resolve() not in (SCANNER_FILE, WORKER_FILE)
    ]
    assert modules, "expected top-level web modules to scan"
    offenders = []
    for path in modules:
        tree = ast.parse(path.read_text(), filename=str(path))
        if any(_is_alerts_import(n) for n in ast.walk(tree)) or any(
            (isinstance(n, ast.Name) and n.id in FORBIDDEN_NAMES)
            or (isinstance(n, ast.Attribute) and n.attr in FORBIDDEN_NAMES)
            for n in ast.walk(tree)
        ):
            offenders.append(str(path))
    assert offenders == [], f"Telegram transport outside worker: {offenders}"


def test_worker_file_is_allowed():
    # R15 negative control: worker.py DOES import + call the transport and MUST
    # NOT be flagged (it is the sanctioned trust zone).
    assert WORKER_FILE.exists()
    source = WORKER_FILE.read_text()
    assert "src.alerts" in source and "send_telegram" in source
    assert str(WORKER_FILE) not in _telegram_offenders(WEB.parent)


def test_scanner_flags_a_fixture_import(tmp_path):
    # R15 negative control: an import under the request path is an offender.
    (tmp_path / "leaky.py").write_text("from src.alerts import send_telegram\n")
    (tmp_path / "clean.py").write_text("from src.client import BitunixClient\n")
    assert _telegram_offenders(tmp_path) == [str(tmp_path / "leaky.py")]


@pytest.mark.parametrize(
    "source",
    [
        "import src.alerts\n",
        "from src import alerts\n",
        "send_telegram('hi')\n",
        "token = TELEGRAM_TOKEN\n",
        "chat = config.TELEGRAM_CHAT_ID\n",
    ],
)
def test_scanner_flags_telegram_symbols(tmp_path, source):
    (tmp_path / "leaky.py").write_text(source)
    (tmp_path / "clean.py").write_text("x = 1\n")
    assert _telegram_offenders(tmp_path) == [str(tmp_path / "leaky.py")]


def test_scanner_skips_pycache(tmp_path):
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "leaky.py").write_text("from src.alerts import send_telegram\n")
    (tmp_path / "clean.py").write_text("x = 1\n")
    assert _telegram_offenders(tmp_path) == []
