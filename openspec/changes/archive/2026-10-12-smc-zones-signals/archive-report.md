# Archive Report: smc-zones-signals

**Archived**: 2026-10-12
**Verdict**: `pass_with_warnings` (0 blockers, 0 criticals) — 13 new requirements / 34 scenarios across 3 new capabilities; `core-domain-boundary` R11 delta
**Delivery**: 3-slice Feature Branch Chain — PR #93 (zones) → #94 (range) → #95 (signals), each based on tracker `feat/smc-zones-signals`; tracker merged to `develop` via PR #96 (merge `3ec3ea2`)
**Feature commits**: `cd6da95` zones · `346fefb` range · `54f01d6` signals · `439f44e` FVG orientation fix
**Issue**: #74 (Fase B2)
**Code diff vs pre-change**: 9 files (src 4, tests 4, boundary 1) — `src/smc/{zones,range,signals}.py`, `src/smc/config.py` (+9 constants), `tests/smc_fixtures.py`, `tests/test_smc_{zones,range,signals}.py`, `tests/test_boundary.py` (`PURE_MODULES` += 3)

## What Shipped

Fase B2: the second pure SMC layer after B1 (`smc-structure`) — order blocks,
fair value gaps, EQH/EQL, liquidity sweeps, dealing range, and a confluence-gated
`Setup` derivation. No user-visible behavior, no Django, no migration, no new
dependency; inert until C1 (render) / E1 (calibration) import the frozen shapes.
Consumes the frozen B1 seam (`Swing`, `StructureEvent`) read-only; B1 unchanged.

| Area | Delivered |
|------|-----------|
| Zones | `src/smc/zones.py`: `OrderBlock(kind,index,top,bottom,anchor)`, `FVG(kind,index,top,bottom)`, `EqualLevel(kind,index,price,twin)`, `Sweep(kind,index,level,direction)` + `find_order_blocks` (BOS anchors only; most-recent opposite candle in `[max(0,t-lookback),t-1]`), `find_fvg` (3-candle rule, `top>=bottom`), `find_equal_highs_lows` (consecutive same-kind, tolerance), `find_liquidity_sweeps` (wick beyond + close back inside; most-recent qualifying per side per bar). |
| Range | `src/smc/range.py`: `DealingRange(high,low,equilibrium,index)`, `dealing_range` (fixed `RANGE_LOOKBACK`, `None` on empty/mismatched/`lookback<=0`), `classify_price` → `premium`/`discount`/`equilibrium`. |
| Signals | `src/smc/signals.py`: `Setup(direction,entry,stop,take_profit,rr,score,index)`, `find_setups` — latest `StructureEvent` → direction; equal-weight 0..4 confluence gated at `MIN_CONFLUENCE`; entry = OB proximal (FVG fallback); stop = distal ∓ `SL_BUFFER`; TP = range extreme if `rr>=MIN_RR` else `entry ± MIN_RR_TP_R*(entry-stop)`; R:R gate `MIN_RR`; `entry==stop` skipped. `Setup` is a proposal — never an order. |
| Config | `src/smc/config.py`: `OB_LOOKBACK=10`, `FVG_MIN_GAP=0.0`, `EQ_TOLERANCE=0.0`, `SWEEP_LOOKBACK=20`, `RANGE_LOOKBACK=50`, `SL_BUFFER=0.0`, `MIN_RR=2.0`, `MIN_CONFLUENCE=3`, `MIN_RR_TP_R=3.0` (9 constants, plain module-level, imported as defaults). |
| Boundary | `tests/test_boundary.py` `PURE_MODULES` += `"smc/zones.py"`, `"smc/range.py"`, `"smc/signals.py"`. |
| Tests | `tests/smc_fixtures.py` (synthetic OHLC + `mirror_ohlc`); `tests/test_smc_{zones,range,signals}.py` — bull/bear per rule + edge battery. |

## Verify Findings

Verdict `pass_with_warnings` (verify-report.md). L1: `python -m pytest tests/ --ignore=tests/web` → 219 passed; focused boundary/order-surface/dependency-guard 46 green; `ruff check` + `ruff format --check` clean (119 files); `requirements.txt` vs develop empty diff; `src/smc/*.py` imports stdlib + intra-package only. L2: `diff-cover --fail-under=100` → 100% (193 changed lines, 0 missing). L3 spec conformance: all 13 requirements satisfied; B1 seam frozen. Adversarial probes (OB long/short, FVG fallback both directions, gates, edges) confirmed coherent setup geometry.

### Warnings carried (non-blocking)

