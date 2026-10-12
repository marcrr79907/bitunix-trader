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


def macd(
    series: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """MACD line, signal line, histogram.

    ``line = ema(fast) - ema(slow)`` (``None`` where either leg is ``None``);
    ``signal = ema(line[slow-1:], signal)`` left-padded with ``slow - 1``
    ``None``s; ``histogram = line - signal`` where both are defined. Default
    warm-up: line at ``slow - 1`` (25), signal/histogram at ``slow - 1 +
    signal - 1`` (33).
    """
    n = len(series)
    if n == 0:
        return ([], [], [])
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    line: list[float | None] = [None] * n
    for i in range(n):
        f, s = fast_ema[i], slow_ema[i]
        if f is not None and s is not None:
            line[i] = f - s

    start = slow - 1
    sig: list[float | None] = [None] * n
    if 0 <= start < n:
        for j, v in enumerate(ema(line[start:], signal)):
            sig[start + j] = v

    hist: list[float | None] = [None] * n
    for i in range(n):
        if line[i] is not None and sig[i] is not None:
            hist[i] = line[i] - sig[i]
    return (line, sig, hist)


def bollinger(
    series: list[float],
    window: int = 20,
    num_std: float = 2,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Bollinger bands ``(upper, middle, lower)``; middle = SMA.

    ``sd`` is the window's population standard deviation. A flat window
    (``sd == 0``) collapses the bands onto the middle: ``upper == middle ==
    lower`` — ``None`` is never returned for a computable position.
    """
    n = len(series)
    if n == 0:
        return ([], [], [])
    middle = sma(series, window)
    upper: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n
    for i in range(n):
        m = middle[i]
        if m is None:
            continue
        sd = statistics.pstdev(series[i - window + 1 : i + 1])
        upper[i] = m + num_std * sd
        lower[i] = m - num_std * sd
    return (upper, middle, lower)


def stochastic(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    k: int = 14,
    d: int = 3,
) -> tuple[list[float | None], list[float | None]]:
    """Stochastic oscillator ``(%K, %D)``.

    ``%K = 100 * (close - lowest_low) / (highest_high - lowest_low)`` over the
    ``k`` window; a zero range yields ``None`` for that position. ``%D`` is the
    SMA of ``%K`` over ``d``, ``None`` where any averaged ``%K`` is ``None``.
    Warm-up: ``%K`` at ``k - 1``, ``%D`` at ``k - 1 + d - 1``.
    """
    n = len(closes)
    if n == 0:
        return ([], [])
    pct_k: list[float | None] = [None] * n
    if k >= 1:
        for i in range(k - 1, n):
            lowest = min(lows[i - k + 1 : i + 1])
            highest = max(highs[i - k + 1 : i + 1])
            rng = highest - lowest
            if rng == 0:
                continue
            pct_k[i] = 100.0 * (closes[i] - lowest) / rng
    pct_d: list[float | None] = [None] * n
    if d >= 1:
        for i in range(d - 1, n):
            chunk = pct_k[i - d + 1 : i + 1]
            if any(v is None for v in chunk):
                continue
            pct_d[i] = statistics.fmean(chunk)
    return (pct_k, pct_d)


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
