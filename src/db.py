"""SQLite storage. Standard library only, no ORM.

The monitor persists one row per symbol per poll, building our own dataset
for later analysis (funding history, price history).
"""

from __future__ import annotations

import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS funding_snapshots (
    ts                INTEGER NOT NULL,
    symbol            TEXT    NOT NULL,
    funding_rate      REAL,
    mark_price        REAL,
    index_price       REAL,
    next_funding_time INTEGER,
    funding_interval  INTEGER
);
CREATE INDEX IF NOT EXISTS ix_funding_symbol_ts ON funding_snapshots(symbol, ts);

CREATE TABLE IF NOT EXISTS price_snapshots (
    ts         INTEGER NOT NULL,
    symbol     TEXT    NOT NULL,
    last_price REAL,
    high       REAL,
    low        REAL,
    quote_vol  REAL
);
CREATE INDEX IF NOT EXISTS ix_price_symbol_ts ON price_snapshots(symbol, ts);

CREATE TABLE IF NOT EXISTS trades (
    trade_id     TEXT PRIMARY KEY,
    order_id     TEXT,
    symbol       TEXT NOT NULL,
    side         TEXT,
    qty          REAL,
    price        REAL,
    fee          REAL,
    realized_pnl REAL,
    ctime        INTEGER
);
CREATE INDEX IF NOT EXISTS ix_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS ix_trades_ctime ON trades(ctime);
"""


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def insert_funding(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        "INSERT INTO funding_snapshots "
        "(ts, symbol, funding_rate, mark_price, index_price, "
        "next_funding_time, funding_interval) "
        "VALUES (:ts, :symbol, :funding_rate, :mark_price, :index_price, "
        ":next_funding_time, :funding_interval)",
        rows,
    )
    conn.commit()


def insert_prices(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        "INSERT INTO price_snapshots "
        "(ts, symbol, last_price, high, low, quote_vol) "
        "VALUES (:ts, :symbol, :last_price, :high, :low, :quote_vol)",
        rows,
    )
    conn.commit()


def upsert_trades(conn: sqlite3.Connection, rows: list[dict]) -> None:
    """Insert trades, ignoring ones already stored (trade_id is the key)."""
    conn.executemany(
        "INSERT OR IGNORE INTO trades "
        "(trade_id, order_id, symbol, side, qty, price, fee, realized_pnl, ctime) "
        "VALUES (:trade_id, :order_id, :symbol, :side, :qty, :price, :fee, "
        ":realized_pnl, :ctime)",
        rows,
    )
    conn.commit()
