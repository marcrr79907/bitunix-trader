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


class FundingSnapshot(models.Model):
    """Global funding snapshot, shared by all users (R1). No owner FK.

    ``next_funding_time`` stays a raw epoch-ms integer; ``ts`` is the poll
    instant (UTC). The unique ``(symbol, ts)`` makes re-persist a no-op.
    """

    symbol = models.CharField(max_length=32)
    ts = models.DateTimeField()
    funding_rate = models.FloatField(null=True)
    mark_price = models.FloatField(null=True)
    index_price = models.FloatField(null=True)
    next_funding_time = models.BigIntegerField(null=True)
    funding_interval = models.IntegerField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "ts"], name="uniq_funding_symbol_ts"
            )
        ]


class TickerSnapshot(models.Model):
    """Global ticker snapshot, shared by all users (R1). No owner FK."""

    symbol = models.CharField(max_length=32)
    ts = models.DateTimeField()
    last_price = models.FloatField(null=True)
    high = models.FloatField(null=True)
    low = models.FloatField(null=True)
    quote_vol = models.FloatField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "ts"], name="uniq_ticker_symbol_ts"
            )
        ]


class Candle(models.Model):
    """Global OHLC candle, shared by all users (R1). No owner FK.

    Persisted directly from BitUnix, one row per (symbol, interval, time).
    ``time`` is the candle OPEN in UNIX seconds; ``(symbol, interval, time)``
    is the idempotency key. The composite index is redundant with the unique
    constraint on Postgres but is mandated by spec R1.
    """

    symbol = models.CharField(max_length=32)
    interval = models.CharField(max_length=8)
    time = models.BigIntegerField()
    open = models.FloatField()
    high = models.FloatField()
    low = models.FloatField()
    close = models.FloatField()
    quote_vol = models.FloatField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "interval", "time"],
                name="uniq_candle_symbol_interval_time",
            )
        ]
        indexes = [
            models.Index(
                fields=["symbol", "interval", "time"],
                name="ix_candle_symbol_interval_time",
            )
        ]


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
