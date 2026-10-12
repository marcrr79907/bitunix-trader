# Proposal: alert-rules (Fase D1, issue #76)

## Intent

First trusted-zone (D) change. Users define per-user `AlertRule`s over the frozen
SMC/indicator/price chain; the worker evaluates them after sync and records the
false→true **edge** in `last_fired_at`. D1 evaluates and marks only — it never
sends, never orders. D2 (channels, UI) consumes D1's fired seam.

## Why Now

The frozen seams D1 needs already exist: the `AlertState` edge pattern
(`src/alerts.py`), the `run_once` isolated-step pipeline, the `UserOwnedModel`
contract, and the frozen pure SMC/indicator chain. D1 is the named first D change
and unblocks D2; delaying it blocks the trusted-zone series.

## Scope

### In Scope
- `AlertRule(UserOwnedModel)`: `symbol, interval, condition(JSON), is_active,
  last_fired_at` + additive migration; joins `OWNED_MODELS` + R14.2/R14.3 deltas.
- Pure engine `src/alert_rules.py` (joins `PURE_MODULES`): 3 condition types,
  `matches` state + `evaluate` edge over the last two closed bars.
- Worker step `run_alert_rules()` in `run_once` as an isolated broad-`except` step;
  module-level `on_fired(rule, detail)` sink (stub = logger).

### Out of Scope
- D2: Telegram delivery/retries, alert UI, endpoints, write-time validation,
  events table.
- Order execution (HARD fence); new deps; changes to `src/smc/`, `src/indicators`,
  `market/`.

## Capabilities

### New Capabilities
- `alert-rules`: per-user rule model + deterministic edge evaluation in the worker.

### Modified Capabilities
- `per-user-isolation`: R14.2/R14.3 gain `AlertRule` (collection, no unique).
- `core-domain-boundary`: `PURE_MODULES` gains `"alert_rules.py"`.

## Approach

**Split** — pure engine (`src/alert_rules.py`, imports `src.smc.*`/`src.indicators`,
stdlib only) + Django/worker wiring (`web/trading/models.py`, `web/worker.py`). The
worker imports `src` (allowed direction).

**Edge = Option B** — recompute over the latest TWO closed bars:
`fired = now and not prev`. Stateless, deterministic, restart-safe; identical
result regardless of cadence. `last_fired_at` stores the **fired bar's time** (UTC
datetime) and doubles as the dedup key (fire only when edge bar time
`> last_fired_at` or unset). No extra state field.

**Condition schema** (defensive at eval; unknown type/op ⇒ `False`, never raises):
- `{"type":"price","op":"above|below","level":f}` — strict on latest close.
- `{"type":"indicator","name":<scalar series>,"params":{},"op":..,"level":f}` —
  scalar only (`rsi/sma/ema/atr/vwap`); tuple indicators deferred.
- `{"type":"smc_setup","direction":"long|short|any","min_score":n}` — any matching
  `Setup` on the latest bar; `min_score` defaults to `MIN_CONFLUENCE`.

**Worker** — `run_alert_rules` reads `AlertRule.objects.filter(is_active=True)`
**unscoped** in `web/worker.py` (outside `REQUEST_PATH`, R14.4), groups by
`(symbol, interval)` for one window per group, evaluates each rule in its own
`try/except` (per-rule isolation), stamps `last_fired_at` on fire. Mirrors
candle/private-sync steps. Intervals constrained to `CANDLE_INTERVALS` (`1m` out).

**D2 seam** — module-level `on_fired(rule, detail)` called on each fire; stub logs.
No events table (YAGNI).

**Deterministic** — engine reads no wall-clock; the only timestamp is the edge bar.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/alert_rules.py` | New | pure engine |
| `web/trading/models.py` | Modified | `+AlertRule` |
| `web/trading/migrations/0007_alertrule.py` | New | additive |
| `web/worker.py` | Modified | `run_alert_rules` + `run_once` + `on_fired` |
| `tests/test_alert_rules.py` | New | engine edge battery |
| `tests/web/test_worker_alert_rules.py` | New | seeded-candle integration |
| `tests/test_boundary.py` | Modified | `PURE_MODULES += "alert_rules.py"` |
| `tests/web/test_owned_model_guard.py`, `test_isolation.py` | Modified | `+AlertRule` |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Framework-free boundary drift | Med | engine in `src/`; `PURE_MODULES`; Django only in `web/` |
| Owned-model guard interaction | Med | unscoped read in `worker.py`; model in `OWNED_MODELS` |
| Worker testability | Med | pure engine → plain pytest; step → `django_db` seeded |
| Restart / duplicate fires | Med | Option B + `last_fired_at` dedup; same-bar test |
| Determinism (stray clock) | Low | no clock in engine; guard test; `PURE_MODULES` |
| Candle warm-up / short input | Low | engine returns `False`; worker logs skip |
| Scope creep into D2 | Med | fence to model + engine + worker + `last_fired_at` |

## Rollback Plan

Pure additive, no destructive data. Revert in reverse: drop the `run_once` step +
`run_alert_rules` + `on_fired`; delete `src/alert_rules.py` and revert
`PURE_MODULES`; delete `migrations/0007_alertrule.py` (+ migration row) and
`AlertRule`; revert `OWNED_MODELS` + isolation tests. Inert until the step runs.

## Read-Only Boundary

The system MUST NOT place, modify, or cancel orders. D1 adds no execution path,
no `client` import in the engine, no new dependency; rules evaluate market data
only. R11 order scanner stays clean.

## Dependencies

- SMC/indicator seams frozen (B1/B2) — D1 consumes them read-only.
- D2 consumes D1's `on_fired` fired seam.

## Delivery (Chained PRs — Feature Branch Chain)

Base = `feat/alert-rules` tracker; each child targets the previous slice.
`400-line budget risk: High` (~830 lines). 3 slices:

1. **Slice 1 — model + guard** (~200): `AlertRule` + migration + `OWNED_MODELS` +
   isolation + per-user-isolation delta.
2. **Slice 2 — pure engine** (~410): `src/alert_rules.py` + `PURE_MODULES` + tests.
3. **Slice 3 — worker wiring** (~220): `run_alert_rules` + `run_once` + `on_fired`
   + integration tests.

- Decision needed before apply: Yes · Chained PRs recommended: Yes · budget risk: High

## Success Criteria

- [ ] `for_user(other).get(pk=rule.pk)` raises `DoesNotExist`; guard stays green.
- [ ] Engine pure + deterministic: same OHLC → byte-identical `(state, fired)`;
      no `time`/`datetime`/`random`; empty/short → `False`.
- [ ] Edge battery green: false→true fires; true→true / true→false do not; same
      bar twice = one fire; restart = no spurious fire.
- [ ] Worker step isolated: failing rule logged + skipped, peers continue; ticks
      and private-sync unaffected.
- [ ] `on_fired` invoked on fire (stub logger); no events table, no channel.
- [ ] No new dependency; `pytest` green; patch 100%; `ruff` clean.
