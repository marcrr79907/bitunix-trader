"""Global market ingestion service (R3).

Reuses the proven ``src.monitor.fetch_rows`` parser so field names never fork,
splits each row into a funding and a ticker dict, converts the epoch-ms stamp to
a UTC ``datetime`` exactly once, and persists both via a single idempotent
``bulk_create(ignore_conflicts=True)`` transaction. Read-only.
"""

from __future__ import annotations

from datetime import UTC, datetime

from django.db import transaction

from src.monitor import fetch_rows
from trading.models import FundingSnapshot, TickerSnapshot


def fetch_market(client, symbols) -> dict[str, list[dict]]:
    """Fetch and split each row into independent funding + ticker model dicts.

    ``src.monitor.fetch_rows`` fabricates one default row per requested symbol,
    so a symbol absent from the API response comes back with every price field
    ``None``. Funding and tickers are independent API series, so presence is
    decided per series rather than per row:

    * a funding dict is emitted only when the funding payload is real
      (``mark_price`` or ``index_price`` present — both come from the funding
      endpoint), never on ``funding_rate == 0.0``, which is a legitimate rate;
    * a ticker dict is emitted only when ``last_price`` is present.

    A missing series writes nothing instead of a fabricated ``0.0``/``None`` row
    into an immutable ``(symbol, ts)`` series.
    """
    funding: list[dict] = []
    tickers: list[dict] = []
    for r in fetch_rows(client, symbols):
        ts = datetime.fromtimestamp(r["ts"] / 1000, tz=UTC)
        if r["mark_price"] is not None or r["index_price"] is not None:
            funding.append(
                {
                    "symbol": r["symbol"],
                    "ts": ts,
                    "funding_rate": r["funding"],
                    "mark_price": r["mark_price"],
                    "index_price": r["index_price"],
                    "next_funding_time": r["next_funding_time"],  # raw epoch ms
                    "funding_interval": r["funding_interval"],
                }
            )
        if r["last_price"] is not None:
            tickers.append(
                {
                    "symbol": r["symbol"],
                    "ts": ts,
                    "last_price": r["last_price"],
                    "high": r["high"],
                    "low": r["low"],
                    "quote_vol": r["quote_vol"],
                }
            )
    return {"funding": funding, "tickers": tickers}


def persist_market(funding, tickers) -> tuple[int, int]:
    """Persist both slices in one transaction; ignore duplicate (symbol, ts).

    ``bulk_create(ignore_conflicts=True)`` returns every attempted object, not
    the inserted ones, so the inserted count comes from a row-count delta.
    """
    with transaction.atomic():
        f_before = FundingSnapshot.objects.count()
        FundingSnapshot.objects.bulk_create(
            [FundingSnapshot(**row) for row in funding], ignore_conflicts=True
        )
        n_funding = FundingSnapshot.objects.count() - f_before

        t_before = TickerSnapshot.objects.count()
        TickerSnapshot.objects.bulk_create(
            [TickerSnapshot(**row) for row in tickers], ignore_conflicts=True
        )
        n_tickers = TickerSnapshot.objects.count() - t_before
    return n_funding, n_tickers
