"""R14.3/R14.4 contract: request paths scope owned models; worker zone does not.

R14.3 — request-serving code MUST NOT use unscoped queries on owned models;
``for_user(user)`` is the sanctioned accessor, and an AST scanner MUST flag any
``<OwnedModel>.objects.<verb>(...)`` bypass. R14.4 — the worker is the trusted
zone and MAY read across users; that exception is proven here too.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent.parent / "web"
# Mirrors the credential scanner's request path: every request-serving app is
# scanned, ``web/worker.py`` is not (trusted-zone exception, R14.4).
REQUEST_PATH = (WEB / "config", WEB / "accounts", WEB / "trading", WEB / "market")
SCANNER_FILE = Path(__file__).resolve()

OWNED_MODELS = frozenset(
    {
        "ExchangeCredential",
        "Watchlist",
        "PositionSnapshot",
        "AccountSnapshot",
        "Trade",
        "ChartLayout",
        "Drawing",
    }
)
UNSCOPED_VERBS = frozenset(
    {
        "all",
        "get",
        "filter",
        "exclude",
        "first",
        "last",
        "create",
        "update",
        "get_or_create",
        "update_or_create",
    }
)


def _unscoped_owned_query_offenders(root: Path) -> list[str]:
    """Files whose code queries an owned model through the unscoped manager.

    Flags ``<OwnedModel>.objects.<verb>(...)`` where the verb is not the
    sanctioned ``for_user``. Self-excludes the scanner file and ``__pycache__``.
    """
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts or path.resolve() == SCANNER_FILE:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if _is_unscoped_owned_call(node):
                offenders.append(str(path))
                break
    return offenders


def _is_unscoped_owned_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in UNSCOPED_VERBS:
        return False
    manager = node.func.value
    if not isinstance(manager, ast.Attribute) or manager.attr != "objects":
        return False
    model = manager.value
    return isinstance(model, ast.Name) and model.id in OWNED_MODELS


def test_scanner_flags_an_unscoped_owned_query(tmp_path):
    (tmp_path / "leaky.py").write_text("ExchangeCredential.objects.get(pk=1)\n")
    (tmp_path / "clean.py").write_text("Watchlist.for_user(user_a)\n")
    assert _unscoped_owned_query_offenders(tmp_path) == [str(tmp_path / "leaky.py")]


def test_scanner_flags_an_unscoped_all_on_the_other_model(tmp_path):
    (tmp_path / "leaky.py").write_text("Watchlist.objects.all()\n")
    (tmp_path / "clean.py").write_text("x = 1\n")
    assert _unscoped_owned_query_offenders(tmp_path) == [str(tmp_path / "leaky.py")]


@pytest.mark.parametrize(
    "query",
    [
        "PositionSnapshot.objects.all()",
        "PositionSnapshot.objects.filter(user=user_a)",
        "AccountSnapshot.objects.get(pk=1)",
        "AccountSnapshot.objects.exclude(ts=ts)",
        "Trade.objects.first()",
        "Trade.objects.get_or_create(user=user_a, trade_id='T1')",
        "ChartLayout.objects.all()",
        "Drawing.objects.all()",
    ],
)
def test_scanner_flags_the_private_models(tmp_path, query):
    # R14.3: the 3 new owned models are scoped exactly like credentials/watchlist.
    (tmp_path / "leaky.py").write_text(f"{query}\n")
    (tmp_path / "clean.py").write_text("PositionSnapshot.for_user(user_a)\n")
    assert _unscoped_owned_query_offenders(tmp_path) == [str(tmp_path / "leaky.py")]


def test_scanner_allows_for_user_on_the_private_models(tmp_path):
    (tmp_path / "scoped.py").write_text(
        "PositionSnapshot.for_user(user_a)\n"
        "AccountSnapshot.for_user(user_a)\n"
        "Trade.for_user(user_a)\n"
    )
    assert _unscoped_owned_query_offenders(tmp_path) == []


def test_request_path_covers_the_market_app():
    # R14.3 spirit: every request-serving app stays inside the scanned path.
    assert WEB / "market" in REQUEST_PATH


@pytest.mark.parametrize(
    "query",
    [
        "ExchangeCredential.objects.filter(is_active=True)",
        "Watchlist.objects.exclude(symbol='BTCUSDT')",
        "ExchangeCredential.objects.first()",
        "Watchlist.objects.last()",
        "ExchangeCredential.objects.create(user=user_a)",
        "Watchlist.objects.get_or_create(user=user_a, symbol='BTCUSDT')",
    ],
)
def test_scanner_flags_unscoped_verbs(tmp_path, query):
    (tmp_path / "leaky.py").write_text(f"{query}\n")
    assert _unscoped_owned_query_offenders(tmp_path) == [str(tmp_path / "leaky.py")]


def test_scanner_allows_for_user(tmp_path):
    # R14.3 negative control: for_user is the sanctioned accessor.
    (tmp_path / "scoped.py").write_text(
        "ExchangeCredential.for_user(user_a)\nWatchlist.for_user(user_b)\n"
    )
    assert _unscoped_owned_query_offenders(tmp_path) == []


def test_scanner_skips_pycache(tmp_path):
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "leaky.py").write_text("ExchangeCredential.objects.all()\n")
    (tmp_path / "clean.py").write_text("x = 1\n")
    assert _unscoped_owned_query_offenders(tmp_path) == []


def test_request_path_has_no_unscoped_owned_query():
    # R14.3: the real request-serving tree must be clean today.
    offenders = [
        f for root in REQUEST_PATH for f in _unscoped_owned_query_offenders(root)
    ]
    assert offenders == [], f"unscoped owned query in request path: {offenders}"


@pytest.mark.django_db
def test_worker_zone_reads_across_users(user_a, user_b):
    # R14.4: the worker is the trusted zone. Reading every user's credentials
    # through the unscoped default manager is legitimate and MUST stay readable;
    # it is not a cross-tenant request-path read.
    from trading.models import ExchangeCredential

    mine = ExchangeCredential.objects.create(
        user=user_a, api_key_encrypted="k-a", api_secret_encrypted="s-a"
    )
    theirs = ExchangeCredential.objects.create(
        user=user_b, api_key_encrypted="k-b", api_secret_encrypted="s-b"
    )

    readable = set(ExchangeCredential.objects.all())
    assert readable == {mine, theirs}
