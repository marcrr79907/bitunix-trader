# Tasks: setup-outcomes

Strict TDD: each RED task writes its failing assertion first. `[S1]`/`[S2]` = slice. `(n)` = changed lines.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 565 (S1 345 + S2 220) |
| 400-line budget risk | S1 Medium, S2 Low (each slice under budget) |
| Chained PRs recommended | Yes |
| Suggested split | PR A = Slice 1, PR B = Slice 2 stacked on A, PR C → develop |

Decision needed before apply: No (resolved: feature-branch-chain)
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | PR | Base |
|------|------|----|------|
| A | Pure resolver + model + `0019` | PR A | `develop` @ 23a160c |
| B | Command + cron docs | PR B | `feat/setup-outcomes` (stacked) |
| Final | Full chain → `develop` | PR C | `develop` |

Chain mechanics (as #264→#265→#266): `feat/setup-outcomes` off `develop`; `feat/setup-outcomes-command` stacked on it — PR B diff must show only S2 (retarget/rebase if not). After both green, PR C merges `feat/setup-outcomes` into `develop`. Never `gh pr merge --delete-branch` mid-chain.

## Phase 1: Pure resolver — Slice 1

- [x] 1.1 `[S1]` RED: `tests/test_smc_outcomes.py` DB-free table-driven — 5 statuses, same-candle SL+TP → ambiguous (never TP), `sl_then_tp` strictly-after True/False/NULL, R=0 → NULL guards, long/short MFE/MAE sign formulas, `bars_to_resolution` 0/M/NULL from activation, mae_r clamp ≤ 0, determinism (130)
- [x] 1.2 `[S1]` GREEN: `OutcomeRecord` NamedTuple + `resolve_setup(direction, entry, stop, take_profit, candles, *, horizon_bars=200)` in `src/smc/signals.py`; stdlib-only, never raises, empty candles → not_triggered (75)
- [x] 1.3 `[S1]` `test_boundary.py` green, NO edit (`smc/signals.py` already in `PURE_MODULES`) (0)

## Phase 2: Model + migration — Slice 1

- [x] 2.1 `[S1]` RED: `tests/web/test_setup_outcomes_model.py` — global (no `user`, absent from `OWNED_MODELS`, AST pattern of `test_setups_model.py`), OneToOne `related_name="outcome"`, field types via `get_internal_type`, migration AST (one `CreateModel`, no alter/delete, depends on `0018`), leaf `>= "0019"` (70)
- [x] 2.2 `[S1]` GREEN: `SetupOutcome` in `web/trading/models.py` — plain `models.Model`, CASCADE, `evaluated_at` auto_now (30)
- [x] 2.3 `[S1]` GREEN: verify leaf is `0018_setup`, then `makemigrations trading` → `web/trading/migrations/0019_setupoutcome.py`; `makemigrations --check` green (40)
- [x] 2.4 `[S1]` Gate: `ruff check .`, `ruff format --check .`, `python -m pytest` full, patch coverage 100% (0)

## Phase 3: Command + docs — Slice 2

- [x] 3.1 `[S2]` RED: `tests/web/test_evaluate_setups.py` — direct `run()` with seeded `Candle` rows (`OutRecorder` pattern): full-horizon gate skips, evaluates when `now` advances; anchor-ascending order; `--interval` filter and absent → all; `--max-setups`; `--dry-run` writes nothing; idempotent re-run, other-horizon recalc (Setup byte-identical); injected `now`; `out` called; `engine_version` stamp copied verbatim (130)
- [x] 3.2 `[S2]` GREEN: `web/trading/management/commands/evaluate_setups.py` — module-level `run(now, interval, horizon_bars, max_setups, dry_run, out) -> int`; `handle` parses flags, reads wall clock once; `Setup.objects.order_by("anchor_time", "id")`; gate `anchor_time + horizon_bars × INTERVAL_SECONDS[interval] ≤ now`; candles `filter(time__gt=).order_by("time")[:horizon_bars]`; `update_or_create(setup=…)` (85)
- [x] 3.3 `[S2]` one `call_command` wiring test + `docs/deployment.md`: `cron-evaluate` hourly row + third dashboard service, same env rules (6)
- [x] 3.4 `[S2]` Gate: `ruff check .`, `ruff format --check .`, `python -m pytest` full, patch coverage 100%; `test_no_order_surface.py` + `test_owned_model_guard.py` green unedited (0)

## Phase 4: Close-out

- [x] 4.1 PR B → PR A's branch (stacked), CI green; PR C from `feat/setup-outcomes` → `develop`; verify tree equality (merge diff == validated diff) (0)
- [x] 4.2 Close #261 (acceptance criteria ↔ R1–R9); OpenSpec archive + canonical spec sync (sdd-archive) (0)
- [x] 4.3 Branch cleanup AFTER chain lands: delete `feat/setup-outcomes-command`, then `feat/setup-outcomes`; no `--delete-branch` on stacked chains (0)

## Verification Checklist (R1–R9 ↔ #261)

R1 global model + additive `0019` / R2 five statuses, ambiguous-as-SL, `resolved_time` / R3 activation, `bars_to_resolution` 0/M/NULL / R4 MFE/MAE signs, clamp, R=0 NULL / R5 `sl_then_tp` strict-after, NULL elsewhere / R6 full-horizon gate, `now` injected once / R7 `run()` seam, idempotent, flags, dry-run / R8 stamp verbatim across re-runs / R9 purity DB-free 5-state + guards green.

## Rollback

Additive only. Revert cron service first (no new runs), then command file, resolver, model. Reversing `0019` drops only `setup_outcomes` (`Setup`/`Candle`/engine untouched); outcomes recomputable from `Candle` + `Setup`. Docs: revert one table row.
