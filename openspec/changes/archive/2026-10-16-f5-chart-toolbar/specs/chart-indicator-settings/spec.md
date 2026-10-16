# Delta for chart-indicator-settings

Issue #118 (F5): indicator visibility becomes persistent (layout entry gains
optional `visible?`; absent = true) and the host gains an option-only
`setSeriesVisible`. This MODIFIES F2.4 (the `styles` store slot family gains the
`indicatorVisible` slot), F2.5 (host apply contract adds `setSeriesVisible`), and
F2.7 (the layout round-trip carries `visible`). F2.1–F2.3, F2.6, F2.8–F2.10 stay in
force and unmodified.

## MODIFIED Requirements

### Requirement: F2.4 — Style store slot

The chart store MUST gain a `styles` slot (`{token: style}`) that is a top-level
key, NOT nested under `params`. `STORE_KEYS` MUST include `styles`. A style change
MUST flow through `readState()` into `rebuild()` so re-render is the existing
config-change path. Styles MUST NOT enter `params` (which serializes into the
kline query). The store MUST ALSO gain an `indicatorVisible` slot (`{token: bool}`)
as a top-level key and `STORE_KEYS` MUST include it; it is the reactive source the
object tree reads and MUST NOT enter `params`.
(Previously: the store slot family was `styles` only; no visibility key.)

#### Scenario: Store vocabulary

- GIVEN `STORE_KEYS`
- WHEN inspected
- THEN it contains `styles` and `indicatorVisible`, and the store still holds no candle data

#### Scenario: No style leak into params

- GIVEN a saved style for `sma`
- WHEN the kline URL is built
- THEN no `color`/`lineWidth`/`precision` key appears in the query string

#### Scenario: No visibility leak into params

- GIVEN `indicatorVisible.sma20 = false`
- WHEN the kline URL is built
- THEN no `visible` key appears in the query string

### Requirement: F2.5 — Host apply contract

`host.build(state)` MUST read `state.styles[token]` per series, falling back to
the registry default when absent, and MUST apply `color`/`lineWidth` at series
construction and `precision` as the series `priceFormat`
(`{precision, minMove: 10^-precision}`). A style change MUST travel
`indicator:changed` → `rebuild()` (the `setData` path); the live WS `update()`
path MUST remain the sole writer for candles (#68). Precision MUST NOT mutate the
legend `DECIMALS` map. The host MUST expose `setSeriesVisible(token, bool)`,
applying `series.applyOptions({visible})` on the active series for that token
(option-only; no `setData`/`update`, mirroring `setTheme` `main.js:230-233`); when
`state.indicatorVisible[token]` is `false` at build time the series MUST still be
built and immediately set hidden via the same option-only path (no rebuild). The
one-rebuild invariant MUST be proven by a committed E2E
(`tests/web/test_market_e2e.py`) wrapping the CDN global
`LightweightCharts.createChart` as a counter (NOT a `window.marketChart` key) and
asserting `=== 1` builds after one confirmed style change; the legend
style-independence MUST be proven by committed source assertions in
`tests/js/legend-core.test.js`.
(Previously: the host had no visibility method; hidden-at-build was undefined.)

#### Scenario: Series reflects style

- GIVEN `styles.sma = {color:"#ff0000", lineWidth:3, precision:5}`
- WHEN the chart builds
- THEN the `sma` series `options()` have that color/lineWidth and priceFormat precision 5

#### Scenario: Missing style uses registry default

- GIVEN no `styles` entry for `ema`
- WHEN the chart builds
- THEN the `ema` series uses the registry color, width 1

#### Scenario: setSeriesVisible is option-only

- GIVEN a built chart with a hidden token
- WHEN `setSeriesVisible("sma20", true)` runs
- THEN the series option `visible` becomes true and neither `setData` nor `update` is called

#### Scenario: Hidden at build stays option-only

- GIVEN `state.indicatorVisible.sma20 === false`
- WHEN `build(state)` runs
- THEN the `sma20` series is constructed and set hidden via `applyOptions` with no rebuild after boot

#### Scenario: One rebuild per style change (#68 intact)

- GIVEN an active chart with the `createChart` counter installed
- WHEN a style is confirmed
- THEN exactly one `rebuild()` runs on the `setData` path and no live-path full `setData` occurs

#### Scenario: Legend output ignores style precision

- GIVEN `legend-core.js` and `controllers/legend.js` sources
- WHEN `tests/js/legend-core.test.js` scans them
- THEN neither contains a `styles`/`priceFormat` read

### Requirement: F2.7 — Persistence round-trip and style validation

The client PUT payload MUST carry each indicator's optional `style` AND optional
`visible` alongside `token`/`params`. The server MUST preserve and validate both
verbatim: `PUT` with `style`/`visible` → `GET` returns them; an invalid style MUST
yield 400 before any write; a non-boolean `visible` MUST yield 400 before any
write. `parse_layout_indicators` MUST accept and coerce `visible` (absent = true)
and MUST preserve it on read; NO migration is required (the `indicators` JSON
column is open-ended, `models.py:217-221`).
(Previously: only `style` round-tripped; `visible` did not exist.)

#### Scenario: Round-trip verbatim

- GIVEN PUT `indicators=[{token:"sma",params:{sma_len:50},style:{color:"#ff0000",lineWidth:2,precision:4},visible:false}]`
- WHEN GET the same key
- THEN the returned entry carries that exact `style` and `visible:false`

#### Scenario: Absent visible defaults to true

- GIVEN PUT `indicators=[{token:"sma"}]` (no `visible`)
- WHEN GET the same key
- THEN the entry is treated as visible (absent or `true`)

#### Scenario: Bad style or non-bool visible → 400, no write

- GIVEN PUT with `style:{lineWidth:9}` or `visible:"yes"`
- WHEN handled
- THEN 400 `{"error":"..."}` and the stored layout is unchanged
