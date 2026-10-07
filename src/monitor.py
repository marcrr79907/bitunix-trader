"""Public market monitor: funding + prices for the tracked symbols.

Read-only, works with no API key. Persists nothing yet (that's Etapa 3).
Red/green states come from the rate vs the configured threshold.
"""

from __future__ import annotations

import time

import requests
from rich.console import Console
from rich.live import Live
from rich.table import Table

from src import config
from src.client import BitunixClient, BitunixError

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
    rows = []
    for sym in symbols:
        t = tickers.get(sym, {})
        f = funding.get(sym, {})
        rate = float(f.get("fundingRate", 0) or 0)
        interval = int(f.get("fundingInterval", 8) or 8)
        rows.append(
            {
                "symbol": sym,
                "price": t.get("lastPrice", "—"),
                "funding": rate,
                "annual": annualized(rate, interval),
                "countdown": countdown(int(f.get("nextFundingTime", 0) or 0)),
                "state": funding_state(rate),
                "interval": interval,
            }
        )
    return rows


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


def run() -> None:
    client = BitunixClient(config.API_KEY, config.API_SECRET)
    if config.PUBLIC_ONLY:
        console.print(
            "[dim]modo público: sin API key, solo mercado. "
            "Paneles privados (posiciones) quedan desactivados.[/dim]"
        )
    backoff = config.POLL_SECONDS
    try:
        with Live(console=console, refresh_per_second=4) as live:
            while True:
                try:
                    rows = fetch_rows(client, config.SYMBOLS)
                    live.update(render(rows))
                    backoff = config.POLL_SECONDS
                except (BitunixError, requests.RequestException, ValueError) as e:
                    live.update(
                        Table(title=f"[red]error de red: {e}[/red]")
                    )
                    backoff = min(backoff * 2, 300)
                time.sleep(backoff)
    except KeyboardInterrupt:
        console.print("\n[dim]saliendo…[/dim]")


if __name__ == "__main__":
    run()
