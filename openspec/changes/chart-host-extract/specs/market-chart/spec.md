# Delta for market-chart

Issue #146 (DEBT-5): extract the candle channel from `chart-host.js` into a new
host-layer sub-module `chart-host-candles.js`, restoring R14 compliance.

**This is a boundary/inventory delta — NO behavioral requirement changes.**
R1–R13 and R15–R21 stay in force and unmodified. The C1 HA fix, #68
single-write-path, the frozen 8-key seam, and the `chart-types-core` HA contract
are all preserved verbatim. Only R14 (module inventory + size guard) changes.

## MODIFIED Requirements

### Requirement: R14 — Layered ESM module boundary

Modules MUST follow a frozen inventory: entry `chart.js` (thin: Django-injected
`CONFIG` + imports + `boot()`), pure cores `chart-core.js`/`drawing-core.js`/
`smc-overlay-core.js`/`legend-core.js`/`indicator-settings-core.js`/
`chart-types-core.js`, `chart-store.js` (UI/config state ONLY — MUST NOT hold
candle data; its vocabulary is
`symbol, interval, indicators, params, styles, smc, scaleMode, chartType, tool`),
`chart-bus.js`, `chart-host.js` (chart/series/panes/scales/crosshair), the
host-layer sub-module `chart-host-candles.js` (candle channel: `CANDLE_CTORS`,
the candle series, the raw `candles` array, and the incremental HA state;
factory `createCandles(chart, chartType) -> {getCandleSeries, getCandles,
setCandles, updateCandle, remove}`),
`controllers/{indicators,history,stream,drawings,smc,toolbar,legend}.js`,
and `main.js` (ALL orchestration + boot/switch). No module MUST exceed ~300 lines.
Controllers MUST import host/store/bus directly but MUST NOT import `main`;
commands MUST travel the bus, so `main.js` has no circular imports. Every imported
module MUST be served same-origin under `/market/` via its Django route (core →
`MODULE_ALLOWLIST`, controller → `CONTROLLER_ALLOWLIST`). The size rule MUST be
enforced by the committed guard `tests/web/test_module_size_guard.py`
(`CEILING = 300`; scans `web/market/templates/market/**/*.js` via `rglob` +
`splitlines()`). The guard's `ALLOWLIST` MUST be empty — no module is exempt.
`chart-host.js` MUST be ≤ ~300 lines (back under the ceiling after the
extraction). Any module above `CEILING` MUST fail the guard.

(Previously: the inventory did not list `chart-host-candles.js`; `chart-host.js`
was 326 lines and carried the candle channel inline, surviving via an annotated
`ALLOWLIST = {"chart-host.js"}` exemption — DEBT-5 / #146.)

#### Scenario: Inventory and no-cycle

- GIVEN the delivered modules, WHEN imports resolve, THEN the inventory (including `chart-types-core.js` and `chart-host-candles.js`) exists, `chart-types-core.js` imports nothing, no controller imports `main`, and `main.js` has no cycles

#### Scenario: Store never holds candles

- GIVEN `chart-store.js`, WHEN its keys are inspected, THEN it holds only UI/config (`symbol, interval, indicators, params, styles, smc, scaleMode, chartType, tool`) — no candle data

#### Scenario: Size ceiling with empty allowlist

- GIVEN every module, WHEN `tests/web/test_module_size_guard.py` reads line counts
- THEN it passes at `CEILING = 300` with an EMPTY `ALLOWLIST` (no exemption), `chart-host.js` is ≤ ~300 lines, and any module above the ceiling fails

#### Scenario: New candle sub-module is served

- GIVEN `chart-host-candles`, WHEN requested under `/market/` with a JS MIME type, THEN it is served 200 (the name MUST be in `MODULE_ALLOWLIST`; missing → import 404 → blank chart)

#### Scenario: No behavior change

- GIVEN the extraction, WHEN the 138 node tests and the E2E suite run
- THEN they pass with NO behavior-assertion edits, the 8-key seam
  (`window.marketChart`) is unchanged, the C1 same-bucket HA fix is preserved
  verbatim, and the HA contract (`chart-types-core`) is untouched
