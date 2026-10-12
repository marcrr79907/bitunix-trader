"""Pure dealing-range evaluation: range extremes, equilibrium, PD split.

Fixed-lookback dealing range over supplied OHLC lists plus premium/discount
classification. No I/O, no network, stdlib only; deterministic, non-mutating,
never raises: empty / mismatched input returns ``None``.
"""

from __future__ import annotations

from typing import NamedTuple

from src.smc.config import RANGE_LOOKBACK


class DealingRange(NamedTuple):
    """Fixed-window dealing range; ``index`` is the last bar included."""

    high: float
    low: float
    equilibrium: float  # (high + low) / 2
    index: int


def dealing_range(
    highs: list[float],
    lows: list[float],
    *,
    lookback: int = RANGE_LOOKBACK,
) -> DealingRange | None:
    """Extremes over the last ``lookback`` bars, or ``None`` when undefined.

    ``high = max(highs[-lookback:])``, ``low = min(lows[-lookback:])``,
    ``equilibrium = (high + low) / 2``, ``index`` = last bar. Empty,
    mismatched-length, or ``lookback <= 0`` input returns ``None`` — never
    raises. v1 uses this fixed window, not structure extremes.
    """
    n = len(highs)
    if n == 0 or len(lows) != n or lookback <= 0:
        return None

    window = slice(-lookback, None)
    high = max(highs[window])
    low = min(lows[window])
    return DealingRange(high, low, (high + low) / 2, n - 1)


def classify_price(price: float, range_: DealingRange | None) -> str:
    """Classify ``price`` as ``"premium"``, ``"discount"`` or ``"equilibrium"``.

    Above the equilibrium is premium, below is discount, equal is equilibrium.
    A missing range (``None``) degrades to ``"equilibrium"`` without raising.
    """
    if range_ is None:
        return "equilibrium"
    if price > range_.equilibrium:
        return "premium"
    if price < range_.equilibrium:
        return "discount"
    return "equilibrium"
