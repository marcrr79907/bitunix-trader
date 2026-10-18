# Delta for market-chart

Issue #122 (F9): the layered module inventory gains the three pure cores
`drawing-tools-core.js`/`fib-tools-core.js`/`drawing-click-flow-core.js`;
`MODULE_ALLOWLIST` +3 (`views.py:44`) and `CONTROLLER_ALLOWLIST` is UNCHANGED (no
new controller). The click flow moves OUT of `controllers/drawings.js` into
`drawing-click-flow-core.js` (ceiling-forced — `drawings.js`=298, ceiling 300), so
no controller is added or removed. This MODIFIES R14 (inventory + `MODULE_ALLOWLIST`).
R18 and R20 are restated to confirm the seam stays 8 keys, `STORE_KEYS` stays 11,
and no new bus event is added. R1–R13, R15–R17, R19, R21–R23 stay in force and
unmodified.

## MODIFIED Requirements

### Requirement: R14 — Layered ESM module boundary

Modules MUST follow a frozen inventory: entry `chart.js` (thin: Django-injected
`CONFIG` + imports + `boot()`), pure cores `chart-core.js`/`drawing-core.js`/
`smc-overlay-core.js`/`legend-core.js`/`indicator-settings-core.js`/
`chart-types-core.js`/`theme-core.js`/`tool-icons-core.js`/`chart-registry-core.js`/
`add-indicator-core.js`/`measure-core.js`/`position-core.js`/`position-draft-core.js`/
`readout-coalesce-core.js`/`history-core.js`/`context-menu-core.js`/
`drawing-tools-core.js`/`fib-tools-core.js`/`drawing-click-flow-core.js`,
`chart-store.js` (UI/config state ONLY — MUST NOT hold candle data; its vocabulary
is `symbol, interval, indicators, params, styles, smc, scaleMode, chartType, theme,
tool, indicatorVisible`), `chart-bus.js`, `chart-host.js` (chart/series/panes/
scales/crosshair + candle data), the
host-layer sub-module `chart-host-candles.js` (candle channel: `CANDLE_CTORS`,
the candle series, the raw `candles` array, and the incremental HA state;
factory `createCandles(chart, chartType) -> {getCandleSeries, getCandles,
setCandles, updateCandle, remove}`),
`controllers/{indicators,history,stream,drawings,drawing-interaction,smc,toolbar,
legend,draw-toolbar,object-tree,preference,measure,position-seed,undo,context-menu}.js`,
and `main.js` (ALL orchestration + boot/switch). No module MUST exceed ~300 lines.
Controllers MUST import host/store/bus directly but MUST NOT import `main`;
commands MUST travel the bus, so `main.js` has no circular imports. Every imported
module MUST be served same-origin under `/market/` via its Django route (core →
`MODULE_ALLOWLIST`, controller → `CONTROLLER_ALLOWLIST`); `MODULE_ALLOWLIST`
(`views.py:44-65`) MUST include `measure-core`, `position-core`,
`position-draft-core`, `readout-coalesce-core`, `history-core`, `context-menu-core`,
`drawing-tools-core`, `fib-tools-core`, and `drawing-click-flow-core`;
`CONTROLLER_ALLOWLIST`
(`views.py:66-81`) MUST include `measure`, `position-seed`, `undo`, and
`context-menu` (15 entries — UNCHANGED by F9). The size rule
MUST be enforced by the committed guard `tests/web/test_module_size_guard.py`
(`CEILING = 300`; scans `web/market/templates/market/**/*.js` via `rglob` +
`splitlines()`). The guard's `ALLOWLIST` MUST be empty — no module is exempt.
`chart-host.js` MUST be ≤ ~300 lines. Any module above `CEILING` MUST fail the
guard. `smc.js` (300) and `object-tree.js` (299) MUST stay byte-untouched.
(Previously: the pure-core list had no `drawing-tools-core`/`fib-tools-core`/
`drawing-click-flow-core`.)

#### Scenario: Inventory and no-cycle

- GIVEN the delivered modules, WHEN imports resolve, THEN the inventory (including `drawing-tools-core.js`, `fib-tools-core.js`, `drawing-click-flow-core.js`, `theme-core.js`, `history-core.js`, `context-menu-core.js`, and `controllers/undo.js`/`controllers/context-menu.js`) exists, `theme-core.js` imports nothing, no controller imports `main`, and `main.js` has no cycles

#### Scenario: Store never holds candles

- GIVEN `chart-store.js`, WHEN its keys are inspected, THEN it holds only UI/config (`symbol, interval, indicators, params, styles, smc, scaleMode, chartType, theme, tool, indicatorVisible`) — no candle data

#### Scenario: Size ceiling with empty allowlist

- GIVEN every module, WHEN `tests/web/test_module_size_guard.py` reads line counts
- THEN it passes at `CEILING = 300` with an EMPTY `ALLOWLIST`, `drawings.js` SHRINKS (click flow extracted), `smc.js`/`object-tree.js` are byte-untouched, and any module above the ceiling fails

#### Scenario: New cores are served

- GIVEN `drawing-tools-core`, `fib-tools-core`, and `drawing-click-flow-core`
- WHEN requested under `/market/` with a JS MIME type
- THEN each is served 200 (present in `MODULE_ALLOWLIST`; missing → 404 → blank chart; `test_market_ux.py::test_f9_cores_are_served`)

#### Scenario: Controller allowlist count unchanged

- GIVEN `CONTROLLER_ALLOWLIST`
- WHEN inspected
- THEN it holds **15** entries and `tests/web/test_market_ux.py` asserts the count `== 15` and passes unedited — F9 adds no controller (the click flow is a pure core)

