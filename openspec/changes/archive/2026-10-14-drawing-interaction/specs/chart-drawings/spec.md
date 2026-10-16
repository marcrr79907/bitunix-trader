# Delta for chart-drawings

Issue #117 (Fase F4, Ola 4): drawings become selectable, draggable, restyleable,
and keyboard-deletable. R2 gains `PUT`. New requirements R9–R13 cover selection,
per-kind handles, drag, keyboard, the properties dialog, and the selection
lifecycle. R5 schemas, R3 isolation, R6 render, R7 load/switch stay in force.

## ADDED Requirements

### Requirement: R9 — Selection (hit-test + highlight)

A single drawing MAY be selected at a time. On `pointerdown` in the plot area the
resolver MUST hit-test handles FIRST, then the shape body via
`drawing-core.hitTest`; a miss MUST clear any current selection. The selected
drawing MUST render a visible highlight (thicker stroke and/or its handles). The
controller MUST publish selection via `bus.emit("drawing:selected", {id})`;
selection state MUST live in the interaction controller's closure, NOT in the
frozen store keys.

#### Scenario: Click a shape selects it

- GIVEN a rendered `trendline`
- WHEN `pointerdown` lands within its hit radius
- THEN that drawing is selected and highlighted, and `drawing:selected` is emitted with its `id`

#### Scenario: Click empty plot clears selection

- GIVEN a selected drawing
- WHEN `pointerdown` lands on no shape/handle
- THEN selection clears and a null selection is published

#### Scenario: Handle wins over body

- GIVEN a selected `rect` and a point within both a corner handle and the body radius
- WHEN resolving the grab
- THEN the corner handle is chosen over the body

### Requirement: R10 — Per-kind handles and drag

The pure `drawing-interaction-core.js` MUST expose `handlesFor(kind, points, map)`
returning handle `{id,x,y}` positions (hline 1; trendline 2; fib 2; rect 4; text
1), `grabHandle(items, x, y, radius)` returning the grabbed handle id, `"body"`,
or `null`, and `applyDrag(shape, target, dx, dy, map)` returning NEW `points` (no
mutation). Dragging a handle MUST move only that anchor; dragging the body MUST
translate every anchor by the same pixel delta. hline's drag MUST update only
`price`. The core MUST be deterministic, chart-lib-free, and MUST clamp/guard
null coordinates.

#### Scenario: Drag a trendline endpoint

- GIVEN a selected `trendline`
- WHEN its `p2` handle is dragged to a new pixel
- THEN only `p2` becomes the mapped `{time,price}`; `p1` is unchanged

#### Scenario: Translate a rect body

- GIVEN a selected `rect`
- WHEN its body is dragged by (dx,dy)
- THEN both corners shift by the same mapped delta

#### Scenario: hline moves price only

- GIVEN a selected `hline`
- WHEN its handle is dragged
- THEN `points.price` updates from `coordinateToPrice`; no `time` is added

#### Scenario: Drag resolves per kind

- GIVEN each of hline / trendline / fib / rect / text
- WHEN `handlesFor` runs
- THEN it returns exactly 1 / 2 / 2 / 4 / 1 handle(s)

### Requirement: R11 — Keyboard delete and deselect

`#chart` MUST be focusable (`tabindex="0"` with an accessible label). While it
holds focus, `Delete`/`Backspace` MUST delete the selected drawing, and `Escape`
MUST deselect (or cancel a pending create anchor). `Backspace` MUST
`preventDefault` to stop browser navigation. A keyboard path to delete MUST exist
so the feature is not pointer-only.

#### Scenario: Delete removes the selected drawing

- GIVEN a selected drawing and focus on `#chart`
- WHEN `Delete` (or `Backspace`) is pressed
- THEN the drawing is deleted (same path as `deleteDrawing`) and selection clears

#### Scenario: Escape deselects

- GIVEN a selected drawing
- WHEN `Escape` is pressed
- THEN selection clears and no delete occurs

#### Scenario: Delete with nothing selected is a no-op

- GIVEN no selection and focus on `#chart`
- WHEN `Delete` is pressed
- THEN nothing is deleted and no request is issued

### Requirement: R12 — Properties dialog (double-click)

