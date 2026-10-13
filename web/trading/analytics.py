"""Historical SMC signal extraction seam for ``/analytics/`` (Slice 2).

Web seam (I/O): dedupes the caller's trade bars by UTC hour, runs the frozen
``market.quotes.get_smc_payload`` chain ONCE per distinct bar (bounded by that
bar's end), and reshapes the payload ``setups`` into the calibration signal
records ``src.analytics.calibrate`` consumes. SMC math stays only in ``src/smc/``
— this module maps, it never recomputes. An upstream ``BitunixError`` or
``RequestException`` degrades to no signals (never 500).
"""

from __future__ import annotations

import logging

import requests
from market.quotes import get_smc_payload

from src.client import BitunixClient, BitunixError

logger = logging.getLogger(__name__)

# Calibration granularity: one hourly bar per distinct trade hour; the chain
# window is 200 candles ending at the trade's bar (matches ``window_seconds``).
INTERVAL = "1h"
LIMIT = 200
HOUR_MS = 3_600_000


def _signal_record(symbol: str, setup: dict) -> dict:
    """Reshape a frozen SMC setup into an ``src.analytics`` signal record."""
    return {
        "symbol": symbol,
        "time": setup["time"],
        "direction": setup["direction"],
        "entry": setup["entry"],
        "stop": setup["stop"],
        "score": setup["score"],
    }


def extract_signals(symbol: str, ctimes: list[int]) -> list[dict]:
    """SMC signals over the hourly bars of ``ctimes`` (epoch ms), deduped.

    One ``get_smc_payload`` chain pass per distinct UTC hour, oldest bar first,
    bounded by that bar's end (exclusive). Malformed/``None`` ctimes are skipped
    and upstream failures degrade to ``[]``.
    """
    bars = sorted({c // HOUR_MS for c in ctimes if c is not None})
    signals: list[dict] = []
    for bar in bars:
        try:
            payload = get_smc_payload(
                BitunixClient(),
                symbol,
                INTERVAL,
                LIMIT,
                before=(bar + 1) * 3600,
            )
        except (BitunixError, requests.RequestException):
            logger.warning("analytics signals degraded symbol=%s bar=%s", symbol, bar)
            continue
        signals.extend(_signal_record(symbol, setup) for setup in payload["setups"])
    return signals
