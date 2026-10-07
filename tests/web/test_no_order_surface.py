"""R11 contract: the web layer exposes no order-placement surface.

Scans all of ``web/`` for known order-execution verbs (in code, not comments or
strings) and fails if any appears. Read-only is a product invariant that MUST
NOT be relaxed by later changes.
"""

from __future__ import annotations

import ast
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent.parent / "web"

ORDER_VERBS = frozenset(
    {"place_order", "batch_order", "cancel_order", "close_position"}
)


def _order_offenders(root: Path) -> list[str]:
    """Files whose code defines or calls an order-execution verb."""
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ORDER_VERBS:
                offenders.append(str(path))
                break
            if isinstance(node, ast.Name) and node.id in ORDER_VERBS:
                offenders.append(str(path))
                break
    return offenders


def test_no_order_surface_in_web():
    offenders = _order_offenders(WEB)
    assert offenders == [], f"order-execution surface found in web/: {offenders}"


def test_scanner_flags_an_order_call(tmp_path):
    (tmp_path / "leaky.py").write_text("client.place_order(symbol='BTCUSDT')\n")
    (tmp_path / "clean.py").write_text("client.fetch_positions()\n")
    assert _order_offenders(tmp_path) == [str(tmp_path / "leaky.py")]
