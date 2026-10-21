# Archive Report: setup-outcomes

**Change**: `setup-outcomes` (issue **#261** — second link of the measurable-baseline chain)
**Archived**: 2026-10-21
**Delivered on**: `develop` at `600be90` via PR #270, closing a three-PR chain (#267 resolver → #268 model → #269 command, merged as e6363f7 / 6769536 / 600be90)
**Verdict**: PASS WITH WARNINGS — 0 CRITICAL; R1–R9 9/9 COMPLIANT; 24/24 scenarios with passing covering tests; 10/10 acceptance criteria with named tests
**Closure**: issue #261 CLOSED; PR feature branches already deleted (remote + local)

## What shipped

A global `SetupOutcome` model (`web/trading/models.py`, OneToOne to `Setup`,
additive migration `0019`), a pure stdlib-only resolver
(`resolve_setup` + `OutcomeRecord` in `src/smc/signals.py`, registered in
`PURE_MODULES`), and the `evaluate_setups` management command (module-level
`run()` seam with injected `now`, full-horizon gating, idempotent
`update_or_create`, flags `--interval` / `--horizon-bars` / `--max-setups` /
`--dry-run`) documented as the `cron-evaluate` hourly service in
`docs/deployment.md`. `Setup` and the SMC engine untouched; zero network; no
order surface.

| Task | Status | Delivered |
|---|---|---|
| 1.1–1.3 | ✅ | DB-free resolver tests (5 statuses, ambiguous-as-SL, `sl_then_tp` strictly-after, R=0 NULL guards, MFE/MAE sign formulas, determinism); `resolve_setup` pure in `smc/signals.py`; `test_boundary.py` green unedited |
| 2.1–2.4 | ✅ | Global `SetupOutcome` (no `user`, outside `OWNED_MODELS`), OneToOne `related_name="outcome"`; additive `0019_setupoutcome` (depends `0018`); leaf test `>= "0019"` |
| 3.1–3.4 | ✅ | `evaluate_setups` `run()` seam (42/42 stmts = 100% coverage) + 14 command tests + `call_command` wiring; `cron-evaluate` hourly row |
| 4.1–4.3 | ✅ | Chain PRs merged (#267 → #268 → #269 → PR C #270 at `600be90`); issue #261 closed; archive + canonical sync (this report) |

## Specs synced

| Canonical spec | Action |
|---|---|
| `openspec/specs/smc-setup-outcomes/spec.md` | **CREATED** (9 requirements R1–R9, 24 scenarios) |

No destructive deltas: the change declared only `ADDED` requirements and
modified no existing capability, so no other canonical spec was touched
(`smc-signals`, `smc-setup-ledger` unchanged).

## Verification evidence

| Gate | Result |
|---|---|
| Targeted suite (996 tests: `tests/web`, `test_smc_outcomes.py`, `test_smc_capture.py`, `test_boundary.py`) | all green, exit 0 (log sha256 `3206bd3a…`) |
| Guards batch | `test_no_order_surface.py` + `test_owned_model_guard.py` + `test_health.py` → 64 passed |
| Secrets/dependency gates | `test_no_secrets.py` + `test_dependency_guard.py` → 8 passed |
| Build | `ruff check .` clean; `ruff format --check .` 175 files formatted; `makemigrations --check --dry-run` → "No changes detected"; trading leaf = `0019` |
| Coverage | `evaluate_setups.py` 100%; resolver patch region (`smc/signals.py` 213–325) 100% |

Resolver hand-walk (verify phase): activation = first touch of entry;
resolution scan starts AT activation (same-candle resolve, bars 0);
`ambiguous` checked BEFORE stop/TP (conservative precedence); `bars_to_resolution`
from activation, not anchor; `sl_then_tp` strictly after resolution candle;
R=0 guards both excursions and `sl_then_tp`; `mae_r` clamp only for
`not_triggered`; no look-ahead.

## Accepted warnings (documented in the verify report)

- Tasks.md Phase 3 checkboxes were stale (unticked despite green); already
  corrected in the working tree after verify.
- No formal RED/GREEN TDD-cycle table for Slice 1 in Engram; mitigated — every
  RED-written test file exists and passes at runtime.

## Verify suggestions (informational, follow-ups)

1. `smc/signals.py:259` — invalid `direction` silently resolves as short
   (accepted: never-raise contract; `Setup.direction ∈ {long, short}`).
2. `evaluate_setups.py:58` — `--max-setups` slices before the horizon gate; M
   ineligible head setups consume the budget (matches design D4; cron catches
   up next hour).
3. Aggregation rule "ambiguous counts as loss" documented but no guard test
   pins future aggregators — add one with the first aggregation consumer.

## Follow-ups

- **#262 — ATR stop floor**; **#263 — `/setups/` screen** (can now read
  outcomes for the user-facing view).
- First aggregation consumer adds the ambiguous-as-loss guard test.
