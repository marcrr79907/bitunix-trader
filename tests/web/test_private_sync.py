"""R2/R3 contract: decrypt-free persistence + read-only private fetch.

No sockets: a stub client returns fixtures for ``positions()``/``account()``/
``history_trades()``, so ``sync_user`` exercises the real mapping and the
``bulk_create(ignore_conflicts=True)`` idempotency. The module lives in the
credential scanner's request path, so an AST scan proves it never reaches
``decrypt``.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest
from trading import sync
from trading.models import AccountSnapshot, PositionSnapshot, Trade
from trading.sync import (
    persist_account,
    persist_positions,
    persist_trades,
    sync_user,
)

TS = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

POSITION = {
    "symbol": "BTCUSDT",
    "side": "BUY",
    "qty": "0.5",
    "avgOpenPrice": "50000",
    "leverage": "10",
    "liqPrice": "45000",
    "unrealizedPNL": "125.5",
    "marginRate": "0.05",
}
ACCOUNT = [
    {
        "available": "1000.25",
        "crossUnrealizedPNL": "-12.5",
    }
]
TRADE = {
    "tradeId": "T-1",
    "symbol": "BTCUSDT",
    "side": "SELL",
    "qty": "0.5",
    "price": "51000",
    "fee": "2.5",
    "realizedPNL": "500",
    "ctime": 1700000000000,
    "orderId": "ignored",
}


class StubClient:
    """Read-only double: fixtures only, never opens a socket."""

    def __init__(self, positions=(), account=(), trades=()):
        self._positions = list(positions)
        self._account = account
        self._trades = list(trades)

    def positions(self, symbol=None):
        return self._positions

    def account(self, margin_coin="USDT"):
        return self._account

    def history_trades(self, symbol=None, skip=0):
        return {"tradeList": self._trades[skip : skip + 100]}


# --- R2: idempotent persistence -------------------------------------------


@pytest.mark.django_db
def test_persist_positions_twice_is_idempotent(user_a):
    assert persist_positions(user_a, [POSITION], TS) == 1
    assert persist_positions(user_a, [POSITION], TS) == 0
    assert PositionSnapshot.objects.count() == 1


@pytest.mark.django_db
def test_persist_account_twice_is_idempotent(user_a):
    assert persist_account(user_a, ACCOUNT, TS) == 1
    assert persist_account(user_a, ACCOUNT, TS) == 0
    assert AccountSnapshot.objects.count() == 1


@pytest.mark.django_db
def test_persist_trades_twice_is_idempotent(user_a):
    assert persist_trades(user_a, [TRADE]) == 1
    assert persist_trades(user_a, [TRADE]) == 0
    assert Trade.objects.count() == 1


@pytest.mark.django_db
def test_empty_inputs_persist_nothing(user_a):
    assert persist_positions(user_a, [], TS) == 0
    assert persist_account(user_a, [], TS) == 0
    assert persist_account(user_a, None, TS) == 0
    assert persist_trades(user_a, []) == 0
    assert PositionSnapshot.objects.count() == 0
    assert AccountSnapshot.objects.count() == 0
    assert Trade.objects.count() == 0


# --- R3: mapping mirrors the CLI rows --------------------------------------


@pytest.mark.django_db
def test_position_mapping(user_a):
    persist_positions(user_a, [POSITION], TS)
    row = PositionSnapshot.for_user(user_a).get()

    assert row.symbol == "BTCUSDT"
    assert row.side == "BUY"
    assert row.qty == 0.5
    assert row.avg_open == 50000.0
    assert row.leverage == 10
    assert row.liq_price == 45000.0
    assert row.upnl == 125.5
    assert row.margin_rate == 0.05
    assert row.ts == TS


@pytest.mark.django_db
def test_account_mapping_and_list_normalization(user_a):
    persist_account(user_a, ACCOUNT, TS)
    row = AccountSnapshot.for_user(user_a).get()

    assert row.available == 1000.25
    assert row.cross_upnl == -12.5
    assert row.ts == TS
    # A bare dict is normalized the same way.
    assert persist_account(user_a, ACCOUNT[0], TS.replace(hour=13)) == 1


@pytest.mark.django_db
def test_trade_mapping_omits_order_id(user_a):
    persist_trades(user_a, [TRADE])
    row = Trade.for_user(user_a).get()

    assert row.trade_id == "T-1"
    assert row.symbol == "BTCUSDT"
    assert row.side == "SELL"
    assert row.qty == 0.5
    assert row.price == 51000.0
    assert row.fee == 2.5
    assert row.realized_pnl == 500.0
    assert row.ctime == 1700000000000
    assert not hasattr(row, "order_id")


@pytest.mark.django_db
def test_unparseable_floats_become_null(user_a):
    persist_positions(user_a, [{"symbol": "ETHUSDT", "qty": "x"}], TS)
    row = PositionSnapshot.for_user(user_a).get()
    assert row.qty is None
    assert row.avg_open is None


# --- sync_user: orchestrates the three series ------------------------------


@pytest.mark.django_db
def test_sync_user_persists_all_three(user_a):
    client = StubClient([POSITION], ACCOUNT, [TRADE])
    result = sync_user(user_a, client, ts=TS)

    assert result == {"positions": 1, "account": 1, "trades": 1}
    assert PositionSnapshot.for_user(user_a).count() == 1
    assert AccountSnapshot.for_user(user_a).count() == 1
    assert Trade.for_user(user_a).count() == 1


@pytest.mark.django_db
def test_sync_user_twice_is_a_noop(user_a):
    client = StubClient([POSITION], ACCOUNT, [TRADE])
    sync_user(user_a, client, ts=TS)
    assert sync_user(user_a, client, ts=TS) == {
        "positions": 0,
        "account": 0,
        "trades": 0,
    }


@pytest.mark.django_db
def test_fetch_trades_paginates(user_a):
    trades = [
        {"tradeId": f"T-{i}", "symbol": "BTCUSDT", "ctime": i} for i in range(150)
    ]
    result = sync_user(user_a, StubClient(trades=trades), ts=TS)
    assert result["trades"] == 150
    assert Trade.for_user(user_a).count() == 150


# --- R3/R13: the module never reaches decrypt ------------------------------


def _decrypt_offenders(root: Path) -> list[str]:
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            imports = (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.split(".")[-1] == "credentials"
                and any(a.name == "decrypt" for a in node.names)
            )
            attr = isinstance(node, ast.Attribute) and node.attr == "decrypt"
            bare = isinstance(node, ast.Name) and node.id == "decrypt"
            hidden = (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and any(
                    isinstance(a, ast.Constant) and a.value == "decrypt"
                    for a in node.args
                )
            )
            if imports or attr or bare or hidden:
                offenders.append(str(path))
                break
    return offenders


def test_sync_module_has_no_decrypt_reference():
    module_file = Path(sync.__file__).resolve()
    # The whole trading tree is in the scanner's request path; sync.py must be
    # clean, and none of its siblings may smuggle a decrypt reference either.
    assert _decrypt_offenders(module_file.parent) == []


def test_scanner_flags_a_decrypt_call(tmp_path):
    (tmp_path / "leaky.py").write_text("from credentials import decrypt\n")
    (tmp_path / "clean.py").write_text("import os\n")
    assert _decrypt_offenders(tmp_path) == [str(tmp_path / "leaky.py")]
