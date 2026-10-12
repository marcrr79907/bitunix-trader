"""Pure fractal swing detection. Lists in, sparse records out.

No I/O, no network, stdlib only. A pivot needs ``left`` bars before and
``right`` bars after it, so the trailing ``right`` bars are unconfirmed and are
never emitted (no look-ahead). Equal levels are never pivots. The function
never raises: empty, short, or mismatched input returns ``[]``.
"""

from __future__ import annotations

from typing import NamedTuple

from src.smc.config import SWING_LEFT, SWING_RIGHT


class Swing(NamedTuple):
    """A confirmed fractal pivot: ``kind`` is ``"high"`` or ``"low"``."""

    kind: str
    index: int
    price: float


def find_swings(
    highs: list[float],
    lows: list[float],
    *,
    left: int = SWING_LEFT,
    right: int = SWING_RIGHT,
) -> list[Swing]:
    """Confirmed fractal pivots in ascending ``index`` order.

    Bar ``i`` is a pivot HIGH iff ``highs[i]`` is strictly greater than the
    ``left`` prior highs and the ``right`` following highs (mirror for LOWS
    with strict ``<``). The scan stops at ``n - right`` so the trailing
    unconfirmed bars can never emit a pivot.
    """
    n = len(highs)
    if n == 0 or len(lows) != n or left < 0 or right < 0:
        return []

    out: list[Swing] = []
    for i in range(left, n - right):
        hi = highs[i]
        if all(hi > highs[i - k] for k in range(1, left + 1)) and all(
            hi > highs[i + k] for k in range(1, right + 1)
        ):
            out.append(Swing("high", i, hi))
        lo = lows[i]
        if all(lo < lows[i - k] for k in range(1, left + 1)) and all(
            lo < lows[i + k] for k in range(1, right + 1)
        ):
            out.append(Swing("low", i, lo))

    # Deterministic tie order: same index -> high before low.
    out.sort(key=lambda s: (s.index, 0 if s.kind == "high" else 1))
    return out
