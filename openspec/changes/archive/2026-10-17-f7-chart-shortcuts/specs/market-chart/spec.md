# Delta for market-chart

Issue #120 (F7): the layered module inventory gains the two pure cores
`history-core.js`/`context-menu-core.js` and the two controllers
`controllers/undo.js`/`controllers/context-menu.js`; `MODULE_ALLOWLIST` +2 and
`CONTROLLER_ALLOWLIST` 13→15 (`test_market_ux.py:146` `== 13` → `== 15`). This
MODIFIES R14 (inventory + allowlists), R18 and R20 (the seam stays 8 keys,
`STORE_KEYS` stays 11, and no new bus event is added beyond the existing string
literal convention — the duplicate uses `drawing:duplicate`). R1–R13, R15–R17,
R19, R21–R23 stay in force and unmodified.

## MODIFIED Requirements

### Requirement: R14 — Layered ESM module boundary

Modules MUST follow a frozen inventory: entry `chart.js` (thin: Django-injected
`CONFIG` + imports + `boot()`), pure cores `chart-core.js`/`drawing-core.js`/
`smc-overlay-core.js`/`legend-core.js`/`indicator-settings-core.js`/
`chart-types-core.js`/`theme-core.js`/`tool-icons-core.js`/`chart-registry-core.js`/
`add-indicator-core.js`/`measure-core.js`/`position-core.js`/`position-draft-core.js`/
`readout-coalesce-core.js`/`history-core.js`/`context-menu-core.js`,
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
`position-draft-core`, `readout-coalesce-core`, `history-core`, and
`context-menu-core`; `CONTROLLER_ALLOWLIST`
(`views.py:66-81`) MUST include `measure`, `position-seed`, `undo`, and
`context-menu`. The size rule
MUST be enforced by the committed guard `tests/web/test_module_size_guard.py`
(`CEILING = 300`; scans `web/market/templates/market/**/*.js` via `rglob` +
`splitlines()`). The guard's `ALLOWLIST` MUST be empty — no module is exempt.
`chart-host.js` MUST be ≤ ~300 lines. Any module above `CEILING` MUST fail the
guard.
(Previously: the controller inventory had 13 entries and no `undo`/`context-menu`;
the pure-core list had no `history-core`/`context-menu-core`.)

#### Scenario: Inventory and no-cycle

- GIVEN the delivered modules, WHEN imports resolve, THEN the inventory (including `tool-icons-core.js`, `chart-registry-core.js`, `chart-host-candles.js`, `theme-core.js`, `history-core.js`, `context-menu-core.js`, `controllers/undo.js`, and `controllers/context-menu.js`) exists, `theme-core.js` imports nothing, no controller imports `main`, and `main.js` has no cycles

#### Scenario: Store never holds candles

- GIVEN `chart-store.js`, WHEN its keys are inspected, THEN it holds only UI/config (`symbol, interval, indicators, params, styles, smc, scaleMode, chartType, theme, tool, indicatorVisible`) — no candle data

#### Scenario: Size ceiling with empty allowlist

- GIVEN every module, WHEN `tests/web/test_module_size_guard.py` reads line counts
- THEN it passes at `CEILING = 300` with an EMPTY `ALLOWLIST` (no exemption), `chart-host.js` stays ≤ ~300 lines, and any module above the ceiling fails

#### Scenario: New cores and controllers are served

- GIVEN `history-core`, `context-menu-core`, `controllers/undo`, and
  `controllers/context-menu`
- WHEN requested under `/market/` with a JS MIME type
- THEN each is served 200 (present in the matching allowlist; missing → 404 → blank chart)

#### Scenario: Controller allowlist count grows

- GIVEN `CONTROLLER_ALLOWLIST`
- WHEN inspected
- THEN it holds **15** entries and `tests/web/test_market_ux.py` asserts the count
  `== 15` and passes unedited elsewhere — the 13 prior entries plus `undo` and
  `context-menu`.

#### Scenario: New theme core is served

- GIVEN `theme-core`, WHEN requested under `/market/` with a JS MIME type, THEN it is served 200 (missing from the allowlist → 404 → blank chart)

#### Scenario: New candle sub-module is served

- GIVEN `chart-host-candles`, WHEN requested under `/market/` with a JS MIME type, THEN it is served 200 (the name MUST be in `MODULE_ALLOWLIST`; missing → import 404 → blank chart)

#### Scenario: No behavior change

- GIVEN the change, WHEN the node tests and the E2E suite run
- THEN they pass with NO behavior-assertion edits, the 8-key seam
  (`window.marketChart`) is unchanged, the C1 same-bucket HA fix is preserved
  verbatim, and the HA contract (`chart-types-core`) is untouched

