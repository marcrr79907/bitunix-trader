# Delta for market-chart

Issue #119 (F6): the measure tool and the position tool enter the layered module
inventory. This MODIFIES R14 (inventory gains `measure-core.js`/`position-core.js`
as pure cores + `controllers/measure.js`; `MODULE_ALLOWLIST` +2,
`CONTROLLER_ALLOWLIST` 11→12; `test_market_ux.py` count 12), R18 and R20 (the seam
stays 8 keys, `STORE_KEYS` stays 11, and the only new bus events remain the
existing set — position reuses `drawing:changed`/`drawing:selected`; measure adds
none). R1–R13, R15–R17, R19, R21–R23 stay in force and unmodified.

## MODIFIED Requirements

### Requirement: R14 — Layered ESM module boundary

Modules MUST follow a frozen inventory: entry `chart.js` (thin: Django-injected
`CONFIG` + imports + `boot()`), pure cores `chart-core.js`/`drawing-core.js`/
`smc-overlay-core.js`/`legend-core.js`/`indicator-settings-core.js`/
`chart-types-core.js`/`theme-core.js`/`tool-icons-core.js`/`chart-registry-core.js`/
`measure-core.js`/`position-core.js`, `chart-store.js` (UI/config state ONLY — MUST
NOT hold candle data; its vocabulary is `symbol, interval, indicators, params,
styles, smc, scaleMode, chartType, theme, tool, indicatorVisible`), `chart-bus.js`,
`chart-host.js` (chart/series/panes/scales/crosshair + candle data), the
host-layer sub-module `chart-host-candles.js` (candle channel: `CANDLE_CTORS`,
the candle series, the raw `candles` array, and the incremental HA state;
factory `createCandles(chart, chartType) -> {getCandleSeries, getCandles,
setCandles, updateCandle, remove}`),
`controllers/{indicators,history,stream,drawings,drawing-interaction,smc,toolbar,
legend,draw-toolbar,object-tree,preference,measure}.js`,
and `main.js` (ALL orchestration + boot/switch). No module MUST exceed ~300 lines.
Controllers MUST import host/store/bus directly but MUST NOT import `main`;
commands MUST travel the bus, so `main.js` has no circular imports. Every imported
module MUST be served same-origin under `/market/` via its Django route (core →
`MODULE_ALLOWLIST`, controller → `CONTROLLER_ALLOWLIST`); `MODULE_ALLOWLIST`
(`views.py:44-63`) MUST include `measure-core` and `position-core`. The size rule
MUST be enforced by the committed guard `tests/web/test_module_size_guard.py`
(`CEILING = 300`; scans `web/market/templates/market/**/*.js` via `rglob` +
`splitlines()`). The guard's `ALLOWLIST` MUST be empty — no module is exempt.
`chart-host.js` MUST be ≤ ~300 lines. Any module above `CEILING` MUST fail the
guard.
(Previously: the pure-core list had no `measure-core`/`position-core`; the
controller inventory had 11 entries and no `measure`.)

#### Scenario: Inventory and no-cycle

- GIVEN the delivered modules
- WHEN imports resolve
- THEN the inventory (including `measure-core.js`, `position-core.js`, and `controllers/measure.js`) exists, no controller imports `main`, and `main.js` has no cycles

#### Scenario: Store never holds candles

- GIVEN `chart-store.js`
- WHEN its keys are inspected
- THEN it holds only UI/config (`symbol, interval, indicators, params, styles, smc, scaleMode, chartType, theme, tool, indicatorVisible`) — no candle data

#### Scenario: Size ceiling with empty allowlist

- GIVEN every module
- WHEN `tests/web/test_module_size_guard.py` reads line counts
- THEN it passes at `CEILING = 300` with an EMPTY `ALLOWLIST`, `chart-host.js` and `smc.js`/`object-tree.js` stay ≤ 300, and any module above the ceiling fails

#### Scenario: New cores and controller are served

- GIVEN `measure-core`, `position-core`, and `controllers/measure`
- WHEN requested under `/market/` with a JS MIME type
- THEN each is served 200 (present in the matching allowlist; missing → 404 → blank chart)

