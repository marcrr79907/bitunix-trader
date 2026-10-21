# Design: setup-ledger

## Technical Approach

Capture reads the already-persisted candle window (no network), runs the same
SMC composition `get_smc_payload` runs, and persists one immutable row per
engine/anchor. The capture *composition* is a new additive pure helper in
`src/smc/signals.py`; the persistence pipeline is a new `web/trading/setups.py`
sibling of `candles.py`; `run_once` gains one isolated step after the candle
cycle. `find_setups`, its `Setup` shape, and both existing callers are untouched.

## Architecture Decisions

### D1 — Enriched record: additive pure helper (A), not recomputation (B)

**Choice**: `capture_setups(opens, highs, lows, closes, times, *, atr_window=14) -> list[SetupRecord]` in `src/smc/signals.py`. It composes the frozen chain (`find_swings` → `find_structure` → `dealing_range` → `find_setups`) and maps `index` → `anchor_time` / `atr` exactly as `_serialize_smc` maps `index` → `time`.
**Alternatives rejected**: (B) recompute zones in `web/trading/setups.py` — duplicates the OB/FVG selection and `recent()` window, the exact drift the "SMC math stays in `src/smc/`" convention exists to prevent, and it is untestable without Django. (A′) new `src/smc/capture.py` — a new pure module must also be registered in `tests/test_boundary.py::PURE_MODULES`; same code, one more file, one more test edit. (A″) refactoring `find_setups` into a private `_derive` — would touch the frozen module's internals for no gain, since the reduced field set (D4) needs nothing from inside `find_setups`.
**Rationale**: one home for the composition, zero duplicated math, `find_setups` byte-identical, no new module → no boundary registration.

### D2 — Capture seam in `web/trading/setups.py`

