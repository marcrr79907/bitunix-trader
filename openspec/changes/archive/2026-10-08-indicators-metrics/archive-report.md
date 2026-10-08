# Archive Report: indicators-metrics

**Archived**: 2026-10-08
**Verdict**: PASS WITH WARNINGS (0 blockers, 0 critical) — 19/20 requirements, 36/38 scenarios, 133/133 tests (131 at verify + 2 boundary-hardening tests added before merge)
**Delivery**: 3 chained PR slices (#25 → #26 → #27) → tracker #24 → `develop`
**Merged commit range**: `3982b47`…`ba56f9c` on `develop`

## What Shipped

Phase 1 pure domain math: deterministic, I/O-free indicator and trade-metric
modules under `src/`, plus a CI patch-coverage gate. Read-only invariant held —
no network, no order endpoints, no Django in `src/`. `journal.metrics()` untouched.

| Area | Delivered |
|------|-----------|
| Indicators | `src/indicators.py` — `sma`, `ema`, `rsi` (Wilder), `atr` (Wilder), `vwap`, `zscore`, stdlib only |
| Metrics | `src/metrics.py` — `expectancy`, `profit_factor`, `r_multiple`, `equity_curve`, stdlib only |
| Tests | `tests/test_indicators.py` (40), `tests/test_metrics.py` (16) — Strict TDD; boundary suite hardened |
| Coverage config | `pyproject.toml`: `source = ["web", "src"]`; global `fail_under` removed; `omit` kept |
| Patch gate | `.github/workflows/ci.yml`: `fetch-depth: 0`, xml report, `diff-cover --fail-under=100` vs `origin/develop` |
| Web gate | Preserved separate step: `coverage report --include="web/*" --fail-under=85` |
| Dev deps | `requirements-dev.txt`: `diff-cover>=9.0` (dev-only; absent from runtime) |

## Requirement Outcomes

| Req | Domain | Outcome | Notes |
|-----|--------|---------|-------|
| R1 | technical-indicators | ✅ Green | 6 pure functions; no I/O, no mutation |
| R2 | technical-indicators | ✅ Green | Same-length output, documented leading `None` warm-up |
| R3 | technical-indicators | ✅ Green | Empty in → empty out, never raises |
| R4 | technical-indicators | ✅ Green | Div-by-zero / zero-range guards → `None` |
| R5 | technical-indicators | ✅ Green | RSI in `[0,100]`; ATR non-negative |
| R6 | technical-indicators | ✅ Green | VWAP typical price `(h+l+c)/3`, cumulative |
| R7 | technical-indicators | ✅ Green | Rolling z-score, `window=n` = full series |
| R8 | technical-indicators | ⚠️ Partial | Code stdlib-only; guard now enforced by hardened `test_boundary.py` (fix landed) |
| R1 | trade-metrics | ✅ Green | 4 pure functions; no I/O, no mutation |
| R2 | trade-metrics | ✅ Green | Expectancy = mean PnL; empty → `None` |
| R3 | trade-metrics | ✅ Green | Profit factor; `gross_loss==0` → `None` |
| R4 | trade-metrics | ✅ Green | R-multiple; `risk==0` → `None` |
| R5 | trade-metrics | ✅ Green | Equity curve running sum; timestamp-agnostic |
| R6 | trade-metrics | ⚠️ Partial | `journal.py` diff empty + AST proven; no runtime test |
| R7 | trade-metrics | ✅ Green | Stdlib-only boundary |
| R1 | patch-coverage-gate | ✅ Green | `diff-cover` 100% on changed lines; fail path verified (18% → exit 1) |
| R2 | patch-coverage-gate | ✅ Green | `fetch-depth: 0`; `origin/develop` refspec source-verified |
| R3 | patch-coverage-gate | ✅ Green | Source spans `web` + `src`; no global `fail_under` |
| R4 | patch-coverage-gate | ✅ Green | Web gate preserved; 92% ≥ 85% |
| R5 | patch-coverage-gate | ✅ Green | `diff-cover` dev-only; no new runtime dep |

**Legend**: ✅ green · ⚠️ partial (test-coverage gap, invariant holds).

## Carry-Forward Items

1. **R8 banned-import guard** — the verify WARNING 1 (scanner only checked Django)
   was **fixed within this change**: `tests/test_boundary.py` now enforces
   stdlib-only imports for `indicators.py`/`metrics.py` via
   `sys.stdlib_module_names` (`11afd7a`). No carry-forward remains.
2. **No dedicated determinism test** — both specs' "called twice → equal" scenario
   is structurally guaranteed and probe-verified, but has no committed test.
3. **No runtime test for `journal.metrics()` unchanged (R6)** — proven statically
   (`journal.py` diff empty; `metrics.py` imports no `sqlite3`/`src.journal`/`src.db`).
4. **`atr`/`vwap` mismatched-length inputs raise `IndexError`** — outside the
   documented equal-length OHLCV contract; a defensive length check or docstring
   note would avoid a future footgun.

## Verify Findings (non-blocking, fix before the noted trigger)

| # | Severity | Finding | Fix trigger |
|---|----------|---------|-------------|
| 1 | Medium | R8 banned-import guard only scanned Django (`test_boundary.py`) | ✅ **Fixed in this change** — `11afd7a` enforces stdlib-only for pure modules |
| 2 | Low | WU2 (3.1–3.8) / Phase 4 (4.1–4.3) task checkboxes left `[ ]` despite completed, verified work | ✅ **Fixed at archive** — boxes checked in the archived `tasks.md` (cosmetic; verified present in tree) |
| S1 | Suggestion | Patch gate hardcodes `origin/develop`, ignoring `github.base_ref` — intentional and correct for the PR→develop flow | Opportunistic; use `origin/${{ github.base_ref }}` if the chain later targets a release branch |
| S2 | Suggestion | No dedicated repeat-call determinism test | Opportunistic |
| S3 | Suggestion | `apply-progress` test count stale (128 vs actual 133) | Opportunistic — artifact only |
| S4 | Suggestion | No runtime test asserting `journal.metrics()` unchanged (R6) | Opportunistic |
| S5 | Suggestion | `atr`/`vwap` index by `len(closes)`; mismatched inputs raise `IndexError` | Opportunistic — docstring note or length guard |

## SDD Cycle Complete

Planned → implemented → verified → archived. Delta specs merged into the main spec store:

- `openspec/specs/technical-indicators/spec.md`
- `openspec/specs/trade-metrics/spec.md`
- `openspec/specs/patch-coverage-gate/spec.md`

Archive audit trail: `openspec/changes/archive/2026-10-08-indicators-metrics/`
(proposal, design, specs, tasks, verify-report).

## Traceability — Engram Observation IDs

| Artifact | Observation ID |
|----------|----------------|
| `sdd/indicators-metrics/proposal` | 1313 |
| `sdd/indicators-metrics/design` | 1315 |
| `sdd/indicators-metrics/spec` | 1314 |
| `sdd/indicators-metrics/tasks` | 1316 |
| `sdd/indicators-metrics/apply-progress` | 1317 |
| `sdd/indicators-metrics/verify-report` | 1320 |
| `sdd/indicators-metrics/prs` | 1321 |

Merged specs have no standalone Engram observations — they live in the OpenSpec
file store (both delta and merged main spec).
