"""R13/R11-credential contract: Fernet credential mechanism + worker-only decrypt.

Two invariants, both Provable NOW (no stored credentials required):

1. Round-trip: ``encrypt``/``decrypt`` work with a Fernet key from the env,
   and fail closed when the key is absent.
2. Confinement: no request-serving module (``web/config/`` or ``web/accounts/``)
   imports or calls ``credentials.decrypt`` — decryption is worker-only.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

WEB = Path(__file__).resolve().parent.parent.parent / "web"
REQUEST_PATH = (WEB / "config", WEB / "accounts", WEB / "trading", WEB / "market")
KEY_ENV = "CREDENTIALS_FERNET_KEY"


@pytest.fixture
def fernet_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv(KEY_ENV, key)
    return key


def _decrypt_offenders(root: Path) -> list[str]:
    """Files that reach ``decrypt``: import, attribute call, bare call, getattr.

    Deliberately broad — a false positive in the request path is cheaper than a
    missed decryption, which would break the worker-only invariant.
    """
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            imports_decrypt = (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.split(".")[-1] == "credentials"
                and any(alias.name == "decrypt" for alias in node.names)
            )
            calls_decrypt = isinstance(node, ast.Attribute) and node.attr == "decrypt"
            bare_call = isinstance(node, ast.Name) and node.id == "decrypt"
            # getattr(mod, "decrypt") hides an attribute access behind a string.
            getattr_decrypt = (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and any(
                    isinstance(arg, ast.Constant) and arg.value == "decrypt"
                    for arg in node.args
                )
            )
            if imports_decrypt or calls_decrypt or bare_call or getattr_decrypt:
                offenders.append(str(path))
                break
    return offenders


def test_encrypt_decrypt_round_trip(fernet_key):
    import credentials

    plaintext = "bitunix-api-secret-abc123"
    token = credentials.encrypt(plaintext)
    assert token != plaintext
    assert credentials.decrypt(token) == plaintext


def test_fails_closed_without_key(monkeypatch):
    import credentials

    monkeypatch.delenv(KEY_ENV, raising=False)
    with pytest.raises(RuntimeError):
        credentials.encrypt("x")


def test_request_path_never_decrypts():
    offenders = [f for root in REQUEST_PATH for f in _decrypt_offenders(root)]
    assert offenders == [], f"decrypt reached the request path: {offenders}"


def test_scanner_flags_a_decrypt_call(tmp_path):
    (tmp_path / "leaky.py").write_text(
        "from credentials import decrypt\n\ndecrypt(token)\n"
    )
    (tmp_path / "clean.py").write_text("import os\n")
    assert _decrypt_offenders(tmp_path) == [str(tmp_path / "leaky.py")]


def test_scanner_flags_a_getattr_decrypt(tmp_path):
    (tmp_path / "sneaky.py").write_text("getattr(mod, 'decrypt')(token)\n")
    assert _decrypt_offenders(tmp_path) == [str(tmp_path / "sneaky.py")]


def test_scanner_covers_the_trading_app():
    # R13.2: the new data app must stay inside the scanned request path.
    assert WEB / "trading" in REQUEST_PATH


def test_scanner_covers_the_market_app():
    # R13.2 spirit: every request-serving app stays inside the scanned path.
    assert WEB / "market" in REQUEST_PATH


@pytest.mark.django_db
def test_set_secrets_stores_ciphertext_at_rest(fernet_key, user_a):
    import credentials
    from trading.models import ExchangeCredential

    cred = ExchangeCredential(user=user_a)
    cred.set_secrets("key-abc123", "secret-xyz789")
    cred.save()

    row = ExchangeCredential.objects.get(pk=cred.pk)
    assert row.api_key_encrypted != "key-abc123"
    assert row.api_secret_encrypted != "secret-xyz789"
    assert row.api_key_encrypted != row.api_secret_encrypted
    assert credentials.decrypt(row.api_key_encrypted) == "key-abc123"
    assert credentials.decrypt(row.api_secret_encrypted) == "secret-xyz789"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "api_key,api_secret",
    [
        ("", "secret-xyz789"),
        ("key-abc123", ""),
        ("   ", "secret-xyz789"),
        ("key-abc123", "  \t "),
    ],
)
def test_set_secrets_rejects_blank_inputs(fernet_key, user_a, api_key, api_secret):
    from trading.models import ExchangeCredential

    cred = ExchangeCredential(user=user_a)
    with pytest.raises(ValueError):
        cred.set_secrets(api_key, api_secret)

    assert cred.pk is None
    assert ExchangeCredential.objects.count() == 0


@pytest.mark.django_db
def test_no_plaintext_accessor_exposed(fernet_key, user_a):
    from trading.models import ExchangeCredential

    cred = ExchangeCredential(user=user_a)
    cred.set_secrets("key-abc123", "secret-xyz789")
    cred.save()
    row = ExchangeCredential.objects.get(pk=cred.pk)

    assert not hasattr(row, "api_key")
    assert not hasattr(row, "api_secret")
    public_surface = [name for name in dir(row) if not name.startswith("_")]
    assert not any("decrypt" in name for name in public_surface)
