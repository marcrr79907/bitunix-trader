# chart-drawings Specification

## Purpose

Per-user drawing collection (issue #72, Fase A3): a user marks what they see on
the chart with hline / trendline / fib / rect / text shapes, persisted server-side
and restored on open and symbol switch. New capability — no prior spec. Drawings
are keyed **per symbol** — `(user, symbol)`, TradingView-style (issue #124, Ola 3):
a drawing is visible across every interval of a pair and is cleared only on a
**symbol** change (the `interval` key was dropped by migration `0012`). Unlike
`chart-config` (one row per `(user, symbol, interval)`), a chart holds **many**
drawings: **no unique constraint**, CRUD keyed by `id`, scoped per `(user, symbol)`.
Visual annotations only — never order execution.

## Requirements

### Requirement: R1 — Drawing model, ownership, and index

`Drawing` MUST inherit `UserOwnedModel` (owner FK `on_delete=CASCADE` +
`for_user`) and carry `symbol` (max 32), `kind` (`CharField`, one of
`DRAWING_KINDS`), `points` (`JSONField`), `style` (`JSONField`), `created_at`
(`auto_now_add`), plus `visible` (`BooleanField`, default `True`) and `locked`
(`BooleanField`, default `False`). It MUST be indexed on `(user, symbol)` and MUST
NOT carry a unique constraint on that tuple. No owner-less rows MAY exist.
`DRAWING_KINDS` MUST include `position` — a `Drawing.Kind.POSITION` choice in
`web/trading/models.py` (`models.py:244-250`), surfaced through
`drawing-core.js` `DRAWING_KINDS` (`drawing-core.js:13`). Migration `0012` MUST
remove the old `(user, symbol, interval)` index BEFORE dropping `interval`, then
add the `(user, symbol)` index (SQLite-safe order). It MUST keep ALL rows and MUST
NOT dedupe (no unique constraint means nothing collides; dedupe would destroy user
data). Its reverse MUST be lossy — it re-adds `interval` defaulted to `"1m"`; the
original per-interval split is NOT recoverable (documented rollback contract).
Migration `0014` MUST be a purely additive AddField pair
(`0013_chartpreference_smc.py:17-21` precedent): it MUST add `visible` (default
True) and `locked` (default False) and MUST be reversible with zero data loss; its
reverse MUST drop both fields leaving every row intact. Migration `0015` MUST be a
choices-only `AlterField` on `kind` (`0015_drawing_kind_position.py`, deps
`0014_drawing_visible_locked`) that widens the choices with `position` and MUST be
reversible to `0014` with zero data loss (reverse restores the prior choices;
every stored row keeps its `kind`). The delivered migration chain is
`0012 → 0013 → 0014 → 0015`.
(Previously: no `position` kind; no `0015`; `DRAWING_KINDS` had no `position`.)

#### Scenario: Many drawings coexist on one chart

- GIVEN A has a `hline` on `BTCUSDT`
- WHEN A creates a second `trendline` on the same symbol
- THEN both rows persist (no `IntegrityError`, distinct `id`)

#### Scenario: Interval drop keeps every row

- GIVEN A has a drawing on `(BTCUSDT, 1m)` and one on `(BTCUSDT, 1h)`
- WHEN `0012` runs
- THEN both rows survive as distinct drawings under `BTCUSDT` (no dedupe, no error)

#### Scenario: JSON round-trip

- GIVEN `points=[{"time":1700000000,"price":50000.0}]` and `style={"color":"#f00","width":1}`
- WHEN saved and re-read
- THEN the nested list and object are equal

#### Scenario: Destructive migration order

- GIVEN the change applied
- WHEN migrations are inspected
- THEN `0012` removes the `interval` index, then the column, then adds `(user, symbol)` (`makemigrations --check` green)

#### Scenario: Reverse is lossy

- GIVEN drawings with `interval` dropped
- WHEN `0012` is reversed
- THEN every row gets `interval="1m"` and the prior per-interval split is gone

#### Scenario: 0014 is additive and reversible

- GIVEN existing drawings
- WHEN `0014` runs forward then reverse
- THEN both rows keep all prior fields, `visible`/`locked` appear with their defaults, and a further reverse drops them with no row lost (`makemigrations --check` green)

#### Scenario: position is a valid kind

- GIVEN a `Drawing` row with `kind="position"`
- WHEN `DRAWING_KINDS` is read
- THEN `"position"` is a member (`test_market_api.py::test_position_kind_is_a_member_of_drawing_kinds`)

#### Scenario: 0015 is choices-only and reversible

- GIVEN existing drawings of every prior kind
- WHEN `0015` runs forward then reverse
- THEN every row keeps its kind and data, `position` is selectable after forward, and reverse restores the prior choices with no row lost (`test_migration_0015.py`; `makemigrations --check` green)

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
`Drawing.for_user(request.user)`, and be idempotent (a miss → 404 with no error
leak). Every read/write MUST route through `for_user`.
(Previously: no `visible`/`locked`; partial PUT set was `{points?,style?}`.)

#### Scenario: GET with no drawings returns empty list

- GIVEN A has no drawings
- WHEN GET `?symbol=BTCUSDT`
- THEN 200 `{"drawings":[]}` (no 404)

#### Scenario: GET lists flags

- GIVEN a drawing saved with `visible:false, locked:true`
- WHEN GET `?symbol=BTCUSDT`
- THEN its row includes `visible:false` and `locked:true`

#### Scenario: GET lists only the caller's symbol

- GIVEN A saved two drawings on `BTCUSDT` and one on `ETHUSDT`
- WHEN GET `?symbol=BTCUSDT` (any `interval` query ignored)
- THEN exactly the two BTCUSDT rows are returned

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

### Requirement: R3 — Cross-user isolation (A ≠ B)

User B MUST NOT list, read, or delete A's drawings. B's list MUST never contain
A's rows, and B's DELETE of an A-owned `id` MUST resolve to nothing (404) without
revealing existence.

#### Scenario: B's GET never leaks A's drawings

- GIVEN A saved drawings on a key
- WHEN B GETs the same `symbol`
- THEN B receives only B's rows (empty if B has none)

#### Scenario: B's DELETE of an A id is 404

- GIVEN A's drawing `d`
- WHEN B DELETEs `/market/api/drawings/<d.id>`
- THEN 404 and A's row is unchanged

#### Scenario: B cannot read A's row via for_user

- GIVEN a `Drawing` owned by A
- WHEN `Drawing.for_user(B).get(pk=d.pk)` runs
- THEN `DoesNotExist`

### Requirement: R4 — Validation before write (kind / points / style)

The server MUST validate the payload BEFORE any write; an unknown `kind`, a
`kind` outside `DRAWING_KINDS`, an empty `symbol`, or `points`/`style` not matching
the kind's schema MUST yield 400 `{"error":"..."}` and MUST NOT create a row.
`interval` is NO LONGER part of the drawing contract: its presence or value MUST
NOT yield 400 (accept-and-ignore). Validation MUST live in a pure
`parse_drawing(kind, points, style)` (raise `ValueError`) in `quotes.py`; the view
maps it to 400.
(Previously: an `interval` outside `INTERVALS` yielded 400.)

#### Scenario: Unknown kind → 400 before write

- GIVEN POST `kind="notreal"`
- WHEN handled
- THEN 400 and no row is written

#### Scenario: Interval in body never 400

- GIVEN POST with `interval="7m"` (or any value)
- WHEN handled
- THEN no 400 is raised for the `interval` key

#### Scenario: Bad shape for kind → 400

- GIVEN POST `kind="trendline"` with a single point
- WHEN handled
- THEN 400 and no row is written

### Requirement: R5 — Kind-specific point and style schemas

Each `kind` MUST enforce its schema: `hline` = exactly 1 point `{time,price}`
(`time` optional), `style {color,width}`; `trendline` = exactly 2 points;
`fib` = exactly 2 points, `style {levels:[...]}`; `rect` = exactly 2 points,
`style {color,fill}`; `text` = 1 point plus a non-empty label in `style.text`,
`style {color}`; `position` = `points` `{entry:{time,price}, stop:number,
take_profit:number}` with numeric `entry.price`, `stop`, `take_profit`, and MUST
reject a missing field, a non-numeric level, or a degenerate `entry.price==stop`
with 400. `DRAWING_KINDS` MUST auto-include `position` so a `position` payload
passes the kind check before the schema branch runs. A count or shape mismatch
MUST be rejected with 400.
(Previously: no `position` schema branch.)

#### Scenario: hline accepts one point

- GIVEN POST `kind="hline"`, `points=[{price:50000.0}]`
- WHEN handled
- THEN 201 and the row persists

#### Scenario: trendline requires two points

- GIVEN POST `kind="trendline"`, `points=[{time:1,price:1.0}]`
- WHEN handled
- THEN 400 and no row is written

#### Scenario: text requires a label

- GIVEN POST `kind="text"` with no `style.text`
- WHEN handled
- THEN 400 and no row is written

#### Scenario: position accepts the level schema

- GIVEN POST `kind="position"`, `points={entry:{time:1700000000,price:50000.0},stop:49000.0,take_profit:52000.0}`
- WHEN handled
- THEN 201 and the row persists (`test_market_api.py::test_drawings_position_post_get_put_round_trip`)

#### Scenario: position rejects bad points

- GIVEN POST `kind="position"` with a missing `stop`, a non-numeric `take_profit`, or `entry.price==stop`
- WHEN handled
- THEN 400 and no row is written (`test_market_api.py::test_drawings_position_post_invalid_points_is_400_and_writes_nothing`)

#### Scenario: Validation error matrix

| Input | Result |
|-------|--------|
| `kind` ∉ `DRAWING_KINDS` | 400, no write |
| `interval` present (any value) | accepted and ignored, no 400 |
| empty `symbol` | 400, no write |
| wrong point count for kind | 400, no write |
| malformed point (missing `price`) | 400, no write |
| `position` with degenerate `entry.price==stop` | 400, no write |
| valid payload | 201, row written |

### Requirement: R6 — Render contract (Lightweight Charts v5 primitive)

Drawings MUST render via the already-loaded Lightweight Charts v5.2.0 series
primitive API (`candleSeries.attachPrimitive`); no new dependency MAY be added.
Each drawing MUST draw through `CanvasRenderingTarget2D` coordinate spaces
(`useMediaCoordinateSpace` / `useBitmapCoordinateSpace`) with no DOM access, so
CSP is untouched. Price↔pixel MUST use `priceToCoordinate`/`coordinateToPrice`;
time↔pixel MUST use `timeScale().timeToCoordinate`/`coordinateToTime`. When a
coordinate maps to `null` (no bar on the axis), the draw MUST skip that leg
rather than throw. A `position` MUST draw a risk zone (entry→stop), a reward zone
(entry→take_profit), three level lines with labels, a `LONG`/`SHORT` label with a
directional arrow, and a `R:R` text, all via `position-core.positionBox`, and its
`autoscaleInfo` MUST include the `stop` and `take_profit` prices so pan/zoom does
not clip them. `position-core.positionBox` MUST degrade a band to null (never
coerce to 0) when a level's pixel maps to `null` — an off-scale stop/take_profit
MUST render no band rather than a band collapsed onto the price axis; a null box
(off-bar entry) MUST skip every leg. Full-width rays and
rectangles MUST supply `autoscaleInfo`. Redraw on pan/zoom MUST use the primitive's
`requestUpdate`. The selected drawing MUST render its highlight and handles in the
SAME primitive; a drag MUST re-render via `requestUpdate` and MUST NEVER call
`setData`/`update` on the series (#68). A drawing with `visible:false` MUST keep
its primitive attached but render nothing, and its `autoscaleInfo` MUST return
`null`; a toggle from hidden back to visible MUST re-render via `requestUpdate`
only. A `locked:true` drawing MUST render but MUST NOT be pointer-grabbable.
(Previously: no `position` render branch; `autoscaleInfo` did not include position
levels; no band-degrade-to-null clause.)

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

#### Scenario: position draws zones, levels, and R:R

- GIVEN a saved `position` with entry/stop/take_profit
- WHEN its primitive redraws
- THEN it draws the risk zone, the reward zone, three level lines with labels, a `LONG`/`SHORT` label with an arrow, and an `R:R` text (`drawing-primitive.test.js::renderShape draws a position via position-core (zones + levels + R:R)`)

#### Scenario: position autoscale includes stop and tp

- GIVEN a `position` whose levels sit outside the current price range
- WHEN `autoscaleInfo` is queried
- THEN the returned price range includes `stop` and `take_profit` (`drawing-primitive.test.js::autoscaleInfo of a position includes stop and take_profit (R6)`)

#### Scenario: Off-scale position band degrades to null

- GIVEN a `position` whose `stop` or `take_profit` maps to a null pixel (off-scale)
- WHEN `positionBox` builds the box
- THEN that band's `top`/`bottom` are `null` (never coerced to 0) and no band is drawn (`position-core` band guard; the S4/UI remediation `490d2de`)

#### Scenario: Hidden position renders blank without detaching

- GIVEN a `position` with `visible:false`
- WHEN its primitive redraws
- THEN nothing is drawn, the primitive stays attached, and `autoscaleInfo` is `null`

#### Scenario: Off-bar position anchor degrades gracefully

- GIVEN a `position` whose entry `time` maps to `null`
- WHEN the renderer draws
- THEN `positionBox` returns `null`, every leg is skipped, and nothing is thrown (`drawing-primitive.test.js::renderShape position degrades (no throw) when the entry is off-bar`)

#### Scenario: Drag never touches the series data path

- GIVEN a position drag in progress
- WHEN the shape re-renders
- THEN it uses `requestUpdate` only and no `setData`/`update` reaches the series

### Requirement: R7 — Load and restore on boot and switch

The chart MUST load drawings when it opens: after `buildChart`, fetch the caller's
drawings for the active `symbol` and attach their primitives; a failed fetch MUST
be non-fatal (the chart still renders). `switchTo(symbol, interval)` MUST
detach/clear the previous chart's primitives and reload ONLY when the `symbol`
changed; on an interval-only change drawings MUST stay attached with no refetch.
The `window.marketChart.drawings` seam MUST expose the loaded shapes for tests and
`window.marketChart` MUST keep exactly its 8 frozen keys (no new key).
(Previously: fetched per `(symbol, interval)` and cleared on every switch.)

#### Scenario: Reload restores saved drawings

- GIVEN saved drawings for the active symbol
- WHEN the page reloads
- THEN the chart attaches those primitives and `window.marketChart.drawings` lists them

#### Scenario: Symbol switch clears then loads

- GIVEN drawings on `BTCUSDT` and different ones on `ETHUSDT`
- WHEN `switchTo("ETHUSDT", "1m")` runs
- THEN BTCUSDT primitives are cleared and only ETHUSDT drawings are attached

#### Scenario: Interval-only switch keeps drawings

- GIVEN drawings rendered on `BTCUSDT 1m`
- WHEN `switchTo("BTCUSDT", "1h")` runs
- THEN the drawings stay attached and no drawings refetch is issued

#### Scenario: Failed fetch is non-fatal

- GIVEN the drawings fetch fails
- WHEN the chart boots
- THEN the chart renders with no drawings and no error surfaces

#### Scenario: Create and delete round-trip

- GIVEN a new shape drawn and saved
- WHEN the page reloads
- THEN the shape renders; after delete-by-id it is gone on reload

#### Scenario: Seam stays 8 keys

- GIVEN a booted chart
- WHEN `window.marketChart` is read
- THEN exactly `{chart, candleSeries, panes, ready, drawings, smc, smcCounts, smcToggles}` exist (no new key)

### Requirement: R8 — Read-only boundary, CSP, no new dependency

The change MUST NOT place, modify, or cancel orders, MUST NOT expose
order-execution endpoints, and MUST NOT relax R11; client code MUST stay
order-silent and the order scanner MUST remain clean. No inline `<script>` or
event handler MAY be added; all handlers MUST be `addEventListener` in
same-origin `chart.js` using the page CSRF token, so `Content-Security-Policy`
MUST be unchanged. No npm/build MAY be added; `requirements.txt` MUST be
unchanged and `src/` MUST stay framework-free.

#### Scenario: CSP unchanged

- GIVEN the rendered market page
- WHEN the header and templates are inspected
- THEN `Content-Security-Policy` equals the prior value and no inline script/handler exists

#### Scenario: No new runtime dependency

- GIVEN the manifest and templates
- WHEN scanned
- THEN no runtime dependency was added and `src/` imports no framework

#### Scenario: Order scanner clean

- GIVEN the drawings routes and client code
- WHEN the order scanner runs
- THEN no order-execution verb or endpoint is matched

### Requirement: R9 — Selection (hit-test + highlight)

A single drawing MAY be selected at a time. On `pointerdown` in the plot area the
resolver MUST hit-test handles FIRST, then the shape body via
`drawing-core.hitTest`; a miss MUST clear any current selection. A drawing MUST be
excluded from pointer hit-testing (both `pointerdown` and `dblclick`) — so it is
neither pointer-selectable nor draggable — when it is `locked:true` **OR** when it
is `visible:false` (an unseen drawing MUST NOT be grabbable); the shared guard is
`row.locked !== true && row.visible !== false` (`drawing-interaction.js`). A
flag-excluded drawing MUST remain selectable from the object tree (a bus emit,
not a pointer hit). The selected drawing MUST render a visible highlight (thicker
stroke and/or its handles). The controller MUST publish selection via
`bus.emit("drawing:selected", {id})`; selection state MUST live in the interaction
controller's closure, NOT in the frozen store keys.
(Previously: no `locked` exclusion; hidden-but-unlocked was still pointer-grabbable.)

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

#### Scenario: Hidden drawing is not pointer-selectable or draggable

- GIVEN a drawing with `visible:false` (and `locked:false`)
- WHEN `pointerdown` or `dblclick` lands within its hit radius
- THEN no selection, drag, or dialog occurs (the shared flag guard excludes it)

#### Scenario: Flag-excluded drawing stays tree-selectable

- GIVEN a drawing with `locked:true` or `visible:false`
- WHEN its tree row is selected
- THEN `drawing:selected` is emitted and the highlight shows

### Requirement: R10 — Per-kind handles and drag

The pure `drawing-interaction-core.js` MUST expose `handlesFor(kind, points, map)`
returning handle `{id,x,y}` positions (hline 1; trendline 2; fib 2; rect 4; text
1; position 4 — the `stop`, `take_profit`, and entry-price levels plus the entry
anchor), `grabHandle(items, x, y, radius)` returning the grabbed handle id,
`"body"`, or `null`, and `applyDrag(shape, target, dx, dy, map)` returning NEW
`points` (no mutation). Dragging a handle MUST move only that anchor; dragging the
body MUST translate every anchor by the same pixel delta. hline's drag MUST update
only `price`. Dragging a position level handle MUST move only that level's `price`
(y only); dragging the position body MUST translate `entry`, `stop`, and
`take_profit` together. `bodyHit` MUST treat the entry→stop ∪ entry→take_profit
span as the box body. The core MUST be deterministic, chart-lib-free, and MUST
clamp/guard null coordinates.
(Previously: no `position` cases in `handlesFor`/`applyDrag`/`bodyHit`.)

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

- GIVEN each of hline / trendline / fib / rect / text / position
- WHEN `handlesFor` runs
- THEN it returns exactly 1 / 2 / 2 / 4 / 1 / 4 handle(s)

#### Scenario: Drag position level

- GIVEN a selected `position`
- WHEN its `stop` handle is dragged vertically
- THEN only `points.stop` updates; `entry` and `take_profit` are unchanged (`drawing-interaction-core.test.js::applyDrag position moves ONLY the dragged stop level`)

#### Scenario: Move position box

- GIVEN a selected `position`
- WHEN its body is dragged
- THEN `entry`, `stop`, and `take_profit` all shift by the same mapped delta (`drawing-interaction-core.test.js::applyDrag position body shifts all three levels + the anchor column`)

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

### Requirement: R15 — Explicit SMC position seed (single source)

The position tool MUST offer an explicit "Position from setup" action (the
`#position-seed` button, `controllers/position-seed.js`) that copies `entry`,
`stop`, and `take_profit` **verbatim** from the already-fetched
`window.marketChart.smc.setups` payload. The button MUST be disabled until the
`smc:loaded` payload carries at least one setup (an empty payload re-disables it),
so a click can never silently no-op. The client MUST NOT recompute SMC levels (no
`find_setups` equivalent in JS). When no setup exists for the active key the tool
MUST still work from a user-drawn (three-click) box.

#### Scenario: Seed copies server levels verbatim

- GIVEN `window.marketChart.smc.setups` contains a setup with `{entry,stop,take_profit}`
- WHEN the "Position from setup" action runs
- THEN the created `position` row carries those exact three levels (most recent setup)
- AND no JS SMC recompute path is executed (E2E `test_position_seed_copies_smc_setup_verbatim`)

#### Scenario: Works without a setup

- GIVEN no setup for the active key
- WHEN the user draws a position box
- THEN the three-click flow still produces a persisted `position` (E2E `test_position_three_click_persists_and_drag_one_put`)
