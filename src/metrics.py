"""Pure performance math over caller-supplied realized-PnL sequences.

Lists in, numbers or lists out; no I/O, timestamp-agnostic, stdlib only.
Complementary to ``journal.metrics()`` (SQLite accounting), which is left
untouched. Empty input is ``None`` for the scalar metrics and ``[]`` for the
equity curve.
"""

from __future__ import annotations

import statistics


def expectancy(pnls: list[float]) -> float | None:
    """Mean realized PnL per trade; ``None`` when there are no trades."""
    if not pnls:
        return None
    return statistics.fmean(pnls)


def profit_factor(pnls: list[float]) -> float | None:
    """``gross_profit / gross_loss``; ``None`` when there are no losses."""
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = -sum(p for p in pnls if p < 0)
    if gross_loss == 0:
        return None
    return gross_profit / gross_loss


def r_multiple(pnl: float, risk: float) -> float | None:
    """``pnl / risk``; ``None`` when the caller-supplied risk is zero."""
    if risk == 0:
        return None
    return pnl / risk


def equity_curve(pnls: list[float]) -> list[float]:
    """Cumulative running sum of realized PnL; same length as the input."""
    out: list[float] = []
    running = 0.0
    for pnl in pnls:
        running += pnl
        out.append(running)
    return out
