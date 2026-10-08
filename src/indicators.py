"""Pure, index-aligned chart math. Lists in, lists/numbers out.

No I/O, no network, stdlib only. Output length always equals input length;
positions that cannot be computed are ``None`` (leading warm-up).
"""

from __future__ import annotations

import statistics


def sma(series: list[float], window: int) -> list[float | None]:
    """Simple moving average; warm-up ``window - 1`` leading ``None``s."""
    n = len(series)
    if n == 0:
        return []
    if window < 1:
        return [None] * n
    return [
        statistics.fmean(series[i - window + 1 : i + 1]) if i >= window - 1 else None
        for i in range(n)
    ]


def ema(series: list[float], window: int) -> list[float | None]:
    """Exponential moving average; seed = SMA at ``window - 1``, ``k=2/(w+1)``."""
    n = len(series)
    if n == 0:
        return []
    if window < 1:
        return [None] * n
    out: list[float | None] = [None] * n
    if window > n:
        return out
    k = 2 / (window + 1)
    prev = statistics.fmean(series[:window])
    out[window - 1] = prev
    for i in range(window, n):
        prev = prev + k * (series[i] - prev)
        out[i] = prev
    return out


def rsi(series: list[float], window: int) -> list[float | None]:
    """Wilder RSI; first valid index is ``window`` (needs ``window`` deltas)."""
    n = len(series)
    if n == 0:
        return []
    if window < 1:
        return [None] * n
    out: list[float | None] = [None] * n
    if n <= window:
        return out

    avg_gain = 0.0
    avg_loss = 0.0
    for i in range(1, window + 1):
        delta = series[i] - series[i - 1]
        avg_gain += max(delta, 0.0)
        avg_loss += max(-delta, 0.0)
    avg_gain /= window
    avg_loss /= window
    out[window] = _rsi_from(avg_gain, avg_loss)

    for i in range(window + 1, n):
        delta = series[i] - series[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (window - 1) + gain) / window
        avg_loss = (avg_loss * (window - 1) + loss) / window
        out[i] = _rsi_from(avg_gain, avg_loss)
    return out


def _rsi_from(avg_gain: float, avg_loss: float) -> float | None:
    if avg_loss == 0:
        return None
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    window: int,
) -> list[float | None]:
    """Wilder ATR; first valid index is ``window`` (TR needs a prior close)."""
    n = len(closes)
    if n == 0:
        return []
    if window < 1:
        return [None] * n
    out: list[float | None] = [None] * n
    if n <= window:
        return out

    tr: list[float] = [0.0] * n
    for i in range(1, n):
        prev_c = closes[i - 1]
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - prev_c),
            abs(lows[i] - prev_c),
        )
    avg = statistics.fmean(tr[1 : window + 1])
    out[window] = avg
    for i in range(window + 1, n):
        avg = (avg * (window - 1) + tr[i]) / window
        out[i] = avg
    return out


def vwap(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    volumes: list[float],
) -> list[float | None]:
    """Cumulative VWAP on typical price; zero cumulative volume -> ``None``."""
    n = len(closes)
    if n == 0:
        return []
    out: list[float | None] = [None] * n
    cum_pv = 0.0
    cum_v = 0.0
    for i in range(n):
        tp = (highs[i] + lows[i] + closes[i]) / 3.0
        cum_pv += tp * volumes[i]
        cum_v += volumes[i]
        out[i] = cum_pv / cum_v if cum_v != 0 else None
    return out


def zscore(series: list[float], window: int) -> list[float | None]:
    """Rolling z-score (population pstdev); ``window == n`` = full series."""
    n = len(series)
    if n == 0:
        return []
    if window < 1:
        return [None] * n
    out: list[float | None] = [None] * n
    for i in range(window - 1, n):
        chunk = series[i - window + 1 : i + 1]
        sd = statistics.pstdev(chunk)
        if sd == 0:
            continue
        out[i] = (series[i] - statistics.fmean(chunk)) / sd
    return out
