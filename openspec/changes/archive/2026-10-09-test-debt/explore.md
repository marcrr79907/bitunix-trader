# Exploration: test-debt (issue #46)

## Current State

Three LOW non-blocking debts from the Phase-4 (market-chart) verify.

**W1 — R5 JS-runtime scenarios verified by inspection only.** `openspec/changes/archive/2026-10-09-market-chart/verify-report.md:151-153` marks three of R5's scenarios `❌ UNTESTED`:
- *Forming candle updates in place* → inspection of `chart.js::onPush` (lines 204-224) + `bucket` (71-73).
- *Switch unsubscribes before subscribing* → inspection of `sendSubscribe` (226-243): it sends `unsubscribe` for the old `sub`, then sets `sub = next`, then `subscribe`.
- *Reconnect after drop with capped delay* → inspection of `backoff` (65-68) + `ws.onclose` (265-269).

The existing E2E (`tests/web/test_market_e2e.py`) is DOM-only: it asserts `typeof LightweightCharts`, canvas count, and that the candle series grows after a left-edge scroll. It never drives an interval switch and never observes WS frames. It is dev-only (`@pytest.mark.e2e`, `pytest.importorskip`, deselected via `addopts = "-q -m 'not e2e'"`).

**W2 — R7 "runtime dependencies unchanged" has no test.** `verify-report.md:160` marks it `❌ UNTESTED`; verified only by `git diff develop...HEAD -- requirements.txt` being empty. Same debt was reported for market-ingestion as WARNING 4 (`archive/2026-10-08-market-ingestion/verify-report.md:260-261`), with the identical fix trigger. No guard exists; existing scanners are `tests/test_boundary.py` (Django-in-src, AST) and `tests/web/test_no_order_surface.py` (order verbs, AST) — both use `ast.walk` + `sys.stdlib_module_names`.

**SUGGESTION 3 — `web/manage.py` invisible to the patch gate.** `pyproject.toml:29-34` omits `web/manage.py`, `wsgi.py`, `asgi.py`, `*/migrations/*` from `[tool.coverage.run]`. The Phase-4 CRITICAL fix (`web/manage.py::_ensure_project_paths`, lines 11-25) is therefore absent from `coverage.xml`, so `diff-cover --fail-under=100` does not measure it. Behavior is locked by `tests/web/test_manage_boot.py`, which spawns `python web/manage.py check` as a subprocess with a minimal env.

## Affected Areas

- `web/market/templates/market/chart.js` — W1 subject; frozen unless a test seam is needed.
- `tests/web/test_market_e2e.py` — W1: add a WS-lifecycle E2E (dev-only).
- `tests/test_dependency_guard.py` — W2: new AST guard (web/ + src/).
- `requirements.txt` — W2: the declared runtime set the guard derives/validates.
- `pyproject.toml` — SUGGESTION 3: document the `manage.py` omit rationale.
- `openspec/specs/market-chart/spec.md` — R5/R7 spec wording (verification method).
- `tests/web/test_manage_boot.py` — existing contract for manage.py (unchanged).

## Approaches

### W1 — runtime evidence for the 3 R5 scenarios

1. **Playwright `page.route_web_socket` interception (recommended).**
   Playwright 1.62 (installed) exposes `page.route_web_socket(url, handler)` and `WebSocketRoute` with `on_message`/`send`/`close`. Install the route before `goto`, capture client→server frames in order, `select_option("#interval", "5m")` to drive `switchTo`, and assert the tail frames are `unsubscribe`(`market_kline_1min`) then `subscribe`(`market_kline_5m`). Then `route.send()` a crafted push twice in the same bucket and assert `candleSeries.data()` length grows by exactly 1 and the last time is unchanged (bucketing in place). Fully deterministic — no live network, no CDN.
   - Pros: real runtime evidence for 2 of 3 scenarios; no production-code change; deterministic.
   - Cons: dev-only (not run in CI); reconnect *timing* remains untested.
   - Effort: Low-Medium.

2. **`page.on("websocket")` + `framesent` (observe-only).**
   `WebSocket` supports `framesent`/`framereceived` events, but it cannot inject server pushes and still needs the live endpoint to stay open — flaky.
   - Pros: minimal.
   - Cons: cannot deterministically drive bucketing; network-dependent.
   - Effort: Low.

3. **`node --test` on an extracted pure module (`bucket`/`backoff`).**
   - Pros: fastest for the pure arithmetic.
   - Cons: adds Node+npm to a pure-Python repo for ~10 lines; YAGNI.
   - Effort: High for the value.

