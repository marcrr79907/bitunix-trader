"""Fernet credential mechanism (R13).

Encrypts/decrypts exchange API keys. The key comes from the environment and
**decryption is worker-only**: request-serving modules (``web/config/``,
``web/accounts/``) must never import ``decrypt`` from here. Enforcement is by
``tests/web/test_credentials_mechanism.py``.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet

KEY_ENV = "CREDENTIALS_FERNET_KEY"


def _fernet() -> Fernet:
    key = os.environ.get(KEY_ENV)
    if not key:
        raise RuntimeError(f"{KEY_ENV} is not set; refusing to handle credentials")
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    """Encrypt ``plaintext`` and return a Fernet token (URL-safe ASCII)."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a Fernet token. Worker trust zone only — see module docstring."""
    return _fernet().decrypt(token.encode()).decode()
