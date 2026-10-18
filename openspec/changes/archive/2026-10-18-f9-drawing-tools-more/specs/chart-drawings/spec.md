# Delta for chart-drawings

Issue #122 (F9): the drawing surface gains **eight** new kinds — `ray`, `vline`,
`channel`, `price`, `callout`, `fib_ext`, `fib_time`, `fib_zone` — over the SAME
persistence / render / interaction stack. Persistence needs ONE new choices-only
migration `0016_drawing_kind_tools` (`Drawing.kind` is a `choices` CharField,
`models.py:244-249,253`; `parse_drawing` rejects any kind outside `DRAWING_KINDS`,
`quotes.py:402,440-441`; F6's `0015` is the precedent). `channel` is the 3-point
`{p1,p2,p3}` schema; `fib_ext` uses a NEW `FIB_EXT_RATIOS` (extension ratios > 1);
`fib_time`/`fib_zone` reuse `FIB_RATIOS`; `price` is a labelled horizontal line,
distinct from `hline`; `callout` reuses `#text-dialog`. This MODIFIES R1 (model +
`0016`), R4 (validation matrix), R5 (per-kind schemas), R6 (render), R10
(handles/drag). R2 (CRUD), R8 (read-only/CSP), R15 (SMC seed) stay in force and
unmodified; R3, R7, R9, R11–R14 stay in force.

## MODIFIED Requirements

### Requirement: R1 — Drawing model, ownership, and index

`Drawing` MUST inherit `UserOwnedModel` (owner FK `on_delete=CASCADE` +
`for_user`) and carry `symbol` (max 32), `kind` (`CharField`, one of
`DRAWING_KINDS`), `points` (`JSONField`), `style` (`JSONField`), `created_at`
(`auto_now_add`), plus `visible` (`BooleanField`, default `True`) and `locked`
(`BooleanField`, default `False`). It MUST be indexed on `(user, symbol)` and MUST
NOT carry a unique constraint on that tuple. No owner-less rows MAY exist.
`DRAWING_KINDS` MUST include `position` — a `Drawing.Kind.POSITION` choice in
`web/trading/models.py` (`models.py:244-250`), surfaced through
`drawing-core.js` `DRAWING_KINDS` (`drawing-core.js:13`). `DRAWING_KINDS` MUST
also include the eight F9 kinds — `Drawing.Kind` gains `RAY`/`VLINE`/`CHANNEL`/
`PRICE`/`CALLOUT`/`FIB_EXT`/`FIB_TIME`/`FIB_ZONE` (`models.py:244-249`) and
`drawing-core.js` `DRAWING_KINDS` (`drawing-core.js:13`) gains the matching
strings. Migration `0012` MUST remove the old `(user, symbol, interval)` index
BEFORE dropping `interval`, then add the `(user, symbol)` index (SQLite-safe
order). It MUST keep ALL rows and MUST NOT dedupe. Its reverse MUST be lossy
(re-adds `interval` defaulted to `"1m"`). Migration `0014` MUST be a purely
additive AddField pair adding `visible`/`locked`, reversible with zero data loss.
Migration `0015` MUST be a choices-only `AlterField` on `kind` (deps
`0014_drawing_visible_locked`) widening choices with `position`, reversible to
`0014`. Migration `0016_drawing_kind_tools` MUST be a choices-only `AlterField` on
`kind` (deps `0015_drawing_kind_position`) that widens the choices with all eight
F9 kinds at once (mirrors `0015_drawing_kind_position.py`) and MUST be reversible
to `0015` with zero data loss — reverse restores the prior choices and every
stored row keeps its `kind`; it MUST touch no column and no row (SQLite-safe —
`choices` lives in Django state). The delivered migration chain is
`0012 → 0013 → 0014 → 0015 → 0016`, and `makemigrations --check` MUST be green.
(Previously: six kinds and no `0016`; the chain ended at `0015`.)

#### Scenario: Many drawings coexist on one chart

- GIVEN A has a `hline` on `BTCUSDT`
- WHEN A creates a second `trendline` on the same symbol
- THEN both rows persist (no `IntegrityError`, distinct `id`)

#### Scenario: position is a valid kind

- GIVEN a `Drawing` row with `kind="position"`
- WHEN `DRAWING_KINDS` is read
- THEN `"position"` is a member

#### Scenario: The eight F9 kinds are valid members

- GIVEN the eight new kind strings
- WHEN `DRAWING_KINDS` (`quotes.py:402`) and `drawing-core.js` `DRAWING_KINDS` are read
- THEN each of `ray`/`vline`/`channel`/`price`/`callout`/`fib_ext`/`fib_time`/`fib_zone` is a member of both

#### Scenario: 0016 is choices-only and reversible

- GIVEN existing drawings of every prior kind
- WHEN `0016` runs forward then reverse
- THEN every row keeps its kind and data, all eight F9 kinds are selectable after forward, and reverse restores the prior choices with no row lost (`test_migration_0016.py`; `makemigrations --check` green)

#### Scenario: 0015 is choices-only and reversible

- GIVEN existing drawings of every prior kind
- WHEN `0015` runs forward then reverse
- THEN every row keeps its kind and data, `position` is selectable after forward, and reverse restores the prior choices with no row lost

### Requirement: R4 — Validation before write (kind / points / style)

The server MUST validate the payload BEFORE any write; an unknown `kind`, a
`kind` outside `DRAWING_KINDS`, an empty `symbol`, or `points`/`style` not matching
the kind's schema MUST yield 400 `{"error":"..."}` and MUST NOT create a row.
`interval` is NO LONGER part of the drawing contract: its presence or value MUST
NOT yield 400 (accept-and-ignore). Validation MUST live in a pure
`parse_drawing(kind, points, style)` (raise `ValueError`) in `quotes.py`; the view
maps it to 400. `parse_drawing` MUST gain one branch per F9 kind
(`quotes.py:427-461`) so a valid F9 payload passes and a malformed one 400s before
any write (the `position` `elif` at `:445-460` is the precedent). A new kind with
no branch here MUST 400.

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

#### Scenario: F9 kind matrix validates per kind

- GIVEN each F9 kind's valid payload and each of its malformed variants (wrong point count, missing `time`/`price`, missing `text`, non-numeric `price`)
- WHEN POST
- THEN the valid payload is 201 and each malformed payload is 400 with no row written (`test_market_api.py` per-kind parse matrix)

### Requirement: R5 — Kind-specific point and style schemas

Each `kind` MUST enforce its schema: `hline` = exactly 1 point `{time,price}`
(`time` optional), `style {color,width}`; `trendline` = exactly 2 points;
`fib` = exactly 2 points, `style {levels:[...]}`; `rect` = exactly 2 points,
`style {color,fill}`; `text` = 1 point plus a non-empty label in `style.text`,
`style {color}`; `position` = `points` `{entry:{time,price}, stop:number,
take_profit:number}` with numeric `entry.price`, `stop`, `take_profit`, and MUST
reject a missing field, a non-numeric level, or a degenerate `entry.price==stop`
with 400. The eight F9 kinds MUST enforce: `ray` = exactly 2 points
`{time,price}`; `callout` = exactly 2 points `{time,price}` plus a non-empty
`points.text`; `fib_time` = exactly 2 points; `fib_zone` = exactly 2 points;
`channel` = exactly 3 points `{p1,p2,p3}`; `fib_ext` = exactly 3 points
`{p1,p2,p3}`; `vline` = 1 point `{time}` only (no `price`); `price` = 1 point
`{price}` only (no `time`). A count or shape mismatch MUST be rejected with 400.
`DRAWING_KINDS` MUST auto-include every F9 kind so a payload passes the kind check
before the schema branch runs.
(Previously: no F9 schema branches.)

#### Scenario: hline accepts one point

- GIVEN POST `kind="hline"`, `points=[{price:50000.0}]`
- WHEN handled
- THEN 201 and the row persists

#### Scenario: position rejects bad points

- GIVEN POST `kind="position"` with a missing `stop`, a non-numeric `take_profit`, or `entry.price==stop`
- WHEN handled
- THEN 400 and no row is written

#### Scenario: vline accepts a time-only point

- GIVEN POST `kind="vline"`, `points={time:1700000000}`
- WHEN handled
- THEN 201 and the row persists; a `vline` payload missing `time` is 400

#### Scenario: price accepts a price-only point

- GIVEN POST `kind="price"`, `points={price:50000.0}`
- WHEN handled
- THEN 201 and the row persists; a `price` payload missing `price` is 400

#### Scenario: channel requires three points

- GIVEN POST `kind="channel"` with `{p1,p2,p3}` each `{time,price}`
- WHEN handled
- THEN 201; a 2-point or a 4-point `channel` is 400 with no write

#### Scenario: fib_ext requires three points

- GIVEN POST `kind="fib_ext"` with `{p1,p2,p3}` each `{time,price}`
- WHEN handled
- THEN 201; a 2-point `fib_ext` is 400 with no write

#### Scenario: ray and fib kinds require two points

- GIVEN POST `kind` in `{ray, fib_time, fib_zone}` with exactly 2 `{time,price}` points
- WHEN handled
- THEN 201; a 1-point or 3-point payload for any of them is 400 with no write

#### Scenario: callout requires two points plus text

- GIVEN POST `kind="callout"` with 2 `{time,price}` points and a non-empty `points.text`
- WHEN handled
- THEN 201; a `callout` missing `text` is 400 with no write

#### Scenario: Validation error matrix

| Input | Result |
|-------|--------|
| `kind` ∉ `DRAWING_KINDS` | 400, no write |
| `interval` present (any value) | accepted and ignored, no 400 |
| empty `symbol` | 400, no write |
| wrong point count for kind | 400, no write |
| malformed point (missing `price`) | 400, no write |
| `vline` point carrying `price` only | 400, no write |
| `callout` missing `text` | 400, no write |
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
coerce to 0) when a level's pixel maps to `null`; a null box MUST skip every leg.
Full-width rays and rectangles MUST supply `autoscaleInfo`. Redraw on pan/zoom
MUST use the primitive's `requestUpdate`. The selected drawing MUST render its
highlight and handles in the SAME primitive; a drag MUST re-render via
`requestUpdate` and MUST NEVER call `setData`/`update` on the series (#68). A
drawing with `visible:false` MUST keep its primitive attached but render nothing,
and its `autoscaleInfo` MUST return `null`; a toggle from hidden back to visible
MUST re-render via `requestUpdate` only. A `locked:true` drawing MUST render but
MUST NOT be pointer-grabbable. The eight F9 kinds MUST each draw their geometry in
the same primitive: `ray` a line from `p1` through `p2` extended to the RIGHT edge
only; `vline` a full-height vertical line at its `time`; `channel` two parallel
lines (base `p1→p2`, parallel through `p3`); `price` a horizontal line **plus a
right-axis price label**; `callout` an anchor point, an arrow, and a text balloon;
`fib_ext` the `FIB_EXT_RATIOS` extension levels projected from the 3-point swing;
`fib_time` vertical lines at `FIB_RATIOS` over the bar span; `fib_zone` coloured
bands between consecutive `FIB_RATIOS` levels. `fib_ext`/`fib_time`/`fib_zone` MUST
show ratio labels (as `fib` does, `drawing-primitive.js:64`) and `price` MUST show
a price tag, so no F9 kind is distinguished by color alone. `autoscaleInfo` MUST
include ALL of a kind's anchors (`p1`,`p2`,`p3` for `channel`/`fib_ext`; the
`price` for `price`/`vline`'s time is x-only) so pan/zoom does not clip them.
(Previously: no F9 render branch; `autoscaleInfo` included no `p3`.)

#### Scenario: Attach one primitive per drawing

- GIVEN a chart with N saved drawings
- WHEN the chart is built
- THEN N primitives are attached to the candle series

#### Scenario: Hidden drawing renders blank without detaching

- GIVEN a drawing with `visible:false`
- WHEN its primitive redraws
- THEN nothing is drawn, the primitive stays attached, and `autoscaleInfo` is `null`

#### Scenario: Off-bar anchor degrades gracefully

- GIVEN a drawing whose `time` maps to `null` on the current time scale
- WHEN the renderer draws
- THEN it skips that leg and does not throw

#### Scenario: Drag never touches the series data path

- GIVEN a drag in progress
- WHEN the shape re-renders
- THEN it uses `requestUpdate` only and no `setData`/`update` reaches the series

#### Scenario: Each F9 kind draws its geometry

- GIVEN a saved drawing of each F9 kind
- WHEN its primitive redraws
- THEN it draws the kind's geometry per the render contract (ray extension, vline, parallel channel, labelled price line, callout balloon, fib_ext/time/zone levels via their cores), asserted by `drawing-primitive.test.js` node path-builder cases

#### Scenario: F9 autoscale includes all anchors

- GIVEN a `channel`/`fib_ext` whose `p3` sits outside the current price range
- WHEN `autoscaleInfo` is queried
- THEN the returned price range includes `p1`, `p2`, and `p3` (`drawing-primitive.test.js::autoscaleInfo of a channel/fib_ext includes p3`)

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
clamp/guard null coordinates. For the F9 kinds `handlesFor` MUST return `ray` 2,
`callout` 2, `fib_time` 2, `fib_zone` 2, `channel` 3, `fib_ext` 3, `vline` 1,
`price` 1 handle(s); dragging a handle MUST move ONLY its anchor (`p1`/`p2`/`p3`,
or `vline`'s `time`, or `price`'s `price`), and dragging the body MUST shift the
whole shape by the same mapped delta. `drawing-interaction-core.js:31,107,162`
MUST each gain ONE guard dispatching F9 kinds to the `drawing-tools-core`
descriptor map (`Tools.toolHandles`/`toolBodyHit`/`toolDrag`).
(Previously: no `position` cases and no F9 cases in `handlesFor`/`applyDrag`/`bodyHit`.)

#### Scenario: Drag a trendline endpoint

- GIVEN a selected `trendline`
- WHEN its `p2` handle is dragged to a new pixel
- THEN only `p2` becomes the mapped `{time,price}`; `p1` is unchanged

#### Scenario: Drag position level

- GIVEN a selected `position`
- WHEN its `stop` handle is dragged vertically
- THEN only `points.stop` updates; `entry` and `take_profit` are unchanged

#### Scenario: F9 handle counts resolve per kind

- GIVEN each F9 kind
- WHEN `handlesFor` runs
- THEN it returns exactly ray 2 / callout 2 / fib_time 2 / fib_zone 2 / channel 3 / fib_ext 3 / vline 1 / price 1 handle(s) (`drawing-interaction-core.test.js` node cases)

#### Scenario: Drag an F9 anchor moves only it

- GIVEN a selected `channel`
- WHEN its `p3` handle is dragged
- THEN only `p3` changes; `p1` and `p2` are unchanged

#### Scenario: Drag a vline moves time only

- GIVEN a selected `vline`
- WHEN its handle is dragged
- THEN `points.time` updates and no `price` is added

#### Scenario: Move an F9 shape body

- GIVEN a selected `fib_ext` (or `ray`/`callout`)
- WHEN its body is dragged
- THEN every anchor shifts by the same mapped delta (`drawing-interaction-core.test.js`)
