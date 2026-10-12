# Exploration: alert-rules (issue #76, Fase D1)

## Executive Summary

D1 is the FIRST trusted-zone (D) change. It adds a per-user `AlertRule` owned
model plus a **deterministic evaluation pass in the worker** that runs after the
sync and fires on the **false→true edge** of a user-defined condition over the
frozen SMC/indicator/price chain. The anti-debounce pattern already exists as
`src/alerts.AlertState` (an in-memory `dict[str, bool]` with `fire()`), and the
worker already runs an isolated "sync then extras" pipeline (`run_once`) that
provides the exact hook point. Notification channels (Telegram) and the config
UI are D2 — D1 only *evaluates and marks* (`last_fired_at`) and exposes a thin
seam D2 can consume.

The work splits cleanly along the existing architectural seam: a **pure,
framework-free evaluation engine** (`src/alert_rules.py`, joins `PURE_MODULES`)
and a **Django/worker wiring** half (`AlertRule` model + `worker.run_alert_rules`
+ trusted-zone read). No new dependency, no order path, additive migration.

**D1 is bigger than a trivial model change** (model + guard + pure engine + 3
condition types + worker wiring + tests) and should ship as a **CHAINED PR**,
not a single PR. Details in the last section.

---

## 1. Current state (the seams we extend)

### 1.1 The edge-trigger pattern — `src/alerts.py` (READ FULLY, mirror it)

```python
class AlertState:
    """Remembers last known state per key; fires only on false->true edges."""
    def __init__(self) -> None:
        self._active: dict[str, bool] = {}
    def fire(self, key: str, condition: bool) -> bool:
        was = self._active.get(key, False)
        self._active[key] = condition
        return condition and not was
```

Verified properties:

- **Edge semantics**: fires only when `condition is True` AND the prior state for
  that key was falsy (`was = self._active.get(key, False)`). Naturally re-arms:
  after a `condition=False` call, the next `True` fires again.
- **Per-key state**: independent boolean per key (`"funding:BTCUSDT"`,
  `"margin:ETHUSDT"`). Different key → own state.
- **In-memory only**: state dies when the process exits; a restart re-arms every
  key (first evaluation after restart always "fires" if true). It is **not**
  persisted.
- **`fire()` is pure-ish**: no I/O, no clock. The predicates `funding_alert` /
  `margin_alert` are pure. Only `send_telegram` does network.
- **Caller owns the lifecycle**: `monitor.run()` creates ONE `AlertState()` and
  threads it through `check_market`/`check_positions` each poll.

`tests/test_alerts.py` is the contract: fires on transition, does NOT re-fire
while true, re-fires after re-arm, per-key independence. D1's engine tests MUST
mirror this battery.

**Key gap for D1**: `AlertState` is in-memory and has no notion of *what
persisting* an edge means. D1 must decide how the "prior state" survives a worker
restart (see §4).

### 1.2 Worker topology — `web/worker.py`

- **Boot**: `main()` → `_bootstrap()` sets `DJANGO_SETTINGS_MODULE` and calls
  `django.setup()`. Django is imported lazily so `scheduler.py` can import
  `idle_loop` without booting Django.
- **Cycle** (`run_loop` → `run_once(client, symbols)`):
  1. `fetch_market` + `persist_market` (global funding/ticker) → `(funding, ticker)`.
  2. **Candle cycle** (`fetch_closed_candles` + `persist_candles`) wrapped in a
     broad `except Exception` — "a candle failure must never degrade
     funding/ticker persistence or kill the loop".
  3. **Private sync** (`run_private_sync()`) wrapped in the same broad
     `except Exception` — per-user isolation (R5).
  4. `return counts` — the `(funding, ticker)` contract is frozen for callers.
- **Trusted zone**: `run_private_sync` reads `ExchangeCredential.objects.filter(
  is_active=True)` **unscoped** and calls `credentials.decrypt`. `worker.py` is
  explicitly OUTSIDE the credential scanner's request path (R13) and OUTSIDE the
  owned-model guard's `REQUEST_PATH` (R14.4) — it MAY read across users.
- **Deployment**: `docker-compose.yml` runs `python web/worker.py` as its own
  service; `start.sh` is the *web* entrypoint (migrate + gunicorn), not the
  worker. No management command runs the worker loop; `scheduler.py` is still a
  Redis-ping idle stub.

