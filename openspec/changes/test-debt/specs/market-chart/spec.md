# Delta for market-chart

Issue #46: changes only the **verification method** of R5/R7 and documents the `manage.py` coverage omission — no production behavior, no new runtime dep.

## MODIFIED Requirements

### Requirement: R5 — Live candles over browser WS

Page JS MUST connect to `wss://fapi.bitunix.com/public/`, subscribe `market_kline_<interval>`, update the FORMING candle in place via interval bucketing (no duplicate times), unsubscribe BEFORE subscribing on interval/symbol switch, reconnect with exponential backoff capped at a fixed maximum, resubscribing on reopen. Verified by dev-only E2E assertions, not image diffs. The two live-candle scenarios MUST be driven via `page.route_web_socket` (no live network/CDN); reconnect is accepted as inspection-verified (single pure capped expression).
(Previously: verified by DOM assertions only; live-candle scenarios were inspection-only.)

#### Scenario: Forming candle updates in place

- GIVEN latest candle shown
- WHEN two WS pushes in the same bucket are injected via `page.route_web_socket`
- THEN the series grows by exactly 1 and the last `time` is unchanged (bucketed in place)

#### Scenario: Switch unsubscribes before subscribing

- GIVEN active subscription
- WHEN `#interval` switches interval
- THEN parsed JSON frames show `{op:"unsubscribe", ch:"market_kline_<old>"}` strictly before `{op:"subscribe", ch:"market_kline_<new>"}`

#### Scenario: Reconnect after drop with capped delay

- GIVEN WS drops
- WHEN the client reconnects
- THEN `backoff()` is `min(1000·2^n, 60000)·(0.5..1.5)` and resubscribes on reopen; verified by inspection of `backoff`/`onclose`, MAY add a deterministic cap assertion if `backoff` is exposed on the `window.marketChart` seam; in-browser timing is NOT asserted

#### Scenario: E2E DOM smoke

- GIVEN logged-in browser on `/market/`, WHEN page loads, THEN `LightweightCharts` defined, canvas exists, `/market/api/kline` returns JSON with `candles`

### Requirement: R7 — Boundary, read-only, no new runtime dependency

`src/` MUST stay framework-free (`tests/test_boundary.py` green). `/market/kline` MUST match no order-scanner forbidden fragment. `requirements.txt` MUST be unchanged (`pytest-playwright` is dev-only). No schema field/migration; auth, CSRF, CSP and the WS path unchanged. The "no new runtime dependency" invariant MUST be enforced by an AST guard over `web/**/*.py` + `src/**/*.py` failing when a top-level import root is outside `stdlib ∪ declared-deps ∪ local`; a requirements-sync test MUST keep manifest and guard from diverging.
(Previously: verified only by inspecting `requirements.txt`; no guard existed.)

#### Scenario: No schema change or migration

- GIVEN the change, WHEN migrations are inspected, THEN no new migration/model field exists; `Candle` is read-only

#### Scenario: Auth, CSRF, CSP, WS unchanged

- GIVEN the new params and JS, WHEN exercised, THEN login/302, CSRF, market CSP and the WS path behave as before

#### Scenario: Core boundary stays green

- GIVEN new client method and market app, WHEN boundary suite runs, THEN `src/` imports no framework; `web/market` → `src/` permitted

#### Scenario: Order scanner clean

- GIVEN new routes and code, WHEN order scanner runs, THEN `/market/kline` matches no forbidden fragment

#### Scenario: Guard passes on the current tree

- GIVEN the change, WHEN the dependency guard runs
- THEN it passes: stdlib, declared deps (`requests`, `rich`, `django`, `psycopg`, `dj_database_url`, `gunicorn`, `redis`, `cryptography`) and local modules (`web/` packages + `src`) are allowed; relative imports excluded

#### Scenario: Guard fails on an unknown import (negative control)

- GIVEN an injected `import pandas` in a scanned file, WHEN the guard runs, THEN it reports that file as an offender

#### Scenario: Requirements sync enforced

- GIVEN a declared dist with no import-root mapping, or a mapped root absent from the allowlist
- WHEN the sync test runs
- THEN it fails; the map (`psycopg[binary]→psycopg`, `dj-database-url→dj_database_url`, …) MUST cover every declared dist

## ADDED Requirements

### Requirement: R9 — manage.py coverage contract

`web/manage.py` MUST stay in coverage `omit`; its contract is the subprocess test `tests/web/test_manage_boot.py` (stronger than line coverage — dropping `omit` adds uncovered import-time lines without instrumenting the child).

#### Scenario: Documented omission

- GIVEN `pyproject.toml`, WHEN `[tool.coverage.run].omit` is read, THEN `web/manage.py` is omitted with a comment naming `tests/web/test_manage_boot.py`

#### Scenario: Boot behavior locked

- GIVEN the subprocess test, WHEN `python web/manage.py check` runs in a minimal env, THEN the bootstrap succeeds
