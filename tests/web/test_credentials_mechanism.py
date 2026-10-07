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
REQUEST_PATH = (WEB / "config", WEB / "accounts")
KEY_ENV = "CREDENTIALS_FERNET_KEY"


@pytest.fixture
def fernet_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv(KEY_ENV, key)
    return key


def _decrypt_offenders(root: Path) -> list[str]:
    """Files that import ``decrypt`` from a credentials module or call it."""
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
            if imports_decrypt or calls_decrypt:
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
