"""Public market monitor: funding + prices for the tracked symbols.

Read-only, works with no API key. Persists nothing yet (that's Etapa 3).
Red/green states come from the rate vs the configured threshold.
"""

from __future__ import annotations

import time

import requests
from rich.console import Console, Group
from rich.live import Live
from rich.table import Table

from src import config
from src.alerts import AlertState, check_market, check_positions, dispatch
from src.client import BitunixClient, BitunixError
from src.db import init_db, insert_funding, insert_prices

console = Console(highlight=False)


def annualized(rate: float, interval_h: int) -> float:
    """Funding rate -> yearly rate as a fraction. 8h interval -> *3*365."""
    return rate * (24 / interval_h) * 365


def countdown(next_ms: int, now_ms: int | None = None) -> str:
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    secs = max(0, (next_ms - now) // 1000)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def funding_state(rate: float) -> str:
    if abs(rate) >= config.FUNDING_EXTREME:
        return "[red]extremo[/red]"
    if abs(rate) >= config.FUNDING_EXTREME / 2:
        return "[yellow]alta[/yellow]"
    return "[green]ok[/green]"


def fetch_rows(client: BitunixClient, symbols: list[str]) -> list[dict]:
    tickers = {t["symbol"]: t for t in client.tickers(symbols)}
    funding = {f["symbol"]: f for f in client.funding_rate_batch()}
    ts = int(time.time() * 1000)
    rows = []
    for sym in symbols:
        t = tickers.get(sym, {})
        f = funding.get(sym, {})
        rate = float(f.get("fundingRate", 0) or 0)
        interval = int(f.get("fundingInterval", 8) or 8)
        next_funding = int(f.get("nextFundingTime", 0) or 0)
        rows.append(
            {
                # display
                "symbol": sym,
                "price": t.get("lastPrice", "—"),
                "funding": rate,
                "annual": annualized(rate, interval),
                "countdown": countdown(next_funding),
                "state": funding_state(rate),
                # persistence
                "ts": ts,
                "mark_price": _f(f.get("markPrice")),
                "index_price": _f(f.get("indexPrice")),
                "next_funding_time": next_funding,
                "funding_interval": interval,
                "last_price": _f(t.get("lastPrice")),
                "high": _f(t.get("high")),
                "low": _f(t.get("low")),
                "quote_vol": _f(t.get("quoteVol")),
            }
        )
    return rows


def _f(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def persist(conn, rows: list[dict]) -> None:
    insert_funding(
        conn,
        [
            {
                "ts": r["ts"],
                "symbol": r["symbol"],
                "funding_rate": r["funding"],
                "mark_price": r["mark_price"],
                "index_price": r["index_price"],
                "next_funding_time": r["next_funding_time"],
                "funding_interval": r["funding_interval"],
            }
            for r in rows
        ],
    )
    insert_prices(
        conn,
        [
            {
                "ts": r["ts"],
                "symbol": r["symbol"],
                "last_price": r["last_price"],
                "high": r["high"],
                "low": r["low"],
                "quote_vol": r["quote_vol"],
            }
            for r in rows
        ],
    )


def render(rows: list[dict]) -> Table:
    table = Table(title="BitUnix · funding & precios", title_justify="left")
    table.add_column("Símbolo", style="bold")
    table.add_column("Precio", justify="right")
    table.add_column("Funding/8h", justify="right")
    table.add_column("Anualizado", justify="right")
    table.add_column("Settlement en", justify="right")
    table.add_column("Estado")
    for r in rows:
        table.add_row(
            r["symbol"],
            r["price"],
            f"{r['funding'] * 100:+.4f}%",
            f"{r['annual'] * 100:+.1f}%",
            r["countdown"],
            r["state"],
        )
    return table


# --- positions panel (private, requires read-only API key) ---


def liq_distance_pct(liq_price, mark) -> float | None:
    """Absolute % distance from mark to liquidation. None if no liq price."""
    try:
        liq, mk = float(liq_price), float(mark)
    except (TypeError, ValueError):
        return None
    if liq <= 0 or mk <= 0:
        return None
    return abs(liq - mk) / mk * 100


def margin_state(rate) -> str:
    try:
        r = float(rate)
    except (TypeError, ValueError):
        return "ok"
    return "danger" if r >= config.MARGIN_WARN else "ok"


def position_row(raw: dict, mark: float | None) -> dict:
    # API returns side "BUY"/"SELL" (some docs say LONG/SHORT) — normalize.
    side = str(raw.get("side", "")).upper()
    is_long = side in ("BUY", "LONG")
    side = "LONG" if is_long else "SHORT" if side in ("SELL", "SHORT") else side
    state = margin_state(raw.get("marginRate"))
    return {
        "symbol": raw.get("symbol", ""),
        "side": side,
        "side_fmt": "[green]LONG[/green]" if is_long else "[red]SHORT[/red]",
        "leverage": raw.get("leverage", ""),
        "qty": raw.get("qty", ""),
        "avg_open": raw.get("avgOpenPrice", ""),
        "upnl": _f(raw.get("unrealizedPNL")),
        "liq_price": raw.get("liqPrice", ""),
        "distance": liq_distance_pct(raw.get("liqPrice"), mark),
        "margin_rate": _f(raw.get("marginRate")),
        "margin_state": state,
    }


def render_positions(rows: list[dict], balance: dict | None = None) -> Table:
    title = "BitUnix · posiciones"
    if balance:
        avail = balance.get("available", "—")
        upnl = balance.get("crossUnrealizedPNL", "—")
        title += f"   ·   disponible: {avail} USDT   ·   uPnL cross: {upnl}"
    if not rows:
        table = Table(title=title, title_justify="left")
        table.add_column("Sin posiciones abiertas", style="dim")
        table.add_row("—")
        return table
    table = Table(title=title, title_justify="left")
    table.add_column("Símbolo", style="bold")
    table.add_column("Lado")
    table.add_column("Lev", justify="right")
    table.add_column("Cant.", justify="right")
    table.add_column("Entrada", justify="right")
    table.add_column("uPnL", justify="right")
    table.add_column("Liq", justify="right")
    table.add_column("Dist. liq", justify="right")
    table.add_column("Margen")
    for r in rows:
        dist = f"{r['distance']:.1f}%" if r["distance"] is not None else "—"
        upnl = f"{r['upnl']:+.2f}" if r["upnl"] is not None else "—"
        if r["margin_rate"] is None:
            marg = "—"
        elif r["margin_state"] == "danger":
            marg = f"[red]{r['margin_rate'] * 100:.0f}% ⚠[/red]"
        else:
            marg = f"{r['margin_rate'] * 100:.0f}%"
        table.add_row(
            r["symbol"],
            r["side_fmt"],
            str(r["leverage"]),
            str(r["qty"]),
            str(r["avg_open"]),
            upnl,
            str(r["liq_price"]),
            dist,
            marg,
        )
    return table


def fetch_positions(
    client: BitunixClient, marks: dict[str, float]
) -> tuple[list[dict], dict | None]:
    raw = client.positions()
    # Positions may include symbols outside config.SYMBOLS; fetch their marks too.
    extra = [p["symbol"] for p in raw if p.get("symbol") and p["symbol"] not in marks]
    if extra:
        for t in client.tickers(extra):
            marks[t["symbol"]] = _f(t.get("lastPrice"))
    rows = [position_row(p, marks.get(p.get("symbol"))) for p in raw]
    rows.sort(key=lambda r: r["symbol"])
    account = client.account()
    # API returns a dict here despite docs showing a list.
    balance = account[0] if isinstance(account, list) else account
    return rows, balance


def run() -> None:
    client = BitunixClient(config.API_KEY, config.API_SECRET)
    conn = init_db(config.DB_PATH)
    if config.PUBLIC_ONLY:
        console.print(
            "[dim]modo público: sin API key, solo mercado. "
            "Paneles privados (posiciones) quedan desactivados.[/dim]"
        )
    backoff = config.POLL_SECONDS
    alerts = AlertState()
    try:
        with Live(console=console, refresh_per_second=4) as live:
            while True:
                try:
                    rows = fetch_rows(client, config.SYMBOLS)
                    persist(conn, rows)
                    messages = check_market(rows, alerts)
                    renderables = [render(rows)]
                    if not config.PUBLIC_ONLY:
                        try:
                            marks = {r["symbol"]: r["last_price"] for r in rows}
                            pos, balance = fetch_positions(client, marks)
                            renderables.append(render_positions(pos, balance))
                            messages += check_positions(pos, alerts)
                        except (BitunixError, requests.RequestException) as e:
                            renderables.append(
                                Table(title=f"[red]posiciones: {e}[/red]")
                            )
                    if messages:
                        dispatch(messages)
                    live.update(Group(*renderables))
                    backoff = config.POLL_SECONDS
                except (BitunixError, requests.RequestException, ValueError) as e:
                    live.update(Table(title=f"[red]error de red: {e}[/red]"))
                    backoff = min(backoff * 2, 300)
                time.sleep(backoff)
    except KeyboardInterrupt:
        console.print("\n[dim]saliendo…[/dim]")


if __name__ == "__main__":
    run()
