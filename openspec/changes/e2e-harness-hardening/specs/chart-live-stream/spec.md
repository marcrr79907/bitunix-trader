# Delta for chart-live-stream

Issue #149 (DEBT-8). Product: a switch before boot completes MUST still open the live socket. Harness: the 3 mocked-socket E2E tests MUST be readiness-gated. `#68` (update-only live) and the stale-frame guard (DEBT-1) are preserved; no new dependency.

## ADDED Requirements

### Requirement: R8 — Pre-boot switch opens the live socket

The stream adapter's `subscribe(next)` MUST open the WebSocket when no socket is OPEN — routing through the existing `connect(next)` seam — instead of only recording the pending key. A subscription requested before boot completes (an interval/symbol change firing before `start()` resolves) MUST therefore still establish the live stream for the requested key. When a socket is already OPEN, `subscribe` MUST keep the live behavior (`unsubscribe(old)` strictly before `subscribe(new)`) and MUST NOT open a second socket while one is OPEN or CONNECTING. `#68` (writes via `update()` only, no periodic full-series `setData`) and the stale-frame guard (`isFrameForChannel(frame, config.channels[sub.interval])`) MUST be unchanged.

#### Scenario: Switch before boot opens the socket
- GIVEN the page is mid-boot and no WebSocket exists
- WHEN `subscribe({symbol, interval:"5m"})` is called
- THEN `connect()` is invoked, a socket to `config.wsUrl` is created, and it subscribes `market_kline_5min` on open

#### Scenario: No duplicate socket on an open connection
- GIVEN a socket already OPEN
- WHEN `subscribe(next)` is called
- THEN no new WebSocket is constructed and `unsubscribe(old)` precedes `subscribe(new)`

#### Scenario: #68 and the stale-frame guard hold
- GIVEN an open socket streaming
- WHEN frames are pushed
- THEN writes go through `update()` only (a `setData` spy reads 0) and a frame whose `ch` differs from `config.channels[sub.interval]` is dropped before `updateCandle`

### Requirement: R9 — Deterministic E2E readiness contract

The 3 mocked-socket E2E tests MUST wait for boot readiness (`window.marketChart.ready === true`, or a bounded poll for the open socket) BEFORE switching interval or injecting frames; readiness MUST replace any retry as the determinism mechanism. E2E `wait_for_function` predicates MUST null-guard `window.marketChart.candleSeries` (and pane series) so a mid-boot `null` cannot surface as a hard `TypeError`. The run requirement `python -m pytest -m e2e -p no:randomly` on an idle machine MUST be documented in the test module docstring and the README dev note. No new dependency; no CI `addopts` change.

#### Scenario: WS tests wait ready before switching
- GIVEN a mocked-socket WS test
- WHEN it prepares to `select_option("#interval", ...)` or inject a frame
- THEN it has first awaited `ready` (or a bounded poll for the socket), with no retry wrapper

#### Scenario: Predicates are null-guarded
- GIVEN a predicate referencing `window.marketChart.candleSeries`
- WHEN the page is mid-boot and `candleSeries` is `null`
- THEN the predicate returns falsy and Playwright keeps polling (no `Cannot read properties of null`)

#### Scenario: Idle-machine command documented
- GIVEN the repo docs
- WHEN the E2E run command is looked up
- THEN the module docstring and the README note both state `-m e2e -p no:randomly` on an idle machine
