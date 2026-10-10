"""Worker service: real global market ingester (R4).

Boots Django, then polls the two read-only public endpoints on an interval and
persists global snapshots via ``trading.ingest``. Django is imported lazily so
importing this module (e.g. ``scheduler`` reusing ``idle_loop``) does NOT force
``django.setup()``.

The ``idle_loop`` Redis-ping stub is kept unchanged for ``web/scheduler.py``.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from threading import Event

import requests

from src import config
from src.client import BitunixError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

IDLE_SECONDS = 30
INGEST_POLL_SECONDS = int(os.environ.get("INGEST_POLL_SECONDS", "30"))
_MAX_BACKOFF_SECONDS = 300


def _bootstrap() -> None:
    """Configure Django settings and initialise the app registry."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    import django

    django.setup()


def run_once(client, symbols) -> tuple[int, int]:
    """Fetch one market snapshot and persist it. Returns (funding, ticker) counts.

    A closed-candle cycle runs AFTER tick ingestion and is isolated: a candle
    failure must never degrade funding/ticker persistence or kill the loop.
    The return contract stays ``(funding, ticker)`` for existing callers.
    """
    from trading.candles import fetch_closed_candles, persist_candles
    from trading.ingest import fetch_market, persist_market

    market = fetch_market(client, symbols)
    counts = persist_market(market["funding"], market["tickers"])
    try:
        n_candles = persist_candles(fetch_closed_candles(client, symbols))
        logger.info("candle cycle ok persisted=%d", n_candles)
    except (
        Exception
    ) as exc:  # ponytail: broad by spec — candle failure must never kill ticks
        logger.warning("candle cycle failed: %s", exc)
    try:
        n_users = run_private_sync()
        logger.info("private sync ok users=%d", n_users)
    except (
        Exception
    ) as exc:  # ponytail: broad by spec — private failure must never kill ticks
        logger.warning("private sync failed: %s", exc)
    return counts


def run_private_sync(client_factory=None) -> int:
    """Trusted-zone private sync: decrypt active creds, fetch, persist (R4).

    ``worker.py`` is outside the credential scanner's request path and the
    owned-model guard, so it MAY read ``ExchangeCredential`` unscoped and call
    ``decrypt``. Each user is isolated: one credential's failure is logged and
    the loop continues (R5). Returns the number of users synced.
    """
    from credentials import decrypt
    from trading.models import ExchangeCredential
    from trading.sync import sync_user

    from src.client import BitunixClient

    factory = client_factory or BitunixClient
    synced = 0
    for cred in ExchangeCredential.objects.filter(is_active=True):
        try:
            client = factory(
                decrypt(cred.api_key_encrypted),
                decrypt(cred.api_secret_encrypted),
            )
            sync_user(cred.user, client)
            synced += 1
        except (
            Exception
        ) as exc:  # ponytail: per-user isolation by spec (R5) — never abort peers
            logger.warning("private sync failed user=%s: %s", cred.user_id, exc)
    return synced


def run_loop(client, symbols=None, iterations=None, stop=None, sleep=time.sleep) -> int:
    """Poll the market until ``iterations`` or ``stop()``; back off on errors.

    No real sleeps when ``sleep`` is injected, so tests reach every branch.
    """
    symbols = config.SYMBOLS if symbols is None else symbols
    backoff, count = INGEST_POLL_SECONDS, 0
    while iterations is None or count < iterations:
        if stop is not None and stop():
            break
        try:
            n_funding, n_tickers = run_once(client, symbols)
            logger.info(
                "cycle ok symbols=%d funding=%d tickers=%d",
                len(symbols),
                n_funding,
                n_tickers,
            )
            backoff = INGEST_POLL_SECONDS
        except (BitunixError, requests.RequestException) as exc:
            logger.warning("cycle failed: %s; backoff=%ds", exc, backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)
        count += 1
        sleep(backoff)
    return 0


def _install_signal_handlers() -> Event:
    """Flip the returned Event on SIGTERM/SIGINT; checked between cycles."""
    stop = Event()

    def _handle(signum, frame):
        logger.info("signal %s received; stopping after current cycle", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    return stop


def main(
    iterations=None, client=None, symbols=None, stop=None, sleep=time.sleep
) -> int:
    _bootstrap()
    from src.client import BitunixClient

    # ``run_loop`` expects ``stop`` to be a callable predicate. When none is
    # injected (the deployed path), install signal handlers and pass the
    # Event's ``is_set`` bound method — passing the Event itself raised
    # ``TypeError: 'Event' object is not callable`` in production.
    if stop is None:
        stop = _install_signal_handlers().is_set

    return run_loop(
        client or BitunixClient(),
        symbols,
        iterations,
        stop,
        sleep,
    )


# --- Phase 0 stub kept for web/scheduler.py (R5) ---


def ping_redis() -> None:
    """Connect to Redis via ``REDIS_URL`` and ping. Raises if unreachable."""
    import redis

    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    redis.Redis.from_url(url).ping()


def idle_loop(iterations: int | None = None) -> int:
    """Ping Redis each pass, then idle. Returns 0 on clean exit."""
    count = 0
    while iterations is None or count < iterations:
        ping_redis()
        logger.info("worker up; redis reachable; idle (no business logic)")
        count += 1
        if iterations is None:
            time.sleep(IDLE_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
