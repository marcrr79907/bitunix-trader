# Proposal: setup-outcomes

Issue **#261** — second link of the measurable-baseline chain (#260 ledger done).

## Intent

Resolve every `Setup` from the ledger against the real candles that follow it
and record **what happened next** — TP, SL, ambiguous, expired, not-triggered —
plus MFE/MAE in R and **`sl_then_tp`**: setups that touched SL and, had the stop
held, would have reached TP. A win rate alone can't say whether the stop is bad;
`sl_then_tp` and MAE near 1R can. Today the ledger stores intentions, not
outcomes: nothing resolves setups against later candles.

## Scope

### In scope

1. **`SetupOutcome` model** (global, `web/trading/models.py`): OneToOne to
   `Setup`; `status` (`take_profit` | `stop_loss` | `ambiguous` | `expired` |
   `not_triggered`), `resolved_time` (BigInt null, candle OPEN s),
   `bars_to_resolution` (Integer null), `mfe_r`, `mae_r` (≤ 0),
   `sl_then_tp` (Boolean null), `horizon_bars`, `engine_version`, `evaluated_at`
   (auto). Additive migration; outside `OWNED_MODELS`; no user FK.
2. **Pure resolver** (stdlib-only in `src/smc/`, no DB): walks candles forward
   from `anchor_time + 1`, max `horizon_bars` (default 200), conservative on
   same-candle SL+TP (`ambiguous`, counted as SL); R = |entry − stop|; MFE/MAE
   from activation to resolution (end of horizon if unresolved; from anchor if
   never activated). Returns the 5 states without look-ahead.
3. **`evaluate_setups` command** (`web/trading/management/commands/`), pattern
   of `backfill_candles`/`prune_snapshots`: module-level `run(...)` seam with
   injectable `out`; flags `--interval`, `--horizon-bars`, `--max-setups`,
   `--dry-run`; idempotent `update_or_create` per setup (re-evaluation with a
   different horizon overwrites the outcome, never the setup).
4. **Railway cron** documented in `docs/deployment.md`, same contract as
   existing jobs (`python web/manage.py evaluate_setups`), hourly suggested,
   container-decoupled.

### Out of scope

- **Trade↔Setup matching** — signal evaluation, not execution; future issue.
- **SMC engine changes** — thresholds, capture, frozen `Setup` untouched.
- **Notifications.**
- Order execution — never; read-only surface, `test_no_order_surface.py` green.

## Capabilities

- **New** `smc-setup-outcomes`: outcome model, deterministic resolution
  semantics, evaluation command, cron contract.
- **Modified** none.

## Recorded decisions (owner, binding)

1. **Evaluation only when full horizon available**: `anchor + horizon_bars ×
   interval ≤ now`. The command takes `now` once and injects it; no
   `datetime.now` inside the loop (deterministic).
2. **`bars_to_resolution` counted from ACTIVATION** (first touch of entry), 0
   if the same candle resolves; NULL if never activated or never resolved.
3. **`sl_then_tp` = True only if TP touched in a candle STRICTLY AFTER the
   resolution candle**; computed only for status `stop_loss`/`ambiguous`;
   `None` otherwise.
4. **R formulas** (R = |entry − stop|): long → `mfe_r = max((H−E)/R)`,
   `mae_r = min((L−E)/R)`; short → `mfe_r = max((E−L)/R)`, `mae_r =
   min((E−H)/R)`. `mae_r ≤ 0` always. `None` when R = 0 (unreachable with valid
   setups; the code never divides by zero).
5. **`--interval` optional**: without it, evaluate all intervals present in the
   Setup ledger (distinct), deterministic order by `anchor_time` ascending.
6. **Outcome `engine_version`** copies the setup's stamp verbatim (`"1:w200"`);
   re-evaluation doesn't change the stamp.

## Approach

The pure resolver receives OHLC lists and setup parameters, returns a
NamedTuple; the Django command loads candles via direct `Candle.objects.filter
(time__gt=anchor_time).order_by("time")` per `(symbol, interval)`, injects `now`
once, and persists via `update_or_create`. `Setup` stays byte-identical; the
SMC engine is untouched.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/trading/models.py` | New | `SetupOutcome` (global, OneToOne) |
| `web/trading/migrations/00XX_setupoutcome.py` | New | Additive migration |
| `src/smc/outcomes.py` | New | Pure resolver (stdlib-only, in PURE_MODULES) |
| `web/trading/management/commands/evaluate_setups.py` | New | Command, `run()` seam |
| `docs/deployment.md` | Modified | Cron service entry |
| `tests/` | New | Pure + command tests, 5-state coverage |

## Risks

- **Walk volumetry** (Med): re-evaluating the whole ledger without
  `--max-setups` scans thousands of candles — flag + `(symbol, interval, time)`
  index bound it.
- **Ambiguous intra-candle** (Low): OHLC can't order SL vs TP in one candle;
  `ambiguous` counted as SL is the honest conservative choice.
- **Guards** (Low): resolver must stay stdlib-only (`test_boundary.py`),
  `SetupOutcome` outside `OWNED_MODELS` (`test_owned_model_guard.py`).

## Rollback Plan

Revert the cron service first (no new runs), then the command, the resolver,
and the model. Reversing the migration drops only `SetupOutcome`; `Setup` and
the engine are untouched. Never destructive: additive columns only, outcomes
are recomputable from `Candle` + `Setup` at any time.

## Dependencies

- Requires the setup ledger (#260, archived `2026-10-21-setup-ledger`): no
  `Setup` rows, nothing to evaluate.

## Success Criteria (#261)

- [ ] Setup touching TP before SL → `take_profit`, `mfe_r ≥ rr`.
- [ ] SL touched, then TP strictly later within horizon → `stop_loss`,
      `sl_then_tp=True`.
- [ ] Same candle touches SL and TP → `ambiguous`, counted as SL, never TP.
- [ ] Entry never touched → `not_triggered`, MFE/MAE computed from anchor.
- [ ] Horizon exhausted without resolution → `expired`.
- [ ] Setup without full-horizon candles available is not evaluated.
- [ ] Re-running the command duplicates nothing; re-running with another
      `horizon_bars` recalculates without altering `Setup`.
- [ ] `--dry-run` writes nothing.
- [ ] Pure unit test of the resolver (no DB) covers the 5 states.
- [ ] Guards green: `test_boundary.py`, `test_no_order_surface.py`,
      `test_owned_model_guard.py`; `makemigrations --check` green.

## Changed-lines forecast

~220–260 lines. Single PR — `400-line budget risk: Low`.

`Decision needed before apply:` none — all 6 ambiguities resolved above.
`Chained PRs recommended:` no.