#### Scenario: No behavior change

- GIVEN the change, WHEN the node tests and the E2E suite run
- THEN they pass with no behavior-assertion edits beyond the added F9 cases, the 8-key seam (`window.marketChart`) is unchanged, and the HA contract (`chart-types-core`) is untouched

### Requirement: R18 — Test-seam preservation

The refactor MUST expose `window.marketChart` with frozen keys `{chart,
candleSeries, panes, ready, drawings, smc, smcCounts, smcToggles}` and equivalent
update-timing, and MUST re-expose `window.SmcOverlayCore` as the sanctioned test
seam. The toolbar, the object tree, indicator visibility, the F5 vertical toolbar,
the F6 measure/position tools, the F7 undo/context-menu layer, and the F9 drawing
tools MUST NOT add a 9th key; the measure readout MUST be asserted via its DOM node
(`#measure-readout`) and a position via `window.marketChart.drawings` (existing)
plus the captured POST/PUT, never via a new seam key; the F7 undo/redo via captured
POST/PUT/DELETE and the context menu via its DOM `role="menu"`, never via a new
seam key. The F9 kinds MUST be asserted via `window.marketChart.drawings` (existing)
plus the captured POST/PUT/DELETE and their rendered DOM/canvas, never via a new
seam key. Every removed/edited scenario MUST have an equivalent replacement.
(Previously: the clause was silent on the F9 drawing tools.)

#### Scenario: Seam shape frozen

- GIVEN a booted chart after the toolbar and tree exist with the measure, position, undo, context-menu, and F9 drawing layers
- WHEN `window.marketChart` is read
- THEN all eight keys exist and update as before, with no toolbar/tree/visibility/measure/position/undo/menu/F9 key added

#### Scenario: F9 kinds assert without a seam key

- GIVEN an F9 drawing created, moved, then deleted
- WHEN it is observed
- THEN it is asserted via `window.marketChart.drawings` and the captured POST/PUT/DELETE, and `window.marketChart` still has exactly 8 keys

#### Scenario: SMC core reachable

- GIVEN the ESM entry loaded
- WHEN `window.SmcOverlayCore.setupMarkers(...)` is called
- THEN it returns the marker array as before

### Requirement: R20 — Shell change stays inside the frozen host/seam envelope

The `autoSize: true` host option, the `#chart` markup change, the F8 chart-type
and scale controls, the theme control, the F5 vertical toolbar, the object tree,
the indicator-visibility toggle, the F6 measure/position tools, the F7
undo/context-menu layer, and the F9 drawing tools MUST stay within R14 (host owns
construction) and MUST NOT add a `window.marketChart` key. `window.marketChart`
MUST keep exactly its 8 frozen keys `{chart, candleSeries, panes, ready, drawings,
smc, smcCounts, smcToggles}` and `window.SmcOverlayCore` MUST be untouched. The E2E
seam shape and timing (R18) and the single-write-path invariants (R17) MUST be
preserved. F8 added exactly one bus event, `scale:changed` (`{mode}`); F5 added
exactly ONE more, `indicator:visibility` (`{token, visible}`), routed by `main` to
the host's option-only `setSeriesVisible` (mirroring `scale:changed`,
`main.js:179-182`). Drawing hide/lock MUST reuse the existing `drawing:changed`
event; the live theme flip MUST go through the host's option-only `setTheme`
method, not a new event. The theme value MUST live in the store (`state.theme`)
and/or `data-theme`, never in the seam. The F6 position tool MUST reuse the
existing `drawing:changed`/`drawing:selected` events and the measure tool MUST add
NO bus event. The F7 layer MUST add NO bus event to `EVENTS`: undo replays through
the existing commands, and the F7 drawing events are STRING LITERALS handled in
`drawings.js` (not `EVENTS` members). The F9 tools MUST add NO bus event and NO
store key: activating an F9 tool writes the existing `store.tool` value; creating
reuses `createDrawing` (#68) and the existing `drawing:created` literal; `STORE_KEYS`
MUST stay 11. No `history:*`/`undo:*`/`menu:*`/`tool:*`/`fib:*`/`channel:*` event
exists.
(Previously: the envelope was silent on the F9 drawing tools.)

#### Scenario: Seam stays 8 keys

- GIVEN a booted chart after the toolbar and tree with the measure, position, undo, menu, and F9 layers
- WHEN `window.marketChart` is read
- THEN exactly the 8 frozen keys exist and no toolbar/tree/visibility/measure/position/undo/menu/F9 key was added

#### Scenario: Exactly one new bus event (unchanged set)

- GIVEN the change
- WHEN the bus events are inspected
- THEN the only `EVENTS` members are the pre-existing set plus `scale:changed` plus `indicator:visibility`; the F9 tools add none, and the F9 create reuses the `drawing:created` string literal — no `tool:*`/`fib:*`/`channel:*` event and no new `EVENTS` entry exist

#### Scenario: STORE_KEYS stays 11

- GIVEN `chart-store.js` after F9
- WHEN its keys are inspected
- THEN it holds exactly the 11 frozen keys — F9 adds none (new tools reuse `tool`)

#### Scenario: F9 render is option-only

- GIVEN a built chart with the `setData`/`update` spies installed
- WHEN an F9 drawing is created or dragged
- THEN it renders via `requestUpdate` (primitive) and neither `setData` nor `update` is called

#### Scenario: Existing E2E stays green except replaced assertions

- GIVEN the existing E2E assertions
- WHEN the suite runs after the change
- THEN they pass except for any assertion replaced per R18, and the default type stays candles
