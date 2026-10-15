# Tasks: validator-spec-cleanups

DOCS-ONLY (issue #147, DEBT-6). 0 code, 0 tests. Deliverable = the 4 delta specs.

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

## Guard/Edge Matrix (no code touched; no behavior change)

- [ ] `git diff origin/develop -- web/ src/` prints NOTHING (the no-behavior-change proof)
- [ ] No edit under `openspec/changes/archive/**` (immutable audit trail)
- [ ] No edit under `openspec/specs/**` until archive (canonical merge only at archive)
- [ ] Delta edits are canonical-spec clarifications only (W1–W4)
- [ ] No new 400 / no `quotes.py` change (DOCUMENT option, per proposal)
- [ ] `git diff --stat` confined to `openspec/changes/validator-spec-cleanups/**`

## Phase 1 — Delta specs (done in spec phase)

- [x] 1.1 `specs/chart-config/spec.md` R2 accept-and-ignore clause + 3 scenarios (W3/W4).
- [x] 1.2 `specs/smc-range/spec.md` R2 `None`→`"equilibrium"` + edge-matrix row (W2).
- [x] 1.3 `specs/alert-rules/spec.md` R2 explicit `direction` required note (W1).
- [x] 1.4 `specs/smc-zones/spec.md` R4 confirmed-swings ≤2-bar look-ahead note + edge row (W4).

## Phase 2 — Verification (gates)

- [ ] 2.1 `git diff origin/develop -- web/ src/` EMPTY → prove no behavior change.
- [ ] 2.2 `python -m pytest` green (e2e deselected per `addopts`).
- [ ] 2.3 `node --test "tests/js/**/*.test.js"` green.
- [ ] 2.4 `ruff check . && ruff format --check .` green.
- [ ] 2.5 Confirm `git diff --stat` touches only the change folder; archive untouched.
- [ ] 2.6 **Rollback**: revert the branch — 4 spec files return to prior text.

## Phase 3 — Archive

- [ ] 3.1 Merge the 4 deltas into `openspec/specs/{domain}/spec.md` (canonical).
- [ ] 3.2 Move `openspec/changes/validator-spec-cleanups/` → `archive/2026-10-14-validator-spec-cleanups/`.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~40–80 doc lines (0 code) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | single-pr |

### Suggested Work Units

| Unit | Goal | Likely PR |
|------|------|-----------|
| 1 | 4 delta specs + archive (docs only) | PR 1 |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low
