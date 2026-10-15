# Delta for market-chart

Issue #148 (DEBT-7). The frozen layered ESM boundary gains one pure core
(`theme-core.js`), one store key (`theme`), and a host theme option path
(born-themed `build()` + option-only `setTheme`). R14 changes (inventory + store
vocabulary); R20's envelope is extended to allow the theme host method with NO
new bus event. R17 (single-write-path) and R18 (8-key seam) stay in force
unmodified.

## MODIFIED Requirements

### Requirement: R14 — Layered ESM module boundary

Modules MUST follow a frozen inventory: entry `chart.js` (thin: Django-injected
`CONFIG` + imports + `boot()`), pure cores `chart-core.js`/`drawing-core.js`/
`smc-overlay-core.js`/`legend-core.js`/`indicator-settings-core.js`/
`chart-types-core.js`/`theme-core.js`, `chart-store.js` (UI/config state ONLY —
MUST NOT hold candle data; its vocabulary is
`symbol, interval, indicators, params, styles, smc, scaleMode, chartType, theme,
tool`), `chart-bus.js`, `chart-host.js` (chart/series/panes/scales/crosshair +
candle data), the host-layer sub-module `chart-host-candles.js`,
`controllers/{indicators,history,stream,drawings,smc,toolbar,legend}.js`, and
`main.js` (ALL orchestration + boot/switch). No module MUST exceed ~300 lines.
Controllers MUST import host/store/bus directly but MUST NOT import `main`;
commands MUST travel the bus, so `main.js` has no circular imports. Every imported
module MUST be served same-origin under `/market/` via its Django route (core →
`MODULE_ALLOWLIST`, controller → `CONTROLLER_ALLOWLIST`). The size guard's
`ALLOWLIST` MUST be empty.
(Previously: the store vocabulary had no `theme` and the pure-core list had no
`theme-core.js`.)

#### Scenario: Inventory and no-cycle

- GIVEN the delivered modules, WHEN imports resolve, THEN the inventory (including `theme-core.js`) exists, `theme-core.js` imports nothing, no controller imports `main`, and `main.js` has no cycles

#### Scenario: Store never holds candles

- GIVEN `chart-store.js`, WHEN its keys are inspected, THEN it holds only UI/config (`symbol, interval, indicators, params, styles, smc, scaleMode, chartType, theme, tool`) — no candle data

#### Scenario: Size ceiling with empty allowlist

- GIVEN every module, WHEN the size guard reads line counts
- THEN it passes at `CEILING = 300` with an EMPTY `ALLOWLIST` and `chart-host.js` stays ≤ ~300 lines

#### Scenario: New theme core is served

- GIVEN `theme-core`, WHEN requested under `/market/` with a JS MIME type, THEN it is served 200 (missing from the allowlist → 404 → blank chart)

### Requirement: R20 — Shell change stays inside the frozen host/seam envelope

The `autoSize: true` host option, the `#chart` markup change, the F8 chart-type
and scale controls, and the theme control MUST stay within R14 (host owns
construction) and MUST NOT add a `window.marketChart` key. `window.marketChart`
MUST keep exactly its 8 frozen keys `{chart, candleSeries, panes, ready,
drawings, smc, smcCounts, smcToggles}` and `window.SmcOverlayCore` MUST be
untouched. The E2E seam shape and timing (R18) and the single-write-path
invariants (R17) MUST be preserved; the existing E2E assertions MUST stay green
with NO edits. F8 added exactly one bus event, `scale:changed` (`{mode}`); this
change MUST NOT add another bus event — the live theme flip MUST go through the
host's option-only `setTheme` method, not a new event. The theme value MUST live
in the store (`state.theme`) and/or `data-theme`, never in the seam.
(Previously: the envelope covered type/scale; theme was not present.)

#### Scenario: Seam stays 8 keys

- GIVEN a booted chart after the theme control
- WHEN `window.marketChart` is read
- THEN exactly the 8 frozen keys exist and no theme key was added

#### Scenario: No new bus event

- GIVEN the change
- WHEN the bus events are inspected
- THEN the only events are the pre-existing set plus `scale:changed`; no `theme:*` event was added

#### Scenario: Existing E2E stays green unedited

- GIVEN the existing E2E assertions
- WHEN the suite runs after the change
- THEN they pass with no assertion edits and the default type stays candles

## ADDED Requirements

### Requirement: R22 — Theme host contract

`chart-host.js` `build()` MUST read `state.theme` and pass the theme option set
built by `theme-core.optionsFor` into `createChart` at its single construction
site, so every rebuild is born themed (no separate re-apply). It MUST expose
`setTheme(resolved)` (chart option only; no data write) applying
`chart.applyOptions({layout, grid, crosshair, rightPriceScale, timeScale})`
mirroring `setScaleMode`; it MUST pass full values, never `undefined` keys. A
theme change MUST NOT introduce a second full-series `setData` writer.

#### Scenario: Build is born themed

- GIVEN `state.theme="light"`
- WHEN `build(state)` runs
- THEN the created chart's `layout.background.color` and `layout.textColor` are the light values

#### Scenario: setTheme is option-only

- GIVEN a built chart
- WHEN `setTheme("dark")` runs
- THEN the chart options swap to the dark set and neither `setData` nor `update` is called

#### Scenario: Rebuild preserves theme

- GIVEN `state.theme="dark"`
- WHEN a chart-type change rebuilds the chart
- THEN the new chart's options are the dark set and drawings/SMC re-attach
