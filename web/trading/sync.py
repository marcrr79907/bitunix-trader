"""Read-only private sync: fetch + persist, no decryption (R2/R3).

Lives inside the credential scanner's request path, so it MUST NOT reach
``credentials.decrypt`` — the worker owns decryption and hands over an already
authenticated client. Persistence mirrors ``ingest.py``/``candles.py``:
model-ready dicts via ``bulk_create(ignore_conflicts=True)`` and an inserted
count from a row-count delta. Field names mirror ``src.monitor.position_row``
and ``src.journal.trade_row``; ``side`` is stored raw (no LONG/SHORT coercion)
and ``order_id`` is intentionally dropped.
"""

from __future__ import annotations

from datetime import UTC, datetime

from django.db import transaction

from trading.models import AccountSnapshot, PositionSnapshot, Trade

_PAGE = 100


def _f(value) -> float | None:
    """Coerce a raw API field to float; None when absent or unparseable."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _i(value) -> int | None:
    """Coerce a raw API field to int; None when absent or unparseable."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _position_dict(raw: dict, ts: datetime) -> dict:
    return {
        "symbol": raw.get("symbol", ""),
        "side": raw.get("side"),
        "qty": _f(raw.get("qty")),
        "avg_open": _f(raw.get("avgOpenPrice")),
        "leverage": _i(raw.get("leverage")),
        "liq_price": _f(raw.get("liqPrice")),
        "upnl": _f(raw.get("unrealizedPNL")),
        "margin_rate": _f(raw.get("marginRate")),
        "ts": ts,
    }


def _trade_dict(raw: dict) -> dict:
    return {
        "trade_id": raw.get("tradeId", ""),
        "symbol": raw.get("symbol", ""),
        "side": raw.get("side"),
        "qty": _f(raw.get("qty")),
        "price": _f(raw.get("price")),
        "fee": _f(raw.get("fee")),
        "realized_pnl": _f(raw.get("realizedPNL")),
        "ctime": _i(raw.get("ctime")),
    }


def persist_positions(user, rows, ts) -> int:
    """Persist position dicts for ``user``; duplicates on (user, symbol, ts)."""
    if not rows:
        return 0
    with transaction.atomic():
        before = PositionSnapshot.objects.count()
        PositionSnapshot.objects.bulk_create(
            [PositionSnapshot(user=user, **_position_dict(r, ts)) for r in rows],
            ignore_conflicts=True,
        )
        return PositionSnapshot.objects.count() - before


def persist_account(user, row, ts) -> int:
    """Persist one account snapshot for ``user``; duplicates on (user, ts).

    The API returns a one-element list despite docs showing a dict, so a list
    input is normalized to its first element (empty list → nothing).
    """
    if isinstance(row, list):
        row = row[0] if row else None
    if not row:
        return 0
    record = {
        "user": user,
        "available": _f(row.get("available")),
        "cross_upnl": _f(row.get("crossUnrealizedPNL")),
        "ts": ts,
    }
    with transaction.atomic():
        before = AccountSnapshot.objects.count()
        AccountSnapshot.objects.bulk_create(
            [AccountSnapshot(**record)], ignore_conflicts=True
        )
        return AccountSnapshot.objects.count() - before


def persist_trades(user, rows) -> int:
    """Persist trade dicts for ``user``; duplicates on (user, trade_id)."""
    if not rows:
        return 0
    with transaction.atomic():
        before = Trade.objects.count()
        Trade.objects.bulk_create(
            [Trade(user=user, **_trade_dict(r)) for r in rows],
            ignore_conflicts=True,
        )
        return Trade.objects.count() - before


def _fetch_trades(client) -> list[dict]:
    """Page through history trades (mirrors ``src.journal.sync`` pagination)."""
    trades: list[dict] = []
    skip = 0
    while True:
        data = client.history_trades(skip=skip)
        batch = (data or {}).get("tradeList", [])
        if not batch:
            break
        trades.extend(batch)
        if len(batch) < _PAGE:
            break
        skip += _PAGE
    return trades


def sync_user(user, client, ts=None) -> dict:
    """Fetch and persist a user's positions, account, and trades.

    ``ts`` is stamped once per cycle and shared by positions and account so a
    re-poll of the same instant is a no-op (R2); trades are keyed by
    ``trade_id`` and need no clock.
    """
    ts = ts or datetime.now(UTC)
    return {
        "positions": persist_positions(user, client.positions(), ts),
        "account": persist_account(user, client.account(), ts),
        "trades": persist_trades(user, _fetch_trades(client)),
    }
