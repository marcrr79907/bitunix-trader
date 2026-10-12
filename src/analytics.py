"""Pure, framework-free analytics over caller-supplied trade records.

Imports the standard library and :mod:`src.metrics` only. No I/O, no clock, no
global state; deterministic (same input -> byte-identical output), non-mutating,
and never raises on empty, short, or mismatched input. Read-only — never orders.
"""

from __future__ import annotations

import statistics
from xml.sax.saxutils import escape

from src.metrics import (
    equity_curve,
    expectancy,
    max_drawdown,
    net_pnl,
    profit_factor,
    r_multiple,
    win_rate,
)

_DIMENSIONS = ("setup", "hour", "symbol")
_DIRECTION_BY_SIDE = {"BUY": "long", "SELL": "short"}


def summarize(pnls: list[float]) -> dict:
    """Per-bucket record over a sequence of realized net PnL values."""
    pnls = list(pnls or [])
    return {
        "trades": len(pnls),
        "wins": sum(1 for pnl in pnls if pnl > 0),
        "win_rate": win_rate(pnls),
        "net_pnl": net_pnl(pnls),
        "expectancy": expectancy(pnls),
        "profit_factor": profit_factor(pnls),
        "max_drawdown": max_drawdown(equity_curve(pnls)),
    }


def _sort_key(item: tuple) -> tuple:
    """Deterministic ordering across mixed numeric/string keys, never raising."""
    key = item[0]
    if isinstance(key, (int, float)):
        return (0, key, "")
    return (1, 0, str(key))


def group_metrics(rows: list[dict], dimension: str) -> dict:
    """``{key: summarize(nets)}`` grouped by ``dimension``.

    ``dimension`` must be ``"setup"``, ``"hour"`` or ``"symbol"``; anything else
    returns ``{}``. A ``None`` key buckets under ``"unmatched"`` (setup) or
    ``"unknown"`` (hour/other). Keys are sorted deterministically.
    """
    if dimension not in _DIMENSIONS:
        return {}
    buckets: dict = {}
    for row in rows or []:
        try:
            key = row[dimension]
            net = row["net"]
        except (TypeError, KeyError):
            continue
        if key is None:
            key = "unmatched" if dimension == "setup" else "unknown"
        buckets.setdefault(key, []).append(net)
    ordered = sorted(buckets.items(), key=_sort_key)
    return {key: summarize(nets) for key, nets in ordered}


def equity_and_drawdown(pnls: list[float]) -> dict:
    """``{"equity": equity_curve(pnls), "max_drawdown": max_drawdown(equity)}``."""
    equity = equity_curve(pnls or [])
    return {"equity": equity, "max_drawdown": max_drawdown(equity)}


def _mean_or_none(values: list) -> float | None:
    present = [value for value in values if value is not None]
    return statistics.fmean(present) if present else None


def _direction_for_side(side) -> str | None:
    return _DIRECTION_BY_SIDE.get(str(side).upper())


def calibrate(signals: list[dict], trades: list[dict], *, window_seconds: int) -> dict:
    """Join historical signals to real trades; R is join-only.

    A trade matches the nearest same-symbol signal whose ``direction`` equals the
    trade's mapped direction (``BUY->long``, ``SELL->short``) and whose
    ``abs(ctime/1000 - time) <= window_seconds``; ties pick the smaller delta,
    then the earlier ``time``. ``risk = abs(entry - stop) * qty`` and
    ``R = r_multiple(net, risk)`` (``None`` when risk is zero).
    """
    matched_nets: list[float] = []
    unmatched_nets: list[float] = []
    kind_nets: dict = {}
    kind_risks: dict = {}
    in_window = bool(window_seconds) and window_seconds > 0

    for trade in trades or []:
        try:
            net = trade["net"]
            ctime = trade["ctime"]
            qty = trade["qty"]
            symbol = trade["symbol"]
        except (TypeError, KeyError):
            continue
        direction = _direction_for_side(trade.get("side"))

        best = None
        best_key = None
        if direction is not None and in_window:
            trade_seconds = ctime // 1000
            for signal in signals or []:
                try:
                    if signal["symbol"] != symbol:
                        continue
                    if signal["direction"] != direction:
                        continue
                    delta = abs(trade_seconds - signal["time"])
                    if delta > window_seconds:
                        continue
                except (TypeError, KeyError):
                    continue
                key = (delta, signal["time"])
                if best is None or key < best_key:
                    best = signal
                    best_key = key

        if best is None:
            unmatched_nets.append(net)
            continue

        matched_nets.append(net)
        kind = f"{direction}:score{best.get('score')}"
        kind_nets.setdefault(kind, []).append(net)
        risk = abs(best["entry"] - best["stop"]) * qty
        kind_risks.setdefault(kind, []).append(r_multiple(net, risk))

    return {
        "matched": summarize(matched_nets),
        "unmatched": summarize(unmatched_nets),
        "by_setup": {kind: summarize(nets) for kind, nets in sorted(kind_nets.items())},
        "r_by_setup": {
            kind: _mean_or_none(risks) for kind, risks in sorted(kind_risks.items())
        },
    }


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _svg_open(width: int, height: int, label: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(label)}">'
    )


def _empty_svg(width: int, height: int) -> str:
    return _svg_open(width, height, "no data") + "</svg>"


def equity_svg(points: list[float], *, width: int = 300, height: int = 100) -> str:
    """Deterministic inline SVG polyline for an equity curve; labels escaped."""
    points = list(points or [])
    if not points:
        return _empty_svg(width, height)
    n = len(points)
    lo, hi = min(points), max(points)
    span = hi - lo
    pad = 2.0
    inner_h = max(height - 2 * pad, 0.0)
    coords = []
    for i, value in enumerate(points):
        x = width / 2.0 if n == 1 else pad + i / (n - 1) * (width - 2 * pad)
        y = height / 2.0 if span == 0 else pad + (hi - value) / span * inner_h
        coords.append(f"{_fmt(x)},{_fmt(y)}")
    return (
        _svg_open(width, height, "equity curve")
        + f'<polyline fill="none" stroke="currentColor" points="{" ".join(coords)}" />'
        + "</svg>"
    )


def bars_svg(items: list[dict], *, width: int = 300, height: int = 100) -> str:
    """Deterministic inline SVG bar chart; labels escaped, malformed rows skipped."""
    clean = []
    for item in items or []:
        try:
            clean.append((str(item["label"]), float(item["value"])))
        except (TypeError, KeyError, ValueError):
            continue
    if not clean:
        return _empty_svg(width, height)
    max_abs = max((abs(value) for _, value in clean), default=0.0) or 1.0
    row_h = height / len(clean)
    pad = 2.0
    max_w = max(width - 2 * pad, 0.0)
    bar_h = max(row_h - 2 * pad, 0.0)
    parts = []
    for i, (label, value) in enumerate(clean):
        y = i * row_h + pad
        bar_w = abs(value) / max_abs * max_w
        parts.append(
            f'<g><rect x="{_fmt(pad)}" y="{_fmt(y)}" width="{_fmt(bar_w)}" '
            f'height="{_fmt(bar_h)}" />'
            f'<text x="{_fmt(pad + bar_w)}" y="{_fmt(y)}">{escape(label)}</text></g>'
        )
    return _svg_open(width, height, "bars") + "".join(parts) + "</svg>"