A `dblclick` on a drawing MUST open a native `<dialog>` seeded with its `style`.
Confirming MUST merge the edited `color` and `lineWidth` into `style`, re-render,
and persist via PUT. `kind` and `points` MUST NOT be editable here. v1 scope is
`color` + `lineWidth` only; `fill`/`levels`/`fontSize` MAY stay untouched.

#### Scenario: Edit color and line width

- GIVEN a rendered drawing
- WHEN it is double-clicked, the dialog is confirmed with a new color/width
- THEN `style` merges those keys, the shape re-renders, and a PUT persists them

#### Scenario: Cancel leaves the style unchanged

- GIVEN the properties dialog open
- WHEN it is dismissed without confirming
- THEN `style` is unchanged and no PUT is issued

### Requirement: R13 — Edge-case handling matrix

The interaction surface MUST handle these edges deterministically:

| Edge | Expected |
|------|----------|
| Drag endpoint off-bar | clamp to nearest valid bar / keep last valid time; never persist `null` |
| Drag onto price-scale gutter | ignore / no coordinate write |
| Delete with nothing selected | no-op, no request |
| Escape with a pending create anchor | cancels the anchor, no shape created |
| Escape with a selection | deselects, no delete |
| PUT unknown id | 404, no write |
| PUT on another user's id (A≠B) | 404, A unchanged |
| Interval-only switch | selection + drawings survive, no refetch |
| Symbol switch | selection cleared with the drawings |
| Double-click with nothing selected | no-op / no dialog |

#### Scenario: Off-bar drag clamps

- GIVEN a `trendline` endpoint dragged past the last bar into empty space
- WHEN the drag is applied
- THEN the persisted `time` is clamped to a valid bar (never `null`)

#### Scenario: Edit targets kind and points immutably

- GIVEN the properties dialog
- WHEN confirmed
- THEN only `style` (color/lineWidth) changes; `kind` and `points` are untouched

### Requirement: R14 — Selection lifecycle across switches

Selection MUST clear on a SYMBOL switch (with the drawings) and MUST survive an
interval-only switch. A stale selected `id` MUST NEVER linger after its drawing
is cleared or deleted.

#### Scenario: Symbol switch clears selection

- GIVEN a selected drawing on `BTCUSDT`
- WHEN `switchTo("ETHUSDT", ...)` runs
- THEN selection is cleared and no stale id remains

#### Scenario: Interval-only switch keeps selection

- GIVEN a selected drawing on `BTCUSDT 1m`
- WHEN `switchTo("BTCUSDT", "1h")` runs
- THEN the drawings stay attached and the selection is retained

## MODIFIED Requirements

### Requirement: R2 — Drawings CRUD API

`GET /market/api/drawings?symbol=` MUST be login-required (anonymous → 302) and
return the caller's drawings for that `(user, symbol)` as
`{"drawings":[{id,kind,points,style}]}`, or an empty list when none exist (never
404). It MUST NOT filter by `interval`. `POST /market/api/drawings` MUST be
login-required and CSRF-protected, validate the payload before any write, store
the row for `(user, symbol)` via `Drawing.for_user(request.user)`, and return the
created row including its `id`; an `interval` key in the body MUST be accepted and
ignored (never 400). `PUT /market/api/drawings/<id>` MUST be login-required and
CSRF-protected, resolve through `Drawing.for_user(request.user)` (miss → 404, A≠B
→ 404 with no existence leak), accept a PARTIAL `{points?, style?}` body, treat
`kind` as immutable, validate via `parse_drawing`, and return the updated row
`{id,kind,points,style}` (200). `DELETE /market/api/drawings/<id>` MUST be
login-required and CSRF-protected, delete through `Drawing.for_user(request.user)`,
and be idempotent (a miss → 404 with no error leak). Every read/write MUST route
through `for_user`.
(Previously: only GET/POST/DELETE; no `PUT` update path.)

#### Scenario: GET with no drawings returns empty list

- GIVEN A has no drawings
- WHEN GET `?symbol=BTCUSDT`
- THEN 200 `{"drawings":[]}` (no 404)

#### Scenario: GET lists only the caller's symbol

- GIVEN A saved two drawings on `BTCUSDT` and one on `ETHUSDT`
- WHEN GET `?symbol=BTCUSDT` (any `interval` query ignored)
- THEN exactly the two BTCUSDT rows are returned

#### Scenario: POST creates a row with id

