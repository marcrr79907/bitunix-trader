"""R4/R5 contract: worker trusted-zone private sync.

Decryption lives ONLY in ``web/worker.py`` (outside the credential scanner's
request path). Tests drive ``run_private_sync`` with an injected client factory
and a real Fernet fixture key, so the real ``decrypt``/``sync_user``/persist
chain runs with no sockets. Per-user isolation and the ``run_once`` return
contract are proven explicitly.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import worker
from cryptography.fernet import Fernet
from trading import sync as trading_sync
from trading.models import (
    AccountSnapshot,
    ExchangeCredential,
    FundingSnapshot,
    PositionSnapshot,
    TickerSnapshot,
    Trade,
)

from src.client import BitunixError

KEY_ENV = "CREDENTIALS_FERNET_KEY"

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
ACCOUNT = [{"available": "1000.25", "crossUnrealizedPNL": "-12.5"}]
TRADE = {
    "tradeId": "T-1",
    "symbol": "BTCUSDT",
    "side": "SELL",
    "qty": "0.5",
    "price": "51000",
    "fee": "2.5",
    "realizedPNL": "500",
    "ctime": 1700000000000,
}


@pytest.fixture
def fernet_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv(KEY_ENV, key)
    return key


class PrivateStubClient:
    """Read-only private double: fixtures only, never opens a socket."""

    def __init__(self, error: Exception | None = None):
        self._error = error

    def positions(self, symbol=None):
        if self._error is not None:
            raise self._error
        return [POSITION]

    def account(self, margin_coin="USDT"):
        return ACCOUNT

    def history_trades(self, symbol=None, skip=0):
        return {"tradeList": [TRADE] if skip == 0 else []}


class MarketStub:
    """Serves funding/ticker and an empty kline for the global ingest path."""

    def tickers(self, symbols=None):
        return [
            {
                "symbol": "BTCUSDT",
                "lastPrice": "1",
                "high": "1",
                "low": "1",
                "quoteVol": "1",
            }
        ]

    def funding_rate_batch(self):
        return [
            {
                "symbol": "BTCUSDT",
                "fundingRate": "0.0001",
                "fundingInterval": "8",
                "nextFundingTime": "1700000000000",
                "markPrice": "1",
                "indexPrice": "1",
            }
        ]

    def kline(self, symbol, interval="1m", limit=100, start_time=None, end_time=None):
        return []


def _make_credential(user, key="plain-key", secret="plain-secret", is_active=True):
    cred = ExchangeCredential(user=user, is_active=is_active)
    cred.set_secrets(key, secret)
    cred.save()
    return cred


# --- R4: active credentials are decrypted and synced per user ---------------


@pytest.mark.django_db
def test_active_credential_is_decrypted_and_persisted(user_a, fernet_key):
    _make_credential(user_a, key="plain-key-a", secret="plain-secret-a")
    seen = {}

    def factory(api_key, secret):
        seen["api_key"] = api_key
        seen["secret"] = secret
        return PrivateStubClient()

    assert worker.run_private_sync(client_factory=factory) == 1

    # decrypt() recovered the original plaintext for BOTH columns.
    assert seen == {"api_key": "plain-key-a", "secret": "plain-secret-a"}
    assert PositionSnapshot.for_user(user_a).count() == 1
    assert AccountSnapshot.for_user(user_a).count() == 1
    assert Trade.for_user(user_a).count() == 1


@pytest.mark.django_db
def test_inactive_credential_is_skipped_without_fetch(user_a, fernet_key):
    _make_credential(user_a, is_active=False)
    calls = []

    def factory(api_key, secret):
        calls.append((api_key, secret))
        return PrivateStubClient()

    assert worker.run_private_sync(client_factory=factory) == 0
    assert calls == []
    assert PositionSnapshot.objects.count() == 0


@pytest.mark.django_db
def test_no_credentials_is_a_noop(fernet_key):
    calls = []

    def factory(api_key, secret):
        calls.append((api_key, secret))
        return PrivateStubClient()

    assert worker.run_private_sync(client_factory=factory) == 0
    assert calls == []


# --- R5: per-user isolation -------------------------------------------------


@pytest.mark.django_db
def test_one_failing_user_does_not_stop_peers(user_a, user_b, fernet_key):
    _make_credential(user_a, key="ka", secret="sa")
    _make_credential(user_b, key="kb", secret="sb")

    def factory(api_key, secret):
        if api_key == "ka":
            return PrivateStubClient(error=BitunixError(500, "boom"))
        return PrivateStubClient()

    # Only B succeeds; A's raise is contained.
    assert worker.run_private_sync(client_factory=factory) == 1
    assert PositionSnapshot.for_user(user_b).count() == 1
    assert Trade.for_user(user_b).count() == 1
    assert PositionSnapshot.for_user(user_a).count() == 0


@pytest.mark.django_db
def test_run_once_survives_private_sync_failure(user_a, fernet_key, monkeypatch):
    _make_credential(user_a)

    def boom():
        raise RuntimeError("private boom")

    monkeypatch.setattr(worker, "run_private_sync", boom)

    # Global ingest still produces the (funding, ticker) contract.
    assert worker.run_once(MarketStub(), ["BTCUSDT"]) == (1, 1)
    assert FundingSnapshot.objects.count() == 1
    assert TickerSnapshot.objects.count() == 1


# --- decrypt confinement: worker owns it, sync.py never touches it ----------


def _has_decrypt_reference(path: Path) -> bool:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        imports_decrypt = (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[-1] == "credentials"
            and any(alias.name == "decrypt" for alias in node.names)
        )
        attr = isinstance(node, ast.Attribute) and node.attr == "decrypt"
        bare = isinstance(node, ast.Name) and node.id == "decrypt"
        hidden = (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and any(
                isinstance(arg, ast.Constant) and arg.value == "decrypt"
                for arg in node.args
            )
        )
        if imports_decrypt or attr or bare or hidden:
            return True
    return False


def test_sync_is_decrypt_free_while_worker_owns_it():
    assert _has_decrypt_reference(Path(trading_sync.__file__).resolve()) is False
    # Positive control: the scanner is not vacuously green.
    assert _has_decrypt_reference(Path(worker.__file__).resolve()) is True
