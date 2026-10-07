"""Trade journal: sync history into SQLite and report metrics.

Read-only against the API. `sync()` paginates history trades into the local
`trades` table; `report()` computes net PnL (realized minus fees) per trade.
"""

from __future__ import annotations

import sqlite3

from rich.console import Console
from rich.table import Table

from src import config
from src.client import BitunixClient
from src.db import init_db, upsert_trades

console = Console(highlight=False)
_PAGE = 100


def _f(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def trade_row(raw: dict) -> dict:
    return {
        "trade_id": raw.get("tradeId", ""),
        "order_id": raw.get("orderId", ""),
        "symbol": raw.get("symbol", ""),
        "side": str(raw.get("side", "")).upper(),
        "qty": _f(raw.get("qty")),
        "price": _f(raw.get("price")),
        "fee": _f(raw.get("fee")),
        "realized_pnl": _f(raw.get("realizedPNL")),
        "ctime": int(raw.get("ctime") or 0),
    }


def sync(
    client: BitunixClient, conn: sqlite3.Connection, symbol: str | None = None
) -> int:
    """Page through history trades and upsert them. Returns rows seen."""
    seen = 0
    skip = 0
    while True:
        data = client.history_trades(symbol=symbol, skip=skip)
        batch = (data or {}).get("tradeList", [])
        if not batch:
            break
        upsert_trades(conn, [trade_row(t) for t in batch])
        seen += len(batch)
        if len(batch) < _PAGE:
            break
        skip += _PAGE
    return seen


def metrics(rows: list[dict]) -> dict:
    """Compute net-PnL metrics from trade rows (dicts with realized_pnl, fee)."""
    trades = len(rows)
    if not trades:
        return {
            "trades": 0,
            "wins": 0,
            "net_pnl": 0.0,
            "win_rate": 0.0,
            "per_symbol": {},
            "best": None,
            "worst": None,
        }
    nets = [r["realized_pnl"] - r["fee"] for r in rows]
    per_symbol: dict[str, float] = {}
    for r, net in zip(rows, nets, strict=True):
        per_symbol[r["symbol"]] = per_symbol.get(r["symbol"], 0.0) + net
    wins = sum(1 for n in nets if n > 0)
    best = max(per_symbol.items(), key=lambda kv: kv[1])
    worst = min(per_symbol.items(), key=lambda kv: kv[1])
    return {
        "trades": trades,
        "wins": wins,
        "net_pnl": sum(nets),
        "win_rate": wins / trades * 100,
        "per_symbol": per_symbol,
        "best": best,
        "worst": worst,
    }


def _load(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT symbol, fee, realized_pnl FROM trades").fetchall()
    return [{"symbol": r[0], "fee": r[1], "realized_pnl": r[2]} for r in rows]


def render_report(m: dict) -> Table:
    table = Table(title="BitUnix · journal", title_justify="left")
    table.add_column("Par", style="bold")
    table.add_column("PnL neto", justify="right")
    for sym, pnl in sorted(m["per_symbol"].items(), key=lambda kv: kv[1], reverse=True):
        color = "green" if pnl >= 0 else "red"
        table.add_row(sym, f"[{color}]{pnl:+.2f}[/{color}]")
    console.print(
        f"operaciones: [bold]{m['trades']}[/bold]   "
        f"win rate: [bold]{m['win_rate']:.1f}%[/bold]   "
        f"PnL neto: [bold]{m['net_pnl']:+.2f}[/bold]"
    )
    if m["best"]:
        console.print(
            f"mejor: {m['best'][0]} ({m['best'][1]:+.2f})   "
            f"peor: {m['worst'][0]} ({m['worst'][1]:+.2f})"
        )
    return table


def report(conn: sqlite3.Connection) -> dict:
    m = metrics(_load(conn))
    console.print(render_report(m))
    return m


def main() -> None:
    import sys

    conn = init_db(config.DB_PATH)
    if config.PUBLIC_ONLY:
        console.print("[red]journal requiere API key (solo lectura).[/red]")
        raise SystemExit(1)
    client = BitunixClient(config.API_KEY, config.API_SECRET)
    action = sys.argv[1] if len(sys.argv) > 1 else "report"
    if action == "sync":
        seen = sync(client, conn)
        console.print(f"sincronizadas {seen} operaciones (nuevas quedan en la DB).")
    else:
        report(conn)


if __name__ == "__main__":
    main()
