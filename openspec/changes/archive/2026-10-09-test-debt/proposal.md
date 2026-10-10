# Proposal: test-debt

## Intent

Close the three LOW verification debts from the Phase-4 (market-chart) verify
(`archive/2026-10-09-market-chart/verify-report.md`) so R5 and R7 carry real
evidence instead of static inspection, and so the `manage.py` coverage omission
is a documented contract rather than a silent gap. No production behavior
changes.

## Scope

### In Scope
- **W1**: extend the dev-only E2E (`tests/web/test_market_e2e.py`) with
  `page.route_web_socket` to assert (a) `unsubscribe`→`subscribe` frame order on
  interval switch and (b) forming-candle in-place bucketing (no duplicate time).
  Mark the *reconnect-with-capped-backoff* scenario inspection-verified in the
  R5 spec with justification (pure capped arithmetic; in-browser timing flaky).
- **W2**: new guard `tests/test_dependency_guard.py` — AST-scan `web/**/*.py` +
  `src/**/*.py`, fail on any top-level import root outside
  `stdlib ∪ declared-deps ∪ local`; local roots derived dynamically; plus a
  requirements-sync test.
- **SUGGESTION 3**: keep `web/manage.py` in coverage `omit`; document
  `tests/web/test_manage_boot.py` as its contract (pyproject comment + spec note).
- Spec deltas (R5/R7 verification method) + Strict TDD tests.

### Out of Scope
- `railway.json` → IaC (#54); Node/npm JS test infra; subprocess coverage
  instrumentation (`COVERAGE_PROCESS_START`); backoff-timing E2E; any `src/`
  edit or runtime behavior change.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `market-chart`: R5 and R7 verification methods — the two JS-runtime scenarios
  gain runtime E2E evidence; the reconnect scenario and R7 "runtime dependencies
  unchanged" move to tested/inspection-verified with named artifacts.

## Approach

Reuse existing seams. W1 uses the already-exposed `window.marketChart` global
and the real interval selector; Playwright 1.62 `route_web_socket` intercepts
frames deterministically (no live network/CDN). W2 mirrors `tests/test_boundary.py`
AST style (`ast.walk` + `sys.stdlib_module_names`); requirements roots
(`dj_database_url`, `psycopg`) are mapped explicitly and asserted in sync.
SUGGESTION 3 is a comment + spec note — zero runtime risk.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `tests/web/test_market_e2e.py` | Modified | WS-order + bucketing E2E |
| `tests/test_dependency_guard.py` | New | runtime-import guard + sync test |
| `pyproject.toml` | Modified | comment the `manage.py` omit reason |
| `openspec/specs/market-chart/spec.md` | Modified | R5/R7 verification wording |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| E2E dev-only (not in CI) | High | Accepted; `chart.js` is not coverage-instrumented |
| Frame assertion brittle to JSON shape | Med | Assert parsed `op`/`args[0].ch`, not raw text |
| Allowlist drifts from requirements | Low | Derive local roots; add requirements-sync test |
| New runtime dep sneaks in | Low | The guard itself is the mitigation |

## Rollback Plan

Revert the branch: delete `tests/test_dependency_guard.py`, restore the prior
E2E and spec text, drop the pyproject comment. No production code, no dependency,
no migration changes — nothing to unwind at runtime.

## Dependencies

- `pytest-playwright` 1.62 (dev-only, already installed), chromium bundle.

## Success Criteria

- [ ] W1: E2E asserts `unsubscribe` before `subscribe` on switch and bucketed
  in-place update; reconnect scenario inspection-verified in spec.
- [ ] W2: guard fails on a synthetic `import pandas`; passes on declared/local.
- [ ] SUGGESTION 3: omission documented; `test_manage_boot.py` named as contract.
- [ ] `python -m pytest` green; ruff clean; patch coverage 100%.

## Review Workload Forecast

- Estimated diff: **~150–220 changed lines** (E2E ~60, guard + fixture ~90,
  docs/spec ~40).
- Decision needed before apply: No
- Chained PRs recommended: No
- 400-line budget risk: Low
