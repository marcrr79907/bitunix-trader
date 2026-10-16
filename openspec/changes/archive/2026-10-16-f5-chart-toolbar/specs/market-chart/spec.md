# Delta for market-chart

Issue #118 (F5): the chart gains a vertical icon toolbar, a unified object tree,
persistent drawing hide/lock, and persistent indicator visibility. This MODIFIES
R11 (drawings flags enter the endpoint/render contract), R14 (the store gains an
11th key `indicatorVisible`; inventory +2 cores +2 controllers; allowlist/count),
R18 (seam stays 8 keys), and R20 (permits exactly ONE new bus event
`indicator:visibility`). R1–R10, R12, R13, R15–R17, R19, R21–R23 stay in force and
unmodified.

## MODIFIED Requirements

### Requirement: R11 — Drawings endpoint and render/restore contract

`/market/api/drawings` MUST expose the caller's persisted drawings for a chart.
`GET ?symbol=&interval=` MUST be GET-only and login-required (anonymous → 302)
and MUST return the caller's drawings for that `(symbol, interval)` as
`{"drawings":[...]}`, or an empty list when none exist (never 404). `POST` MUST be
login-required and CSRF-protected, validate `kind`/`symbol`/`points`/`style` and
any `visible`/`locked` flags before any write (unknown `kind`, bad shape, or a
non-boolean flag → 400), create through `Drawing.for_user(request.user)`, and
return the created row with its `id`. `PUT /market/api/drawings/<id>` MUST be
login-required and CSRF-protected, resolve through `Drawing.for_user(request.user)`
(miss → 404 and another user's `id` → 404 with no leak), accept a PARTIAL
`{points?,style?,visible?,locked?}` body, keep `kind` immutable, validate via
`parse_drawing` (→ 400 before write), and return the updated row
`{id,kind,points,style,visible,locked}` (200). `DELETE /market/api/drawings/<id>`
MUST be login-required and CSRF-protected, delete through
`Drawing.for_user(request.user)` (miss → 404), and never touch another user's row.
The market page MUST render saved drawings via the already-loaded Lightweight
Charts v5.2.0 series primitive (no new dependency, no DOM access — CSP unchanged),
restore them after `buildChart` and on `switchTo(symbol, interval)` (clearing the
previous key's primitives), render a drawing with `visible:false` blank (primitive
kept attached, `autoscaleInfo` null), exclude a `locked:true` drawing from pointer
hit-testing while keeping it tree-selectable, and MUST support selecting, dragging,
keyboard deleting/deselecting, and restyling a drawing, persisting a drag via ONE
`PUT` on `pointerup` through `requestUpdate` only (never `setData`/`update`; #68).
It MUST NOT introduce inline script/handlers or relax the read-only boundary.
(Previously: no `visible`/`locked`; partial PUT was `{points?,style?}`.)

#### Scenario: GET empty when no drawings

- GIVEN an authenticated user with no drawings
- WHEN GET `?symbol=BTCUSDT&interval=1m`
- THEN 200 `{"drawings":[]}` (no 404)

#### Scenario: POST then GET returns the drawing with flags

- GIVEN a valid drawing payload with `visible:false`
- WHEN POST then GET the same key
- THEN 201 with an `id`, and GET lists that drawing with `visible:false`

#### Scenario: Invalid kind or non-bool flag → 400 before write

- GIVEN POST `kind="notreal"`, or `visible="yes"`
- WHEN handled
- THEN 400 `{"error":"..."}` before any write

#### Scenario: PUT updates a drawing in place

- GIVEN the caller's drawing `d`
- WHEN PUT `/market/api/drawings/<d.id>` with a partial `{points, style, locked}`
- THEN 200 with the updated row; a following GET lists the new coordinates and `locked`

#### Scenario: PUT miss or cross-user is 404

- GIVEN an unknown `id`, or an `id` owned by another user
- WHEN PUT
- THEN 404 and no row is modified

#### Scenario: PUT kind immutable → 400

- GIVEN the caller's drawing `d`
- WHEN PUT carries a differing `kind`
- THEN 400 before any write

#### Scenario: DELETE by id is idempotent-by-id

- GIVEN the caller's drawing `d`
- WHEN DELETE `/market/api/drawings/<d.id>`
- THEN 200 and the row is removed; a second DELETE of the same id yields 404

#### Scenario: Per-user isolation

- GIVEN user A's drawing `d`
- WHEN user B GETs the same key or PUTs/DELETEs `<d.id>`
- THEN B sees no drawing and B's PUT/DELETE returns 404; A's row is unchanged

#### Scenario: Select, drag, and persist round-trips

- GIVEN a rendered drawing
- WHEN it is selected and dragged, then the drag ends
- THEN exactly one `PUT /market/api/drawings/<id>` is issued and the seam shows the new points

#### Scenario: Hidden and locked render and restore

- GIVEN a saved drawing with `visible:false, locked:true`
- WHEN the page loads or `switchTo` restores it
- THEN its primitive is attached but draws nothing, it is not pointer-selectable, and its tree row reflects the flags

#### Scenario: Market page stays CSP-clean

- GIVEN the rendered `/market/` page
- WHEN the response header and templates are inspected
- THEN `Content-Security-Policy` is unchanged and no inline script/handler exists

### Requirement: R14 — Layered ESM module boundary

Modules MUST follow a frozen inventory: entry `chart.js` (thin: Django-injected
`CONFIG` + imports + `boot()`), pure cores `chart-core.js`/`drawing-core.js`/
`smc-overlay-core.js`/`legend-core.js`/`indicator-settings-core.js`/
`chart-types-core.js`/`theme-core.js`/`tool-icons-core.js`/`chart-registry-core.js`,
`chart-store.js` (UI/config state ONLY — MUST NOT hold candle data; its vocabulary
is `symbol, interval, indicators, params, styles, smc, scaleMode, chartType, theme,
tool, indicatorVisible`), `chart-bus.js`, `chart-host.js` (chart/series/panes/
scales/crosshair + candle data), the host-layer sub-module
`chart-host-candles.js` (candle channel: `CANDLE_CTORS`, the candle series, the
raw `candles` array, and the incremental HA state; factory
`createCandles(chart, chartType) -> {getCandleSeries, getCandles, setCandles,
updateCandle, remove}`), `controllers/{indicators,history,stream,drawings,smc,
toolbar,legend,draw-toolbar,object-tree}.js`, and `main.js` (ALL orchestration +
boot/switch). No module MUST exceed ~300 lines. Controllers MUST import
host/store/bus directly but MUST NOT import `main`; commands MUST travel the bus,
so `main.js` has no circular imports. Every imported module MUST be served
same-origin under `/market/` via its Django route (core → `MODULE_ALLOWLIST`,
controller → `CONTROLLER_ALLOWLIST`). The size rule MUST be enforced by the
committed guard `tests/web/test_module_size_guard.py` (`CEILING = 300`; scans
`web/market/templates/market/**/*.js` via `rglob` + `splitlines()`). The guard's
`ALLOWLIST` MUST be empty. `chart-host.js` MUST be ≤ ~300 lines (the
`REGISTRY`/`PANE_ORDER`/`SCALE_MODES` extraction to `chart-registry-core.js` MUST
land before `setSeriesVisible` is added).
(Previously: store vocabulary had 10 keys, no `tool-icons-core`/
`chart-registry-core`, and 8 controllers.)

#### Scenario: Inventory and no-cycle

- GIVEN the delivered modules
- WHEN imports resolve
- THEN the inventory (including `tool-icons-core.js` and `chart-registry-core.js`) exists, no controller imports `main`, and `main.js` has no cycles

#### Scenario: Store never holds candles

- GIVEN `chart-store.js`
- WHEN its keys are inspected
- THEN it holds only UI/config (`symbol, interval, indicators, params, styles, smc, scaleMode, chartType, theme, tool, indicatorVisible`) — no candle data

#### Scenario: Size ceiling with empty allowlist

- GIVEN every module
- WHEN `tests/web/test_module_size_guard.py` reads line counts
- THEN it passes at `CEILING = 300` with an EMPTY `ALLOWLIST` and any module above the ceiling fails

#### Scenario: New cores and controllers are served

- GIVEN `tool-icons-core`, `chart-registry-core`, `draw-toolbar`, `object-tree`
- WHEN requested under `/market/` with a JS MIME type
- THEN each is served 200 (present in the matching allowlist; missing → 404 → blank chart)

#### Scenario: Controller allowlist count grows

- GIVEN `CONTROLLER_ALLOWLIST`
- WHEN inspected
- THEN it holds 10 entries and `tests/web/test_market_ux.py` asserts the count 10 and passes unedited elsewhere

### Requirement: R18 — Test-seam preservation

The refactor MUST expose `window.marketChart` with frozen keys `{chart,
candleSeries, panes, ready, drawings, smc, smcCounts, smcToggles}` and equivalent
update-timing, and MUST re-expose `window.SmcOverlayCore` as the sanctioned test
seam. The toolbar, the object tree, and indicator visibility MUST NOT add a 9th
key. `tests/web/test_market_e2e.py` MUST stay green with NO assertion edits beyond
the tree/toolbar scenarios introduced by this change.
(Previously: identical seam; F5 explicitly reaffirms no 9th key despite new UI.)

#### Scenario: Seam shape frozen

- GIVEN a booted chart after the toolbar and tree exist
- WHEN `window.marketChart` is read
- THEN all eight keys exist and update as before, with no toolbar/tree/visibility key added

#### Scenario: SMC core reachable

- GIVEN the ESM entry loaded
- WHEN `window.SmcOverlayCore.setupMarkers(...)` is called
- THEN it returns the marker array as before

### Requirement: R20 — Shell change stays inside the frozen host/seam envelope

The `autoSize: true` host option, the `#chart` markup change, the F8 chart-type
and scale controls, the theme control, the F5 vertical toolbar, the object tree,
and the indicator-visibility toggle MUST stay within R14 (host owns construction)
and MUST NOT add a `window.marketChart` key. `window.marketChart` MUST keep
exactly its 8 frozen keys and `window.SmcOverlayCore` MUST be untouched. The E2E
seam shape and timing (R18) and the single-write-path invariants (R17) MUST be
preserved. F8 added exactly one bus event, `scale:changed` (`{mode}`); F5 MUST add
exactly ONE more, `indicator:visibility` (`{token, visible}`), routed by `main` to
the host's option-only `setSeriesVisible` (mirroring `scale:changed`,
`main.js:179-182`). Drawing hide/lock MUST reuse the existing `drawing:changed`
event and MUST NOT add a drawing event; the live theme flip MUST keep going
through `setTheme`. The theme value MUST live in the store and/or `data-theme`,
never in the seam.
(Previously: envelope covered type/scale/theme; F5 adds exactly one event.)

#### Scenario: Seam stays 8 keys

- GIVEN a booted chart after the toolbar and tree
- WHEN `window.marketChart` is read
- THEN exactly the 8 frozen keys exist and no toolbar/tree/visibility key was added

#### Scenario: Exactly one new bus event

- GIVEN the change
- WHEN the bus events are inspected
- THEN the only events are the pre-existing set plus `scale:changed` plus `indicator:visibility`; no `drawing:visibility`/`drawing:lock` event was added

#### Scenario: Visibility toggle is option-only

- GIVEN a built chart with the `setData`/`update` spies installed
- WHEN `indicator:visibility` fires for a token
- THEN the host calls `setSeriesVisible` (option-only) and neither `setData` nor `update` is called

#### Scenario: Existing E2E stays green unedited

- GIVEN the existing E2E assertions
- WHEN the suite runs after the change
- THEN they pass with no assertion edits and the default type stays candles