- **W1 — Real bug found and fixed at the root (documented).** Both the spec and design originally assigned the bullish FVG zone as `top=highs[i-1]`, `bottom=lows[i+1]`, but the bullish condition is `highs[i-1] < lows[i+1]`, so `top < bottom` — inverted. Slice 1 masked it with `abs(top-bottom) >= min_gap`; in Slice 3 the FVG fallback then produced `entry < stop` for a long (incoherent geometry) and one test **encoded** the bug. Fixed at the root in commit `439f44e`: `src/smc/zones.py` → `top=lows[i+1], bottom=highs[i-1]`; spec prose corrected to assert the `top >= bottom` invariant; design pseudo-code, fixture comment, and the two affected tests updated. Verified: both kinds satisfy `top >= bottom`; both directions produce coherent Setup geometry.
- **W2 — `classify_price(price, None)` → `"equilibrium"` is undocumented.** The spec omits the `None` case; the implementation degrades to `equilibrium` (neutral). Recorded, not a defect.
- **W3 — Structure confluence component is always 1.** Component (1) is tautological by construction (the candidate derives from the latest `StructureEvent`). Intentional for v1; E1 may tighten it.
- **W4 — Sweep look-ahead nuance.** Sweeps consume confirmed B1 swings (which already exclude unconfirmed trailing pivots) without an extra `index+right<=t` guard; ≤2-bar edge effect, documented simplification.
- **SUGGESTION — `tasks.md` checkboxes unmarked.** Apply left the boxes unmarked (orchestrator hard contract); engram `sdd/smc-zones-signals/apply-progress` is the completion source, not `tasks.md`.

## Requirement Outcomes

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| smc-zones (new) | R1 order blocks anchored on BOS | ✅ BOS-only anchors; most-recent opposite candle; CHoCH excluded; no-opposite → none |
| smc-zones (new) | R2 fair value gaps (3-candle) | ✅ `top>=bottom` after the 439f44e fix; `min_gap` gate; raw unfilled only |
| smc-zones (new) | R3 equal highs / equal lows | ✅ consecutive same-kind; `tolerance=0.0` exact only |
| smc-zones (new) | R4 liquidity sweeps | ✅ wick beyond + close back inside; most-recent per side per bar (W4) |
| smc-zones (new) | R5 determinism, purity, never-raise | ✅ pure, non-mutating; empty/short/mismatched → `[]` |
| smc-range (new) | R1 dealing range from fixed lookback | ✅ last-N window; `None` on empty/mismatched/`lookback<=0` |
| smc-range (new) | R2 premium / discount classification | ✅ `premium`/`discount`/`equilibrium`; `None` degrade (W2) |
| smc-range (new) | R3 determinism, purity, never-raise | ✅ repeatable, non-mutating |
| smc-signals (new) | R1 direction candidate | ✅ latest event → long/short; no event → `[]` |
| smc-signals (new) | R2 equal-weight confluence score | ✅ 0..4 gated at `MIN_CONFLUENCE`; component (1) always 1 (W3) |
| smc-signals (new) | R3 entry / stop / take-profit derivation | ✅ OB proximal entry (FVG fallback); `sl_buffer`; structural-else-fixed-R TP; R:R gate; `entry==stop` skipped |
| smc-signals (new) | R4 output shape and ordering | ✅ `list[Setup]` index-ordered; 7-tuple; proposal never an order |
| smc-signals (new) | R5 determinism, purity, never-raise | ✅ pure, non-mutating; empty/short/mismatched → `[]` |
| core-domain-boundary | R11 smc package joins inventory | ✅ 6 compute modules stdlib-only, importable without Django, registered in `PURE_MODULES` |

## Gates

`python -m pytest tests/ --ignore=tests/web` 219 passed; focused boundary + order-surface + dependency-guard 46 passed; `ruff check` + `ruff format --check` clean (119 files); `diff-cover` patch gate 100% (193 changed lines, 0 missing); `requirements.txt` unchanged; `src/smc/` boundary + order-scanner green.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| smc-zones | Created | New capability — R1–R5 (15 scenarios) from the change spec |
| smc-range | Created | New capability — R1–R3 (7 scenarios) from the change spec |
| smc-signals | Created | New capability — R1–R5 (12 scenarios) from the change spec |
| core-domain-boundary | Updated | R11 modified (inventory + `PURE_MODULES` = 6 compute modules, +1 scenario); R9/R10 preserved untouched |

## Carry-forward

- None blocking.
- W1: FVG orientation root-caused and fixed (`439f44e`); canonical `smc-zones` R2 now carries the `top>=bottom` invariant **and** the corrected scenario example (`top=11.0, bottom=10.0`).
- W2: `classify_price(price, None) == "equilibrium"` remains an undocumented neutral degrade; a future change may spec it explicitly.
- W3: confluence structure component stays tautological in v1; E1 may tighten.
- W4: sweep look-ahead ≤2-bar edge effect stays a documented simplification unless a future change adds the guard.
- B1 seam (`src/smc/{swings,structure}.py`) and B2 output shapes (`OrderBlock`/`FVG`/`EqualLevel`/`Sweep`/`DealingRange`/`Setup`) are the frozen seams C1/E1 consume — do not change without a new change.

## SDD Cycle Complete

Planned (explore/proposal/design/tasks) → implemented (3-slice chain PRs #93/#94/#95 → tracker #96) → verified (`pass_with_warnings`; no CRITICAL/BLOCKER) → merged (`3ec3ea2`) → archived.

Traceability: `openspec/changes/archive/2026-10-12-smc-zones-signals/` (explore, proposal, design, specs, tasks, verify-report); engram `sdd/smc-zones-signals/{archive-report,proposal,spec,design,tasks,verify-report}`.
