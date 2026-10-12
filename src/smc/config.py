"""Tunable defaults for the pure SMC core (``src/smc``).

Plain module-level constants imported as function default arguments, mirroring
``src/config.py`` (no class, single source of truth). These are tunable
defaults: downstream callers may override them per call via keyword arguments.
"""

from __future__ import annotations

SWING_LEFT = 2
SWING_RIGHT = 2
USE_CLOSE = True

# --- B2 zones -------------------------------------------------------------
OB_LOOKBACK = 10  # bars scanned back for the opposite order-block candle
FVG_MIN_GAP = 0.0  # minimum gap size (price units) to emit an FVG
EQ_TOLERANCE = 0.0  # max |Δprice| for two swings to be an equal level
SWEEP_LOOKBACK = 20  # bars a prior swing stays sweepable
