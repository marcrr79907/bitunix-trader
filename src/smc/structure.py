"""Pure market structure: labels, trend state, BOS/CHoCH events.

No I/O, no network, stdlib only. Consumes the confirmed swings from
``src.smc.swings`` and the frozen BOS/CHoCH state machine in design.md:
the first decisive break seeds the trend silently, ``bos`` continues it,
``choch`` reverses it, and a broken level is consumed (no re-fire) until a
new swing re-arms it. Deterministic, non-mutating, never raises.
"""

from __future__ import annotations

from typing import NamedTuple

from src.smc.config import SWING_LEFT, SWING_RIGHT, USE_CLOSE
from src.smc.swings import Swing, find_swings


class LabeledSwing(NamedTuple):
    """A swing with an HH/HL/LH/LL label relative to the prior same kind."""

    kind: str
    index: int
    price: float
    label: str


class StructureEvent(NamedTuple):
    """A BOS/CHoCH break; ``trend`` is the trend AFTER the event."""

    kind: str
    index: int
    price: float
    direction: str
    trend: str


def label_swings(swings: list[Swing]) -> list[LabeledSwing]:
    """Label swings from the SECOND same-kind swing onward.

    A high is ``HH`` if ``price > `` the prior high else ``LH``; a low is
    ``HL`` if ``price > `` the prior low else ``LL``. The first swing of each
    kind has no predecessor and is omitted. Input is not mutated.
    """
    prev: dict[str, float] = {}
    out: list[LabeledSwing] = []
    for s in swings:
        prior = prev.get(s.kind)
        prev[s.kind] = s.price
        if prior is None:
            continue
        if s.kind == "high":
            label = "HH" if s.price > prior else "LH"
        else:
            label = "HL" if s.price > prior else "LL"
        out.append(LabeledSwing(s.kind, s.index, s.price, label))
    return out


def trend_state(labeled: list[LabeledSwing]) -> list[str | None]:
    """Aligned trend label per ``LabeledSwing`` position.

    ``None`` until both a high-label and a low-label have been seen; then
    ``up`` (latest HH + HL), ``down`` (latest LH + LL), else ``range``.
    """
    last_high: str | None = None
    last_low: str | None = None
    out: list[str | None] = []
    for item in labeled:
        if item.kind == "high":
            last_high = item.label
        else:
            last_low = item.label
        if last_high is None or last_low is None:
            out.append(None)
        elif last_high == "HH" and last_low == "HL":
            out.append("up")
        elif last_high == "LH" and last_low == "LL":
            out.append("down")
        else:
            out.append("range")
    return out


def find_structure(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    *,
    left: int = SWING_LEFT,
    right: int = SWING_RIGHT,
    use_close: bool = USE_CLOSE,
) -> list[StructureEvent]:
    """BOS/CHoCH events ordered by bar index.

    Requires at least one confirmed high AND one confirmed low, else ``[]``.
    Iterates bars; a swing at ``j`` becomes usable when ``j + right <= t``.
    The break reference is the bar close by default, or the wick
    (``highs``/``lows``) when ``use_close`` is ``False``.
    """
    n = len(highs)
    if n == 0 or len(lows) != n or len(closes) != n:
        return []

    swings = find_swings(highs, lows, left=left, right=right)
    if not any(s.kind == "high" for s in swings):
        return []
    if not any(s.kind == "low" for s in swings):
        return []

    # Swings grouped by the bar that confirms them (index + right).
    confirms: dict[int, list[Swing]] = {}
    for s in swings:
        confirms.setdefault(s.index + right, []).append(s)

    active_high: float | None = None
    active_low: float | None = None
    armed_high = False
    armed_low = False
    trend = "none"
    out: list[StructureEvent] = []

    for t in range(n):
        for s in confirms.get(t, ()):  # latest same-kind wins (sorted input)
            if s.kind == "high":
                active_high, armed_high = s.price, True
            else:
                active_low, armed_low = s.price, True

        up_ref = closes[t] if use_close else highs[t]
        dn_ref = closes[t] if use_close else lows[t]
        break_up = active_high is not None and armed_high and up_ref > active_high
        break_dn = active_low is not None and armed_low and dn_ref < active_low

        if trend == "none":
            if break_up:  # seed silently
                trend, armed_high = "up", False
            elif break_dn:
                trend, armed_low = "down", False
        elif trend == "up":
            if break_up:
                out.append(StructureEvent("bos", t, active_high, "bullish", "up"))
                armed_high = False
            elif break_dn:
                out.append(StructureEvent("choch", t, active_low, "bearish", "down"))
                trend, armed_low = "down", False
        else:  # down
            if break_dn:
                out.append(StructureEvent("bos", t, active_low, "bearish", "down"))
                armed_low = False
            elif break_up:
                out.append(StructureEvent("choch", t, active_high, "bullish", "up"))
                trend, armed_high = "up", False

    return out
