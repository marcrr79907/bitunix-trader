"""R11 contract: the system exposes no order-placement surface.

Scans ``web/`` and ``src/`` for known order-execution verbs (in code, not
comments or strings), ``getattr``-hidden verb calls, and forbidden mutating
endpoint paths. Read-only is a product invariant that MUST NOT be relaxed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent.parent / "web"
SRC = Path(__file__).resolve().parent.parent.parent / "src"
SCANNER_FILE = Path(__file__).resolve()

ORDER_VERBS = frozenset(
    {
        "place_order",
        "create_order",
        "submit_order",
        "batch_order",
        "modify_order",
        "cancel_order",
        "cancel_orders",
        "cancel_all_orders",
        "close_position",
        "close_all_position",
        "flash_close_position",
        "place_tpsl_order",
        "place_position_tpsl_order",
        "modify_tpsl_order",
        "modify_position_tpsl_order",
        "cancel_tpsl_order",
        "change_leverage",
        "change_margin_mode",
        "change_position_mode",
        "adjust_position_margin",
        "batch_place_order",
        "create_market_order",
        "create_limit_order",
    }
)

# Mutating endpoint fragments only — read paths (e.g. ``/trade/get_history_orders``)
# must never match. A string Constant containing any of these is an offender.
FORBIDDEN_PATHS = frozenset(
    {
        "/trade/place_order",
        "/trade/batch_order",
        "/trade/cancel_orders",
        "/trade/cancel_all_orders",
        "/trade/modify_order",
        "/trade/close_all_position",
        "/trade/flash_close_position",
        "/tpsl/place_order",
        "/tpsl/cancel_order",
        "/tpsl/modify_order",
        "/tpsl/position/place_order",
        "/tpsl/position/modify_order",
        "/account/change_leverage",
        "/account/change_margin_mode",
        "/account/change_position_mode",
        "/account/adjust_position_margin",
    }
)


def _order_offenders(root: Path) -> list[str]:
    """Files whose code defines or calls an order-execution surface.

    Flags verb attributes/names, ``getattr``-hidden verbs, and string constants
    containing a mutating endpoint fragment. Self-excludes the scanner file and
    ``__pycache__`` (the verb/path strings live here as data, not as a surface).
    """
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts or path.resolve() == SCANNER_FILE:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ORDER_VERBS:
                offenders.append(str(path))
                break
            if isinstance(node, ast.Name) and node.id in ORDER_VERBS:
                offenders.append(str(path))
                break
            # getattr(mod, "place_order") hides a verb behind a string.
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and any(
                    isinstance(arg, ast.Constant) and arg.value in ORDER_VERBS
                    for arg in node.args
                )
            ):
                offenders.append(str(path))
                break
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if any(fragment in node.value for fragment in FORBIDDEN_PATHS):
                    offenders.append(str(path))
                    break
    return offenders


def test_no_order_surface_in_web_and_src():
    # R11: the invariant covers the whole system, not only the web layer.
    offenders = [f for root in (WEB, SRC) for f in _order_offenders(root)]
    assert offenders == [], f"order-execution surface found: {offenders}"


def test_scanner_flags_an_order_call(tmp_path):
    (tmp_path / "leaky.py").write_text("client.place_order(symbol='BTCUSDT')\n")
    (tmp_path / "clean.py").write_text("client.fetch_positions()\n")
    assert _order_offenders(tmp_path) == [str(tmp_path / "leaky.py")]


@pytest.mark.parametrize(
    "verb",
    [
        "place_tpsl_order",
        "place_position_tpsl_order",
        "modify_tpsl_order",
        "modify_position_tpsl_order",
        "cancel_tpsl_order",
        "change_leverage",
        "change_margin_mode",
        "change_position_mode",
        "adjust_position_margin",
        "batch_place_order",
        "create_market_order",
        "create_limit_order",
    ],
)
def test_scanner_flags_extended_verbs(tmp_path, verb):
    (tmp_path / "leaky.py").write_text(f"client.{verb}(symbol='BTCUSDT')\n")
    (tmp_path / "clean.py").write_text("client.fetch_positions()\n")
    assert _order_offenders(tmp_path) == [str(tmp_path / "leaky.py")]


def test_scanner_flags_a_getattr_hidden_verb(tmp_path):
    (tmp_path / "sneaky.py").write_text(
        "getattr(client, 'place_order')(symbol='BTCUSDT')\n"
    )
    (tmp_path / "clean.py").write_text("x = 1\n")
    assert _order_offenders(tmp_path) == [str(tmp_path / "sneaky.py")]


@pytest.mark.parametrize(
    "path",
    [
        "/trade/place_order",
        "/trade/batch_order",
        "/trade/cancel_orders",
        "/trade/cancel_all_orders",
        "/trade/modify_order",
        "/trade/close_all_position",
        "/trade/flash_close_position",
        "/tpsl/place_order",
        "/tpsl/cancel_order",
        "/tpsl/modify_order",
        "/tpsl/position/place_order",
        "/tpsl/position/modify_order",
        "/account/change_leverage",
        "/account/change_margin_mode",
        "/account/change_position_mode",
        "/account/adjust_position_margin",
    ],
)
def test_scanner_flags_forbidden_endpoint_paths(tmp_path, path):
    (tmp_path / "leaky.py").write_text(f'client.post("{path}", body={{}})\n')
    (tmp_path / "clean.py").write_text('client.get("/trade/get_history_orders")\n')
    assert _order_offenders(tmp_path) == [str(tmp_path / "leaky.py")]


@pytest.mark.parametrize(
    "path",
    [
        "/trade/get_history_orders",
        "/trade/get_history_trades",
        "/position/get_pending_positions",
        "/account",
    ],
)
def test_scanner_ignores_read_only_endpoints(tmp_path, path):
    # R11 negative control: read endpoints MUST NOT be flagged (src/client.py).
    (tmp_path / "client.py").write_text(f'client.get("{path}")\n')
    assert _order_offenders(tmp_path) == []


def test_scanner_skips_pycache(tmp_path):
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "leaky.py").write_text("client.place_order()\n")
    (tmp_path / "clean.py").write_text("x = 1\n")
    assert _order_offenders(tmp_path) == []
