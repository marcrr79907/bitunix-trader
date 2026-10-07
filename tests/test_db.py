"""Persistence contract tests.

db.py is the storage interface; reading back with SQL asserts the behavior
(what gets persisted), not internal structure.
"""

import os
import tempfile

from src.db import init_db, insert_funding, insert_prices, upsert_trades


def _read(conn, sql):
    return conn.execute(sql).fetchall()


def test_funding_snapshot_roundtrip():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = init_db(path)
        insert_funding(
            conn,
            [
                {
                    "ts": 1000,
                    "symbol": "BTCUSDT",
                    "funding_rate": 0.0001,
                    "mark_price": 60000.0,
                    "index_price": 59990.0,
                    "next_funding_time": 2000,
                    "funding_interval": 8,
                }
            ],
        )
        rows = _read(
            conn,
            "SELECT ts, symbol, funding_rate, funding_interval FROM funding_snapshots",
        )
        assert rows == [(1000, "BTCUSDT", 0.0001, 8)]
    finally:
        os.remove(path)


def test_price_snapshot_roundtrip():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = init_db(path)
        insert_prices(
            conn,
            [
                {
                    "ts": 1000,
                    "symbol": "ETHUSDT",
                    "last_price": 2680.5,
                    "high": 2700.0,
                    "low": 2650.0,
                    "quote_vol": 1234.5,
                }
            ],
        )
        rows = _read(
            conn, "SELECT ts, symbol, last_price, quote_vol FROM price_snapshots"
        )
        assert rows == [(1000, "ETHUSDT", 2680.5, 1234.5)]
    finally:
        os.remove(path)


def test_init_db_is_idempotent():
    """Re-running init on an existing DB must not raise or wipe data."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        init_db(path)
        conn = init_db(path)
        insert_prices(
            conn,
            [
                {
                    "ts": 1,
                    "symbol": "X",
                    "last_price": 1,
                    "high": 1,
                    "low": 1,
                    "quote_vol": 1,
                }
            ],
        )
        assert _read(conn, "SELECT COUNT(*) FROM price_snapshots") == [(1,)]
    finally:
        os.remove(path)


def test_upsert_trades_is_idempotent():
    """Syncing twice must not duplicate trades (trade_id is the key)."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = init_db(path)
        trade = {
            "trade_id": "t1",
            "order_id": "o1",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": 1.0,
            "price": 60000.0,
            "fee": 0.5,
            "realized_pnl": 10.0,
            "ctime": 1000,
        }
        upsert_trades(conn, [trade])
        upsert_trades(conn, [trade])  # same trade again
        assert _read(conn, "SELECT COUNT(*) FROM trades") == [(1,)]
    finally:
        os.remove(path)


if __name__ == "__main__":
    test_funding_snapshot_roundtrip()
    test_price_snapshot_roundtrip()
    test_init_db_is_idempotent()
    test_upsert_trades_is_idempotent()
    print("ok: db roundtrips work")