- GIVEN a valid `{symbol,kind,points,style}` body
- WHEN POST
- THEN 201 and the returned row carries the new `id`, persisted for A

#### Scenario: Stale interval accepted and ignored

- GIVEN POST `{symbol,interval:"1m",kind,points,style}`
- WHEN handled
- THEN 201 with a row (the `interval` key is ignored, not rejected)

#### Scenario: PUT updates points and style

- GIVEN A's `trendline` `d`
- WHEN PUT `/market/api/drawings/<d.id>` with `{points, style}`
- THEN 200 with the updated row and the persisted `points`/`style` match

#### Scenario: PUT partial body keeps the other field

- GIVEN A's drawing `d`
- WHEN PUT with `{style}` only
- THEN 200 and `points` is unchanged

#### Scenario: PUT miss or A≠B is 404

- GIVEN an `id` that does not exist for A, or a drawing owned by B
- WHEN PUT
- THEN 404 with no existence leak and no row is modified

#### Scenario: PUT kind is immutable

- GIVEN A's drawing `d`
- WHEN PUT includes a `kind` differing from the stored kind
- THEN 400 and no row is modified

#### Scenario: PUT invalid payload → 400 before write

- GIVEN PUT with `points`/`style` failing `parse_drawing`
- WHEN handled
- THEN 400 and no row is modified

#### Scenario: DELETE by id removes the row

- GIVEN A's drawing `d`
- WHEN DELETE `/market/api/drawings/<d.id>`
- THEN the row is gone and a subsequent GET omits it

#### Scenario: DELETE miss is 404

- GIVEN an `id` that does not exist for A
- WHEN DELETE
- THEN 404 and no row is affected

#### Scenario: Unauthenticated → redirect

- GIVEN an anonymous session
- WHEN GET, POST, PUT, or DELETE `/market/api/drawings*`
- THEN 302 to login

#### Scenario: CSRF enforced on write

- GIVEN an authenticated POST, PUT, or DELETE without a valid CSRF token
- WHEN handled
- THEN 403 and no write occurs

### Requirement: R6 — Render contract (Lightweight Charts v5 primitive)

Drawings MUST render via the already-loaded Lightweight Charts v5.2.0 series
primitive API (`candleSeries.attachPrimitive`); no new dependency MAY be added.
Each drawing MUST draw through `CanvasRenderingTarget2D` coordinate spaces
(`useMediaCoordinateSpace` / `useBitmapCoordinateSpace`) with no DOM access, so
CSP is untouched. Price↔pixel MUST use `priceToCoordinate`/`coordinateToPrice`;
time↔pixel MUST use `timeScale().timeToCoordinate`/`coordinateToTime`. When a
coordinate maps to `null` (no bar on the axis), the draw MUST skip that leg
rather than throw. Full-width rays and rectangles MUST supply `autoscaleInfo` so
pan/zoom does not clip them. Redraw on pan/zoom MUST use the primitive's
`requestUpdate`. The selected drawing MUST render its highlight and handles in the
SAME primitive; a drag MUST re-render via `requestUpdate` and MUST NEVER call
`setData`/`update` on the series (#68).
(Previously: no selection highlight/handles; re-render rule unchanged.)

#### Scenario: Attach one primitive per drawing

- GIVEN a chart with N saved drawings
- WHEN the chart is built
- THEN N primitives are attached to the candle series

#### Scenario: Off-bar anchor degrades gracefully

- GIVEN a drawing whose `time` maps to `null` on the current time scale
- WHEN the renderer draws
- THEN it skips that leg and does not throw

#### Scenario: Redraw on pan/zoom

- GIVEN an attached drawing
- WHEN the time scale is panned or zoomed
- THEN the primitive calls `requestUpdate` and the shape redraws

#### Scenario: Selected drawing draws highlight and handles

- GIVEN a selected drawing
- WHEN its primitive redraws
- THEN it draws the highlight and the per-kind handles

#### Scenario: Drag never touches the series data path

- GIVEN a drag in progress
- WHEN the shape re-renders
- THEN it uses `requestUpdate` only and no `setData`/`update` reaches the series

#### Scenario: Separate canvas layer preserves single-write-path

- GIVEN the drawings primitive active
- WHEN history updates or WS live candles arrive
- THEN drawings use their own canvas layer; no extra `setData`/`update` on the series occurs
