# Tasks: smc-structure (issue #73, Fase B1)

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Medium

## Guard/Edge Matrix

- [ ] `PURE_MODULES` in `tests/test_boundary.py` gains `"smc/config.py"`, `"smc/swings.py"`, `"smc/structure.py"` (blind-spot guard — else stdlib-only check is blind to them)
- [ ] strict inequality: equal/plateau highs (and lows) → NO pivot
- [ ] no-look-ahead: trailing `right` bars can never emit a pivot (`range(left, n-right)`)
- [ ] never-raise: empty / `len(highs)!=len(lows)` / `left<0` / `right<0` / `<1` swing → `[]`
- [ ] determinism + non-mutation: run twice → equal; inputs unchanged
- [ ] R7 no re-fire: `armed_*=False` consumes the level; re-arms only on a NEW swing confirm
- [ ] seeding silently: no trend → first break sets trend, emits NO event
- [ ] CHoCH requires established trend (`none` only seeds); labels inform, never gate
- [ ] close-vs-wick: default `use_close=True`; wick-only break when `False`
- [ ] `find_structure` needs ≥1 confirmed high AND ≥1 confirmed low else `[]`
- [ ] read-only: no order verb/path, stdlib only, `requirements.txt` + `src/` boundary unchanged
- [ ] patch 100%; ruff `check` + `format --check` green

## WU1 — Pure core `src/smc/` (SINGLE PR, base `main`)

Rollback: delete `src/smc/` + `tests/test_smc_{swings,structure}.py`; revert `PURE_MODULES` (pure additive, inert until B2/C1 import).

- [ ] 1.1 **RED** `tests/test_smc_swings.py`: literal `highs`/`lows`, pivots `[("high",1,3.0),("high",3,4.0)]`; tie index excluded; `left=0`/`right=0` immediate-neighbour; trailing local max absent; empty/mismatched/negative → `[]`; ascending order; no mutation. Acceptance: fails before 1.3.
- [ ] 1.2 **GREEN** `src/smc/__init__.py` (empty) + `src/smc/config.py`: `SWING_LEFT=2`, `SWING_RIGHT=2`, `USE_CLOSE=True`. Acceptance: importable, constants read.
- [ ] 1.3 **GREEN** `src/smc/swings.py`: `Swing(kind,index,price)` NamedTuple + `find_swings(highs,lows,*,left=SWING_LEFT,right=SWING_RIGHT)` per design scan (strict `>`, `range(left,n-right)`, sort `(index,high-first)`). Acceptance: 1.1 green.
- [ ] 1.4 **RED** `tests/test_smc_structure.py` + tiny OHLC fixture helper: bull BOS chain (`bos/bullish`), bear BOS (`bos/bearish`), bearish+bullish CHoCH, silent seed, close-inside/wick-beyond (R5 close-vs-wick), labels `HH/HL/LH/LL` (first-of-kind omitted), `trend_state` `up/down/range/None`, no re-fire (R7 level advance), repeat+inputs unchanged. Acceptance: fails before 1.5.
- [ ] 1.5 **GREEN** `src/smc/structure.py`: `LabeledSwing(kind,index,price,label)`, `StructureEvent(kind,index,price,direction,trend)`, `label_swings`, `trend_state(labeled)`, `find_structure(highs,lows,closes,*,left,right,use_close)` frozen state machine (seed/no-event; `armed_*` consume; R7 level update). Acceptance: 1.4 green.
- [ ] 1.6 **REFACTOR** ruff clean; factor fixture helper if duplicated. Acceptance: WU1 tests green, patch 100%.

## WU2 — Boundary registration

- [ ] 2.1 **RED/GREEN** `tests/test_boundary.py`: `PURE_MODULES += ("smc/config.py","smc/swings.py","smc/structure.py")`. Acceptance: `test_pure_modules_are_stdlib_only` green; negative-control fixture still flags a violation.

## Phase 3 — Verification

- [ ] 3.1 `python -m pytest` green; `diff-cover --fail-under=100` on changed lines.
- [ ] 3.2 `ruff check . && ruff format --check .` green; no new dependency; `requirements.txt` unchanged; order scanner clean.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~385 (src/smc ≈130, tests ≈250, boundary +3) |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Single PR (pure internal logic, no user-visible behavior) |
| Delivery strategy | single-pr |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Medium
