# Archive Report: smc-structure

**Archived**: 2026-10-12
**Verdict**: PASS (0 blockers, 0 criticals) — 11 new requirements / 15 scenarios; `core-domain-boundary` R11 delta
**Delivery**: single PR #92 (`feat/smc-structure` → `develop`); **not chained**
**Feature commit**: `1a870ee` feat(smc): add pure swing and market-structure core
**Merged commit**: PR #92 merge `6a673d0` on `develop`
**Code diff vs pre-change**: 7 files, +557/−1 (excluding openspec) — `src/smc/{__init__,config,swings,structure}.py`, `tests/test_smc_{swings,structure}.py`, `tests/test_boundary.py`

## What Shipped

Fase B1 (issue #73): the second pure-module family after `src/indicators.py` —
a framework-free Smart Money Concepts core. No user-visible behavior, no Django,
no migration, no new dependency; inert until B2 (zones) / C1 (render) import it.

| Area | Delivered |
|------|-----------|
| Records | `src/smc/swings.py`: `Swing(kind,index,price)`; `src/smc/structure.py`: `LabeledSwing(kind,index,price,label)`, `StructureEvent(kind,index,price,direction,trend)` — stdlib `NamedTuple`, no classes beyond. |
| Swings | `find_swings(highs, lows, *, left=SWING_LEFT, right=SWING_RIGHT)` — strict fractal pivots (`range(left, n-right)`; trailing `right` bars never emitted, no look-ahead; sort `(index, high-first)`). |
| Structure | `label_swings` (HH/HL/LH/LL, first-of-kind omitted), `trend_state(labeled) -> list[str\|None]` (`up`/`down`/`range`), `find_structure(highs, lows, closes, *, left, right, use_close)` frozen event state machine (BOS/CHoCH; silent seed; `armed_*` consume; R7 level update). |
| Config | `src/smc/config.py`: `SWING_LEFT=2`, `SWING_RIGHT=2`, `USE_CLOSE=True` — plain constants imported as function defaults (mirrors `src/config.py`; no class). |
| Boundary | `tests/test_boundary.py` `PURE_MODULES` += `"smc/config.py"`, `"smc/swings.py"`, `"smc/structure.py"`. |
| Tests | `tests/test_smc_swings.py`, `tests/test_smc_structure.py` — bull/bear BOS/CHoCH + edge battery. |

## Verify Findings

Verdict `pass` (verify-report.md): 576 passed / 0 fail; focused suite green (38);
`ruff check` + `ruff format --check` clean; `requirements.txt` diff empty;
patch gate 100% (115 changed lines, 0 missing); `src/smc/` imports stdlib +
intra-package only. Adversarial probes confirmed strict pivots, no-look-ahead,
trend flips, determinism, non-mutation.

### Warnings carried (non-blocking)

- **W1 — `LabeledSwing`/`trend_state` are the frozen public seam.** Not yet
  consumed by `find_structure`; they are the interface for B2 (zones/signals) and
  C1 (render). Intentional, not dead code — do not prune before B2/C1 land.
- **W2 — CHoCH tie-breaking is per-design.** `break_up` wins an equal-index
  high+low break; deterministic but not independently spec'd. Recorded, not a
  defect.
- **W3 — Spec reconciled to the frozen contract.** The change spec was corrected
  because the initial draft diverged from proposal/design. Exact reconciliations:
  1. Record `kind` literals lowercased: `"high"/"low"` and `"bos"/"choch"`
     (draft used `"BOS"/"CHoCH"`).
  2. Record field order frozen as `(kind, index, price[, label|direction, trend])`.
  3. `StructureEvent` gained the trailing `trend` field (trend AFTER the event).
  4. `trend_state` input frozen as `trend_state(labeled)` (pure fold over
     `LabeledSwing`), not `(highs, lows, closes, …)`.
  5. `find_structure` signature frozen as `find_structure(highs, lows, closes, *,
     left, right, use_close)` — positional `closes` required by R5 close-vs-wick.
  Design Open Questions marked RESOLVED accordingly.
- **W4 — Full suite is slow** (~5m20s locally, test-client + SQLite); a short tool
  timeout reads as a "hang" but all tests pass. Not a defect.
- **SUGGESTION — `tasks.md` checkboxes unmarked.** Apply left WU1/WU2 checkboxes
  unmarked (orchestrator hard contract); `tasks.md` is not the completion source.

## Requirement Outcomes

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| smc-structure (new) | R1 fractal swing detection | ✅ strict `>`/`<`; equal excluded; trailing `right` bars never emitted |
| smc-structure (new) | R2 swing output shape/ordering | ✅ `list[Swing]`, ascending index, no `confirmed` flag |
| smc-structure (new) | R3 swing labeling | ✅ `LabeledSwing(kind,index,price,label)`; first-of-kind omitted |
| smc-structure (new) | R4 trend state | ✅ `trend_state(labeled)`; `up`/`down`/`range`/`None` |
| smc-structure (new) | R5 BOS events | ✅ `kind="bos"`; close (or wick) beyond active swing; `use_close` toggles |
| smc-structure (new) | R6 CHoCH events | ✅ `kind="choch"` on first break against trend; flips; requires trend |
| smc-structure (new) | R7 active-level update | ✅ level re-arms; same break does not re-fire (W2) |
| smc-structure (new) | R8 seeding rule | ✅ first break seeds silently; ≥1 high AND ≥1 low required |
| smc-structure (new) | R9 determinism/purity | ✅ repeatable, non-mutating, no time/random/I/O |
| smc-structure (new) | R10 framework-free boundary | ✅ package + stdlib-only; `PURE_MODULES` registration |
| smc-structure (new) | R11 edge/error handling | ✅ empty/short/mismatched → `[]`, never raise |
| core-domain-boundary | R11 smc package joins inventory | ✅ `src/smc/` stdlib-only, importable without Django, registered in `PURE_MODULES` |

## Gates

`python -m pytest tests/` 576 passed (0 fail); focused smc+boundary suite 38
passed; `ruff check` + `ruff format --check` clean (112 files);
`diff-cover` patch gate 100% (115 changed lines, 0 missing); `requirements.txt`
unchanged; `src/smc/` boundary + order-scanner green.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| smc-structure | Created | New capability — R1–R11 (15 scenarios) copied verbatim from the change spec |
| core-domain-boundary | Updated | + R11 (3 scenarios); R9/R10 preserved untouched |

## Carry-forward

- None blocking.
- W1: `LabeledSwing`/`trend_state` are the frozen seam — B2 and C1 consume this
  shape; do not change it without a new change.
- W2: CHoCH tie-breaking stays per-design unless a future change specifies it.
- W4: keep the full suite in mind for timeouts; local run prefers `-p no:randomly`.

## SDD Cycle Complete

Planned → implemented (single PR #92, `1a870ee`) → verified (`pass`; no
CRITICAL/BLOCKER) → merged (`6a673d0`) → archived.

Traceability: `openspec/changes/archive/2026-10-12-smc-structure/`
(explore, proposal, design, specs, tasks, verify-report); engram
`sdd/smc-structure/{archive-report,proposal,spec,design,tasks,verify-report}`.