#### Scenario: Controller allowlist count grows

- GIVEN `CONTROLLER_ALLOWLIST`
- WHEN inspected
- THEN it holds **12** entries and `tests/web/test_market_ux.py` asserts the count `== 12` and passes unedited elsewhere — the 11 prior entries plus `measure`

### Requirement: R18 — Test-seam preservation

The refactor MUST expose `window.marketChart` with frozen keys `{chart,
candleSeries, panes, ready, drawings, smc, smcCounts, smcToggles}` and equivalent
update-timing, and MUST re-expose `window.SmcOverlayCore` as the sanctioned test
seam. The toolbar, the object tree, indicator visibility, the F5 vertical toolbar,
and the F6 measure/position tools MUST NOT add a 9th key; the measure readout MUST
be asserted via its DOM node and the position via `window.marketChart.drawings`
(existing) plus the captured POST/PUT, never via a new seam key.
`tests/web/test_market_e2e.py` MUST stay green except for the assertions that
covered the DOM this change removes; each such assertion MUST be replaced by
equivalent coverage, documented in the E2E itself.
(Previously: the clause was silent on the measure/position tools.)

#### Scenario: Seam shape frozen

- GIVEN a booted chart after the toolbar and tree exist with the measure and position tools
- WHEN `window.marketChart` is read
- THEN all eight keys exist and update as before, with no measure/position key added

#### Scenario: Measure has no seam key

- GIVEN a completed measurement
- WHEN `window.marketChart` is read
- THEN it still has exactly 8 keys and the readout is observed through its `aria-live` DOM node

#### Scenario: SMC core reachable

- GIVEN the ESM entry loaded
- WHEN `window.SmcOverlayCore.setupMarkers(...)` is called
- THEN it returns the marker array as before

### Requirement: R20 — Shell change stays inside the frozen host/seam envelope

The `autoSize: true` host option, the `#chart` markup change, the F8 chart-type
and scale controls, the theme control, the F5 vertical toolbar, the object tree,
the indicator-visibility toggle, and the F6 measure/position tools MUST stay
within R14 (host owns construction) and MUST NOT add a `window.marketChart` key.
`window.marketChart` MUST keep exactly its 8 frozen keys `{chart, candleSeries,
panes, ready, drawings, smc, smcCounts, smcToggles}` and `window.SmcOverlayCore`
MUST be untouched. The E2E seam shape and timing (R18) and the single-write-path
invariants (R17) MUST be preserved. F8 added exactly one bus event,
`scale:changed` (`{mode}`); F5 MUST add exactly ONE more, `indicator:visibility`
(`{token, visible}`), routed by `main` to the host's option-only
`setSeriesVisible`. Drawing hide/lock MUST reuse the existing `drawing:changed`
event and MUST NOT add a drawing event; the live theme flip MUST go through the
host's option-only `setTheme` method, not a new event. The F6 position tool MUST
reuse the existing `drawing:changed`/`drawing:selected` events and the measure
tool MUST add NO bus event.
(Previously: the envelope was silent on measure/position; it forbade a 9th key and
a third new event.)

#### Scenario: Seam stays 8 keys

- GIVEN a booted chart after the toolbar and tree with the measure and position tools
- WHEN `window.marketChart` is read
- THEN exactly the 8 frozen keys exist and no measure/position key was added

#### Scenario: Exactly one new bus event (unchanged set)

- GIVEN the change
- WHEN the bus events are inspected
- THEN the only events are the pre-existing set plus `scale:changed` plus `indicator:visibility`; the position tool reuses `drawing:changed`/`drawing:selected` and the measure tool adds none — no `measure:*`/`position:*` event exists

#### Scenario: Measure and position render option-only

- GIVEN a built chart with the `setData`/`update` spies installed
- WHEN a measure drag runs or a position is dragged
- THEN each renders via `requestUpdate` (primitive) and neither `setData` nor `update` is called

#### Scenario: Existing E2E stays green except replaced assertions

- GIVEN the existing E2E assertions
- WHEN the suite runs after the change
- THEN they pass except for assertions covering removed DOM (replaced and documented per R18) and the default type stays candles
