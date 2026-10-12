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
import time
from collections.abc import Mapping

import requests
from trading.candles import CANDLE_INTERVALS
from trading.models import Candle

from src import indicators
from src.client import BitunixError

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
    want = limit + warmup
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
                raise  # view maps: BitunixError -> 400, RequestException -> 502
            logger.warning("kline degraded symbol=%s interval=%s", symbol, interval)
            upstream = []

    # Merge, DB wins on duplicate ``time`` (the durable record is authoritative).
    merged = {c["time"]: c for c in upstream}
    merged.update({c["time"]: c for c in db})
    rows_full = sorted(merged.values(), key=lambda c: c["time"])[-want:]

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
