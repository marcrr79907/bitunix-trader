# Tasks: indicators-metrics

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

## Guard Matrix (every row must appear in WU1 tests)

- [x] Empty → `[]` (indicators, `equity_curve`) / `None` (`expectancy`, `profit_factor`)
- [x] `window < 1` → all `None`, length kept (sma, ema, rsi, atr, zscore)
- [x] `avg_loss == 0` → `None` (rsi)
- [x] `pstdev == 0` → `None` (zscore)
- [x] `cum_volume == 0` → `None` (vwap)
- [x] `gross_loss == 0` → `None` (profit_factor)
- [x] `risk == 0` → `None` (r_multiple)
- [x] Output length `== n` for every series function
- [x] Input list unchanged for every function

## WU1 (PR1) — `src/indicators.py`, `src/metrics.py`, tests

Base `feat/indicators-metrics`. Strict TDD: RED → GREEN per function, stdlib only.

### Phase 1 — Indicators (`tests/test_indicators.py`)

- [x] 1.1 **RED** `sma`: `[1,2,3,4],3 → [None,None,2.0,3.0]`; empty → `[]`; `w<1` → all `None`; no mutation.
- [x] 1.2 **GREEN** `sma(series, window)` via `statistics.fmean`.
- [x] 1.3 **RED** `ema`: seed SMA at `w-1`; `k=2/(w+1)`; warm-up/empty/`w<1`/no mutation.
- [x] 1.4 **GREEN** `ema(series, window)`.
- [x] 1.5 **RED** `rsi` (Wilder): first idx `w`; rising → `None` (avg_loss=0); values in `[0,100]`.
- [x] 1.6 **GREEN** `rsi(series, window)`.
- [x] 1.7 **RED** `atr`: first idx `w`; TR uses prior close; non-negative; empty; `w<1`.
- [x] 1.8 **GREEN** `atr(highs, lows, closes, window)`.
- [x] 1.9 **RED** `vwap`: `h3 l1 c2 v10 → 2.0`; zero cum volume → `None`; empty.
- [x] 1.10 **GREEN** `vwap(highs, lows, closes, volumes)`.
- [x] 1.11 **RED** `zscore`: rolling; flat window → `None`; `window=n` whole series; empty; `w<1`.
- [x] 1.12 **GREEN** `zscore(series, window)`.
- [x] 1.13 **RED→GREEN** `test_no_mutation` over all six on a shared list.

### Phase 2 — Metrics (`tests/test_metrics.py`)

- [x] 2.1 **RED** `expectancy`: `[10,-5,5] → 3.333`; `[] → None`.
- [x] 2.2 **GREEN** `expectancy(pnls)`.
- [x] 2.3 **RED** `profit_factor`: `[10,-5,20] → 6.0`; no losses → `None`; `[] → None`.
- [x] 2.4 **GREEN** `profit_factor(pnls)`.
- [x] 2.5 **RED** `r_multiple`: `30,10 → 3.0`; `risk=0 → None` (no raise).
- [x] 2.6 **GREEN** `r_multiple(pnl, risk)`.
- [x] 2.7 **RED** `equity_curve`: `[5,-2,3] → [5,3,6]`; len kept; `[] → []`; no mutation.
- [x] 2.8 **GREEN** `equity_curve(pnls)`.
- [x] 2.9 **GREEN** boundary: only `math`/`statistics`; `test_boundary.py` + full suite + ruff green.
- [x] 2.10 **Rollback**: delete both modules + tests; `src/journal.py` and CLI untouched.

## WU2 (PR2) — CI patch-coverage gate + config

Base PR1 branch. Config-only; no new test needed.

- [x] 3.1 `ci.yml` test job: add `fetch-depth: 0` to checkout (merge-base vs `origin/develop`, R2).
- [x] 3.2 `ci.yml`: test run → `python -m pytest --cov --cov-report=xml`.
- [x] 3.3 `ci.yml`: add `coverage report --include="web/*" --fail-under=85` (web gate, R4).
- [x] 3.4 `ci.yml`: add `diff-cover coverage.xml --compare-branch=origin/develop --fail-under=100` (R1).
- [x] 3.5 `pyproject.toml`: `source = ["web", "src"]`; drop `fail_under`; keep `omit` (R3).
- [x] 3.6 `requirements-dev.txt`: add `diff-cover>=9.0` (dev-only, R5).
- [x] 3.7 Verify diff-cover ignores YAML/TOML diffs; if flagged, use `--ignore-errors`/exclude. `coverage.xml` must precede 3.4. Coverage sees `src/` only after 3.5, so PR2's config lines are exercised by PR1's covered src lines.
- [x] 3.8 **Rollback**: revert the three config files; PR1 modules stay tested.

## Phase 4 — Verification

- [x] 4.1 `python -m pytest` green; `test_boundary.py` + 20 existing tests green.
- [x] 4.2 `ruff check . && ruff format --check .` green.
- [x] 4.3 Web gate ≥85%; diff-cover 100%; no new runtime dep.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | WU1 ~330–380, WU2 ~50 → ~380–430 total |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR2 (PR2 targets PR1 branch) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |
| Tracker branch | `feat/indicators-metrics` → merges to `develop` |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium
