# Proposal: indicators-metrics

## Intent

Phase 1 adds the pure domain math the dashboard will consume. The core currently talks to the API and journals trades, but has no reusable indicators/metrics layer. Ship deterministic, I/O-free functions behind a small interface, unit-tested under Strict TDD.

## Scope

### In Scope
- `src/indicators.py`: `sma`, `ema`, `rsi`, `atr`, `vwap`, `zscore` (stdlib only).
- `src/metrics.py`: `expectancy`, `profit_factor`, `r_multiple`, `equity_curve`.
- `tests/test_indicators.py`, `tests/test_metrics.py` (tests first).
- CI patch-coverage gate: `diff-cover` over changed lines, threshold **100%**.
- Preserve web gate: `coverage report --include="web/*" --fail-under=85`.
- Coverage `source` spans `web` + `src`; CI checkout `fetch-depth: 0`; remove `fail_under = 85` from `[tool.coverage.report]`.

### Out of Scope
- Persisting market data, charts, JSON API, alerts, worker sync.
- Order automation (HARD invariant).
- Changing `src/journal.py` `metrics()` (untouched; see Approach).

## Capabilities

### New Capabilities
- `technical-indicators`: pure chart math (`sma`, `ema`, `rsi`, `atr`, `vwap`, `zscore`).
- `trade-metrics`: pure performance math (`expectancy`, `profit_factor`, `r_multiple`, `equity_curve`).
- `patch-coverage-gate`: CI fails when any changed line is uncovered.

### Modified Capabilities
- None. (`core-domain-boundary` is a constraint to satisfy, not alter.)

## Approach

Deep, pure modules: lists in, lists/numbers out, no I/O, deterministic. The small interface is the test surface; edge cases (empty input, divide-by-zero, warm-up) are explicit invariants. Stdlib `math` only — no new runtime deps.

**Reuse vs New**: REUSED UNCHANGED — all 7 `src/` modules, 20 tests, CLI, `journal.metrics()`. NEW — `src/indicators.py`, `src/metrics.py`, two test files. `journal.metrics()` is accounting (SQLite rows → net PnL); `src/metrics.py` is pure math over supplied sequences. Complementary, not duplicative — `journal.py` stays unrefactored to avoid destabilizing the live CLI.

**Boundary (read-only)**: computation-only. No network, no `Client`, no order endpoints ever. `tests/test_boundary.py` stays green; `src/` imports no Django.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/indicators.py` | New | SMA/EMA/RSI/ATR/VWAP/Z-score |
| `src/metrics.py` | New | Expectancy/profit factor/R-multiple/equity curve |
| `tests/test_indicators.py`, `tests/test_metrics.py` | New | Unit tests (TDD) |
| `pyproject.toml` | Modified | coverage `source` += `src`; drop report `fail_under` |
| `.github/workflows/ci.yml` | Modified | xml report + `diff-cover` gate; fetch-depth 0 |
| `requirements-dev.txt` | Modified | add `diff-cover` (dev-only) |
| `src/journal.py` | Unchanged | existing `metrics()` untouched |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Indicator edge cases (warm-up, div-by-zero) | Med | Explicit invariants + tests-first |
| `diff-cover` merge-base unavailable | Low | `fetch-depth: 0`; compare vs `origin/develop` |
| `src` added dilutes web gate | Low | Web gate scoped to `web/*` |

## Rollback Plan

Revert the branch: delete the two modules and their test files; restore `pyproject.toml`, `ci.yml`, `requirements-dev.txt`. Core CLI and `journal.metrics()` stay untouched, so `main` keeps shipping a working read-only CLI.

## Open Questions

- Warm-up handling for `ema`/`rsi`/`atr`: `[]`, `None`, or leading `None`s?
- `zscore`: rolling window or full-series?
- `equity_curve` input: realized-PnL list or timestamped rows?

## Success Criteria

- [ ] `python -m pytest` green; new suites pass Strict TDD.
- [ ] `ruff check . && ruff format --check .` green.
- [ ] `tests/test_boundary.py` green; zero Django imports, zero order calls.
- [ ] `diff-cover ... --fail-under=100` passes; web gate still passes.
- [ ] No new runtime dependency added.

## Review Workload Forecast

- Estimated diff: **~350–450 changed lines** (2 modules + 2 test suites + CI/config).
- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: Medium
