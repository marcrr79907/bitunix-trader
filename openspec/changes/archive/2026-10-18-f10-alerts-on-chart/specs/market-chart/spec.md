# Delta for market-chart

Issue #123 (F10): the layered module inventory gains two pure cores
(`alert-markers-core.js`, `alert-condition-core.js`) and one controller
(`controllers/alerts.js`); `MODULE_ALLOWLIST` grows 28→30 (`web/market/views.py:44`)
and `CONTROLLER_ALLOWLIST` 16→17 (`views.py:76`). This MODIFIES R14 (inventory and
allowlists). R18 and R20 are restated to confirm the seam stays 8 keys,
`STORE_KEYS` stays 11, no new bus event exists, and the markers go through
`createSeriesMarkers` (never `setData`/`update`, #68). R1–R13, R15–R17, R19,
R21–R23 stay in force and unmodified; the new JSON endpoint is `alert-rules` R10/R11.

## MODIFIED Requirements

### Requirement: R14 — Layered ESM module boundary

Modules MUST follow a frozen inventory: entry `chart.js` (thin: Django-injected
`CONFIG` + imports + `boot()`), pure cores `chart-core.js`/`drawing-core.js`/
`smc-overlay-core.js`/`legend-core.js`/`indicator-settings-core.js`/
`chart-types-core.js`/`theme-core.js`/`tool-icons-core.js`/`chart-registry-core.js`/
`add-indicator-core.js`/`measure-core.js`/`position-core.js`/`position-draft-core.js`/
`readout-coalesce-core.js`/`history-core.js`/`context-menu-core.js`/
`drawing-tools-core.js`/`fib-tools-core.js`/`drawing-click-flow-core.js`/
`tool-render-core.js`/`object-tree-dom-core.js`/`alert-markers-core.js`/
`alert-condition-core.js`,
`chart-store.js` (UI/config state ONLY — MUST NOT hold candle data; its vocabulary
is `symbol, interval, indicators, params, styles, smc, scaleMode, chartType, theme,
tool, indicatorVisible`), `chart-bus.js`, `chart-host.js` (chart/series/panes/
scales/crosshair + candle data), the
host-layer sub-module `chart-host-candles.js` (candle channel: `CANDLE_CTORS`,
the candle series, the raw `candles` array, and the incremental HA state;
factory `createCandles(chart, chartType) -> {getCandleSeries, getCandles,
setCandles, updateCandle, remove}`),
`controllers/{indicators,history,stream,drawings,drawing-interaction,smc,toolbar,
legend,draw-toolbar,object-tree,preference,measure,position-seed,undo,context-menu,
draft-preview,alerts}.js`,
and `main.js` (ALL orchestration + boot/switch). No module MUST exceed ~300 lines.
Controllers MUST import host/store/bus directly but MUST NOT import `main`;
commands MUST travel the bus, so `main.js` has no circular imports. Every imported
module MUST be served same-origin under `/market/` via its Django route (core →
`MODULE_ALLOWLIST`, controller → `CONTROLLER_ALLOWLIST`); `MODULE_ALLOWLIST`
(`views.py:44-75`, 30 entries) MUST include `measure-core`, `position-core`,
`position-draft-core`, `readout-coalesce-core`, `history-core`, `context-menu-core`,
`drawing-tools-core`, `fib-tools-core`, `drawing-click-flow-core`,
`tool-render-core`, `object-tree-dom-core`, `alert-markers-core`, and
`alert-condition-core`; `CONTROLLER_ALLOWLIST`
(`views.py:76-95`, **17** entries) MUST include `measure`, `position-seed`, `undo`,
`context-menu`, `draft-preview`, and `alerts`. The size rule
MUST be enforced by the committed guard `tests/web/test_module_size_guard.py`
(`CEILING = 300`; scans `web/market/templates/market/**/*.js` via `rglob` +
`splitlines()`). The guard's `ALLOWLIST` MUST be empty — no module is exempt.
`chart-host.js` MUST be ≤ ~300 lines. Any module above `CEILING` MUST fail the
guard. `controllers/smc.js` (300) MUST stay byte-untouched; `controllers/
object-tree.js` (299 before F9) SHRINKS to 263 by moving its row-DOM factories to
`object-tree-dom-core.js`, giving the ceiling back its headroom.
(Previously: the inventory had no `alert-markers-core.js`/`alert-condition-core.js`
and no `controllers/alerts.js`; `MODULE_ALLOWLIST` was 28 and
`CONTROLLER_ALLOWLIST` was 16.)
(Previously: the pure-core list had no `measure-core`/`position-core`/
`position-draft-core`/`readout-coalesce-core`; the controller inventory had 11
entries and no `measure`/`position-seed`.)
(Previously: the pure-core list had no `history-core`/`context-menu-core`; the
controller inventory had 13 entries and no `undo`/`context-menu`.)
(Previously: the pure-core list had no `drawing-tools-core`/`fib-tools-core`/
`drawing-click-flow-core`/`tool-render-core`/`object-tree-dom-core`; the
controller inventory had 15 entries and no `draft-preview`.)

#### Scenario: Inventory and no-cycle

- GIVEN the delivered modules, WHEN imports resolve, THEN the inventory (including `drawing-tools-core.js`, `fib-tools-core.js`, `drawing-click-flow-core.js`, `tool-render-core.js`, `object-tree-dom-core.js`, `alert-markers-core.js`, `alert-condition-core.js`, `theme-core.js`, `history-core.js`, `context-menu-core.js`, and `controllers/undo.js`/`controllers/context-menu.js`/`controllers/draft-preview.js`/`controllers/alerts.js`) exists, `theme-core.js` imports nothing, no controller imports `main`, and `main.js` has no cycles (`test_market_ux.py::test_import_graph_routes_resolve`)

#### Scenario: Store never holds candles

- GIVEN `chart-store.js`, WHEN its keys are inspected, THEN it holds only UI/config (`symbol, interval, indicators, params, styles, smc, scaleMode, chartType, theme, tool, indicatorVisible`) — no candle data

#### Scenario: Size ceiling with empty allowlist

- GIVEN every module, WHEN `tests/web/test_module_size_guard.py` reads line counts
- THEN it passes at `CEILING = 300` with an EMPTY `ALLOWLIST`, `drawings.js` SHRINKS (click flow extracted; 298→282), `object-tree.js` SHRINKS (299→263), `smc.js` is byte-untouched, and any module above the ceiling fails

#### Scenario: New cores are served

- GIVEN `drawing-tools-core`, `fib-tools-core`, `drawing-click-flow-core`, `tool-render-core`, `object-tree-dom-core`, `alert-markers-core`, and `alert-condition-core`
- WHEN requested under `/market/` with a JS MIME type
- THEN each is served 200 (present in `MODULE_ALLOWLIST`; missing → 404 → blank chart; `test_market_ux.py::test_f9_cores_are_served`, `test_f10_alerts_are_served`)

#### Scenario: Controller allowlist count is 16

- GIVEN `CONTROLLER_ALLOWLIST`
- WHEN inspected
- THEN it holds **17** entries and `tests/web/test_market_ux.py:146,195` asserts the count `== 17` and passes — F10 adds exactly one controller (`alerts`) and two pure cores, prior counts 16 / 28

#### Scenario: No behavior change

- GIVEN the change, WHEN the node tests and the E2E suite run
- THEN they pass with no behavior-assertion edits beyond the added F9 cases, the 8-key seam (`window.marketChart`) is unchanged, and the HA contract (`chart-types-core`) is untouched

### Requirement: R18 — Test-seam preservation

The refactor MUST expose `window.marketChart` with frozen keys `{chart,
candleSeries, panes, ready, drawings, smc, smcCounts, smcToggles}` and equivalent
update-timing, and MUST re-expose `window.SmcOverlayCore` as the sanctioned test
seam. The toolbar, the object tree, indicator visibility, the F5 vertical toolbar,
the F6 measure/position tools, the F7 undo/context-menu layer, the F9 drawing
tools, and the F10 alert layer MUST NOT add a 9th key; the measure readout MUST be asserted via its DOM node
(`#measure-readout`) and the position via `window.marketChart.drawings` (existing)
plus the captured POST/PUT, never via a new seam key. The F7 undo layer MUST be
asserted via captured POST/PUT/DELETE and the F7 context menu via its DOM
`role="menu"`, never via a new seam key. The F9 kinds MUST be asserted via
`window.marketChart.drawings` (existing) plus the captured POST/PUT/DELETE and
their rendered DOM/canvas, never via a new seam key.
`tests/web/test_market_e2e.py` MUST stay green except for the
assertions that covered the DOM this change removes (`#drawing-list`, the
indicators `fieldset`); each such assertion MUST be replaced by equivalent
coverage, and the removal + replacement MUST be documented in the E2E itself
(`test_market_e2e.py:582-620`). Every removed scenario has an equivalent
replacement EXCEPT adding-an-indicator, which became the new `chart-indicator-add`
capability (issue #176, slice S5) — so there is no unreplaced coverage gap.
(Previously: the clause read "green with NO assertion edits"; that was unmeetable
by the slice that deletes the DOM — reconciled here per verify W2 / issue #177.
The F6 clause was added for the measure/position tools.)
(Previously: the clause was silent on the F7 undo/context-menu layer.)
(Previously: the clause was silent on the F9 drawing tools.)
(Previously: the clause was silent on the F10 alert layer.)

#### Scenario: Seam shape frozen

- GIVEN a booted chart after the toolbar and tree exist with the measure, position, undo, context-menu, F9 drawing, and alert layers
- WHEN `window.marketChart` is read
- THEN all eight keys exist and update as before, with no toolbar/tree/visibility/measure/position/undo/menu/F9/alert key added

#### Scenario: Measure has no seam key

- GIVEN a completed measurement
- WHEN `window.marketChart` is read
- THEN it still has exactly 8 keys and the readout is observed through its `aria-live` DOM node (E2E `test_shell_keeps_seam_at_eight_keys`; measure asserts `drawings.length == 0`)

#### Scenario: Undo and menu assert without a seam key

- GIVEN an undo/redo or a context-menu command
- WHEN it is observed
- THEN it is asserted via captured POST/PUT/DELETE and the DOM `role="menu"`, and `window.marketChart` still has exactly 8 keys

#### Scenario: F9 kinds assert without a seam key

- GIVEN an F9 drawing created, moved, then deleted
- WHEN it is observed
- THEN it is asserted via `window.marketChart.drawings` and the captured POST/PUT/DELETE, and `window.marketChart` still has exactly 8 keys (E2E `test_f9_tools_create_their_kind_and_drag_is_one_put`)

#### Scenario: Alerts assert without a seam key

- GIVEN an alert created from the bell and a rendered marker set
- WHEN it is observed
- THEN the bell is found by `#chart-alert-bell`, the dialog by `#alert-dialog`, the state summary by `#alert-status[aria-live]`, and the write by the captured POST/PUT/DELETE to `/market/api/alerts`, and `window.marketChart` still has exactly 8 keys

#### Scenario: SMC core reachable

- GIVEN the ESM entry loaded
- WHEN `window.SmcOverlayCore.setupMarkers(...)` is called
- THEN it returns the marker array as before

#### Scenario: Existing E2E green except replaced assertions

- GIVEN the existing E2E assertions
- WHEN the suite runs after the change
- THEN it passes except for the assertions covering the removed `#drawing-list`/`fieldset` DOM, each replaced by equivalent coverage and documented in `test_market_e2e.py:582-620` (and the F9 toolbar count assertion moved 7→15)

### Requirement: R20 — Shell change stays inside the frozen host/seam envelope

The `autoSize: true` host option, the `#chart` markup change, the F8 chart-type
and scale controls, the theme control, the F5 vertical toolbar, the object tree,
the indicator-visibility toggle, the F6 measure/position tools, the F7
undo/context-menu layer, the F9 drawing tools, and the F10 alert bell/dialog/markers MUST stay within R14
(host owns construction) and MUST NOT add a `window.marketChart` key.
`window.marketChart` MUST keep
exactly its 8 frozen keys `{chart, candleSeries, panes, ready, drawings, smc,
smcCounts, smcToggles}` and `window.SmcOverlayCore` MUST be untouched. The E2E
seam shape and timing (R18) and the single-write-path invariants (R17) MUST be
preserved. F8 added exactly one bus event, `scale:changed` (`{mode}`); F5 added
exactly ONE more, `indicator:visibility` (`{token, visible}`), routed by `main` to
the host's option-only `setSeriesVisible` (mirroring `scale:changed`,
`main.js:179-182`). Drawing hide/lock MUST reuse the existing `drawing:changed`
event and MUST NOT add a drawing event; the live theme flip MUST go through the
host's option-only `setTheme` method, not a new event. The theme value MUST live
in the store (`state.theme`) and/or `data-theme`, never in the seam. The F6
position tool MUST reuse the existing `drawing:changed`/`drawing:selected` events
and the measure tool MUST add NO bus event — no `measure:*`/`position:*` event
exists. The F7 layer MUST add NO bus event to `EVENTS`: undo replays through the
existing `drawing:changed`/`drawing:delete` commands, and the F7 drawing events
`drawing:duplicate`/`drawing:restore`/`drawing:created`/`drawing:create-failed`
are STRING LITERALS handled in `drawings.js` (the same literal convention as
`drawing:changed`/`drawing:delete`) — they are NOT `EVENTS` members. No
`history:*`/`undo:*`/`menu:*` event exists. The F9 tools MUST add NO bus event and
NO store key: activating an F9 tool writes the existing `store.tool` value;
creating reuses `createDrawing` (#68) and the existing `drawing:created` literal;
`STORE_KEYS` MUST stay 11. The F10 alert layer MUST add NO bus event and NO store key: `controllers/alerts.js`
reacts to the existing `chart:built` event and its own fetches; the bell, dialog
and marker state live in the controller closure; `STORE_KEYS` MUST stay 11. No
`history:*`/`undo:*`/`menu:*`/`tool:*`/`fib:*`/`channel:*`/`alert:*` event exists.
(Previously: the envelope covered type/scale/theme and forbade a second event; F5
adds exactly one, `indicator:visibility`; the F6 clause was added.)
(Previously: the envelope was silent on the F7 undo/context-menu layer.)
(Previously: the envelope was silent on the F10 alert layer.)
(Previously: the envelope was silent on the F9 drawing tools.)

#### Scenario: Seam stays 8 keys

- GIVEN a booted chart after the toolbar and tree with the measure, position, undo, menu, F9, and alert layers
- WHEN `window.marketChart` is read
- THEN exactly the 8 frozen keys exist and no toolbar/tree/visibility/measure/position/undo/menu/F9/alert key was added (E2E `test_shell_keeps_seam_at_eight_keys`)

#### Scenario: Exactly one new bus event (unchanged set)

- GIVEN the change
- WHEN the bus events are inspected
- THEN the only `EVENTS` members are the pre-existing set plus `scale:changed` plus `indicator:visibility`; the position tool reuses `drawing:changed`/`drawing:selected`, the measure tool adds none, the F9 tools add none (the F9 create reuses the `drawing:created` string literal), and the F7 `drawing:duplicate`/`drawing:restore`/`drawing:created`/`drawing:create-failed` are string literals (not `EVENTS` members) — no `history:*`/`undo:*`/`menu:*`/`tool:*`/`fib:*`/`channel:*` event, no `measure:*`/`position:*` event, no `drawing:visibility`/`drawing:lock` event, and no new `EVENTS` entry exist

#### Scenario: STORE_KEYS stays 11

- GIVEN `chart-store.js` after F10
- WHEN its keys are inspected
- THEN it holds exactly the 11 frozen keys — F9 and F10 add none (F10 keeps alert selection/dialog state in the controller closure; `chart-store.test.js` asserts `length === 11`)

#### Scenario: Visibility toggle is option-only

- GIVEN a built chart with the `setData`/`update` spies installed
- WHEN `indicator:visibility` fires for a token
- THEN the host calls `setSeriesVisible` (option-only) and neither `setData` nor `update` is called

#### Scenario: Measure and position render option-only

- GIVEN a built chart with the `setData`/`update` spies installed
- WHEN a measure drag runs or a position is dragged
- THEN each renders via `requestUpdate` (primitive) and neither `setData` nor `update` is called

#### Scenario: Undo and menu never touch the series data path

- GIVEN a built chart with the `setData`/`update` spies installed
- WHEN an undo replays or a menu command runs
- THEN neither spy is called (replay reuses the HTTP verbs; menu reuses the bus commands)

#### Scenario: F9 render is option-only

- GIVEN a built chart with the `setData`/`update` spies installed
- WHEN an F9 drawing is created or dragged
- THEN it renders via `requestUpdate` (primitive) and neither `setData` nor `update` is called (issue #217; `drawing-primitive.test.js::an F9 primitive never calls setData/update (option-only, #68/#217)` — the throwing-stub proof added in the R1 fix slice)

#### Scenario: Alert markers never touch the series data path

- GIVEN a built chart with the `setData`/`update` spies installed
- WHEN the alert markers render on build or on a symbol/interval switch
- THEN they render through `createSeriesMarkers` and neither spy is called (#68)

#### Scenario: Existing E2E stays green except replaced assertions

- GIVEN the existing E2E assertions
- WHEN the suite runs after the change
- THEN they pass except for the assertions covering the removed DOM (replaced and documented per R18) and the default type stays candles
