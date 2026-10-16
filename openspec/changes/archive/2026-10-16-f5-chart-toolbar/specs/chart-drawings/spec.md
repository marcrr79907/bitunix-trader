# Delta for chart-drawings

Issue #118 (F5): drawings gain persistent `visible`/`locked`
(`Drawing.visible` default True, `Drawing.locked` default False, additive
migration `0014`). This MODIFIES R1 (model + `0014`), R2 (CRUD accepts/returns
both; partial PUT set gains `{visible?,locked?}`; non-bool → 400), R6 (hidden
renders blank + autoscale null), and R9 (locked is not pointer-selectable/
draggable but stays tree-selectable). R3/R4/R5/R7/R8/R10–R14 stay in force and
unmodified.

## MODIFIED Requirements

### Requirement: R1 — Drawing model, ownership, and index

`Drawing` MUST inherit `UserOwnedModel` (owner FK `on_delete=CASCADE` +
`for_user`) and carry `symbol` (max 32), `kind` (`CharField`, one of
`DRAWING_KINDS`), `points` (`JSONField`), `style` (`JSONField`), `created_at`
(`auto_now_add`), plus `visible` (`BooleanField`, default `True`) and `locked`
(`BooleanField`, default `False`). It MUST be indexed on `(user, symbol)` and MUST
NOT carry a unique constraint on that tuple. No owner-less rows MAY exist.
Migration `0012` MUST remove the old `(user, symbol, interval)` index BEFORE
dropping `interval`, then add the `(user, symbol)` index (SQLite-safe order). It
MUST keep ALL rows and MUST NOT dedupe. Its reverse MUST be lossy (re-adds
`interval` defaulted `"1m"`). Migration `0014` MUST be a purely additive
AddField pair (`0013_chartpreference_smc.py:17-21` precedent): it MUST add
`visible` (default True) and `locked` (default False) and MUST be reversible with
zero data loss; its reverse MUST drop both fields leaving every row intact.
(Previously: no `visible`/`locked`; no `0014`.)

#### Scenario: Many drawings coexist on one chart

- GIVEN A has a `hline` on `BTCUSDT`
- WHEN A creates a second `trendline` on the same symbol
- THEN both rows persist (no `IntegrityError`, distinct `id`)

#### Scenario: Interval drop keeps every row

- GIVEN A has a drawing on `(BTCUSDT, 1m)` and one on `(BTCUSDT, 1h)`
- WHEN `0012` runs
- THEN both rows survive as distinct drawings under `BTCUSDT`

#### Scenario: JSON round-trip

- GIVEN `points=[{"time":1700000000,"price":50000.0}]` and `style={"color":"#f00","width":1}`
- WHEN saved and re-read
- THEN the nested list and object are equal

#### Scenario: Destructive migration order

- GIVEN the change applied
- WHEN migrations are inspected
- THEN `0012` removes the `interval` index, then the column, then adds `(user, symbol)` (`makemigrations --check` green)

#### Scenario: Reverse is lossy (0012)

- GIVEN drawings with `interval` dropped
- WHEN `0012` is reversed
- THEN every row gets `interval="1m"` and the prior per-interval split is gone

#### Scenario: 0014 is additive and reversible

- GIVEN existing drawings
- WHEN `0014` runs forward then reverse
- THEN both rows keep all prior fields, `visible`/`locked` appear with their defaults, and a further reverse drops them with no row lost (`makemigrations --check` green)

#### Scenario: Defaults on new rows

- GIVEN a drawing created without flags
- WHEN the row is read
- THEN `visible is True` and `locked is False`

### Requirement: R2 — Drawings CRUD API

`GET /market/api/drawings?symbol=` MUST be login-required (anonymous → 302) and
return the caller's drawings for that `(user, symbol)` as
`{"drawings":[{id,kind,points,style,visible,locked}]}`, or an empty list when none
exist (never 404). It MUST NOT filter by `interval`. `POST /market/api/drawings`
MUST be login-required and CSRF-protected, validate the payload before any write,
accept optional `visible`/`locked` booleans (defaulting to True/False), store the
row for `(user, symbol)` via `Drawing.for_user(request.user)`, and return the
created row including its `id` and both flags; an `interval` key in the body MUST
be accepted and ignored (never 400). A non-boolean `visible`/`locked` MUST yield
400 before any write. `PUT /market/api/drawings/<id>` MUST be login-required and
CSRF-protected, resolve through `Drawing.for_user(request.user)` (miss → 404, A≠B
→ 404 with no existence leak), accept a PARTIAL `{points?, style?, visible?,
locked?}` body, treat `kind` as immutable, validate via `parse_drawing`, and
return the updated row `{id,kind,points,style,visible,locked}` (200). A
non-boolean flag MUST yield 400 before any write. `DELETE /market/api/drawings/<id>`
MUST be login-required and CSRF-protected, delete through
`Drawing.for_user(request.user)`, and be idempotent (a miss → 404). Every
read/write MUST route through `for_user`.
(Previously: no `visible`/`locked`; partial PUT set was `{points?,style?}`.)

