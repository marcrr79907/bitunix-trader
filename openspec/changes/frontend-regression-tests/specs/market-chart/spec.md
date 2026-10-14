# Delta for market-chart

Issue #144 (W4): **verification-evidence only**. No production behavior changes. This delta records that R14's "no module exceeds ~300 lines" rule gains a **committed, executable** guard (`tests/web/test_module_size_guard.py`) with an explicit `chart-host.js` exception — the rule already held by inspection; the HOW of proving it changes from review-only to test-enforced. No production file, no seam key, no dependency.

## MODIFIED Requirements

### Requirement: R14 — Layered ESM module boundary

Modules MUST follow a frozen inventory: entry `chart.js` (thin: Django-injected `CONFIG` + imports + `boot()`), pure cores `chart-core.js`/`drawing-core.js`/`smc-overlay-core.js`/`legend-core.js`/`indicator-settings-core.js`/`chart-types-core.js`, `chart-store.js` (UI/config state ONLY — MUST NOT hold candle data; its vocabulary is `symbol, interval, indicators, params, styles, smc, scaleMode, chartType, tool`), `chart-bus.js`, `chart-host.js` (chart/series/panes/scales/crosshair + candle data), `controllers/{indicators,history,stream,drawings,smc,toolbar,legend}.js`, and `main.js` (ALL orchestration + boot/switch). No module MUST exceed ~300 lines. Controllers MUST import host/store/bus directly but MUST NOT import `main`; commands MUST travel the bus, so `main.js` has no circular imports. Every imported module MUST be served same-origin under `/market/` via its Django route (core → `MODULE_ALLOWLIST`, controller → `CONTROLLER_ALLOWLIST`). The size rule MUST be enforced by the committed guard `tests/web/test_module_size_guard.py` (`CEILING = 300`; scans `web/market/templates/market/**/*.js` via `rglob` + `splitlines()`) with an explicit annotated allowlist exempting `chart-host.js` (326 lines today; DEBT-5 / #146). Any OTHER module above `CEILING` MUST fail the guard.
(Previously: the size rule was verified by inspection only; no committed guard existed.)

#### Scenario: Inventory and no-cycle

- GIVEN the delivered modules, WHEN imports resolve, THEN the inventory (including `chart-types-core.js`) exists, `chart-types-core.js` imports nothing, no controller imports `main`, and `main.js` has no cycles

#### Scenario: Store never holds candles

- GIVEN `chart-store.js`, WHEN its keys are inspected, THEN it holds only UI/config (`symbol, interval, indicators, params, styles, smc, scaleMode, chartType, tool`) — no candle data

#### Scenario: Size ceiling

- GIVEN every module, WHEN `tests/web/test_module_size_guard.py` reads line counts
- THEN it passes at `CEILING = 300` with `chart-host.js` exempted by the annotated allowlist (DEBT-5 / #146), and fails any other module above the ceiling

#### Scenario: New core is served

- GIVEN `chart-types-core`, WHEN requested under `/market/` with a JS MIME type, THEN it is served 200 (missing from the allowlist → 404 → blank chart)