**Choice**: `trading` owns the write pipeline (`run_setup_capture(symbols) -> int`), mirroring `candles.persist_candles`.
**Alternatives rejected**: `web/worker.py` (already 324 lines; the seam would be untestable in isolation); `web/market/` (read-only app by contract — it must not write).
**Rationale**: `trading` owns persistence, `market` owns read-only reads; the seam consumes `market.quotes._db_rows` exactly as `run_alert_rules` already does. It is importable from `worker.run_once` and reusable by `evaluate_setups` (#261), which is also a `trading` concern.

### D3 — `SETUP_CAPTURE_INTERVALS`: reject at import

**Choice**: parse env (default `1h`), and `raise ValueError` naming the offending values when not a subset of `CANDLE_INTERVALS`.
**Alternatives rejected**: filter + warn — silently stops a ledger whose entire value is unbroken history, and the operator sees only "0 persisted".
**Rationale**: loud beats silent for a measurement table. Consequence: a typo disables capture every cycle (warning logged, nothing persisted) while ingestion, sync and alerts stay green — acceptable because the import is placed **inside** the isolated `try` (D6), so the failure cannot escape.

### D4 — Field set: 8 record fields, 11 model columns

**Choice**: drop `zone_top`, `zone_bottom`, `range_high`, `range_low`, `has_ob`, `has_fvg` from the proposal's list.
**Rationale**: no concrete consumer. `score` already encodes OB/FVG presence (1 + 1 each), zone bounds are not read by #260 and #261 measures outcome against `entry`/`stop`/`take_profit`. Adding a nullable column later is an additive migration; carrying unread columns now is permanent schema debt. Re-add when a named reader exists.

### D5 — Unique key includes `engine_version`

**Choice**: `UniqueConstraint(symbol, interval, anchor_time, engine_version)`.
**Alternatives rejected**: the proposal's 3-field constraint — it **contradicts** success criterion "a bumped `SMC_ENGINE_VERSION` writes new rows": the insert would conflict and be ignored, so old rows would be the only rows forever.
**Rationale**: the ledger is append-only at emission; (anchor, engine) is the identity. Cost: changing the math without bumping the version silently keeps the old row (intended immutability, made explicit in the docstring).

### D6 — Window 100, ATR 14, isolation placement

**Choice**: `SETUP_CANDLE_WINDOW = 100`; `atr_window=14`; the capture step sits immediately AFTER the candle `try/except`, in its own `try`.
**Rationale**: the deepest backward need is `RANGE_LOOKBACK` 50 from the window end plus 2 confirming bars (`SWING_RIGHT`) = 52; `OB_LOOKBACK` 10 and ATR 14 sit inside that span. 100 matches `ALERT_CANDLE_WINDOW`, so the ledger and the alert path evaluate the same geometry on the same rows, and any anchor in the last ~86 bars has a non-null ATR. 14 matches `alert_rules._SCALAR_PARAMS["atr"]`. Placement is after persistence (fresh rows) yet independent of its `try` (a candle failure still captures — stale window, same anchor, `ignore_conflicts` no-op).

## Module Boundaries

| File | Owns |
|---|---|
| `src/smc/signals.py` | `Setup` + `SetupRecord` + `find_setups` + `capture_setups`. Pure: stdlib + `src.indicators`, no I/O, never raises. |
| `src/smc/config.py` | `SMC_ENGINE_VERSION = 1` (hand-bumped), alongside the other pure tunables. |
| `web/trading/models.py` | `Setup` row schema (persistence only, no math). |
| `web/trading/setups.py` | env parsing/validation, DB read, enrichment, `bulk_create`. |
| `web/worker.py` | scheduling + isolation of one capture step. |

**Ownership**: `Setup` is GLOBAL — no `user` FK, not in `OWNED_MODELS`. A setup
is a market-derived observation, byte-identical for every user, exactly like
`Candle` and `FundingSnapshot`; a per-user copy would multiply the same row by N
and the worker has no user context. `src/` never imports Django.

## Data Model — `trading.Setup` (migration `0018_setup`, depends on `0017_charttemplate`)

| Field | Type | Null | Note |
|---|---|---|---|
| `symbol` | CharField(32) | no | |
| `interval` | CharField(8) | no | subset of `CANDLE_INTERVALS` |
| `anchor_time` | BigIntegerField | no | candle OPEN, UNIX seconds |
| `direction` | CharField(8) | no | `long` / `short` |
| `entry` / `stop` / `take_profit` / `rr` | FloatField | no | |
| `score` | PositiveSmallIntegerField | no | 0..4 |
| `atr` | FloatField | yes | null when the anchor is inside ATR warm-up |
| `engine_version` | CharField(16) | no | `SMC_ENGINE_VERSION` at write time |
| `created_at` | DateTimeField(auto_now_add) | no | |

Constraints: `UniqueConstraint(symbol, interval, anchor_time, engine_version)` +
`Index(symbol, interval, anchor_time)`. Additive only — no existing table touched.

## Sequence — one capture cycle

1. `run_once` persists funding/tickers; candle cycle fetches + persists closed candles.
2. Capture step: `run_setup_capture(symbols)`.
3. For each `symbol` × `SETUP_CAPTURE_INTERVALS`: `_db_rows(symbol, interval, None, 100)`.
4. `< 3` rows → skip pair. Else `capture_setups(...)` → 0..1 `SetupRecord`.
5. Build `Setup` rows stamped with `engine_version`; `bulk_create(ignore_conflicts=True)`.
6. Return the row-count delta; `run_once` logs and returns `(funding, ticker)` unchanged.

## Failure / Degradation Matrix

| Failure | Effect | Everything else |
|---|---|---|
| `capture_setups` raises | warning `setup capture failed: {exc}`; 0 rows this cycle | intact |
| Candle cycle raises | capture runs on the stale window; same anchor → conflict ignored | intact |
| Bad `SETUP_CAPTURE_INTERVALS` | import raises inside the `try` → warning each cycle, capture disabled | intact |
| No setups / thin window | 0 inserted, no log noise | intact |
| Duplicate run | 0 inserted (unique key) | intact |
| DB write error | warning; loop survives | intact |

## Test Plan (Strict TDD — tests written first)

| File | Covers |
|---|---|
| `tests/test_smc_capture.py` (new, pure) | `anchor_time` from `times`, `atr` value vs `src.indicators.atr`, `atr is None` in warm-up, `[]` on empty/mismatched/`len(times) != n`, fields equal `find_setups` output, determinism/no mutation, never raises |
| `tests/web/test_setups_model.py` (new) | global model (no `user`, not in `OWNED_MODELS`), unique fields, index, migration source: only `CreateModel`, no alter/delete, depends on `0017` |
| `tests/web/test_setups_capture.py` (new) | one row per `(symbol, interval, anchor)` from seeded `Candle`; repeat run = 0; version bump = new row + old intact; `[]` = 0; bad env raises on reload |
| `tests/web/test_worker_setups.py` (new) | capture runs after candles; forced capture failure leaves funding/ticker/private/alerts green and the return tuple unchanged |

## Rollback

Revert the worker step first (capture stops, ingestion untouched), then
`web/trading/setups.py`, the version constant, and the helper. Reversing `0018`
drops only `Setup`; nothing else references it. Never destructive.

## Changed-Lines Forecast

| File | ± |
|---|---|
| `src/smc/config.py` | 3 |
| `src/smc/signals.py` | 40 |
| `web/trading/models.py` | 30 |
| `web/trading/migrations/0018_setup.py` | 52 |
| `web/trading/setups.py` | 62 |
| `web/worker.py` | 12 |
| 4 test files | ~230 |
| **Total** | **~429** |

Over the 400-line budget → recommend two chained PRs: **Slice 1** core + model +
migration + tests (~265), **Slice 2** seam + worker + tests (~164).

## Open Questions

None blocking. Flagged to the orchestrator: D4 and D5 narrow/override the
proposal's field list and unique constraint, and D3's loud failure only stays
safe because of the in-`try` import.
