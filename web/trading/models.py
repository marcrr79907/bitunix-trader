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


class PositionSnapshot(UserOwnedModel):
    """Per-user open-position snapshot (R1). Mirrors ``src.monitor.position_row``.

    ``ts`` is the poll instant (UTC); ``(user, symbol, ts)`` makes a re-poll the
    same instant a no-op. All numeric fields are nullable because the API may
    omit them and a real zero must never be confused with a missing value.
    """

    symbol = models.CharField(max_length=32)
    side = models.CharField(max_length=8, null=True)
    qty = models.FloatField(null=True)
    avg_open = models.FloatField(null=True)
    leverage = models.IntegerField(null=True)
    liq_price = models.FloatField(null=True)
    upnl = models.FloatField(null=True)
    margin_rate = models.FloatField(null=True)
    ts = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "symbol", "ts"], name="uniq_position_user_symbol_ts"
            )
        ]


class AccountSnapshot(UserOwnedModel):
    """Per-user account balance snapshot (R1). Unique ``(user, ts)``."""

    available = models.FloatField(null=True)
    cross_upnl = models.FloatField(null=True)
    ts = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "ts"], name="uniq_account_user_ts")
        ]


class Trade(UserOwnedModel):
    """Per-user history trade (R1). Mirrors ``src.journal.trade_row``.

    ``trade_id`` is the exchange id; uniqueness is per user so two users may
    share one exchange trade id. ``order_id`` is intentionally not stored.
    """

    trade_id = models.CharField(max_length=64)
    symbol = models.CharField(max_length=32)
    side = models.CharField(max_length=8, null=True)
    qty = models.FloatField(null=True)
    price = models.FloatField(null=True)
    fee = models.FloatField(null=True)
    realized_pnl = models.FloatField(null=True)
    ctime = models.BigIntegerField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "trade_id"], name="uniq_trade_user_trade_id"
            )
        ]


class ChartLayout(UserOwnedModel):
    """Per-user persisted chart layout (R14): one layout per chart.

    TradingView-style — one layout per ``(user, symbol, interval)``, enforced by
    the unique constraint. ``indicators`` is a JSON list of ``{token, params}``
    (params an object); the registry is open-ended, so a JSON column avoids a
    migration per indicator token. ``updated_at`` is the save instant.
    """

    symbol = models.CharField(max_length=32)
    interval = models.CharField(max_length=8)
    indicators = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "symbol", "interval"],
                name="uniq_layout_user_symbol_interval",
            )
        ]


class Drawing(UserOwnedModel):
    """Per-user, per-SYMBOL chart annotation collection (R14, R1): one row per shape.

    Unlike ``ChartLayout`` (one row per chart), a chart holds **many** drawings,
    so there is **no unique constraint** on ``(user, symbol)`` — only an index
    for the filtered read. The key is the SYMBOL (not the interval): a drawing is
    visible across every interval of a pair (TradingView-style) and is cleared
    only on a symbol change. ``kind`` is one of ``Kind``; ``points`` is a
    per-kind JSON object and ``style`` a JSON object (see design schemas).
    """

    class Kind(models.TextChoices):
        HLINE = "hline"
        TRENDLINE = "trendline"
        FIB = "fib"
        RECT = "rect"
        TEXT = "text"

    symbol = models.CharField(max_length=32)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    points = models.JSONField(default=dict)
    style = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["user", "symbol"],
                name="ix_drawing_user_symbol",
            )
        ]


class AlertRule(UserOwnedModel):
    """Per-user alert rule (issue #76, Fase D1), evaluated deterministically.

    A pure, framework-free engine evaluates ``condition`` over a window of closed
    candles and reports the false→true edge; the worker records the fired bar in
    ``last_fired_at``, which doubles as the dedup key. D1 defines and evaluates
    only — it never notifies or orders (D2 owns delivery). Like ``Drawing`` a
    rule is a **collection** (many rules per ``(user, symbol, interval)``), so
    there is **no unique constraint** — only an index on ``(user, is_active)``
    for the active-rule read. ``interval`` is matched against the worker's
    ``CANDLE_INTERVALS`` at evaluation time (only persisted closed candles are
    deterministic).
    """

    symbol = models.CharField(max_length=32)
    interval = models.CharField(max_length=8)
    condition = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    last_fired_at = models.DateTimeField(null=True, blank=True)
    telegram_chat_id = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(
                fields=["user", "is_active"],
                name="ix_alertrule_user_active",
            )
        ]


class ChartPreference(UserOwnedModel):
    """Per-user, user-global chart preference (R8): one row per user.

    Distinct from ``ChartLayout`` (per ``(user, symbol, interval)``): the last
    interval a user viewed is global across charts, so the owner is a
    ``OneToOneField`` and ``last_interval`` is validated against
    ``quotes.INTERVALS`` in the view, not the model.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chart_preference",
    )
    last_interval = models.CharField(max_length=8, default="1m")
    scale_mode = models.CharField(max_length=16, default="linear")
    chart_type = models.CharField(max_length=16, default="candles")
    theme = models.CharField(max_length=16, default="system")
    updated_at = models.DateTimeField(auto_now=True)
