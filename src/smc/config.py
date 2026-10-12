"""Tunable defaults for the pure SMC core (``src/smc``).

Plain module-level constants imported as function default arguments, mirroring
``src/config.py`` (no class, single source of truth). These are tunable
defaults: downstream callers may override them per call via keyword arguments.
"""

from __future__ import annotations

SWING_LEFT = 2
SWING_RIGHT = 2
USE_CLOSE = True
