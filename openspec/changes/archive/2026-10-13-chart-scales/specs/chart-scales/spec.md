# chart-scales Specification

## Purpose

User-global chart type and price-scale mode for the layered ESM chart (issue #121,
Fase F8). New capability — no prior spec. Heikin Ashi is a pure OHLC→HA transform
(v5 has no HA series); scale mode is a price-scale option (no data rewrite, #68).

## Requirements

### Requirement: CS1 — `chart-types-core` contract

`chart-types-core.js` MUST be a pure core that imports no module and MUST export:
`CHART_TYPES` (frozen `["candles","line","area","heikin-ashi"]`),
`SCALE_MODES` (frozen `["linear","log","percentage"]`), `isLineLike(type)`,
`heikinAshi(candles)`, and `toChartData(type, candles)`. It MUST be deterministic
and MUST NOT throw for any input (unknown type/scale, empty, or malformed candles).
`heikinAshi` MUST apply: `haClose=(o+h+l+c)/4`; `haOpen = i===0 ? (o+c)/2 :
(prevHaOpen+prevHaClose)/2`; `haHigh=max(h,haOpen,haClose)`;
`haLow=min(l,haOpen,haClose)`; it MUST preserve `time` and round nothing.
`toChartData` MUST return `[{time,open,high,low,close}]` for
`candles`/`heikin-ashi` and `[{time,value}]` (value = close) for `line`/`area`.
The module MUST be served same-origin (added to `MODULE_ALLOWLIST`).

#### Scenario: HA matches the recursive formula

- GIVEN candles `[{o:10,h:12,l:9,c:11},{o:11,h:13,l:10,c:12}]`
- WHEN `heikinAshi(candles)` runs
- THEN bar 0 is `{haOpen:10.5,haClose:10.5,haHigh:12,haLow:9}` and bar 1 `haOpen:10.5`, `haClose:11.5`, `haHigh:13`, `haLow:10`

#### Scenario: Empty input is safe

- GIVEN `[]`
- WHEN `heikinAshi([])` or `toChartData("line", [])` runs
- THEN it returns `[]` without throwing

#### Scenario: Single candle uses the first-bar branch

- GIVEN one candle
- WHEN `heikinAshi` runs
- THEN `haOpen=(o+c)/2` (not `(prevHaOpen+prevHaClose)/2`)

#### Scenario: Unknown type never throws

- GIVEN `type="notreal"`
- WHEN `toChartData(type, candles)` runs
- THEN it degrades to the candle mapping and does not throw

#### Scenario: Line-like mapping

- GIVEN `type="line"` or `"area"`
- WHEN `toChartData` runs
- THEN each point is `{time,value}` with `value === c`

#### Scenario: Core is pure and served

- GIVEN the module
- WHEN imports are inspected and it is requested under `/market/`
- THEN it imports nothing and is served 200 with a JS MIME type

### Requirement: CS2 — Price-scale mode contract

A scale change MUST be applied via `chart.priceScale("right").applyOptions({mode})`
using the `LightweightCharts.PriceScaleMode` symbol (never a magic number), reusing
the same series data (#68). It MUST NOT issue `setData`/`update`. The scale MUST be
re-applied inside `build()` after `createChart`. A new bus event `scale:changed`
(`{mode}`) MUST drive a host option only — no rebuild, no `fetchHistory`. An
invalid mode MUST fall back to `linear` without throwing.

#### Scenario: Scale applies without a data write

- GIVEN a booted chart
- WHEN `setScaleMode("log")` runs
- THEN `chart.priceScale("right").options().mode` is Logarithmic and no `setData`/`update` occurs

#### Scenario: Re-applied on rebuild

- GIVEN `scaleMode="percentage"`
- WHEN the chart rebuilds (chart-type change)
- THEN the new chart's right price scale mode is Percentage

#### Scenario: Unknown scale falls back to linear

- GIVEN `setScaleMode("bogus")`
- WHEN applied
- THEN the mode is `linear` and no error is thrown

### Requirement: CS3 — Chart-type rebuild contract

A chart-type change MUST route through `build()`/`rebuild()` (a v5 series cannot
change type in place). `build()` MUST select the Ctor from `state.chartType`:
`candles`/`heikin-ashi` → `CandlestickSeries`, `line` → `LineSeries`, `area` →
`AreaSeries`. After every rebuild the drawings and SMC primitives MUST re-attach
(`attachAllDrawings()` + `attachSmcLayer()`), preserving the F0–F3 re-attach path.
Overlay/pane indicator series MUST be unchanged across chart types.

#### Scenario: Each type builds its Ctor

- GIVEN each of `candles`,`line`,`area`,`heikin-ashi`
- WHEN the chart is built
- THEN `candleSeries` is the matching v5 series type

#### Scenario: Type change goes through rebuild

- GIVEN a rendered chart with drawings and SMC
- WHEN the chart type changes
- THEN `build()` runs once and drawings/SMC re-attach (`window.marketChart.drawings` populated)

#### Scenario: Indicators survive a type change

- GIVEN active overlay/pane indicators
- WHEN the chart type changes
- THEN the indicator series are rebuilt on the same panes

### Requirement: CS4 — Heikin Ashi live contract

The host MUST carry incremental HA state (`lastHaOpen`/`lastHaClose`) and MUST
apply HA to both history and live data. History (`setCandles`) MUST reset the HA
state and write the transformed series via `setData`; each live `updateCandle` MUST
transform the forming/current bar via `update()` only (#68). A new bar MUST derive
its `haOpen` from the previous bar's HA state.

#### Scenario: Live push uses update only

- GIVEN an active HA chart
- WHEN a WS push arrives
- THEN the transformed bar is applied via `update()` and no full-series `setData` occurs

#### Scenario: New bar chains HA state

- GIVEN HA history ending at bar N
- WHEN the first push of bar N+1 arrives
- THEN its `haOpen = (prevHaOpen+prevHaClose)/2`

#### Scenario: setCandles resets HA state

- GIVEN prior HA state
- WHEN `setCandles` loads a fresh page
- THEN the HA state is recomputed from the new first bar

#### Scenario: Non-HA types are untouched

- GIVEN `chartType="candles"`
- WHEN history/live writes run
- THEN bars are written verbatim (no transform)

### Requirement: CS5 — UI control contract

The toolbar MUST render two native `<select>` controls (scale mode; chart type)
with accessible names, options built from `SCALE_MODES`/`CHART_TYPES`, above the
fold and CSP-safe. Changing scale MUST emit `scale:changed` (`{mode}`); changing
type MUST emit `config:changed`-style rebuild (via `indicator:changed`) so `main`
owns the rebuild. Controls MUST reflect the restored preference on boot.

#### Scenario: Selects are present and labelled

- GIVEN the rendered `/market/` page
- WHEN the controls are inspected
- THEN both `<select>`s exist with accessible names and no inline handler

#### Scenario: Scale select emits the light event

- GIVEN the scale select
- WHEN a different mode is chosen
- THEN exactly one `scale:changed` is emitted and no `fetchHistory` occurs

#### Scenario: Type select triggers rebuild

- GIVEN the type select
- WHEN a different type is chosen
- THEN a rebuild event is emitted and the chart rebuilds once

#### Scenario: Controls restore the preference

- GIVEN a saved `scale_mode`/`chart_type`
- WHEN the page boots
- THEN each select reflects the saved value

### Requirement: CS6 — Persistence contract

`scale_mode`/`chart_type` MUST persist user-global via `ChartPreference` and
`/market/api/preference` (see `chart-config` delta). Boot MUST read both before
the first build; a failed/empty fetch MUST fall back to `linear`/`candles` without
blocking boot. A change MUST debounce-PUT only the changed field; a failed save
MUST be non-fatal.

#### Scenario: Round-trip persists the pair

- GIVEN a saved `scale_mode="log"` and `chart_type="area"`
- WHEN the page reloads
- THEN the chart boots log/area and the selects reflect them

#### Scenario: Fetch failure falls back

- GIVEN the preference fetch fails
- WHEN the page boots
- THEN the chart boots linear/candles (never blank) and boot is not blocked

#### Scenario: Only the changed field is sent

- GIVEN an active chart
- WHEN only the chart type changes
- THEN the PUT body carries `chart_type` only

### Requirement: CS7 — Boundary, seam, no dependency

No `src/` change, no new runtime dependency, CSP unchanged. `window.marketChart`
MUST keep exactly its 8 frozen keys — type/scale MUST NOT be added to it. Indicators
and SMC MUST stay computed from real OHLC server-side (HA affects the candle series
only). `Candle` stays read-only.

#### Scenario: Seam stays 8 keys

- GIVEN a booted chart
- WHEN `window.marketChart` is read
- THEN exactly 8 keys exist and no type/scale key was added

#### Scenario: No dependency or CSP change

- GIVEN the change
- WHEN manifest, `src/` and the CSP header are inspected
- THEN no dep was added, `src/` is untouched, and the CSP equals the prior value

## Edge-Case Matrix

| Case | Input | Expected |
|------|-------|----------|
| Empty candles | `[]` | `heikinAshi`/`toChartData` → `[]`, no throw |
| Single candle | one bar | first-bar `haOpen=(o+c)/2` |
| Short page | 2 bars | recursive chain, no gap |
| Unknown chart type | `"notreal"` | candles mapping, no throw |
| Unknown scale | `"bogus"` | `linear`, no throw |
| Missing preference | GET miss | `linear`/`candles`, `exists:false` |
| HA live new bar | first push of N+1 | `haOpen` from prev HA state, `update()` only |
| A≠B | B reads/writes | B gets own defaults, A untouched |
