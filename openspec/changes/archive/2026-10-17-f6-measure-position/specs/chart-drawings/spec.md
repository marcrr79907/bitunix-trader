# Delta for chart-drawings

Issue #119 (F6): drawings gain a persisted `position` kind — a Long/Short box with
entry / stop / take-profit and a live R:R readout, seedable verbatim from the
single-source SMC `setups`. This MODIFIES R1 (`Kind` enum gains `POSITION`;
choices-only migration `0015`), R5 (`position` points schema
`{entry:{time,price}, stop:number, take_profit:number}`), R6 (risk/reward zones,
3 levels + labels + R:R text; `autoscaleInfo` includes `stop`/`take_profit`), and
R10 (position handles + drag). R2 (CRUD) and R8 (read-only boundary) stay in force
and are reused unmodified: position rows ride the existing `api_drawings` route,
`for_user` scoped. R3/R4/R7/R9/R11–R14 stay in force and unmodified.

## MODIFIED Requirements

### Requirement: R1 — Drawing model, ownership, and index

`Drawing` MUST inherit `UserOwnedModel` (owner FK `on_delete=CASCADE` +
`for_user`) and carry `symbol` (max 32), `kind` (`CharField`, one of
`DRAWING_KINDS`), `points` (`JSONField`), `style` (`JSONField`), `created_at`
(`auto_now_add`), plus `visible` (`BooleanField`, default `True`) and `locked`
(`BooleanField`, default `False`). It MUST be indexed on `(user, symbol)` and MUST
NOT carry a unique constraint on that tuple. No owner-less rows MAY exist.
`DRAWING_KINDS` MUST include `position` (a `Drawing.Kind.POSITION` choice in
`web/trading/models.py:244-249`). Migration `0015` MUST be a choices-only
`AlterField` on `kind`, MUST be reversible, and MUST lose no data (`0014` is the
additive precedent). Migration `0012` MUST remove the old `(user, symbol,
interval)` index BEFORE dropping `interval`, then add the `(user, symbol)` index
(SQLite-safe order). It MUST keep ALL rows and MUST NOT dedupe. Its reverse MUST
be lossy — it re-adds `interval` defaulted to `"1m"`; the original per-interval
split is NOT recoverable. Migration `0014` MUST be a purely additive AddField pair
(`0013_chartpreference_smc.py:17-21` precedent): it MUST add `visible` and `locked`
and MUST be reversible with zero data loss.
(Previously: `DRAWING_KINDS` had no `position`; no `0015`.)

#### Scenario: Many drawings coexist on one chart

- GIVEN A has a `hline` on `BTCUSDT`
- WHEN A creates a second `trendline` on the same symbol
- THEN both rows persist (no `IntegrityError`, distinct `id`)

#### Scenario: position is a valid kind

- GIVEN a `Drawing` row with `kind="position"`
- WHEN `DRAWING_KINDS` is read
- THEN `"position"` is a member

#### Scenario: 0015 is choices-only and reversible

- GIVEN existing drawings of every prior kind
- WHEN `0015` runs forward then reverse
- THEN every row keeps its kind and data, `position` is selectable after forward, and reverse restores the prior choices with no row lost (`makemigrations --check` green)

#### Scenario: Interval drop keeps every row (0012)

- GIVEN A has a drawing on `(BTCUSDT, 1m)` and one on `(BTCUSDT, 1h)`
- WHEN `0012` runs
- THEN both rows survive as distinct drawings under `BTCUSDT`

#### Scenario: 0014 is additive and reversible

- GIVEN existing drawings
- WHEN `0014` runs forward then reverse
- THEN both rows keep all prior fields, `visible`/`locked` appear with their defaults, and a further reverse drops them with no row lost

#### Scenario: Defaults on new rows

- GIVEN a drawing created without flags
- WHEN the row is read
- THEN `visible is True` and `locked is False`

### Requirement: R5 — Kind-specific point and style schemas

Each `kind` MUST enforce its schema: `hline` = exactly 1 point `{time,price}`
(`time` optional), `style {color,width}`; `trendline` = exactly 2 points;
`fib` = exactly 2 points, `style {levels:[...]}`; `rect` = exactly 2 points,
`style {color,fill}`; `text` = 1 point plus a non-empty label in `style.text`,
`style {color}`; `position` = `points` `{entry:{time,price}, stop:number,
take_profit:number}` with numeric `entry.price`, `stop`, `take_profit`, and MUST
reject a missing field, a non-numeric level, or a degenerate `entry.price==stop`
with 400. A count or shape mismatch MUST be rejected with 400.
(Previously: no `position` schema branch.)

#### Scenario: hline accepts one point

- GIVEN POST `kind="hline"`, `points=[{price:50000.0}]`
- WHEN handled
- THEN 201 and the row persists

#### Scenario: position accepts the level schema

- GIVEN POST `kind="position"`, `points={entry:{time:1700000000,price:50000.0},stop:49000.0,take_profit:52000.0}`
- WHEN handled
- THEN 201 and the row persists

#### Scenario: position rejects bad points

- GIVEN POST `kind="position"` with a missing `stop`, a non-numeric `take_profit`, or `entry.price==stop`
- WHEN handled
- THEN 400 and no row is written

#### Scenario: Validation error matrix

