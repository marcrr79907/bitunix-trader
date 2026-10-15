# Proposal: e2e-harness-hardening

## Intent

Make the 3 mocked-socket E2E tests in `tests/web/test_market_e2e.py`
deterministic, and fix the real product defect they mask. An interval switch
before boot completes leaves the live stream dead for the session:
`stream.subscribe` stores `sub` but never opens the socket, and boot aborts via
`gen !== 0`. A harness-only fix would hide this — the invariant is "no ocultar
fallos reales".

## Scope

### In Scope
- **Product fix (minimal)**: `stream.subscribe(next)` opens the socket via the
  existing `connect()` when `ws` is absent, so a pre-boot switch still streams.
  `#68` (update-only live) and the `gen` guards stay. Regression test added.
- **Harness fix**: wait for readiness (`_wait_ready` / `_poll(... "route" in
  holder)`) BEFORE `select_option` in the 3 WS tests, so the socket is open when
  frames are injected. Deterministic, not a retry.
- **Flake hardening**: null-guard `wait_for_function` predicates
  (`window.marketChart && ...candleSeries...`) against the
  `Cannot read properties of null` class.
- **Docs**: extend the `test_market_e2e.py` docstring + one README E2E note
  (`-m e2e -p no:randomly` on an idle machine; `playwright install chromium`).

### Out of Scope
- Retry / `pytest-rerunfailures` as the primary mechanism (forbidden; masks
  class A). Opt-in logged retry only if residual class C needs it.
- CI job for E2E / `addopts` change / new runtime deps.
- Class C (SQLite + threaded `live_server`) root fix — documented, not papered.

## Capabilities

- New: None.
- Modified `chart-live-stream`: an interval switch before boot completes MUST
  still open the WS and stream the new channel (requirement + scenario near R5/R6).

## Approach

Reuse existing seams. Product: one guard in `stream.js::subscribe` calling the
existing `connect(next)`. Harness: reuse `_wait_ready` (used by ~20 tests).
Predicates: add the null short-circuit. Docs only. Single PR: harness + product
fix + docs together — the product fix is what makes the harness fix honest.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `.../controllers/stream.js` | Modified | Pre-connect `subscribe` opens the socket |
| `tests/web/test_market_e2e.py` | Modified | Readiness guards + null-guarded predicates |
| `tests/web/` (unit or E2E) | New | Regression for pre-boot switch |
| `README.md` | Modified | One E2E dev note |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Harness fix masks the product bug | High | Fix both; regression pins it |
| Breaks `#68`/`gen` guards | Med | Keep guards; regression + existing WS tests |
| CI does not run E2E | High | Local-verified; stated in docs |
| Residual class C under load | Med | Documented, bounded, not introduced |

## Rollback Plan

Revert the branch: restore `stream.js::subscribe`, the 3 WS tests, and the
docstring/README. No dependency, migration, or config change to unwind at
runtime. The regression test reverts with it.

## Dependencies

- `pytest-playwright` (dev-only, installed); chromium bundle.

## Success Criteria

- [ ] 3 WS tests pass deterministically (no retry) across repeated runs.
- [ ] Regression fails on the pre-fix `subscribe` and passes after.
- [ ] `python -m pytest -m e2e -p no:randomly` green on an idle machine.
- [ ] `python -m pytest` green; `ruff check`/`format --check` clean.

## Review Workload Forecast

- Estimated diff: **~80–140 changed lines** (product ~15, tests ~60, docs ~20).
- Decision needed before apply: No
- Chained PRs recommended: No
- 400-line budget risk: Low
