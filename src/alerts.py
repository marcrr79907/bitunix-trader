"""Telegram alerts for the monitor.

Rules fire on a transition into a bad state (not every poll) so you don't get
spammed. Requires TELEGRAM_TOKEN and TELEGRAM_CHAT_ID.
"""

from __future__ import annotations

import requests
from rich.console import Console

from src import config

console = Console(highlight=False)


def funding_alert(row: dict, threshold: float) -> bool:
    return abs(row.get("funding", 0) or 0) >= threshold


def margin_alert(row: dict, threshold: float) -> bool:
    rate = row.get("margin_rate")
    return rate is not None and rate >= threshold


class AlertState:
    """Remembers last known state per key; fires only on false->true edges."""

    def __init__(self) -> None:
        self._active: dict[str, bool] = {}

    def fire(self, key: str, condition: bool) -> bool:
        was = self._active.get(key, False)
        self._active[key] = condition
        return condition and not was


def send_telegram(
    text: str, token: str | None = None, chat_id: str | None = None
) -> bool:
    token = token or config.TELEGRAM_TOKEN
    chat_id = chat_id or config.TELEGRAM_CHAT_ID
    if not (token and chat_id):
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        return r.ok
    except requests.RequestException as e:
        console.print(f"[red]telegram: {e}[/red]")
        return False


def check_market(rows: list[dict], state: AlertState) -> list[str]:
    """Return alert texts for market rows that just crossed a threshold."""
    out = []
    for r in rows:
        cond = funding_alert(r, config.FUNDING_EXTREME)
        if state.fire(f"funding:{r['symbol']}", cond):
            out.append(
                f"⚠ Funding extremo {r['symbol']}: {r['funding'] * 100:+.4f}%/8h "
                f"(anual {r['annual'] * 100:+.0f}%)"
            )
    return out


def check_positions(rows: list[dict], state: AlertState) -> list[str]:
    out = []
    for r in rows:
        if state.fire(f"margin:{r['symbol']}", margin_alert(r, config.MARGIN_WARN)):
            out.append(
                f"🚨 Margen peligroso {r['symbol']}: "
                f"{r['margin_rate'] * 100:.0f}% (liq a {r['distance']:.1f}%)"
            )
    return out


def dispatch(messages: list[str]) -> int:
    if not (config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID):
        return 0
    sent = 0
    for text in messages:
        if send_telegram(text):
            sent += 1
    return sent