**Where "after the sync" hooks**: inside `run_once`, after step 3. The existing
pattern (candle, private) is the template: a new isolated step
`run_alert_rules()` with its own broad `except Exception`, so an alert-evaluation
bug can never kill ticks or private sync.

### 1.3 Persistence layer

- `web/trading/models.py`: global models (`FundingSnapshot`, `TickerSnapshot`,
  `Candle`) have **no owner FK** (R1) and are shared by all users. `Candle` is
  keyed by `(symbol, interval, time)` with `time` = bar OPEN in UNIX seconds,
  `interval` a string (`"5m"…"1M"`).
- **`UserOwnedModel`** (abstract): `user` FK (`CASCADE`, `related_name=
  "%(app_label)s_%(class)s_set"`) + classmethod `for_user(user)` →
  `cls.objects.filter(user=user)`. Concrete owned models: `ExchangeCredential`,
  `Watchlist`, `PositionSnapshot`, `AccountSnapshot`, `Trade`, `ChartLayout`,
  `Drawing`.
- `ChartLayout` / `Drawing` are the closest precedents for `AlertRule`:
  `symbol` + `interval` CharFields, a `JSONField` for an open-ended config
  (`indicators` / `points`+`style`). `ChartLayout` has a unique
  `(user, symbol, interval)`; `Drawing` is a **collection** (no unique
  constraint, indexed on `(user, symbol, interval)`).
- `web/trading/candles.py`: `INTERVAL_SECONDS` / `CANDLE_INTERVALS` — the
  persisted, closed-candle intervals are `("5m","15m","1h","2h","4h","1d","1w",
  "1M")`. **`1m` is NOT persisted.**

### 1.4 Condition sources (what a rule can evaluate over)

- **SMC chain** (`src/smc/`, frozen B1+B2, consumed by C1 in
  `web/market/quotes.py`): `find_swings` → `label_swings`/`find_structure`
  (`StructureEvent.kind ∈ {bos,choch}`, `.direction ∈ {bullish,bearish}`,
  `.trend ∈ {up,down}`) → `find_order_blocks`/`find_fvg` → `dealing_range` →
  `find_setups` (`Setup.direction ∈ {long,short}`, `.score 0..4`, `.rr`,
  `.entry/.stop/.take_profit`, `.index`). All pure, list-in / sparse-list-out,
  never raise, stdlib only.
- **Indicators** (`src/indicators.py`): `sma`, `ema`, `rsi`, `atr`, `vwap`,
  `macd`, `bollinger`, `stochastic`, `zscore`. Index-aligned lists, leading
  `None` warm-up. The chart registry in `quotes.py` maps token→params→build and
  is the canonical vocabulary (`sma_len`, `rsi_len`, `bb_len`, `macd_fast`…).
- **Price**: the latest `Candle.close` (or `TickerSnapshot.last_price`). For
  determinism, evaluate over the latest **closed candle**, not a live tick.
- **The reuse seam**: `web/market/quotes.get_smc_payload` already runs the whole
  chain over a DB-first window and is the exact computation D1's `smc_setup`
  condition needs. Its `_fetch_window` / `_db_rows` helpers are the DB-first read
  pattern. **But `quotes.py` lives in `market/` (request path) and needs a
  `client`.** D1 should not import a view helper into the worker; it should call
  the *same pure functions* directly.

---

## 2. Worker wiring (where the evaluation lives)

### 2.1 The framework-free boundary — confirmed

- **Rule**: `src/` MUST NOT import Django (enforced by `tests/test_boundary.py`,
  which `rglob`s all of `src/`). `web/` MAY import `src/`. `PURE_MODULES` adds a
  stronger stdlib-only check per listed module.
- **Consequence for D1**: the pure evaluation logic (condition → bool over OHLC)
  belongs in **`src/`** so it is testable without Django and reusable by the
  chart/UI later. The model access + loop over users/rules + `last_fired_at`
  write belong in the **Django zone** (`web/`).
- **`src/alert_rules.py`** is the natural home: it imports `src.smc.*` +
  `src.indicators` (all pure) and evaluates a `condition` dict against OHLC
  lists. **Add `"alert_rules.py"` to `PURE_MODULES`.**