### Requirement: R18 — Test-seam preservation

The refactor MUST expose `window.marketChart` with frozen keys `{chart,
candleSeries, panes, ready, drawings, smc, smcCounts, smcToggles}` and equivalent
update-timing, and MUST re-expose `window.SmcOverlayCore` as the sanctioned test
seam. The toolbar, the object tree, indicator visibility, the F5 vertical toolbar,
the F6 measure/position tools, and the F7 undo/context-menu layer MUST NOT add a
9th key; the measure readout MUST
be asserted via its DOM node (`#measure-readout`) and the position via
`window.marketChart.drawings` (existing) plus the captured POST/PUT, never via a
new seam key; the undo redo/undo MUST be asserted via captured POST/PUT/DELETE and
the context menu via its DOM `role="menu"`, never via a new seam key.
`tests/web/test_market_e2e.py` MUST stay green except for the
assertions that covered the DOM this change removes (`#drawing-list`, the
indicators `fieldset`); each such assertion MUST be replaced by equivalent
coverage, and the removal + replacement MUST be documented in the E2E itself
(`test_market_e2e.py:582-620`). Every removed scenario has an equivalent
replacement EXCEPT adding-an-indicator, which became the new `chart-indicator-add`
capability (issue #176, slice S5) — so there is no unreplaced coverage gap.
(Previously: the clause was silent on the F7 undo/context-menu layer.)

#### Scenario: Seam shape frozen

- GIVEN a booted chart after the toolbar and tree exist with the measure, position, undo, and context-menu layers
- WHEN `window.marketChart` is read
- THEN all eight keys exist and update as before, with no toolbar/tree/visibility/measure/position/undo/menu key added

#### Scenario: Measure has no seam key

- GIVEN a completed measurement
- WHEN `window.marketChart` is read
- THEN it still has exactly 8 keys and the readout is observed through its `aria-live` DOM node (E2E `test_shell_keeps_seam_at_eight_keys`; measure asserts `drawings.length == 0`)

#### Scenario: Undo and menu assert without a seam key

- GIVEN an undo/redo or a context-menu command
- WHEN it is observed
- THEN it is asserted via captured POST/PUT/DELETE and the DOM `role="menu"`, and `window.marketChart` still has exactly 8 keys

#### Scenario: SMC core reachable

- GIVEN the ESM entry loaded
- WHEN `window.SmcOverlayCore.setupMarkers(...)` is called
- THEN it returns the marker array as before

#### Scenario: Existing E2E green except replaced assertions

- GIVEN the existing E2E assertions
- WHEN the suite runs after the change
- THEN it passes except for the assertions covering the removed `#drawing-list`/`fieldset` DOM, each replaced by equivalent coverage and documented in `test_market_e2e.py:582-620`

### Requirement: R20 — Shell change stays inside the frozen host/seam envelope

The `autoSize: true` host option, the `#chart` markup change, the F8 chart-type
and scale controls, the theme control, the F5 vertical toolbar, the object tree,
the indicator-visibility toggle, the F6 measure/position tools, and the F7
undo/context-menu layer MUST stay within R14 (host owns construction)
and MUST NOT add a `window.marketChart` key. `window.marketChart` MUST keep
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
existing `drawing:changed`/`drawing:delete`/`drawings:changed` commands and
`scale:changed`, and the menu's duplicate uses the string literal
`drawing:duplicate` (the same literal convention as `drawing:changed`), handled in
`drawings.js`; no `history:*`/`undo:*`/`menu:*` event exists.
(Previously: the envelope was silent on the F7 undo/context-menu layer.)

#### Scenario: Seam stays 8 keys

- GIVEN a booted chart after the toolbar and tree with the measure, position, undo, and menu layers
- WHEN `window.marketChart` is read
- THEN exactly the 8 frozen keys exist and no toolbar/tree/visibility/measure/position/undo/menu key was added

#### Scenario: Exactly one new bus event (unchanged set)

- GIVEN the change
- WHEN the bus events are inspected
- THEN the only events are the pre-existing set plus `scale:changed` plus `indicator:visibility`; the position tool reuses `drawing:changed`/`drawing:selected`, the measure tool adds none, and the F7 duplicate uses the `drawing:duplicate` string literal — no `history:*`/`undo:*`/`menu:*` event and no new `EVENTS` entry exist

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

#### Scenario: Existing E2E stays green except replaced assertions

- GIVEN the existing E2E assertions
- WHEN the suite runs after the change
- THEN they pass except for the assertions covering the removed DOM (replaced and documented per R18) and the default type stays candles
