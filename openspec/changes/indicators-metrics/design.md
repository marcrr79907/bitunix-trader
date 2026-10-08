# Design: indicators-metrics

## Technical Approach

Two deep, pure, framework-free modules: lists in, lists/numbers out, no I/O, deterministic, stdlib only. `src/indicators.py` = index-aligned chart math; `src/metrics.py` = pure PnL math over caller sequences; the interface is the test surface (Strict TDD). **No Django app boundary or per-user data ownership applies** — no rows owned, read-only (no network, no `Client`, no order endpoints). `journal.metrics()` untouched (SQLite accounting).

## Algorithm Decisions

| # | Function | Formula | Warm-up | Undefined → `None` |
|---|----------|---------|---------|--------------------|
| A1 | `sma(s,w)` | mean of trailing window | `w-1` | `w < 1` |
| A2 | `ema(s,w)` | seed=`sma` at `w-1`; `k=2/(w+1)`; `prev+k*(s[i]-prev)` | `w-1` | `w < 1` |
| A3 | `rsi(s,w)` | **Wilder**: first `avg_gain/loss` = mean of first `w` deltas (idx `w`); then `avg=(prev*(w-1)+cur)/w`; `100-100/(1+gain/loss)` | `w` | `w < 1`, `avg_loss==0` |
| A4 | `atr(h,l,c,w)` | `tr=max(h-l, abs(h-c[-1]), abs(l-c[-1]))`; first `atr[w]` = mean `tr[1..w]`; then Wilder | `w` | `w < 1` |
| A5 | `vwap(h,l,c,v)` | `cumsum(tp*v)/cumsum(v)`, `tp=(h+l+c)/3` | `0` | `cum_volume==0` |
| A6 | `zscore(s,w)` | `(s[i]-mean)/pstdev` of window | `w-1` | `w < 1`, `pstdev==0` |

**Wilder (A3/A4)**: standard RSI/ATR; weights recent bars, converges to the same steady state, tracks charting libraries. Stdlib `statistics.fmean`/`pstdev` + `math`. `vwap` cumulative from bar 0. `w < 1` → all-`None` (spec names sma/ema/atr; extended to rsi/zscore).

## Guard Matrix (test matrix)

| Guard | Functions | Result |
|-------|-----------|--------|
| Empty | all indicators, `equity_curve` / `expectancy`, `profit_factor` | `[]` / `None` |
| `window < 1` | sma, ema, rsi, atr, zscore | all `None`, length kept |
| avg loss `==0` | rsi | `None` |
| `pstdev==0` | zscore | `None` |
| cumulative volume `==0` | vwap | `None` |
| `gross_loss==0` | profit_factor | `None` |
| `risk==0` | r_multiple | `None` |
| any length `n` | all series | output length `==n` |
| no mutation | all | input unchanged |

## ADRs

**(a) Same-length + `None` warm-up vs truncation.** Length always equals input; truncation shifts chart overlays and forces caller offset bookkeeping.

**(b) `None` vs `inf`/`nan`.** `inf`/`nan` are not JSON-serializable, cannot round-trip the API; `None` is explicit and testable, UI renders `—`/`∞`.

**(c) Patch/diff coverage vs per-module lists.** `diff-cover` gates changed lines at 100%; the 85% floor stays scoped to `web/*`. Per-module thresholds need a growing list and miss edited legacy lines.

**(d) `journal.metrics()` untouched vs refactor.** Untouched — SQLite accounting; refactoring the live CLI risks a working read-only surface for no gain.


## CI Wiring

`test` job: checkout gains `fetch-depth: 0` (R2; shallow = failure). Replace `pytest --cov` with `python -m pytest --cov --cov-report=xml`, then:

1. `coverage report --include="web/*" --fail-under=85` (R4).
2. `diff-cover coverage.xml --compare-branch=origin/develop --fail-under=100` (R1).

Web gate is a **separate step**: diff-cover only inspects changed lines and would let a PR erode `web/*` while covering new lines.

## Coverage Config

`pyproject.toml`: `source = ["web"]` → `["web", "src"]` (R3); remove `fail_under = 85` from `[tool.coverage.report]`; keep `omit`. Scoping 85% to `web/*` stops legacy `src/` diluting that gate; diff-cover protects new/edited `src` lines. `requirements-dev.txt`: + `diff-cover>=9.0` (R5, dev-only).

## Interfaces

```python
sma(series, window) -> list[float | None]
ema(series, window) -> list[float | None]
rsi(series, window) -> list[float | None]
atr(highs, lows, closes, window) -> list[float | None]
vwap(highs, lows, closes, volumes) -> list[float | None]
zscore(series, window) -> list[float | None]
expectancy(pnls) -> float | None
profit_factor(pnls) -> float | None
r_multiple(pnl, risk) -> float | None
equity_curve(pnls) -> list[float]
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/indicators.py` | Create | Six indicators |
| `src/metrics.py` | Create | Four metrics |
| `tests/test_indicators.py`, `tests/test_metrics.py` | Create | TDD suites |
| `pyproject.toml` | Modify | source += `src`; drop `fail_under` |
| `.github/workflows/ci.yml` | Modify | fetch-depth, xml, web gate, diff-cover |
| `requirements-dev.txt` | Modify | + `diff-cover>=9.0` |
| `src/journal.py` | Unchanged | `metrics()` untouched (ADR d) |

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | Every function + guard row | TDD, `python -m pytest` |
| Regression | `test_boundary.py`, 20 tests | Stay green |
| CI | diff-cover 100%, web 85%, ruff | Workflow steps |

## Boundary Note

Both modules import only `math`/`statistics` — no Django, `requests`, `rich`, `src.client`, `src.monitor`; no network or order calls. `tests/test_boundary.py` (AST scan) stays green. **No Django app boundaries or per-user ownership apply** — pure, read-only core concern. No migration.

## Task Breakdown Hint

~350–450 lines vs the 400 budget → **2 chained PRs** (ask-on-risk → chained): **PR1** both modules + tests (~330–380) targeting `feat/indicators-metrics`; **PR2** CI/coverage/requirements (~50). Math first, enforcement second.

## Open Questions

None blocking. Resolved: warm-up = leading `None`s; zscore rolling with `window=n` escape hatch; `equity_curve` timestamp-agnostic PnL list.