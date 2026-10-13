# performance-analytics Specification

## Purpose

Pure, framework-free analytics and calibration over caller-supplied trade
records, living in NEW `src/analytics.py`. Imports stdlib and `src.metrics` only;
never raises; no I/O, no `datetime.now`, no global state. Groups net PnL by
dimension and joins historical SMC signals to real trades. Read-only — never
orders. New capability — no prior spec.

**Frozen vocabulary** — `setup_kind := f"{direction}:score{score}"` (e.g.
`long:score4`); `direction ∈ {"long","short"}`; unmatched/unknown keys bucket
under `"unmatched"` / `"unknown"`. Each `Trade` fill = one trade (journal status
quo). Hour is **caller-supplied** UTC (`(ctime_ms // 3_600_000) % 24`).

## Requirements

### Requirement: A1 — summarize

`summarize(pnls: list[float]) -> dict` MUST return exactly
`{"trades": int, "wins": int, "win_rate": float | None, "net_pnl": float,
"expectancy": float | None, "profit_factor": float | None,
"max_drawdown": float | None}`, delegating to `src.metrics`. `wins` counts
`pnl > 0`. Empty input MUST yield `trades=0`, `wins=0`, `net_pnl=0.0` and `None`
scalars — never raise.

#### Scenario: Known bucket
- GIVEN `pnls = [10.0, -5.0, 5.0]`
- WHEN `summarize` runs
- THEN `trades=3`, `wins=2`, `win_rate≈66.67`, `net_pnl=10.0`, `expectancy≈3.33`, `profit_factor=3.0`, `max_drawdown=-5.0`

#### Scenario: Empty bucket
- GIVEN `pnls = []`
- WHEN it runs
- THEN `trades=0`, `net_pnl=0.0`, all scalar metrics `None`, no raise

### Requirement: A2 — group_metrics

`group_metrics(rows: list[dict], dimension: str) -> dict[str, dict]` MUST group
rows by `dimension ∈ {"setup", "hour", "symbol"}` and return
`{key: summarize(nets)}`. Each row MUST be
`{"net": float, "setup": str | None, "hour": int | None, "symbol": str}`. A row
whose dimension key is `None` MUST bucket under `"unmatched"` (setup) or
`"unknown"` (hour). Keys MUST be sorted (deterministic). Empty rows → `{}`. An
unknown `dimension` MUST NOT raise — return `{}`.

#### Scenario: Group by setup
- GIVEN rows with setups `long:score4` (net 10) and `short:score3` (net -5)
- WHEN `group_metrics(rows, "setup")` runs
- THEN the result has those two keys, each a `summarize` bucket, sorted

#### Scenario: None key buckets as unknown
- GIVEN a row with `hour=None`
- WHEN grouped by `"hour"`
- THEN it lands under `"unknown"`

#### Scenario: Empty and unknown dimension
- GIVEN `rows=[]`, WHEN grouped, THEN `{}`
- GIVEN `dimension="nope"`, WHEN grouped, THEN `{}` without raising

### Requirement: A3 — equity_and_drawdown

`equity_and_drawdown(pnls: list[float]) -> dict` MUST return
`{"equity": list[float], "max_drawdown": float | None}` in one traversal,
delegating to `equity_curve`/`max_drawdown`. Empty input MUST yield
`{"equity": [], "max_drawdown": None}`.

#### Scenario: One call, both values
- GIVEN `pnls = [5.0, -2.0, 3.0]`
- WHEN it runs
- THEN `equity == [5.0, 3.0, 6.0]` and `max_drawdown == -2.0`

### Requirement: A4 — calibrate

`calibrate(signals: list[dict], trades: list[dict], *, window_seconds: int) -> dict`
MUST join historical SMC signals to real trades. Each `signal` MUST carry
`{symbol, time, direction, entry, stop, score}` (`time` UNIX seconds); each
`trade` MUST carry `{net: float, side: str, ctime: int, qty: float}` (`ctime`
epoch **ms**). A trade MATCHES the **nearest** signal with the same `symbol`
whose `direction` equals the trade's mapped direction (`BUY→long`, `SELL→short`)
and `abs(trade.ctime/1000 − signal.time) <= window_seconds`; ties MUST pick the
smaller `abs(delta)` then the earlier `time` (deterministic). Output MUST be
exactly `{"matched": dict, "unmatched": dict, "by_setup": dict,
"r_by_setup": dict}`: `matched`/`unmatched` are `summarize(nets)`; `by_setup` maps
`setup_kind → summarize(nets)` for matched trades only, keys sorted; `r_by_setup`
maps `setup_kind → float | None` = mean `r_multiple(net, |entry−stop|×qty)`
(`None` when risk is zero). `window_seconds <= 0`, missing/empty inputs, or
malformed records MUST yield empty buckets with `None` scalars and MUST NOT raise.
MUST NOT mutate inputs.

#### Scenario: Nearest signal within window matches
- GIVEN a `BUY` trade at `ctime=1_700_000_000_000` and a `long` signal at
  `time=1_699_999_999` with `window_seconds=3600`
- WHEN `calibrate` runs
- THEN the trade is in `matched`, its `by_setup["long:score4"]` bucket is scored, and `r_by_setup` holds its mean R

#### Scenario: Outside window is unmatched
- GIVEN a signal whose `abs(delta) > window_seconds`
- WHEN `calibrate` runs
- THEN the trade contributes to `unmatched` only and no `by_setup` entry

#### Scenario: Direction mismatch does not match
- GIVEN a `SELL` trade and only a `long` signal in window
- WHEN `calibrate` runs
- THEN the trade is unmatched

#### Scenario: Nearest wins and ties break deterministically
- GIVEN two same-direction signals in window at deltas 100 and 50
- WHEN `calibrate` runs
- THEN the delta-50 signal is chosen; equal deltas pick the earlier `time`

#### Scenario: Zero/empty inputs never raise
- GIVEN no signals or no trades, or `window_seconds=0`
- WHEN `calibrate` runs
- THEN `matched`/`unmatched` are empty buckets and `by_setup`/`r_by_setup` are `{}`, no raise

#### Scenario: Zero risk yields None R
- GIVEN a matched trade whose signal has `entry == stop`
- WHEN `calibrate` runs
- THEN its `r_by_setup` value is `None` (no division by zero)

### Requirement: A5 — Purity, determinism, boundary

`src/analytics.py` MUST be pure (same input → byte-identical output), MUST NOT
mutate inputs, MUST NOT use `datetime`, `random`, I/O, or global state, and MUST
import only stdlib + `src.metrics`. It MUST be registered in `PURE_MODULES` in
`tests/test_boundary.py`. All functions MUST NOT raise on empty, mismatched, or
malformed input.

#### Scenario: Deterministic output
- GIVEN identical inputs, WHEN a function is called twice, THEN both results equal

#### Scenario: Boundary test stays green
- GIVEN `analytics.py` registered in `PURE_MODULES`
- WHEN `python -m pytest tests/test_boundary.py` runs
- THEN no non-stdlib import is found and all boundary tests pass

**Edge-case matrix**

| Condition | Result |
|-----------|--------|
| empty `pnls` | `summarize` zero/None; `net_pnl=0.0` |
| unknown `dimension` | `{}` |
| `None` dimension key | `"unmatched"` / `"unknown"` |
| signals/trades empty | empty buckets, `None` scalars |
| `window_seconds <= 0` | all trades unmatched |
| direction mismatch | unmatched |
| equal time deltas | earlier `time` wins |
| `entry == stop` (risk 0) | `r_by_setup` value `None` |
