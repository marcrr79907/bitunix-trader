"""Pure Smart Money Concepts zones. Lists in, sparse records out.

Order blocks, fair value gaps, equal highs/lows, and liquidity sweeps over
supplied OHLC lists. No I/O, no network, stdlib only; the frozen B1 seam
(``StructureEvent``, ``Swing``) is consumed read-only. Deterministic,
non-mutating, never raises: empty / short / mismatched input returns ``[]``.
"""

from __future__ import annotations

from typing import NamedTuple

from src.smc.config import EQ_TOLERANCE, FVG_MIN_GAP, OB_LOOKBACK, SWEEP_LOOKBACK
from src.smc.structure import StructureEvent
from src.smc.swings import Swing


class OrderBlock(NamedTuple):
    """A displacement order block: ``kind`` is ``"bullish"`` or ``"bearish"``."""

    kind: str
    index: int  # bar index of the opposite candle (the OB candle)
    top: float
    bottom: float
    anchor: int  # bar index of the BOS event that anchored the OB


class FVG(NamedTuple):
    """A fair value gap: ``kind`` is ``"bullish"`` or ``"bearish"``."""

    kind: str
    index: int  # bar index of the middle candle
    top: float
    bottom: float


class EqualLevel(NamedTuple):
    """Equal highs/lows: ``kind`` is ``"eqh"`` or ``"eql"``."""

    kind: str
    index: int  # bar index of the later of the two swings
    price: float
    twin: int  # bar index of the earlier of the two swings


class Sweep(NamedTuple):
    """A liquidity sweep: ``kind`` is the swept ``"high"`` or ``"low"``."""

    kind: str
    index: int
    level: float
    direction: str  # implied trade direction: "bullish" | "bearish"


def find_order_blocks(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    structure: list[StructureEvent],
    *,
    lookback: int = OB_LOOKBACK,
) -> list[OrderBlock]:
    """One ``OrderBlock`` per BOS event, anchored on its last opposite candle.

    For a bullish BOS at bar ``t`` the OB candle is the most recent bar in
    ``[max(0, t - lookback), t - 1]`` with ``closes[i] < opens[i]``; bearish
    BOS mirrors (``closes[i] > opens[i]``). Zone is that candle's
    ``[low, high]``; ``choch`` never anchors. Ordered by ``index``.
    """
    n = len(closes)
    if n == 0 or len(opens) != n or len(highs) != n or len(lows) != n or lookback < 0:
        return []

    out: list[OrderBlock] = []
    for ev in structure:
        if ev.kind != "bos" or not 0 <= ev.index < n:
            continue
        pick: int | None = None
        for i in range(ev.index - 1, max(0, ev.index - lookback) - 1, -1):
            if ev.direction == "bullish" and closes[i] < opens[i]:
                pick = i
                break
            if ev.direction == "bearish" and closes[i] > opens[i]:
                pick = i
                break
        if pick is not None:
            out.append(
                OrderBlock(ev.direction, pick, highs[pick], lows[pick], ev.index)
            )

    out.sort(key=lambda ob: ob.index)
    return out


def find_fvg(
    highs: list[float],
    lows: list[float],
    *,
    min_gap: float = FVG_MIN_GAP,
) -> list[FVG]:
    """Raw unfilled 3-candle fair value gaps at each middle bar ``i``.

    Bullish when ``highs[i-1] < lows[i+1]``; bearish when
    ``lows[i-1] > highs[i+1]``. Emitted only when the gap size (``top - bottom``
    magnitude) is ``>= min_gap``. Ordered by ``index``.
    """
    n = len(highs)
    if n < 3 or len(lows) != n:
        return []

    out: list[FVG] = []
    for i in range(1, n - 1):
        if highs[i - 1] < lows[i + 1]:
            top, bottom, kind = lows[i + 1], highs[i - 1], "bullish"
        elif lows[i - 1] > highs[i + 1]:
            top, bottom, kind = lows[i - 1], highs[i + 1], "bearish"
        else:
            continue
        if abs(top - bottom) >= min_gap:
            out.append(FVG(kind, i, top, bottom))
    return out


def find_equal_highs_lows(
    swings: list[Swing],
    *,
    tolerance: float = EQ_TOLERANCE,
) -> list[EqualLevel]:
    """Equal highs/lows over CONSECUTIVE same-kind swings.

    Two high swings are EQH when ``abs(earlier.price - later.price) <=
    tolerance``; lows mirror as EQL. ``tolerance=0.0`` means exact equality
    only. Ordered by ``index``.
    """
    out: list[EqualLevel] = []
    for kind in ("high", "low"):
        same = [s for s in swings if s.kind == kind]
        for earlier, later in zip(same, same[1:], strict=False):
            if abs(earlier.price - later.price) <= tolerance:
                label = "eqh" if kind == "high" else "eql"
                out.append(EqualLevel(label, later.index, later.price, earlier.index))

    out.sort(key=lambda level: level.index)
    return out


def find_liquidity_sweeps(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    swings: list[Swing],
    *,
    lookback: int = SWEEP_LOOKBACK,
) -> list[Sweep]:
    """Liquidity sweeps: a wick beyond a prior swing that closes back inside.

    A swing low is swept when ``lows[t] < s.price`` and ``closes[t] > s.price``;
    a swing high is swept when ``highs[t] > s.price`` and ``closes[t] <
    s.price``. Only the most recent qualifying swing per side per bar emits.
    Ordered by ``index`` (low before high on the same bar).
    """
    n = len(highs)
    if n == 0 or len(lows) != n or len(closes) != n or lookback < 0:
        return []

    out: list[Sweep] = []
    for t in range(n):
        bl: Swing | None = None
        bh: Swing | None = None
        # Swings are ascending by index (B1 contract), so the last qualifying
        # match on a side is the most recent one.
        for s in swings:
            if s.index > t or t - s.index > lookback:
                continue
            if s.kind == "low" and lows[t] < s.price and closes[t] > s.price:
                bl = s
            elif s.kind == "high" and highs[t] > s.price and closes[t] < s.price:
                bh = s
        if bl is not None:
            out.append(Sweep("low", t, bl.price, "bullish"))
        if bh is not None:
            out.append(Sweep("high", t, bh.price, "bearish"))

    return out
