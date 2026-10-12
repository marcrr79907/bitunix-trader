# Tasks: smc-zones-signals (issue #74, Fase B2)

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

Chain: all slices base on tracker `feat/smc-zones-signals`; each later slice bases on the immediate previous slice branch; merge each to the tracker before branching the next. S1 `zones.py` ~410 · S2 `range.py` ~190 · S3 `signals.py` ~340.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~950 (src ~380, tests ~570, config +9, boundary +3) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | S1 zones → S2 range → S3 signals |
| Delivery strategy | ask-on-risk (chain pre-chosen) |
| Chain strategy | feature-branch-chain |

### Suggested Work Units

| Unit | Goal | Likely PR | Base boundary |
|------|------|-----------|---------------|
| 1 | `zones.py` OB/FVG/EQ/sweeps + tests + 4 constants + boundary entry | PR 1 | tracker |
| 2 | `range.py` range + premium/discount + tests + 1 constant + boundary entry | PR 2 | PR 1 branch |
| 3 | `signals.py` confluence → `Setup` + tests + 4 constants + boundary entry | PR 3 | PR 2 branch |

## Guard/Edge Matrix

- [ ] `PURE_MODULES` gains `smc/zones.py` (S1), `smc/range.py` (S2), `smc/signals.py` (S3) — else stdlib-only check stays blind.
- [ ] never-raise: empty/short/mismatched OHLC → `[]`; range empty/mismatched/`lookback<=0` → `None`.
- [ ] determinism + non-mutation: run twice → equal; inputs unchanged.
- [ ] OB anchors `kind=="bos"` ONLY; `choch` never anchors; doji skipped; no opposite candle → no `OrderBlock`.
- [ ] FVG `gap < min_gap` → no `FVG`; `<3` bars → `[]`; kinds mutually exclusive.
- [ ] EQH/EQL consecutive same-kind only; `tolerance=0.0` exact only.
- [ ] sweep: wick beyond + close back inside; ≤1 per side per bar; stale swing not sweepable.
- [ ] R:R gate: emit only when `score>=min_confluence` AND `rr>=min_rr`; `entry==stop` skipped; no OB and no FVG → no entry zone.
- [ ] no-order-surface: no order verb/path, no Django/`requests`/`src.client`; `requirements.txt` unchanged.
- [ ] B1 seam untouched: `src/smc/{config,swings,structure}.py` behavior identical; B2 imports read-only.
- [ ] patch 100%; ruff `check` + `format --check` green.

## Slice 1 — `src/smc/zones.py` (base: tracker)

Dep: none. Rollback: delete `zones.py` + `tests/test_smc_zones.py`; revert `PURE_MODULES` zones line; drop `OB_LOOKBACK`, `FVG_MIN_GAP`, `EQ_TOLERANCE`, `SWEEP_LOOKBACK`.

- [ ] 1.1 **RED** `tests/smc_fixtures.py` (synthetic OHLC + `mirror_ohlc`) + `tests/test_smc_zones.py`: bull+bear per rule + edges (no-opposite-candle, `choch` not anchor, gap`<`min_gap, non-pair, stale level, empty/short/mismatched → `[]`, order, non-mutation). Acceptance: fails before 1.3.
- [ ] 1.2 **GREEN** `config.py` += `OB_LOOKBACK=10`, `FVG_MIN_GAP=0.0`, `EQ_TOLERANCE=0.0`, `SWEEP_LOOKBACK=20`.
- [ ] 1.3 **GREEN** `zones.py`: `OrderBlock`/`FVG`/`EqualLevel`/`Sweep` + 4 finders per design pseudo-code (guards; sorted by `index`). Acceptance: 1.1 green.
- [ ] 1.4 **RED/GREEN** `test_boundary.py`: `PURE_MODULES += ("smc/zones.py",)`. Acceptance: stdlib-only test green; negative-control still flags.
- [ ] 1.5 **REFACTOR** ruff clean; factor duplicated fixtures. Acceptance: S1 green, patch 100%.

## Slice 2 — `src/smc/range.py` (base: S1 branch)

Dep: S1 (chain only; module consumes OHLC only). Rollback: delete `range.py` + `tests/test_smc_range.py`; revert `PURE_MODULES` range line; drop `RANGE_LOOKBACK`.

- [ ] 2.1 **RED** `tests/test_smc_range.py`: last-N window, truncation (smaller/larger `lookback`), flat market, empty/mismatched/`lookback<=0` → `None`, premium/discount/equilibrium at equality, purity. Acceptance: fails before 2.3.
- [ ] 2.2 **GREEN** `config.py` += `RANGE_LOOKBACK=50`.
- [ ] 2.3 **GREEN** `range.py`: `DealingRange`, `dealing_range`, `classify_price`. Acceptance: 2.1 green.
- [ ] 2.4 **RED/GREEN** `test_boundary.py`: `PURE_MODULES += ("smc/range.py",)`.
- [ ] 2.5 **REFACTOR** ruff clean. Acceptance: S2 green, patch 100%.

## Slice 3 — `src/smc/signals.py` (base: S2 branch; final wiring)

Dep: S1 `zones` + S2 `range`. Rollback: delete `signals.py` + `tests/test_smc_signals.py`; revert `PURE_MODULES` signals line; drop `SL_BUFFER`, `MIN_RR`, `MIN_CONFLUENCE`, `MIN_RR_TP_R`.

- [ ] 3.1 **RED** `tests/test_smc_signals.py` + full-confluence fixture: score 4/3/below-threshold, no-OB-no-FVG, structural TP clears gate, fixed-R fallback, `rr<min_rr`, `entry==stop`, `range_=None`, no event → `[]`, ordering, purity. Acceptance: fails before 3.3.
- [ ] 3.2 **GREEN** `config.py` += `SL_BUFFER=0.0`, `MIN_RR=2.0`, `MIN_CONFLUENCE=3`, `MIN_RR_TP_R=3.0` (see R1).
- [ ] 3.3 **GREEN** `signals.py`: `Setup(direction,entry,stop,take_profit,rr,score,index)` + `find_setups` (equal-weight 0..4, OB-proximal entry w/ FVG fallback, `sl_buffer`, structural-TP-else-fixed-R, R:R gate). Acceptance: 3.1 green.
- [ ] 3.4 **RED/GREEN** `test_boundary.py`: `PURE_MODULES += ("smc/signals.py",)`.
- [ ] 3.5 **FINAL WIRING/REFACTOR** no order surface; B1 seam unchanged; ruff clean. Acceptance: S3 green, patch 100%.

## Phase Verification (per slice + close)

- [ ] V.1 `python -m pytest` green; `diff-cover --fail-under=100` on changed lines.
- [ ] V.2 `ruff check . && ruff format --check .` green; no new dependency; `requirements.txt` unchanged; order scanner clean.
- [ ] V.3 bull AND bear fixtures hand-traced; `find_setups` emits only when `score>=min_confluence` and `rr>=min_rr`.

## Risks

- **R1** fallback-multiple name: spec prose `MIN_RR_MULTIPLE` vs design `MIN_RR_TP_R` — lock one at apply (recommend `MIN_RR_TP_R`); reconcile spec at archive.
- **R2** Slice 3 imports S1 & S2 — do not branch it before S2 merges to the tracker.
- **R3** fixture cross-triggering — assert exact lists, one helper per file.
- **R4** OB recency window `0 <= anchor - zone.index <= OB_LOOKBACK` — encode once, test boundary.
- **R5** sweep look-ahead: documented ≤2-bar edge effect (no extra `index+right<=t` guard); test the known simplification.
