"""Pure confluence scoring and trade-setup derivation.

Combines the latest B1 structure event with B2 zones and dealing range to emit
a read-only ``Setup`` proposal. No I/O, no network, no order path, stdlib only;
deterministic, non-mutating, never raises: empty / short / mismatched input
returns ``[]``. A ``Setup`` is a computed proposal — NEVER an order.
"""

from __future__ import annotations

from typing import NamedTuple

from src.indicators import atr
from src.smc.config import MIN_CONFLUENCE, MIN_RR, MIN_RR_TP_R, OB_LOOKBACK, SL_BUFFER
from src.smc.range import classify_price, dealing_range
from src.smc.structure import StructureEvent, find_structure
from src.smc.swings import Swing, find_swings
from src.smc.zones import FVG, OrderBlock, find_fvg, find_order_blocks


class Setup(NamedTuple):
    """A read-only trade-setup proposal; never an order.

    ``direction`` is ``"long"`` or ``"short"``, ``score`` is the 0..4
    confluence count, and ``index`` is the anchoring structure event's bar.
    """

    direction: str
    entry: float
    stop: float
    take_profit: float
    rr: float
    score: int
    index: int


def find_setups(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    swings: list[Swing],
    structure: list[StructureEvent],
    *,
    range_=None,
    min_rr: float = MIN_RR,
    min_confluence: int = MIN_CONFLUENCE,
    sl_buffer: float = SL_BUFFER,
) -> list[Setup]:
    """One ``Setup`` at most, derived from the latest structure event.

    The candidate direction follows ``structure[-1].trend``. The confluence
    score counts, equally weighted, the structure event (always satisfied by
    construction), a recent matching order block, a recent matching FVG, and
    price in the aligned premium/discount half of ``range_`` when given. Entry
    is the order-block proximal edge (FVG fallback); stop is the distal edge
    offset by ``sl_buffer``; take-profit is the structural range extreme when
    it clears ``min_rr``, else the fixed-R fallback. Emitted only when
    ``score >= min_confluence`` and ``rr >= min_rr``.
    """
    n = len(closes)
    if n == 0 or len(opens) != n or len(highs) != n or len(lows) != n:
        return []
    if not structure:
        return []

    event = structure[-1]
    long = event.trend == "up"
    direction = "long" if long else "short"
    anchor = event.index
    want = "bullish" if long else "bearish"

    def recent(index: int) -> bool:
        return 0 <= anchor - index <= OB_LOOKBACK

    ob: OrderBlock | None = None
    for candidate in find_order_blocks(opens, highs, lows, closes, structure):
        if candidate.kind == want and recent(candidate.index):
            ob = candidate

    fvg: FVG | None = None
    for candidate in find_fvg(highs, lows):
        if candidate.kind == want and recent(candidate.index):
            fvg = candidate

    zone = ob if ob is not None else fvg
    if zone is None:
        return []

    if long:
        entry = zone.top
        stop = zone.bottom - sl_buffer
    else:
        entry = zone.bottom
        stop = zone.top + sl_buffer
    if entry == stop:
        return []

    score = 1  # structure component: tautological, the candidate derives from it
    if ob is not None:
        score += 1
    if fvg is not None:
        score += 1
    if range_ is not None:
        aligned = "discount" if long else "premium"
        if classify_price(closes[-1], range_) == aligned:
            score += 1
    if score < min_confluence:
        return []

    def reward_risk(target: float) -> float:
        if long:
            return (target - entry) / (entry - stop)
        return (entry - target) / (stop - entry)

    take_profit = (
        entry + MIN_RR_TP_R * (entry - stop)
        if long
        else entry - MIN_RR_TP_R * (stop - entry)
    )
    if range_ is not None:
        structural = range_.high if long else range_.low
        if reward_risk(structural) >= min_rr:
            take_profit = structural

    rr = reward_risk(take_profit)
    if rr < min_rr:
        return []

    return [Setup(direction, entry, stop, take_profit, rr, score, anchor)]


class SetupRecord(NamedTuple):
    """A ``Setup`` enriched with the anchor bar's time and ATR.

    ``anchor_time`` is ``times[index]`` and ``atr`` is the ATR at ``index``
    (``None`` inside the warm-up). Records whose index falls outside the
    supplied ``times`` window are skipped, never emitted with ``None``.
    Never an order; a persisted observation.
    """

    direction: str
    entry: float
    stop: float
    take_profit: float
    rr: float
    score: int
    index: int
    anchor_time: int
    atr: float | None


def capture_setups(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    times: list[int],
    *,
    atr_window: int = 14,
    range_=None,
    min_rr: float = MIN_RR,
    min_confluence: int = MIN_CONFLUENCE,
    sl_buffer: float = SL_BUFFER,
) -> list[SetupRecord]:
    """Run the ``get_smc_payload`` chain and enrich each setup for persistence.

    Composition mirrors the payload exactly: ``find_swings`` →
    ``find_structure`` → ``dealing_range`` → ``find_setups``. The dealing range
    is always computed and used unless the caller passes ``range_`` (an
    explicit override wins), so the helper is predictable from its inputs.

    ``anchor_time`` is ``times[index]`` with the same bounds rule as
    ``_serialize_smc``; ``atr`` is ``src.indicators.atr(...)[index]``. Records
    whose index falls outside ``times`` are skipped. Empty or mismatched OHLC,
    ``len(times) != len(closes)``, or no structure event yield ``[]``. Pure and
    deterministic: no I/O, no clock, no mutation, never raises.
    """
    n = len(closes)
    if n == 0 or len(opens) != n or len(highs) != n or len(lows) != n:
        return []
    if len(times) != n:
        return []

    swings = find_swings(highs, lows)
    structure = find_structure(highs, lows, closes)
    resolved_range = range_ if range_ is not None else dealing_range(highs, lows)
    setups = find_setups(
        opens,
        highs,
        lows,
        closes,
        swings,
        structure,
        range_=resolved_range,
        min_rr=min_rr,
        min_confluence=min_confluence,
        sl_buffer=sl_buffer,
    )
    if not setups:
        return []

    atrs = atr(highs, lows, closes, atr_window)
    out: list[SetupRecord] = []
    for setup in setups:
        index = setup.index
        if not 0 <= index < n:
            continue
        out.append(
            SetupRecord(
                setup.direction,
                setup.entry,
                setup.stop,
                setup.take_profit,
                setup.rr,
                setup.score,
                index,
                times[index],
                atrs[index],
            )
        )
    return out
