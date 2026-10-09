"""Kline payload seam: candles + server-side overlays.

Pure-ish (accepts any client with ``kline()``, so tests stub it without
monkeypatching). Indicator math lives ONLY in ``src/indicators.py`` — the
single source of truth; the browser never recomputes it.
"""

from __future__ import annotations

from src import indicators

INTERVALS = (
    "1m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1M",
)


CHART_KEYS = ("time", "open", "high", "low", "close")


def get_kline_payload(client, symbol: str, interval: str, limit: int) -> dict:
    candles = sorted(
        {c["time"]: c for c in client.kline(symbol, interval, limit)}.values(),
        key=lambda c: c["time"],  # dedupe by time (last wins) + ascending
    )
    # Strip to exactly the chart's five keys: the client's quote_vol must never
    # reach the response (delta spec R1/R3).
    candles = [{k: c[k] for k in CHART_KEYS} for c in candles]
    times = [c["time"] for c in candles]
    closes = [c["close"] for c in candles]
    return {
        "candles": candles,
        "overlays": {
            "sma20": _zip(times, indicators.sma(closes, 20)),
            "ema20": _zip(times, indicators.ema(closes, 20)),
            "rsi14": _zip(times, indicators.rsi(closes, 14)),
        },
    }


def _zip(times, values):
    # Gaps omitted: Lightweight Charts series arrays must never contain null.
    # strict=False: indicator tails are intentionally shorter than `times`.
    return [
        {"time": t, "value": v}
        for t, v in zip(times, values, strict=False)
        if v is not None
    ]
