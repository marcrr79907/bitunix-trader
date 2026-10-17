# chart-measure Specification

## Purpose

Ephemeral measure tool for the market chart (issue #119, F6). A pointer
press-drag-release between two points reports price Δ (abs + %), elapsed time,
bar count, and candle count. It is a **gesture**, not a `Drawing`: no persistence,
no server call, no object-tree row. It renders on the primitive layer
(#68 single-write-path) with a DOM `aria-live` readout. New capability — no prior
spec; the substrate is F5 (`openspec/changes/archive/2026-10-16-f5-chart-toolbar/`).

## Requirements

### Requirement: R1 — Ephemeral measure gesture

The measure tool MUST start a measurement on `pointerdown` over the plot area
while `store.tool === "measure"`, update it on `pointermove`, and finish it on
`pointerup`. The measurement MUST be ephemeral: it MUST NOT POST/PUT any drawing,
MUST NOT create an object-tree row, and MUST NOT be persisted across reload or
`switchTo`. Starting a new measurement MUST replace the previous one. The measure
controller MUST own its `#chart` pointer listeners and MUST NOT depend on the
drawing interaction controller's bail (`drawing-interaction.js:94`).

#### Scenario: Drag produces a measurement

- GIVEN `store.tool === "measure"` and a built chart
- WHEN the pointer presses, moves, and releases between two points
- THEN a measurement exists between those two points
- AND no `POST`/`PUT` to `/market/api/drawings` is captured on release or after

#### Scenario: New measure replaces the old

- GIVEN an existing measurement
- WHEN a second press-drag-release completes elsewhere
- THEN only the second measurement remains

#### Scenario: No object-tree row

- GIVEN a completed measurement
- WHEN `window.marketChart.drawings` is read
- THEN it is unchanged and no tree row for a measure exists

### Requirement: R2 — Readout content from the pure core

The measurement MUST report price Δ absolute, price Δ %, elapsed time, bar count,
and candle count, all computed by the pure `market/measure-core.js`. Bar/candle
count MUST reuse `intervalSeconds` from `chart-core.js` (single source) rather
than re-deriving interval math. The core MUST be pure (no DOM, no chart lib) and
MUST import the `chart-core` helper.

#### Scenario: Delta readout

- GIVEN point A `{time,price}` and point B `{time,price}` with a known interval
- WHEN `measure(a,b,intervalSeconds)` runs
- THEN it returns `{priceDelta, pricePct, timeDelta, bars, candles}` matching the inputs

#### Scenario: Core is pure and reuses intervalSeconds

- GIVEN `measure-core.js` source
- WHEN inspected
- THEN it has no DOM access and imports `intervalSeconds` from `chart-core.js`

### Requirement: R3 — Render contract (#68)

The measure MUST draw on ONE primitive attached to `host.getCandleSeries()` while
a measurement exists, using `CanvasRenderingTarget2D` (no DOM). Its
`autoscaleInfo` MUST return `null` so a measurement never moves the price scale.
Redraw MUST use the primitive's `requestUpdate` only; a measurement MUST NEVER
call `setData`/`update` on the series.

#### Scenario: autoscaleInfo null

- GIVEN an active measurement primitive
- WHEN `autoscaleInfo` is queried
- THEN it returns `null`

#### Scenario: Redraw never touches series data

- GIVEN a drag in progress with `setData`/`update` spies installed
- WHEN the measurement re-renders
- THEN `requestUpdate` is used and neither `setData` nor `update` reaches the series

### Requirement: R4 — Cancel and clear

`Escape` (owned by the measure controller) MUST cancel the in-progress
measurement; changing the active tool MUST cancel it; switching `symbol` MUST
clear it. Cancel MUST remove the primitive via `requestUpdate`/detach and MUST
NOT persist anything.

#### Scenario: Escape cancels

- GIVEN an in-progress measurement
- WHEN `Escape` is pressed
- THEN the measurement clears and no drawing is written

#### Scenario: Tool change cancels

- GIVEN an active or in-progress measurement
- WHEN `store.tool` changes away from `"measure"`
- THEN the measurement clears

#### Scenario: Symbol switch clears

- GIVEN a completed measurement on `BTCUSDT`
- WHEN the chart switches to `ETHUSDT`
- THEN no measurement primitive remains

### Requirement: R5 — a11y, CSP, size, and seam bounds

The numeric readout MUST live in a DOM node with `aria-live="polite"` (mirroring
`#rsi` in `chart.html:47`). The measure tool MUST NOT add an inline handler or
inline script — no CSP relaxation. `controllers/measure.js` MUST stay ≤300 lines
and live in `CONTROLLER_ALLOWLIST`. `window.marketChart` MUST keep exactly its 8
frozen keys and `STORE_KEYS` MUST stay 11 (measure adds no key).

#### Scenario: Live readout

- GIVEN a completed measurement
- WHEN the DOM is inspected
- THEN a `[aria-live="polite"]` node carries the price/time/bar/candle figures

#### Scenario: Bounds hold

- GIVEN the delivered modules
- WHEN the size guard, the allowlist check, and the seam check run
- THEN `measure.js` is ≤300 and served 200, `window.marketChart` has 8 keys, and `STORE_KEYS` has 11