**Reconnect/backoff:** its cap is arithmetic on a pure function. Asserting exact exponential *delay* in a browser is timing-flaky. Recommend E2E covers ordering + bucketing, and the reconnect scenario is marked inspection-verified in the spec with justification (deterministic cap = `min(1000·2^n, 60000)·(0.5..1.5)`, single pure expression, no integration seam worth a flaky wait). Optionally expose `backoff` on the existing `window.marketChart` seam and assert the cap deterministically — cheap, but only tests the pure function.

### W2 — dependency guard

**AST scan of `web/**/*.py` + `src/**/*.py`; fail on any top-level import root not in `stdlib ∪ declared ∩ local` (recommended).**
- Allowed set = `sys.stdlib_module_names` ∪ declared third-party roots from `requirements.txt` (`requests`, `rich`, `django`, `psycopg`, `dj_database_url`, `gunicorn`, `redis`, `cryptography`) ∪ local roots.
- **Local roots derived dynamically** (first-party): every directory under `web/` containing `__init__.py` (accounts, config, credentials, market, trading, worker) plus `src`. Deriving avoids false positives when a new first-party app is added.
- **False-positive avoidance:** skip relative imports (`node.level > 0`) — three exist in `web/config/settings/{dev,prod}.py` (`from .base import *`); `from __future__` and `typing` are stdlib; tests live outside the scanned roots so test-only imports are irrelevant; `*/migrations/*` import only `django` (declared).
- **Known ceiling:** a third-party import under `if TYPE_CHECKING:` is still AST-visible and would be flagged; none exist today. Document with a `ponytail:` note rather than special-casing.
- **Sync test (should):** parse `requirements.txt` with a small dist→import map (`dj-database-url→dj_database_url`, `psycopg[binary]→psycopg`) and assert it equals the declared allowlist, so the two cannot drift.
- Location `tests/test_dependency_guard.py` (mirrors `test_boundary.py`); includes positive control (`import django` not flagged) and negative fixture (`import pandas` flagged).
- Pros: catches any new runtime import; no false positives on declared/local.
- Cons: allowlist needs updating when a dependency is legitimately added (intended friction; the sync test makes the message actionable).
- Effort: Low.

### SUGGESTION 3 — manage.py omit

1. **Drop `web/manage.py` from `omit` (rejected).**
   `test_manage_boot.py` runs manage.py in a **subprocess**; `coverage` does not instrument child processes without `COVERAGE_PROCESS_START`/concurrency config. Dropping the omit therefore adds `manage.py`'s ~15 import-time lines to the report as **uncovered**, lowering the web % (95% → ~92.5%, still ≥85 but no longer meaningful) without buying real coverage. That is a false safety net.
2. **Keep the omit, document the contract (recommended).**
   Add a `pyproject.toml` comment: manage.py is a thin bootstrap; its contract is the behavioral subprocess test `tests/web/test_manage_boot.py`, which is strictly stronger than line coverage. Optionally mirror the note in the spec/traceability.
   - Pros: honest, zero risk, no false coverage; the subprocess test already proves the fix.
   - Cons: patch gate still does not *measure* future manage.py edits (covered behaviorally).
   - Effort: Trivial.

## Recommendation

- **W1:** Approach 1 — extend the dev-only E2E with `page.route_web_socket` to assert (a) `unsubscribe`→`subscribe` frame order on interval switch and (b) forming-candle in-place bucketing. Mark the *reconnect* scenario inspection-verified in the spec (flaky to assert in-browser; pure capped arithmetic). Optionally add `backoff` to the existing seam for a deterministic cap assert.
- **W2:** AST dependency guard in `tests/test_dependency_guard.py` with dynamically-derived local roots + a requirements-sync test.
- **SUGGESTION 3:** Keep the omit; document `test_manage_boot.py` as manage.py's contract (pyproject comment + spec note).

## Risks

- E2E is dev-only: the R5 scenarios remain unrun in CI (accepted status quo for the JS/template layer; `chart.js` is not coverage-instrumented).
- `route_web_socket` asserts on frame shape: assert parsed `op`/`args[0].ch`, not raw JSON, to survive whitespace/key-order changes.
- Allowlist drift: deriving local roots avoids first-party false positives; the sync test catches requirements drift.
- No new runtime dependency may be introduced while adding these tests (pytest/playwright already dev-only).

## Scope Boundaries

**In:** W1 E2E + spec wording; W2 guard test; SUGGESTION-3 documentation; spec deltas for R5/R7 verification method; Strict TDD; patch gate 100%; no new runtime deps; no edits to `src/`.

**Out:** `railway.json` → IaC (#54); Node/npm JS test infra; subprocess coverage instrumentation; backoff-timing E2E; any production behavior change.

## Ready for Proposal

Yes. Concrete file targets, approach chosen, no open blockers beyond the reconnect-scenario wording decision (recommend inspection-verified).