### 2.2 Proposed wiring

```
src/alert_rules.py            # PURE engine (framework-free)
  matches(condition, ohlc, *, ...) -> bool        # state at the latest bar
  evaluate(condition, ohlc, *, prior=False) -> (state, fired)  # edge over state
  # mirrors AlertState.fire(): fired = state and not prior

web/trading/models.py         # AlertRule(UserOwnedModel) + additive migration
web/trading/alert_rules.py?   # (optional) thin Django-side helper
web/worker.py                 # run_alert_rules() called from run_once, isolated
```

`run_alert_rules()` (trusted zone, in `worker.py`):

1. Read `AlertRule.objects.filter(is_active=True)` **unscoped** (worker is
   outside the owned-model scan — same latitude as `ExchangeCredential` reads).
2. Group rules by `(symbol, interval)` and load ONE candle window per group from
   `Candle` (global, not owned) — avoids an N+1 read.
3. For each rule, in its own `try/except`: build the OHLC lists, call the pure
   `evaluate(...)`, and on `fired` set `rule.last_fired_at` (save with
   `update_fields`). A failing rule is logged and skipped — **peers continue**
   (per-rule isolation, mirrors `run_private_sync`).
4. Return a small count/summary for logging. No network, no order.

`run_once` gains an isolated step (mirroring candles/private):

```python
try:
    fired = run_alert_rules()
    logger.info("alert rules ok fired=%d", fired)
except Exception as exc:  # ponytail: broad by spec — rules must never kill ticks
    logger.warning("alert rules failed: %s", exc)
```

**Boundary note (critical)**: if `run_alert_rules` lived in `web/trading/*.py`,
its unscoped `AlertRule.objects.filter(...)` read would be flagged by
`test_owned_model_guard.py` (the guard scans `web/trading`). Keeping the
unscoped read in `worker.py` (outside `REQUEST_PATH`) is the clean route; the
pure engine stays in `src/`.

### 2.3 Cadence

- The worker polls every `INGEST_POLL_SECONDS` (default 30s). Evaluating rules
  **every cycle** is the simplest and matches the "after the sync" requirement.
- Because evaluation is on **closed candles**, the observable condition only
  changes when a new candle closes; evaluating on the same closed bar twice must
  yield the same edge result (deterministic). Cadence is therefore a *cost*
  concern, not a *correctness* one. Open question Q-CAD (per cycle vs only when a
  new bar appeared).

---

## 3. Condition design (proposed JSON schema)

`condition` is a single JSON object with a discriminating `type`. Three v1
types. All map to frozen pure functions; all deterministic; no wall-clock.
Validation mirrors `parse_drawing` / `parse_layout_indicators` (raise on breach)
— but D1 has no UI, so validation is **defensive at evaluation time** (D2 owns
the write-time validator).

### 3.1 `price` — a level on the latest close

```json
{"type": "price", "op": "above" | "below", "level": 50000.0}
```

- `state = close[-1] > level` (above) / `close[-1] < level` (below); strict.
- Maps to: `Candle.close` of the latest closed bar. No indicator call.

### 3.2 `indicator` — an indicator value vs a level

```json
{"type": "indicator",
 "name": "rsi" | "sma" | "ema" | "atr" | "vwap" | "macd" | "bollinger" | "stochastic",
 "params": {"rsi_len": 14, "sma_len": 20, "...": "..."},
 "op": "above" | "below",
 "level": 30.0}
```

- `state` = the named indicator's series value at the latest bar compared to
  `level` (strict). `None` (warm-up) ⇒ `state = False` (never raises).
- Maps to: the "level-based" indicators (`rsi`, `sma`, `ema`, `atr`, `vwap`).
- **`macd`/`bollinger`/`stochastic` return tuples** — v1 should restrict `name`
  to the scalar series (`rsi,sma,ema,atr,vwap`) OR define a sub-selector key
  (`"line": "signal"`, `"band": "upper"`). Recommendation: **v1 = scalar series
  only**; tuple indicators deferred (open Q-COND).
- Param vocabulary reuses the chart registry keys (`sma_len`, `rsi_len`, …) so
  D2's UI and the chart share one vocabulary. Params default from the pure
  function defaults when omitted.

### 3.3 `smc_setup` — the frozen SMC chain emits a matching Setup

