"""User-owned trading data: credentials and watchlists.

`UserOwnedModel` is the ownership seam (R14): one abstract base carries the
owner FK and the `for_user(user)` scoping classmethod, so every owned model
fails closed when access routes through it. Secrets stay ciphertext-only here;
`set_secrets`/decryption live at the WU2 boundary and the worker trust zone.
"""

from __future__ import annotations

from credentials import encrypt
from django.conf import settings
from django.db import models


class UserOwnedModel(models.Model):
    """Abstract owner-scoped base. Fail-closed: no owner → empty queryset."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    class Meta:
        abstract = True

    @classmethod
    def for_user(cls, user):
        return cls.objects.filter(user=user)


class ExchangeCredential(UserOwnedModel):
    """Per-user exchange API credentials, encrypted at rest (R13)."""

    label = models.CharField(max_length=64, blank=True)
    api_key_encrypted = models.TextField()
    api_secret_encrypted = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def set_secrets(self, api_key: str, api_secret: str) -> None:
        """Encryption boundary: ciphertext-only columns, never plaintext.

        No ``decrypt_*`` accessor exists by design (R13.3): the model stays
        key-unaware, and the scanner forbids decryption in request paths.
        """
        for value in (api_key, api_secret):
            if not value or not value.strip():
                raise ValueError("api_key and api_secret must be non-empty")
        self.api_key_encrypted = encrypt(api_key)
        self.api_secret_encrypted = encrypt(api_secret)


class Watchlist(UserOwnedModel):
    """Per-user symbol watchlist (R14.5)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="watchlist",
    )
    symbol = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "symbol"], name="uniq_user_symbol")
        ]