| Input | Result |
|-------|--------|
| `kind` ∉ `DRAWING_KINDS` | 400, no write |
| `interval` present (any value) | accepted and ignored, no 400 |
| empty `symbol` | 400, no write |
| wrong point count/shape for kind | 400, no write |
| `position` with degenerate `entry.price==stop` | 400, no write |
| valid payload | 201, row written |

### Requirement: R6 — Render contract (Lightweight Charts v5 primitive)

Drawings MUST render via the already-loaded Lightweight Charts v5.2.0 series
primitive API (`candleSeries.attachPrimitive`); no new dependency MAY be added.
Each drawing MUST draw through `CanvasRenderingTarget2D` coordinate spaces
(`useMediaCoordinateSpace` / `useBitmapCoordinateSpace`) with no DOM access, so
CSP is untouched. Price↔pixel MUST use `priceToCoordinate`/`coordinateToPrice`;
time↔pixel MUST use `timeScale().timeToCoordinate`/`coordinateToTime`. When a
coordinate maps to `null`, the draw MUST skip that leg rather than throw. A
`position` MUST draw a risk zone (entry→stop), a reward zone (entry→take_profit),
three level lines with labels, and an R:R text, all via
`position-core.positionBox`, and its `autoscaleInfo` MUST include the `stop` and
`take_profit` prices so pan/zoom does not clip them. Full-width rays and
rectangles MUST supply `autoscaleInfo`. Redraw on pan/zoom MUST use the primitive's
`requestUpdate`. The selected drawing MUST render its highlight and handles in the
SAME primitive; a drag MUST re-render via `requestUpdate` and MUST NEVER call
`setData`/`update` on the series (#68). A drawing with `visible:false` MUST keep
its primitive attached but render nothing, and its `autoscaleInfo` MUST return
`null`; a toggle from hidden back to visible MUST re-render via `requestUpdate`
only. A `locked:true` drawing MUST render but MUST NOT be pointer-grabbable.
(Previously: no `position` render branch; `autoscaleInfo` did not include position levels.)

#### Scenario: Attach one primitive per drawing

- GIVEN a chart with N saved drawings
- WHEN the chart is built
- THEN N primitives are attached to the candle series

#### Scenario: position draws zones, levels, and R:R

- GIVEN a saved `position` with entry/stop/take_profit
- WHEN its primitive redraws
- THEN it draws the risk zone, the reward zone, three level lines with labels, and an R:R text

#### Scenario: position autoscale includes stop and tp

- GIVEN a `position` whose levels sit outside the current price range
- WHEN `autoscaleInfo` is queried
- THEN the returned price range includes `stop` and `take_profit`

#### Scenario: Hidden position renders blank without detaching

- GIVEN a `position` with `visible:false`
- WHEN its primitive redraws
- THEN nothing is drawn, the primitive stays attached, and `autoscaleInfo` is `null`

#### Scenario: Off-bar anchor degrades gracefully

- GIVEN a `position` whose entry `time` maps to `null`
- WHEN the renderer draws
- THEN it skips that leg and does not throw

#### Scenario: Drag never touches the series data path

- GIVEN a position drag in progress
- WHEN the shape re-renders
- THEN it uses `requestUpdate` only and no `setData`/`update` reaches the series

### Requirement: R10 — Per-kind handles and drag

The pure `drawing-interaction-core.js` MUST expose `handlesFor(kind, points, map)`
returning handle `{id,x,y}` positions (hline 1; trendline 2; fib 2; rect 4; text
1; position 4 — the stop, take_profit, entry-price levels plus the entry anchor),
`grabHandle(items, x, y, radius)` returning the grabbed handle id, `"body"`, or
`null`, and `applyDrag(shape, target, dx, dy, map)` returning NEW `points` (no
mutation). Dragging a level handle MUST move only that level's `price` (y only);
dragging the body MUST translate the whole box. `bodyHit` MUST treat the
entry→stop ∪ entry→take_profit span as the box body. The core MUST be
deterministic, chart-lib-free, and MUST clamp/guard null coordinates.
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

#### Scenario: Drag position level

- GIVEN a selected `position`
- WHEN its `stop` handle is dragged vertically
- THEN only `points.stop` updates; `entry` and `take_profit` are unchanged

#### Scenario: Move position box

- GIVEN a selected `position`
- WHEN its body is dragged
- THEN `entry`, `stop`, and `take_profit` all shift by the same mapped delta

#### Scenario: Drag resolves per kind

- GIVEN each of hline / trendline / fib / rect / text / position
- WHEN `handlesFor` runs
- THEN it returns exactly 1 / 2 / 2 / 4 / 1 / 4 handle(s)

## ADDED Requirements

### Requirement: R15 — Explicit SMC seed (single source)

The position tool MUST offer an explicit "position from setup" action that copies
`entry`, `stop`, and `take_profit` **verbatim** from the already-fetched
`window.marketChart.smc.setups` payload. The client MUST NOT recompute SMC levels
(no `find_setups` equivalent in JS). When no setup exists for the active key the
tool MUST still work from a user-drawn box.

#### Scenario: Seed copies server levels verbatim

- GIVEN `window.marketChart.smc.setups` contains a setup with `{entry,stop,take_profit}`
- WHEN the "position from setup" action runs
- THEN the created `position` row carries those exact three levels
- AND no JS SMC recompute path is executed

#### Scenario: Works without a setup

- GIVEN no setup for the active key
- WHEN the user draws a position box
- THEN the three-click flow still produces a persisted `position`
