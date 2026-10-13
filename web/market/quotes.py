"""Kline payload seam: candles + server-side overlays and panes.

DB-first cursor page (R3/R4): read ``Candle`` for ``symbol/interval/time <
before`` newest-first, call BitUnix ONLY when the DB cannot fill the requested
window (or the interval is unpersisted), merge DB-wins, compute
``src/indicators.py`` over the warm window and slice to the newest ``limit``.

A token **registry** maps an indicator token → placement (price-scale overlay
or sub-pane), builder and warm-up. ``parse_indicators`` turns the query into
validated ``(name, params)`` tuples; the view maps its ``ValueError`` to 400.

Pure-ish (accepts any client with ``kline()``, so tests stub it without
monkeypatching). Indicator math lives ONLY in ``src/indicators.py`` — the
single source of truth; the browser never recomputes it.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Mapping

import requests
from trading.candles import CANDLE_INTERVALS
from trading.models import Candle, Drawing

from src import indicators
from src.client import BitunixError
from src.smc.range import dealing_range
from src.smc.signals import find_setups
from src.smc.structure import find_structure, label_swings
from src.smc.swings import find_swings
from src.smc.zones import find_fvg, find_order_blocks

logger = logging.getLogger(__name__)

INTERVALS = (
    "1m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1M",
)


CHART_KEYS = ("time", "open", "high", "low", "close")

# Floor for the warm-up window: every page-edge default overlay (sma20/ema20)
# stays defined even when the selected set needs fewer prior candles (R4).
WARMUP_BASE = 20

# BitUnix caps a single kline request at 200 rows; older warm-up rows come
# from the DB (R3, R4).
MAX_UPSTREAM = 200

# Legacy default set — an omitted ``indicators`` param MUST keep this shape
# (backward compatible, R3).
DEFAULT_INDICATORS = ("sma20", "ema20", "rsi14")

# Default chart layout (R2): the indicator set returned on a GET miss and
# persisted when a user never saved one. Shape mirrors the stored JSON.
DEFAULT_LAYOUT = [{"token": "sma"}, {"token": "ema"}, {"token": "rsi"}]


# --- parameter vocabulary ----------------------------------------------------
#
# Flat query params accepted by the view. Values are validated by
# ``parse_indicators`` and handed to the builders; a bad value raises
# ``ValueError`` (mapped to 400 by the view).
_INT_PARAMS = {
    "sma_len": 20,
    "ema_len": 20,
    "rsi_len": 14,
    "bb_len": 20,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "stoch_k": 14,
    "stoch_d": 3,
    "atr_len": 14,
}
_FLOAT_PARAMS = {"bb_std": 2.0}


# --- builders ----------------------------------------------------------------
#
# Each builder returns ``{series_key: aligned_list}`` computed over the full
# warm window. Overlay tokens use their series key AS the overlay name; pane
# tokens expose their series inside the pane object.


def _b_sma20(ctx: dict, p: dict) -> dict:
    return {"sma20": indicators.sma(ctx["closes"], 20)}


def _b_ema20(ctx: dict, p: dict) -> dict:
    return {"ema20": indicators.ema(ctx["closes"], 20)}


def _b_rsi14(ctx: dict, p: dict) -> dict:
    return {"rsi14": indicators.rsi(ctx["closes"], 14)}


def _b_sma(ctx: dict, p: dict) -> dict:
    return {"sma": indicators.sma(ctx["closes"], p["sma_len"])}


def _b_ema(ctx: dict, p: dict) -> dict:
    return {"ema": indicators.ema(ctx["closes"], p["ema_len"])}


def _b_rsi(ctx: dict, p: dict) -> dict:
    return {"rsi": indicators.rsi(ctx["closes"], p["rsi_len"])}


def _b_bollinger(ctx: dict, p: dict) -> dict:
    upper, middle, lower = indicators.bollinger(ctx["closes"], p["bb_len"], p["bb_std"])
    return {
        "bollinger_upper": upper,
        "bollinger_middle": middle,
        "bollinger_lower": lower,
    }


def _b_vwap(ctx: dict, p: dict) -> dict:
    volumes = [0.0 if v is None else v for v in ctx["volumes"]]
    return {"vwap": indicators.vwap(ctx["highs"], ctx["lows"], ctx["closes"], volumes)}


def _b_macd(ctx: dict, p: dict) -> dict:
    line, signal, histogram = indicators.macd(
        ctx["closes"], p["macd_fast"], p["macd_slow"], p["macd_signal"]
    )
    return {"macd": line, "signal": signal, "histogram": histogram}


def _b_stochastic(ctx: dict, p: dict) -> dict:
    k, d = indicators.stochastic(
        ctx["highs"], ctx["lows"], ctx["closes"], p["stoch_k"], p["stoch_d"]
    )
    return {"k": k, "d": d}


def _b_atr(ctx: dict, p: dict) -> dict:
    return {
        "atr": indicators.atr(ctx["highs"], ctx["lows"], ctx["closes"], p["atr_len"])
    }


def _b_volume(ctx: dict, p: dict) -> dict:
    # quote_vol stays out of candles; it travels here only (R3).
    return {"volume": ctx["volumes"]}


# --- registry ----------------------------------------------------------------
#
# ``place``: "overlay" (price scale) or "pane" (its own sub-pane).
# ``warmup``: first valid index for the series (a callable of the params).
REGISTRY: dict[str, dict] = {
    # Legacy default set.
    "sma20": {"place": "overlay", "warmup": lambda p: 19, "build": _b_sma20},
    "ema20": {"place": "overlay", "warmup": lambda p: 19, "build": _b_ema20},
    "rsi14": {"place": "overlay", "warmup": lambda p: 14, "build": _b_rsi14},
    # Param-driven overlays.
    "sma": {"place": "overlay", "warmup": lambda p: p["sma_len"] - 1, "build": _b_sma},
    "ema": {"place": "overlay", "warmup": lambda p: p["ema_len"] - 1, "build": _b_ema},
    "bollinger": {
        "place": "overlay",
        "warmup": lambda p: p["bb_len"] - 1,
        "build": _b_bollinger,
    },
    "vwap": {"place": "overlay", "warmup": lambda p: 0, "build": _b_vwap},
    # Panes.
    "rsi": {
        "place": "pane",
        "pane": "rsi",
        "type": "line",
        "warmup": lambda p: p["rsi_len"],
        "build": _b_rsi,
    },
    "macd": {
        "place": "pane",
        "pane": "macd",
        "type": "line",
        "warmup": lambda p: p["macd_slow"] - 1 + p["macd_signal"] - 1,
        "build": _b_macd,
    },
    "stochastic": {
        "place": "pane",
        "pane": "stochastic",
        "type": "line",
        "warmup": lambda p: p["stoch_k"] - 1 + p["stoch_d"] - 1,
        "build": _b_stochastic,
    },
    "atr": {
        "place": "pane",
        "pane": "atr",
        "type": "line",
        "warmup": lambda p: p["atr_len"],
        "build": _b_atr,
    },
    "volume": {
        "place": "pane",
        "pane": "volume",
        "type": "histogram",
        "warmup": lambda p: 0,
        "build": _b_volume,
    },
}


def _parse_params(params: Mapping[str, str]) -> dict:
    """Validate the flat indicator params; raise ``ValueError`` on a bad value."""
    out: dict = {}
    for key, default in _INT_PARAMS.items():
        raw = params.get(key)
        if raw is None or raw == "":
            out[key] = default
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise ValueError(f"invalid {key}") from None
        if value < 1:
            raise ValueError(f"invalid {key}")
        out[key] = value
    for key, default in _FLOAT_PARAMS.items():
        raw = params.get(key)
        if raw is None or raw == "":
            out[key] = default
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"invalid {key}") from None
        if value <= 0:
            raise ValueError(f"invalid {key}")
        out[key] = value
    # MACD requires fast < slow (reversed order is undefined; the pure function
    # tolerates it, but the API contract rejects it as a bad request).
    if out["macd_fast"] >= out["macd_slow"]:
        raise ValueError("invalid macd params: macd_fast MUST be < macd_slow")
    return out


def parse_indicators(
    raw: str | None, params: Mapping[str, str]
) -> list[tuple[str, dict]]:
    """Parse/validate the ``indicators`` query into ``(name, params)`` tuples.

    An omitted/empty ``raw`` yields the legacy default set. An unknown token or
    a bad param value raises ``ValueError`` (the view maps it to 400).
    """
    raw = (raw or "").strip()
    names = (
        [n.strip() for n in raw.split(",") if n.strip()]
        if raw
        else list(DEFAULT_INDICATORS)
    )
    parsed = _parse_params(params)
    selected: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for name in names:
        if name not in REGISTRY:
            raise ValueError(f"unknown indicator: {name}")
        if name not in seen:
            seen.add(name)
            selected.append((name, parsed))
    return selected


def parse_layout_indicators(indicators) -> list[dict]:
    """Validate a layout's JSON indicator list; raise ``ValueError`` on bad input.

    Tokens MUST be in ``REGISTRY``; an optional ``params`` object MAY set known
    param keys (type/range checked). The user-supplied shape is preserved (no
    defaults injected) — the kline builders complete partial params at read
    time, so a saved ``{"token":"sma","params":{"sma_len":50}}`` round-trips
    verbatim.
    """
    if not isinstance(indicators, list):
        raise ValueError("indicators must be a list")
    out: list[dict] = []
    seen: set[str] = set()
    for item in indicators:
        if not isinstance(item, dict):
            raise ValueError("invalid indicator entry")
        token = item.get("token")
        if token not in REGISTRY:
            raise ValueError(f"unknown indicator: {token}")
        if token in seen:
            continue
        seen.add(token)
        entry = {"token": token}
        if "params" in item:
            entry["params"] = _validate_layout_params(token, item["params"])
        if "style" in item:
            entry["style"] = _validate_layout_style(token, item["style"])
        out.append(entry)
    return out


def _validate_layout_params(token: str, params) -> dict:
    """Validate a JSON ``params`` object; return it verbatim. Raise ``ValueError``."""
    if not isinstance(params, dict):
        raise ValueError(f"invalid params for {token}")
    for key, value in params.items():
        if key in _INT_PARAMS:
            ok = isinstance(value, int) and not isinstance(value, bool) and value >= 1
        elif key in _FLOAT_PARAMS:
            ok = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and value > 0
            )
        else:
            raise ValueError(f"unknown param: {key}")
        if not ok:
            raise ValueError(f"invalid {key}")
    if (
        "macd_fast" in params
        and "macd_slow" in params
        and params["macd_fast"] >= params["macd_slow"]
    ):
        raise ValueError("invalid macd params: macd_fast MUST be < macd_slow")
    return params


# Frozen per-indicator style shape (F2.7): all three keys optional, values
# whitelisted. ``color`` is #rrggbb; ``lineWidth`` int 1..4; ``precision`` int
# 0..8. Unknown key / bad shape / out of range → ``ValueError`` (→ 400).
_LAYOUT_STYLE_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _validate_layout_style(token: str, style) -> dict:
    """Validate a JSON ``style`` object; return it verbatim. Raise ``ValueError``."""
    if not isinstance(style, dict):
        raise ValueError(f"invalid style for {token}")
    for key, value in style.items():
        if key == "color":
            ok = isinstance(value, str) and bool(_LAYOUT_STYLE_COLOR.match(value))
        elif key == "lineWidth":
            ok = (
                isinstance(value, int)
                and not isinstance(value, bool)
                and 1 <= value <= 4
            )
        elif key == "precision":
            ok = (
                isinstance(value, int)
                and not isinstance(value, bool)
                and 0 <= value <= 8
            )
        else:
            raise ValueError(f"unknown style key: {key}")
        if not ok:
            raise ValueError(f"invalid {key}")
    return style


# --- drawings (R2/R4/R5) -----------------------------------------------------
#
# Drawing kinds mirror ``Drawing.Kind`` (the model is the source of truth); the
# pure validator below is the API's contract. ``points`` is ONE JSON object per
# kind (see design schemas), validated BEFORE any write — a breach raises
# ``ValueError`` and the view maps it to 400.
DRAWING_KINDS = frozenset(Drawing.Kind.values)

# Numeric field check: a real number, never a bool (``True`` is an ``int``).
_NUM = (int, float)


def _is_number(value) -> bool:
    return isinstance(value, _NUM) and not isinstance(value, bool)


def _parse_point(point, *, require_time: bool, where: str) -> None:
    """Validate a ``{time,price}`` anchor in place; raise ``ValueError``."""
    if not isinstance(point, dict):
        raise ValueError(f"invalid {where} point")
    if require_time and not isinstance(point.get("time"), int):
        raise ValueError(f"invalid {where} time")
    if not _is_number(point.get("price")):
        raise ValueError(f"invalid {where} price")


def parse_drawing(kind, points, style) -> tuple[dict, dict]:
    """Validate a drawing payload; raise ``ValueError`` on any breach (R4/R5).

    ``kind`` MUST be one of ``DRAWING_KINDS``; ``points`` MUST match the kind's
    object schema and ``style`` MUST be an object. The validated ``(points,
    style)`` are returned verbatim (no defaults injected) so a stored row
    round-trips unchanged.
    """
    if kind not in DRAWING_KINDS:
        raise ValueError(f"unknown kind: {kind}")
    if not isinstance(points, dict):
        raise ValueError("points must be an object")
    if not isinstance(style, dict):
        raise ValueError("style must be an object")

    if kind == "hline":
        if not _is_number(points.get("price")):
            raise ValueError("invalid hline price")
    elif kind in ("trendline", "fib", "rect"):
        if set(points) != {"p1", "p2"}:
            raise ValueError(f"{kind} requires exactly two points")
        _parse_point(points["p1"], require_time=True, where=f"{kind} p1")
        _parse_point(points["p2"], require_time=True, where=f"{kind} p2")
    elif kind == "text":
        if not isinstance(points.get("time"), int):
            raise ValueError("invalid text time")
        if not _is_number(points.get("price")):
            raise ValueError("invalid text price")
        if not isinstance(points.get("text"), str) or not points["text"].strip():
            raise ValueError("text requires a label")
    return points, style


def _now_seconds() -> int:
    """Wall clock in UNIX seconds (seam for deterministic tests)."""
    return int(time.time())


def _db_rows(symbol: str, interval: str, before: int | None, want: int) -> list[dict]:
    """Newest ``want`` persisted rows ``< before`` (ascending), or ``[]``.

    Skips intervals the worker never persists (``CANDLE_INTERVALS``), so the
    endpoint still serves 1m/30m/6h/8h/12h/3d directly from upstream.
    """
    if interval not in CANDLE_INTERVALS:
        return []
    qs = Candle.objects.filter(symbol=symbol, interval=interval)
    if before is not None:
        qs = qs.filter(time__lt=before)
    newest_first = qs.order_by("-time")[:want]
    return [
        {
            "time": row.time,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "quote_vol": row.quote_vol,
        }
        for row in reversed(newest_first)  # ascending for the merge/slice
    ]


def _ctx_rows(rows: list[dict]) -> dict:
    """Column view over the warm window, for the builders."""
    return {
        "closes": [c["close"] for c in rows],
        "highs": [c["high"] for c in rows],
        "lows": [c["low"] for c in rows],
        "volumes": [c.get("quote_vol") for c in rows],
    }


def _fetch_window(
    client, symbol: str, interval: str, want: int, before: int | None = None
) -> list[dict]:
    """Newest ``want`` candles ``< before`` (ascending) via the shared seam.

    DB-first with upstream gap-fill: read ``Candle`` for the requested window,
    call BitUnix only when the DB is short, merge with DB winning on duplicate
    ``time``. The un-stripped rows (``quote_vol`` retained) are returned so
    both kline and SMC can build over the same window. Re-raises upstream
    failures when the DB holds nothing (view maps: BitunixError → 400,
    RequestException → 502); degraded ``[]`` upstream otherwise.
    """
    db = _db_rows(symbol, interval, before, want)

    upstream: list[dict] = []
    if len(db) < want:
        end_ms = (before if before is not None else _now_seconds()) * 1000
        try:
            upstream = client.kline(
                symbol, interval, min(want, MAX_UPSTREAM), end_time=end_ms
            )
        except (BitunixError, requests.RequestException):
            if not db:
                raise
            logger.warning("kline degraded symbol=%s interval=%s", symbol, interval)
            upstream = []

    # Merge, DB wins on duplicate ``time`` (the durable record is authoritative).
    merged = {c["time"]: c for c in upstream}
    merged.update({c["time"]: c for c in db})
    return sorted(merged.values(), key=lambda c: c["time"])[-want:]


def get_kline_payload(
    client,
    symbol: str,
    interval: str,
    limit: int,
    before: int | None = None,
    indicators: list[tuple[str, dict]] | None = None,
) -> dict:
    if indicators is None:
        indicators = parse_indicators(None, {})
    else:
        # Direct callers may pass partial params; complete them with defaults.
        indicators = [(name, _parse_params(params)) for name, params in indicators]

    # Derived warm-up: the deepest first-valid index across the selected set,
    # floored at WARMUP_BASE (MACD → 33, R4).
    warmup = max(
        WARMUP_BASE,
        max(REGISTRY[name]["warmup"](params) for name, params in indicators),
    )
    rows_full = _fetch_window(client, symbol, interval, limit + warmup, before)

    # Build indicator series over the whole warm window, using un-stripped rows
    # so quote_vol is available to the volume pane (R3).
    ctx = _ctx_rows(rows_full)
    # Strip to exactly the chart's five keys: quote_vol never reaches candles.
    rows = [{k: c[k] for k in CHART_KEYS} for c in rows_full]

    times = [c["time"] for c in rows]
    page_times = times[-limit:]
    overlays: dict = {}
    panes: dict = {}
    for name, params in indicators:
        entry = REGISTRY[name]
        series = entry["build"](ctx, params)
        if entry["place"] == "overlay":
            for key, values in series.items():
                overlays[key] = _zip(page_times, values[-limit:])
        else:
            panes[entry["pane"]] = {
                "type": entry["type"],
                "series": {k: _zip(page_times, v[-limit:]) for k, v in series.items()},
            }

    return {"candles": rows[-limit:], "overlays": overlays, "panes": panes}


def _zip(times, values):
    # Gaps omitted: Lightweight Charts series arrays must never contain null.
    # strict=False: indicator tails are intentionally shorter than `times`.
    return [
        {"time": t, "value": v}
        for t, v in zip(times, values, strict=False)
        if v is not None
    ]


# --- SMC overlay payload (R1/R2/R3) -----------------------------------------
#
# Read-only market analysis: run the frozen ``src/smc/`` chain ONCE over the
# same DB-first window as kline and resolve every bar ``index`` → candle
# ``time`` server-side. No ``index``/``anchor`` key is ever emitted; the JS
# merely draws. SMC is market data — no ``for_user``, no write.


def _time_at(times: list[int], index: int) -> int | None:
    """Resolve a bar index to its candle time, or ``None`` when off-window."""
    return times[index] if 0 <= index < len(times) else None


def _serialize_smc(
    rows: list[dict],
    symbol: str,
    interval: str,
    swings,
    labeled,
    structure,
    obs,
    fvgs,
    range_,
    setups,
) -> dict:
    """Serialize the frozen chain, resolving every index → candle ``time``.

    Pure: records in, frozen JSON out. Records with an off-window index are
    skipped defensively — the payload never carries a raw bar index.
    """
    times = [c["time"] for c in rows]
    labels = {(item.kind, item.index): item.label for item in labeled}

    out_swings = [
        {
            "kind": s.kind,
            "time": times[s.index],
            "price": s.price,
            "label": labels.get((s.kind, s.index)),
        }
        for s in swings
        if _time_at(times, s.index) is not None
    ]
    out_structure = [
        {
            "kind": e.kind,
            "time": times[e.index],
            "price": e.price,
            "direction": e.direction,
            "trend": e.trend,
        }
        for e in structure
        if _time_at(times, e.index) is not None
    ]
    out_obs = [
        {
            "kind": ob.kind,
            "time": times[ob.index],
            "top": ob.top,
            "bottom": ob.bottom,
            "anchor_time": times[ob.anchor],
        }
        for ob in obs
        if _time_at(times, ob.index) is not None
        and _time_at(times, ob.anchor) is not None
    ]
    out_fvgs = [
        {
            "kind": g.kind,
            "time": times[g.index],
            "top": g.top,
            "bottom": g.bottom,
        }
        for g in fvgs
        if _time_at(times, g.index) is not None
    ]
    out_range = (
        {
            "high": range_.high,
            "low": range_.low,
            "equilibrium": range_.equilibrium,
            "time": times[range_.index],
        }
        if range_ is not None and _time_at(times, range_.index) is not None
        else None
    )
    out_setups = [
        {
            "direction": s.direction,
            "time": times[s.index],
            "entry": s.entry,
            "stop": s.stop,
            "take_profit": s.take_profit,
            "rr": s.rr,
            "score": s.score,
        }
        for s in setups
        if _time_at(times, s.index) is not None
    ]
    return {
        "symbol": symbol,
        "interval": interval,
        "swings": out_swings,
        "structure": out_structure,
        "order_blocks": out_obs,
        "fvgs": out_fvgs,
        "range": out_range,
        "setups": out_setups,
    }


def get_smc_payload(
    client, symbol: str, interval: str, limit: int, *, before: int | None = None
) -> dict:
    """Run the frozen SMC chain over the newest ``limit`` candles (no warm-up).

    Uses the shared ``_fetch_window`` seam (``want == limit``) so the SMC
    window matches the chart's ``candles[-limit:]`` exactly. The keyword-only
    ``before`` (UNIX seconds, exclusive upper bound) bounds the window to
    candles older than it, so the chain can run over a historical trade's bar;
    omitting it is byte-identical to before (newest window). Raises like
    ``get_kline_payload`` (view maps: BitunixError → 400, RequestException →
    502); thin windows degrade to empty arrays + ``range:null``, never 500.
    """
    rows = _fetch_window(client, symbol, interval, limit, before)
    if len(rows) < 3:
        # Below three candles no chain can compute; frozen empty shape (R4).
        return _serialize_smc(rows, symbol, interval, [], [], [], [], [], None, [])

    opens = [c["open"] for c in rows]
    highs = [c["high"] for c in rows]
    lows = [c["low"] for c in rows]
    closes = [c["close"] for c in rows]

    swings = find_swings(highs, lows)
    labeled = label_swings(swings)
    structure = find_structure(highs, lows, closes)
    obs = find_order_blocks(opens, highs, lows, closes, structure)
    fvgs = find_fvg(highs, lows)
    range_ = dealing_range(highs, lows)
    setups = find_setups(opens, highs, lows, closes, swings, structure, range_=range_)
    return _serialize_smc(
        rows, symbol, interval, swings, labeled, structure, obs, fvgs, range_, setups
    )
