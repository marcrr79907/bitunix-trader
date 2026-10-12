"""Shared synthetic OHLC fixtures for the pure SMC zone tests (``zones.py``).

Hand-traced series that trigger one rule each without cross-triggering others.
``mirror_ohlc`` flips a bundle into its exact bear mirror (prices negated, high
and low series swapped), mirroring ``test_smc_structure._mirror``. Not collected
by pytest (no ``test_`` prefix).
"""

from __future__ import annotations

# (opens, highs, lows, closes)
OHLC = tuple[list[float], list[float], list[float], list[float]]


def mirror_ohlc(bundle: OHLC) -> OHLC:
    """Flip an OHLC bundle into its exact bear mirror.

    Negating prices turns highs into lows and vice versa, so the high and low
    series swap roles; opens and closes merely negate (candle direction flips).
    """
    opens, highs, lows, closes = bundle
    return (
        [-o for o in opens],
        [-low for low in lows],
        [-high for high in highs],
        [-c for c in closes],
    )


# --- order blocks --------------------------------------------------------
# A bullish BOS is anchored at t=5. Bearish candles (close < open) sit at i=2
# (open 12, close 10) and i=4 (open 13, close 10); the MOST RECENT is i=4
# -> zone [low 9, high 14], anchor 5.
OB_BULL: OHLC = (
    [10, 11, 12, 10, 13, 10],
    [12, 13, 13, 12, 14, 15],
    [9, 10, 9, 8, 9, 10],
    [11, 12, 10, 11, 10, 14],
)

# Every candle is bullish (close > open): a bullish BOS finds no opposite
# candle anywhere in the window.
OB_NONE_BULL: OHLC = (
    [8, 9, 10, 11, 12, 13],
    [10, 11, 12, 13, 14, 15],
    [7, 8, 9, 10, 11, 12],
    [9, 10, 11, 12, 13, 14],
)

# Only bearish candle is i=0 (open 12, close 10); i=1..5 are bullish.
# A bullish BOS at t=5: window with lookback=3 is [2,4] -> no opposite candle;
# with lookback=6 the window is [0,4] -> i=0 is found. Exercises the recency
# window (design R4).
OB_FAR: OHLC = (
    [12, 10, 11, 12, 13, 13],
    [13, 12, 13, 14, 15, 15],
    [9, 9, 10, 11, 12, 12],
    [10, 11, 12, 13, 14, 14],
)

# Bullish BOS at t=2, window [0,1]. i=1 is a doji (open == close) and must be
# skipped as "neither direction"; the bearish i=0 is the match.
# -> OrderBlock("bullish", 0, top=12, bottom=8, anchor=2).
OB_DOJI: OHLC = (
    [10, 10, 11],
    [12, 11, 15],
    [8, 9, 10],
    [9, 10, 14],
)

# --- fair value gaps -----------------------------------------------------
# i=1 bullish: highs[0]=10 < lows[2]=11 -> top=10, bottom=11, gap 1.
FVG_BULL_HIGHS = [10.0, 10.0, 12.0]
FVG_BULL_LOWS = [8.0, 8.0, 11.0]

# i=1 bearish: lows[0]=13 > highs[2]=8 -> top=13, bottom=8, gap 5. The bullish
# condition is deliberately not met (highs[0]=12 is not < lows[2]=11).
FVG_BEAR_HIGHS = [12.0, 12.0, 8.0]
FVG_BEAR_LOWS = [13.0, 13.0, 11.0]

# i=1 bullish gap of 0.1 (highs[0]=10 < lows[2]=10.1); skipped when min_gap=0.5.
FVG_SMALL_HIGHS = [10.0, 10.0, 10.4]
FVG_SMALL_LOWS = [8.0, 8.0, 10.1]

# --- liquidity sweeps ----------------------------------------------------
# Swing low 100.0 at i=2; bar t=5 wicks to 99.5 and closes back at 100.5.
SWEEP_LOW_HIGHS = [105.0, 104.0, 103.0, 102.0, 103.0, 101.0]
SWEEP_LOW_LOWS = [104.0, 103.0, 100.0, 101.0, 102.0, 99.5]
SWEEP_LOW_CLOSES = [104.5, 103.5, 101.0, 101.5, 102.5, 100.5]

# Swing high 110.0 at i=2; bar t=5 wicks to 110.5 and closes back at 109.0.
SWEEP_HIGH_HIGHS = [108.0, 109.0, 110.0, 109.0, 110.0, 110.5]
SWEEP_HIGH_LOWS = [107.0, 108.0, 109.0, 108.0, 109.0, 109.0]
SWEEP_HIGH_CLOSES = [107.5, 108.5, 109.5, 108.5, 109.5, 109.0]