```json
{"type": "smc_setup", "direction": "long" | "short" | "any", "min_score": 3}
```

- `state = any(find_setups(...) with direction match and score >= min_score)` on
  the latest bar. Empty chain ⇒ `False`.
- `min_score` defaults to `MIN_CONFLUENCE` (3) when omitted.
- Optionally a `kind` filter (`"bos"`/`"choch"`) over the latest
  `StructureEvent` — deferred (recommend v1 = setup only; structure-kind is a
  second, additive type `smc_structure` later).

**Determinism**: all three types are pure functions of the OHLC window; no
`datetime`, `random`, or I/O in the engine. The only timestamp in play is the
*edge* timestamp stored in `last_fired_at` (the invariant's allowed exception).

---

## 4. Edge / debounce semantics (the core decision)

`AlertState.fire(key, condition)` semantics, ported to a persisted rule:

- **Fire** iff `state_now == True` AND `state_prior == False`.
- **Re-arm** when `state_now == False` (prior becomes False; next True fires).
- **No re-fire** while the state stays True.

The question is **where `state_prior` lives**. Two candidate designs:

| Option | Mechanism | Pros | Cons |
|--------|-----------|------|------|
| **A. Persisted bool** | Add a field (e.g. `last_state = BooleanField(default=False)` or a JSON `state`) updated each cycle | Direct mirror of `AlertState`; O(1) per cycle | New mutable state; a missed cycle / restart edge case; adds a field the issue did not list |
| **B. Recomputed over history** | Evaluate `matches` at the latest CLOSED bar AND at the previous bar; `fired = now and not prev` | **Stateless in the rule**; deterministic + restart-safe; no schema extension; identical result regardless of worker cadence/restart | Needs a 2-bar window; dedup of repeated fires on the *same* bar still needed |

**Recommendation: B (recomputed edge) + `last_fired_at` as the dedup key.**
This is the strongest reading of issue #76's invariants:

- **Deterministic**: same candles ⇒ same edge, independent of when/whether the
  worker ran before. No hidden mutable per-rule bool.
- **Restart-safe**: a worker restart does not spuriously re-fire (option A does).
- **"no wall-clock except edge timestamps"**: the engine uses *bar times*, not
  `datetime.now()`. The worker stamps `last_fired_at` from the edge bar's time.
- The model's exact field list (`user, symbol, interval, condition, is_active,
  last_fired_at`) is honored **without** adding a state field.
- **Dedup**: because B evaluates the same bar the same way every cycle, store the
  *fired bar's time* in `last_fired_at` and fire only when
  `edge_bar_time > last_fired_at` (or `last_fired_at is None`). `last_fired_at`
  is thus both the observable timestamp AND the idempotency guard — no second
  field.

> Note: `last_fired_at` is a `DateTimeField` by the issue's wording; the edge bar
> time (UNIX seconds) can be stored as a UTC datetime. If the spec prefers raw
> epoch, a `BigIntegerField` variant is a minor deviation to lock in design.

**Open decision**: A vs B is the single highest-leverage choice in D1 and MUST
be locked in the spec. Recommendation is B.

---

## 5. Isolation, anti-spam, determinism

- **Per-user (R14 A≠B)**: `AlertRule(UserOwnedModel)`. `for_user(user).get(pk=..)`
  MUST raise `DoesNotExist` for another user. The rule's evaluation reads only
  the *global* `Candle`/SMC market data (not another user's rows) — ownership is
  the rule row itself. Add `AlertRule` to `OWNED_MODELS` in
  `tests/test_owned_model_guard.py` and to the R14.2/R14.3 scenario lists.
- **Per-rule isolation**: each rule evaluated in its own `try/except`; one bad
  `condition`, missing candle window, or engine error is logged and skipped —
  peers keep going (mirror `run_private_sync`'s broad except + `logger.warning`).
- **Per-user worker isolation**: the worker legitimately reads all users' rules
  unscoped (R14.4, same as `ExchangeCredential`). No `for_user` required in the
  worker; the guard is not applied to `worker.py`.
- **Anti-spam**: the edge semantics (§4) guarantee a persistent True state never
  re-fires. Re-arm on False. Tests MUST prove: true→true = no fire; true→false =
  no fire; false→true = fire; a second consecutive cycle on the *same closed bar*
  = no duplicate.
- **Determinism**: pure engine, no `datetime`/`random`/I/O/global state. Feed it
  OHLC lists; assert byte-identical `(state, fired)` for identical input. `now`
  is never read by the engine.

---

## 6. Open questions / decisions to lock

| # | Question | Recommendation |
|---|----------|----------------|
| Q-EDGE | Persisted prior-state bool (A) vs recomputed edge over the last two bars (B)? | **B** — stateless, restart-safe, deterministic; §4 |
| Q-COND | Exact `condition` schema for each type | §3: `price` / `indicator` (scalar series only) / `smc_setup`; freeze keys |
| Q-COND2 | Tuple indicators (macd/bollinger/stochastic) in v1? | **No** — scalar series only; additive later via a sub-selector key |
| Q-INTERVAL | Which intervals may a rule use? | Constrain to `CANDLE_INTERVALS` (persisted closed candles) for determinism; `1m` excluded |
| Q-CAD | Evaluate every cycle vs only on a new closed bar? | Every cycle (simple); dedup via `last_fired_at`. Optimize later |
| Q-FIRED | Does D1 emit a "fired event" record or just set `last_fired_at`? | Just `last_fired_at` + a thin `on_fired(rule, context)` sink seam (stub = logger). **No events table** (YAGNI) |
| Q-D2SEAM | How does D1 expose fired alerts to D2? | A single pluggable `on_fired(rule, detail)` function (module-level), D2 replaces it with the Telegram sender; optionally a Django `Signal` |
| Q-UNIQUE | Unique constraint on `AlertRule`? | **None** (a collection like `Drawing`); index `(user, is_active)` for the read |
| Q-LASTFIRED | `last_fired_at` type / content | Store the **edge bar's timestamp** (UTC datetime), doubling as the dedup key; lock the type in design |
| Q-ENGINE_SEAM | Does the pure engine accept OHLC lists or the whole chain records? | **OHLC lists** — it calls `src.smc`/`src.indicators` internally (single source of truth; mirrors `get_smc_payload`) |
| Q-VALIDATE | Write-time condition validation lives where? | D2 (UI). D1 validates defensively at evaluation (unknown type/op ⇒ `False`, never raise) |

---

## 7. Risks

- **Framework-free boundary**: evaluation must not drift into Django. *Mitigation:*
  pure engine in `src/alert_rules.py` + `PURE_MODULES` entry; Django model access
  only in `web/`. The worker imports `src` (allowed direction).
- **Owned-model guard interaction**: putting the unscoped rule read inside
  `web/trading/` would fail `test_owned_model_guard.py`. *Mitigation:* the
  unscoped read lives in `web/worker.py` (outside `REQUEST_PATH`); the model
  joins `OWNED_MODELS` so request-path misuse is still caught.
- **Worker testability**: two layers. *Mitigation:* the pure engine → plain
  pytest (like `test_alerts.py` / `test_smc_*`); the worker step →
  `@pytest.mark.django_db` with seeded `Candle` rows and a stub/patched
  evaluator (mirror `test_worker_private_sync.py` / `test_worker_candles.py`).
- **Restart / duplicate fires**: option A's classic failure. *Mitigation:* option
  B (recomputed edge) + `last_fired_at` dedup key; test "same bar twice = one
  fire" and "restart = no spurious fire".
- **Determinism**: a stray `datetime.now()` would break it. *Mitigation:* engine
  never reads a clock; `PURE_MODULES` + a test asserting no `time`/`datetime`
  import (mirror the SMC determinism guard).
- **Candle availability**: rules referencing symbols/windows with fewer than the
  warm-up bars. *Mitigation:* engine returns `False` on short/empty input (never
  raises); the worker logs a skip.
- **Patch 100% coverage**: every branch — each condition type, each op, tuple
  rejection, warm-up `None`, edge armed/re-armed, duplicate bar, failing-rule
  isolation, unknown-condition guard. *Mitigation:* a per-function edge battery
  mirroring `test_alerts.py` + the SMC edge matrices.
- **Scope creep**: D2 (Telegram sender, UI, endpoints) must not leak in.
  *Mitigation:* fence D1 to model + engine + worker evaluation + `last_fired_at`;
  D2 owns channels + config UI.

---

## 8. Proposed PR shape + size (honest estimate)

| Slice | Files | Impl | Tests | Total |
|-------|-------|------|-------|-------|
| 1 — model + guard | `web/trading/models.py` (+`AlertRule`), `migrations/0007_alertrule.py`, `test_owned_model_guard.py`, `test_isolation.py`, per-user-isolation delta | ~60 | ~140 | ~200 |
| 2 — pure engine | `src/alert_rules.py`, `tests/test_boundary.py` (`PURE_MODULES`), `tests/test_alert_rules.py` | ~160 | ~250 | ~410 |
| 3 — worker wiring | `web/worker.py` (`run_alert_rules` + `run_once` step), `tests/web/test_worker_alert_rules.py` | ~60 | ~160 | ~220 |
| **Total** | | **~280** | **~550** | **~830** |

**~830 changed lines — well past the 400-line review budget. `400-line budget
risk: High`.** D1 is *not* a small model change: it carries a new model + guard
edits, a non-trivial pure engine (3 condition types + edge semantics), and worker
wiring, each with its own test battery.

### Recommended: CHAINED PRs (3 slices, Feature Branch Chain)

Base = a `feat/alert-rules` tracker branch; each child targets the previous.

1. **Slice 1 — model + guard** (~200): `AlertRule(UserOwnedModel)`, additive
   migration, `OWNED_MODELS` + isolation tests, per-user-isolation delta. Autonomous;
   rollback = drop migration + revert guard.
2. **Slice 2 — pure engine** (~410): `src/alert_rules.py` (3 condition types +
   `evaluate` edge helper), `PURE_MODULES` entry, engine tests. Depends only on
   frozen `src/smc`/`src.indicators`. Slightly over 400 alone; usable as a single
   PR at the edge of budget or split the engine tests if the reviewer prefers.
3. **Slice 3 — worker wiring** (~220): `run_alert_rules` + `run_once` step +
   `on_fired` sink seam (stub), integration tests with seeded candles. Consumes
   slices 1 & 2.

**2-slice alternative** (issue's suggestion): `{model + engine + guard}` (~610 —
**High**) | `{worker + tests}` (~220). If the reviewer wants two PRs, keep the
3-slice chain — the model/guard slice and the engine slice have no shared code
and are independently verifiable; folding them creates a 600+ line first PR.

**Recommendation: 3-slice chain.**

### Out of scope (fence)

- Notification channels (Telegram), delivery, retries — **D2**.
- Alert config UI, endpoints, write-time validation — **D2**.
- Any new dependency, npm/build, order execution, or `for_user` change to the
  worker trust zone.

---

## Affected Areas

- **NEW**: `src/alert_rules.py` (pure engine).
- **NEW**: `tests/test_alert_rules.py`.
- **EDIT**: `web/trading/models.py` (+`AlertRule`); **NEW** migration
  `web/trading/migrations/0007_alertrule.py`.
- **EDIT**: `web/worker.py` (`run_alert_rules` + `run_once` step + `on_fired`
  sink seam).
- **NEW**: `tests/web/test_worker_alert_rules.py`.
- **EDIT**: `tests/test_boundary.py` (`PURE_MODULES` + `"alert_rules.py"`).
- **EDIT**: `tests/web/test_owned_model_guard.py` (`OWNED_MODELS` +`AlertRule`).
- **EDIT**: `tests/web/test_isolation.py` (A≠B for `AlertRule`).
- **ARCHIVE-TIME**: new `openspec/specs/alert-rules/spec.md`; delta for
  `per-user-isolation` (R14.2/R14.3 gain `AlertRule`).

No change to `src/smc/`, `src/indicators.py`, `market/`, or the chart.

## Ready for Proposal

**YES** — the architecture is a direct extension of proven seams (the
`AlertState` edge pattern, the `run_once` isolated-step pattern, the
`UserOwnedModel` contract, and the frozen pure SMC/indicator chain). No new
dependency, no order path, additive migration. The spec MUST lock: the edge
design (Q-EDGE, recommend B), the `condition` schema per type (Q-COND/Q-COND2),
the interval constraint (Q-INTERVAL), the `last_fired_at` semantics (Q-LASTFIRED),
and the D2 seam (Q-D2SEAM).
