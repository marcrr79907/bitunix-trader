# Delta for market-chart

Issue #121 (Fase F8). The frozen layered ESM boundary gains one pure core
(`chart-types-core.js`), two store keys (`scaleMode`, `chartType`), a host
series-Ctor selection + price-scale option path + HA write path, and one bus event
(`scale:changed`, host option only). R14 changes (inventory + store vocabulary);
R17 (single-write-path) and R18 (8-key seam) stay in force unmodified. R20's "no
new bus event" envelope is tightened to allow exactly `scale:changed`.

## MODIFIED Requirements

### Requirement: R14 — Layered ESM module boundary

Modules MUST follow a frozen inventory: entry `chart.js` (thin: Django-injected
`CONFIG` + imports + `boot()`), pure cores `chart-core.js`/`drawing-core.js`/
`smc-overlay-core.js`/`legend-core.js`/`indicator-settings-core.js`/
`chart-types-core.js`, `chart-store.js` (UI/config state ONLY — MUST NOT hold
candle data; its vocabulary is
`symbol, interval, indicators, params, styles, smc, scaleMode, chartType, tool`),
`chart-bus.js`, `chart-host.js` (chart/series/panes/scales/crosshair + candle
data), `controllers/{indicators,history,stream,drawings,smc,toolbar,legend}.js`,
and `main.js` (ALL orchestration + boot/switch). No module MUST exceed ~300 lines.
Controllers MUST import host/store/bus directly but MUST NOT import `main`;
commands MUST travel the bus, so `main.js` has no circular imports. Every imported
module MUST be served same-origin under `/market/` via its Django route (core →
`MODULE_ALLOWLIST`, controller → `CONTROLLER_ALLOWLIST`).
(Previously: the store vocabulary had 7 keys without `scaleMode`/`chartType`, and
the pure-core list had no `chart-types-core.js`.)

#### Scenario: Inventory and no-cycle

- GIVEN the delivered modules, WHEN imports resolve, THEN the inventory (including `chart-types-core.js`) exists, `chart-types-core.js` imports nothing, no controller imports `main`, and `main.js` has no cycles

#### Scenario: Store never holds candles

- GIVEN `chart-store.js`, WHEN its keys are inspected, THEN it holds only UI/config (`symbol, interval, indicators, params, styles, smc, scaleMode, chartType, tool`) — no candle data

#### Scenario: Size ceiling

- GIVEN every module, WHEN line counts are read, THEN each is ≤ ~300 lines

#### Scenario: New core is served

- GIVEN `chart-types-core`, WHEN requested under `/market/` with a JS MIME type, THEN it is served 200 (missing from the allowlist → 404 → blank chart)

### Requirement: R20 — Shell change stays inside the frozen host/seam envelope

The `autoSize: true` host option, the `#chart` markup change, and the F8 chart-type
and scale controls MUST stay within R14 (host owns construction) and MUST NOT add a
`window.marketChart` key. `window.marketChart` MUST keep exactly its 8 frozen keys
`{chart, candleSeries, panes, ready, drawings, smc, smcCounts, smcToggles}` and
`window.SmcOverlayCore` MUST be untouched. The E2E seam shape and timing (R18) and
the single-write-path invariants (R17) MUST be preserved; the existing E2E
assertions MUST stay green with NO edits. F8 MAY add exactly one bus event,
`scale:changed` (`{mode}`), which MUST drive a host price-scale option only — no
rebuild, no `fetchHistory`; a chart-type change MUST reuse the existing
`indicator:changed` → `rebuild()` path.
(Previously: the envelope allowed no new bus event; F8 adds only `scale:changed`.)

#### Scenario: Seam stays 8 keys

- GIVEN a booted chart after the F8 controls
- WHEN `window.marketChart` is read
- THEN exactly the 8 frozen keys exist and `SmcOverlayCore` is reachable

#### Scenario: Only one new bus event

- GIVEN the F8 change
- WHEN the module inventory and bus events are inspected
- THEN the only new event is `scale:changed`, and chart-type reuses `indicator:changed`

#### Scenario: Existing E2E stays green unedited

- GIVEN the existing E2E assertions
- WHEN the suite runs after the change
- THEN they pass with no assertion edits and the default type stays candles

## ADDED Requirements

### Requirement: R21 — Chart type and scale host contract

`chart-host.js` `build()` MUST choose the candle-series Ctor from `state.chartType`
(`candles`/`heikin-ashi` → `CandlestickSeries`, `line` → `LineSeries`, `area` →
`AreaSeries`) at its single construction site, and MUST apply the price-scale mode
after `createChart` via `priceScale("right").applyOptions({mode})` using the
`LightweightCharts.PriceScaleMode` symbol. It MUST expose
`setScaleMode(mode, autoScale)` (chart option only; no data write) and route the
candle write path through `toChartData(state.chartType, …)`, carrying incremental
HA state (`lastHaOpen`/`lastHaClose` reset on `setCandles`). A chart-type change
MUST go through `build()`/`rebuild()`; scale MUST NOT.

#### Scenario: Ctor from state

- GIVEN each `chartType` in `candles,line,area,heikin-ashi`
- WHEN `build(state)` runs
- THEN the candle series is the matching v5 type

#### Scenario: setScaleMode is option-only

- GIVEN a built chart
- WHEN `setScaleMode("log")` runs
- THEN the right price scale mode changes and neither `setData` nor `update` is called

#### Scenario: Build re-applies the scale

- GIVEN `state.scaleMode="percentage"`
- WHEN `build(state)` runs
- THEN the new chart's right price scale mode is Percentage

#### Scenario: Rebuild preserves drawings and SMC

- GIVEN loaded drawings/SMC
- WHEN a chart-type change rebuilds the chart
- THEN `buildChart()` re-attaches both primitives

#### Scenario: HA live is update-only

- GIVEN an HA chart with fresh `setCandles` history
- WHEN a live push lands on a new bar
- THEN the bar is transformed with chained HA state and applied via `update()` only
