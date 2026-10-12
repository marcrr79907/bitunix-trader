"""Pure, framework-free alert-condition engine (issue #76, Fase D1).

Turns a validated ``condition`` JSON object plus a window of DB-shaped candle
rows (``open``/``high``/``low``/``close``/``quote_vol``/``time``) into a boolean
**state** at a bar and a false->true **edge** over the latest two closed bars.

Stdlib-only, deterministic, never reads a clock, never mutates its inputs.
``parse_condition`` is the only function that raises (``ValueError`` on a
structural breach) so the worker can log and skip a bad rule; ``matches`` and
``edge_fired`` are total — any malformed input returns ``False``.

The indicator / SMC math is NOT reimplemented here: the frozen
``src/indicators.py`` and ``src/smc/`` seams are consumed as-is.
"""

from __future__ import annotations

# Tuple indicators (macd/bollinger/stochastic) are out of v1 scope: the schema
# admits scalar series only. Unknown names are treated the same way at eval.
from src.indicators import atr, ema, rsi, sma, vwap
from src.smc.config import MIN_CONFLUENCE
from src.smc.range import dealing_range
from src.smc.signals import find_setups
from src.smc.structure import find_structure
from src.smc.swings import find_swings

_OPS = ("above", "below")
_DIRECTIONS = ("long", "short", "any")

# Scalar indicator catalogue: name -> (param key, default length).
# ``vwap`` takes no parameters (cumulative over the window).
_SCALAR_PARAMS: dict[str, tuple[str | None, int | None]] = {
    "rsi": ("rsi_len", 14),
    "sma": ("sma_len", 20),
    "ema": ("ema_len", 20),
    "atr": ("atr_len", 14),
    "vwap": (None, None),
}


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_price(condition: dict) -> dict:
    op = condition.get("op")
    if op not in _OPS:
        raise ValueError(f"price: bad op {op!r}")
    level = condition.get("level")
    if not _is_number(level):
        raise ValueError("price: level must be a number")
    return {"type": "price", "op": op, "level": float(level)}


def _parse_indicator(condition: dict) -> dict:
    name = condition.get("name")
    if name not in _SCALAR_PARAMS:
        raise ValueError(f"indicator: unsupported name {name!r}")
    op = condition.get("op")
    if op not in _OPS:
        raise ValueError(f"indicator: bad op {op!r}")
    level = condition.get("level")
    if not _is_number(level):
        raise ValueError("indicator: level must be a number")

    pkey, plen = _SCALAR_PARAMS[name]
    raw = condition.get("params", {})
    if not isinstance(raw, dict):
        raise ValueError("indicator: params must be an object")
    params: dict[str, int] = {}
    if pkey is None:
        if raw:
            raise ValueError(f"indicator {name}: takes no params")
    else:
        unknown = set(raw) - {pkey}
        if unknown:
            raise ValueError(f"indicator {name}: unknown params {sorted(unknown)}")
        length = raw.get(pkey, plen)
        if not isinstance(length, int) or isinstance(length, bool) or length < 1:
            raise ValueError(f"indicator {name}: {pkey} must be a positive int")
        params[pkey] = length
    return {
        "type": "indicator",
        "name": name,
        "op": op,
        "level": float(level),
        "params": params,
    }


def _parse_smc_setup(condition: dict) -> dict:
    direction = condition.get("direction")
    if direction not in _DIRECTIONS:
        raise ValueError(f"smc_setup: bad direction {direction!r}")
    min_score = condition.get("min_score", MIN_CONFLUENCE)
    if not isinstance(min_score, int) or isinstance(min_score, bool):
        raise ValueError("smc_setup: min_score must be an int")
    return {"type": "smc_setup", "direction": direction, "min_score": min_score}


_PARSERS = {
    "price": _parse_price,
    "indicator": _parse_indicator,
    "smc_setup": _parse_smc_setup,
}


def parse_condition(condition) -> dict:
    """Validate + normalize a ``condition``; raise ``ValueError`` on a breach.

    Returns a fresh, fully-defaulted dict. The input is never mutated.
    """
    if not isinstance(condition, dict):
        raise ValueError("condition must be an object")
    ctype = condition.get("type")
    parser = _PARSERS.get(ctype)
    if parser is None:
        raise ValueError(f"unknown condition type {ctype!r}")
    return parser(condition)


def _window(candles, index: int):
    """Rows up to and including bar ``index`` (``-1`` = the whole window)."""
    if index < 0:
        return candles[: len(candles) + index + 1]
    return candles[: index + 1]


def _column(rows, key: str) -> list:
    return [r[key] for r in rows]


def _series(parsed: dict, rows) -> list[float | None]:
    """Latest scalar series for a parsed indicator condition."""
    name = parsed["name"]
    closes = _column(rows, "close")
    if name == "sma":
        return sma(closes, parsed["params"]["sma_len"])
    if name == "ema":
        return ema(closes, parsed["params"]["ema_len"])
    if name == "rsi":
        return rsi(closes, parsed["params"]["rsi_len"])
    if name == "atr":
        return atr(
            _column(rows, "high"),
            _column(rows, "low"),
            closes,
            parsed["params"]["atr_len"],
        )
    # vwap: nullable quote volume degrades to 0.0 (mirrors the chart builder).
    volumes = [0.0 if v is None else v for v in _column(rows, "quote_vol")]
    return vwap(_column(rows, "high"), _column(rows, "low"), closes, volumes)


def _state(parsed: dict, rows) -> bool:
    ctype = parsed["type"]
    if not rows:
        return False
    if ctype == "price":
        close = rows[-1]["close"]
        return (
            close > parsed["level"]
            if parsed["op"] == "above"
            else close < parsed["level"]
        )

    if ctype == "indicator":
        latest = _series(parsed, rows)[-1]
        if latest is None:
            return False
        return (
            latest > parsed["level"]
            if parsed["op"] == "above"
            else latest < parsed["level"]
        )

    # smc_setup
    opens = _column(rows, "open")
    highs = _column(rows, "high")
    lows = _column(rows, "low")
    closes = _column(rows, "close")
    swings = find_swings(highs, lows)
    structure = find_structure(highs, lows, closes)
    range_ = dealing_range(highs, lows)
    setups = find_setups(opens, highs, lows, closes, swings, structure, range_=range_)
    want = parsed["direction"]
    return any(
        (want == "any" or setup.direction == want)
        and setup.score >= parsed["min_score"]
        for setup in setups
    )


def matches(condition: dict, candles, *, index: int = -1) -> bool:
    """Boolean state at bar ``index`` (default latest). Total: never raises."""
    try:
        parsed = parse_condition(condition)
        return _state(parsed, _window(candles, index))
    except (ValueError, TypeError, KeyError, IndexError):
        return False


def edge_fired(condition: dict, candles) -> bool:
    """True iff the state flips false->true across the latest two closed bars.

    Stateless and restart-safe (Option B): ``now and not prev``. Fewer than two
    rows means no edge is determinable -> ``False``.
    """
    try:
        if len(candles) < 2:
            return False
    except TypeError:
        return False
    return matches(condition, candles, index=-1) and not matches(
        condition, candles, index=-2
    )
