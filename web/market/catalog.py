"""Exchange-wide symbol catalog (F11 A-S1, spec ``symbol-catalog``).

``client.tickers()`` with NO argument already returns every pair
(``src/client.py:118-120``), so the universe needs no new client method. This
module projects that payload down to symbol strings and caches the projection
process-locally for ``CATALOG_TTL_SECONDS``.

The cache stores the PROJECTED tuple, never the ticker payload: callers only
ever need names, and the full objects are large. A failed refresh propagates and
leaves the previous value intact — the catalog is reference data, so a transient
network blip must not degrade callers to "cold" (which would make the alerts
path fail open on every symbol).

Imports are stdlib + ``src.client``/``src.config`` only: no Django model and no
``market.views`` (the view imports this module, so the dependency runs one way).
"""

from __future__ import annotations

import re
import time

from src.client import BitunixClient

CATALOG_TTL_SECONDS = 60

# Canonical exchange-symbol shape. One definition shared by the watchlist POST,
# the alerts validator and the worker's union builder.
SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,24}$")

# (fetched_at, symbols) — module-level, process-local.
_cache: tuple[float, tuple[str, ...]] | None = None


def reset_cache() -> None:
    """Drop the cached catalog (test seam; never called from a request path)."""
    global _cache
    _cache = None


def list_symbols(client=None, *, now=None) -> list[str]:
    """Return the sorted, de-duplicated exchange symbol list.

    Served from the cache when younger than ``CATALOG_TTL_SECONDS``. An upstream
    failure propagates and MUST NOT clear or replace a previous value.
    """
    global _cache
    resolved_now = time.time() if now is None else now

    if _cache is not None:
        fetched_at, symbols = _cache
        if resolved_now - fetched_at < CATALOG_TTL_SECONDS:
            return list(symbols)

    fetched = (client or BitunixClient()).tickers()
    symbols = tuple(sorted({row["symbol"] for row in fetched if row.get("symbol")}))
    _cache = (resolved_now, symbols)
    return list(symbols)


def symbol_exists(symbol, *, client=None) -> bool:
    """True when ``symbol`` is in the catalog. Offline when the cache is warm.

    Raises whatever the upstream fetch raises (the caller decides whether an
    unavailable catalog means "reject" or "fail open").
    """
    return symbol in list_symbols(client=client)