#### Scenario: GET with no drawings returns empty list

- GIVEN A has no drawings
- WHEN GET `?symbol=BTCUSDT`
- THEN 200 `{"drawings":[]}` (no 404)

#### Scenario: GET lists flags

- GIVEN a drawing saved with `visible:false, locked:true`
- WHEN GET `?symbol=BTCUSDT`
- THEN its row includes `visible:false` and `locked:true`

#### Scenario: POST creates a row with id and flags

- GIVEN a valid `{symbol,kind,points,style,visible:false,locked:true}` body
- WHEN POST
- THEN 201 and the returned row carries the new `id`, `visible:false`, `locked:true`, persisted for A

#### Scenario: POST defaults absent flags

- GIVEN POST without `visible`/`locked`
- WHEN handled
- THEN 201 with `visible:true` and `locked:false`

#### Scenario: Stale interval accepted and ignored

- GIVEN POST `{symbol,interval:"1m",kind,points,style}`
- WHEN handled
- THEN 201 with a row (the `interval` key is ignored, not rejected)

#### Scenario: PUT updates points, style, and flags

- GIVEN A's `trendline` `d`
- WHEN PUT `/market/api/drawings/<d.id>` with `{points,style,visible,locked}`
- THEN 200 with the updated row and the persisted values match

#### Scenario: PUT partial body keeps other fields

- GIVEN A's drawing `d`
- WHEN PUT with `{visible}` only
- THEN 200 and `points`, `style`, and `locked` are unchanged

#### Scenario: PUT non-bool flag → 400 before write

- GIVEN A's drawing `d`
- WHEN PUT carries `visible:"yes"` or `locked:1`
- THEN 400 and no row is modified

#### Scenario: PUT miss or A≠B is 404

- GIVEN an `id` that does not exist for A, or a drawing owned by B
- WHEN PUT
- THEN 404 with no existence leak and no row is modified

#### Scenario: PUT kind is immutable

- GIVEN A's drawing `d`
- WHEN PUT includes a `kind` differing from the stored kind
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
coordinate maps to `null`, the draw MUST skip that leg rather than throw.
Full-width rays and rectangles MUST supply `autoscaleInfo` so pan/zoom does not
clip them. Redraw on pan/zoom MUST use `requestUpdate`. The selected drawing MUST
render its highlight and handles in the SAME primitive. A drawing with
`visible:false` MUST keep its primitive attached but render nothing, and its
`autoscaleInfo` MUST return `null` so a hidden full-width ray does not influence
autoscale; a toggle from hidden back to visible MUST re-render via
`requestUpdate` only. A drag MUST re-render via `requestUpdate` and MUST NEVER
call `setData`/`update` on the series (#68).
(Previously: no hidden-blank / null-autoscale clause.)

#### Scenario: Attach one primitive per drawing

- GIVEN a chart with N saved drawings
- WHEN the chart is built
- THEN N primitives are attached to the candle series

#### Scenario: Hidden drawing renders blank without detaching

- GIVEN a drawing with `visible:false`
- WHEN its primitive redraws
- THEN nothing is drawn, the primitive stays attached, and `autoscaleInfo` is `null`

#### Scenario: Reveal uses requestUpdate only

- GIVEN a hidden drawing
- WHEN `visible` flips to true
- THEN the shape redraws via `requestUpdate` and no `setData`/`update` reaches the series

#### Scenario: Off-bar anchor degrades gracefully

- GIVEN a drawing whose `time` maps to `null`
- WHEN the renderer draws
- THEN it skips that leg and does not throw

#### Scenario: Selected drawing draws highlight and handles

- GIVEN a selected drawing
- WHEN its primitive redraws
- THEN it draws the highlight and the per-kind handles

#### Scenario: Drag never touches the series data path

- GIVEN a drag in progress
- WHEN the shape re-renders
- THEN it uses `requestUpdate` only and no `setData`/`update` reaches the series

### Requirement: R9 — Selection (hit-test + highlight)

A single drawing MAY be selected at a time. On `pointerdown` in the plot area the
resolver MUST hit-test handles FIRST, then the shape body via
`drawing-core.hitTest`; a miss MUST clear any current selection. A drawing with
`locked:true` MUST be excluded from pointer hit-testing (both `pointerdown` and
`dblclick`) so it is neither pointer-selectable nor draggable, but it MUST remain
selectable from the object tree (a bus emit, not a pointer hit). The selected
drawing MUST render a visible highlight (thicker stroke and/or its handles). The
controller MUST publish selection via `bus.emit("drawing:selected", {id})`;
selection state MUST live in the interaction controller's closure, NOT in the
frozen store keys.
(Previously: no `locked` exclusion rule.)

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

#### Scenario: Locked drawing is not pointer-selectable or draggable

- GIVEN a drawing with `locked:true`
- WHEN `pointerdown` or `dblclick` lands within its hit radius
- THEN no selection, drag, or dialog occurs

#### Scenario: Locked drawing stays tree-selectable

- GIVEN a drawing with `locked:true`
- WHEN its tree row is selected
- THEN `drawing:selected` is emitted and the highlight shows
