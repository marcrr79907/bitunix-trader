# Design: f6-measure-position (issue #119, Fase F6)

## Technical Approach

Layered F0/F5 extension (`docs/architecture/chart-modules.md:9-17`). Two new
**pure cores** hold all new geometry (`measure-core.js`, `position-core.js`);
one new **controller** (`controllers/measure.js`, ephemeral gesture) plus
kind-agnostic branches in the existing drawing stack carry the two instruments.
Every touched module stays ≤300 (`test_module_size_guard.py:20`, allowlist empty).
The two at-ceiling modules `controllers/smc.js`=300 and `controllers/object-tree.js`=299
stay **byte-untouched** by construction: position rows ride the *existing generic*
Drawings group (`object-tree.js:130` renders `row.kind+" #"+row.id` for any kind,
and `TREE_GROUPS[0].kinds` is never consumed — only `TREE_GROUPS[0].label` at
`object-tree.js:22`), and measure is a separate controller that never imports `smc.js`.
Persistence reuses `Drawing` CRUD unchanged (`views.py:397-534`, `for_user`-scoped);
the only server deltas are a choices-only migration and one `parse_drawing` branch.
#68 held: both instruments render on primitives + `requestUpdate`; neither calls
`setData`/`update`.

## Architecture Decisions

| # | Decision | Choice | Alternatives rejected | Rationale |
|---|---|---|---|---|
| D1 | Measure persistence | **Ephemeral**, own `controllers/measure.js`, own primitive, own Escape | persisted `Drawing` kind | Ephemeral = zero migration/CRUD/store-key, TradingView parity (`explore.md:149-158`). A saved measure pollutes the tree for no value |
| D2 | Position persistence | `Drawing.Kind.POSITION`, reuses `api_drawings` + primitive + interaction + tree | separate model | Deletion test: removing it re-materializes CRUD+primitive+tree; reuse is the correct seam (`explore.md:160-170`) |
| D3 | Excluding both new tools from `STORE_KEYS`/seam | measure/position add **no** store key and **no** `window.marketChart` key | new store slot / 9th seam key | R3/R2 freeze: active tool is already `store.tool` (`chart-store.js:23`); seam is 8 keys (`main.js:55-64`) |
| D4 | Measure tool ↔ interaction controller | measure owns its own `#chart` pointer listeners guarded by `state.tool==="measure"`; `drawing-interaction.onPointerDown` already bails in tool mode (`drawing-interaction.js:94`) | share one listener set | No coupling; both bind once, no capture conflict (`explore.md:299`) |
| D5 | SMC seed | Explicit `#position-seed` button; `drawings.js` caches `setups` from `bus.on("smc:loaded")` and copies `entry/stop/take_profit` **verbatim** | auto-seed first box drawn; DOM-read `window.marketChart.smc` | Explicit = testable, unsurprising (`explore.md:312`); `smc:loaded` subscription avoids a controller reading a global |
| D6 | Position point schema | `{entry:{time,price}, stop:number, take_profit:number}` | three `{time,price}` anchors / `{p1,p2,p3}` | SL/TP are horizontal levels; only entry needs a time (`explore.md:305`) |
| D7 | Position render | `renderShape` position branch delegates geometry to `position-core.positionBox`, which returns draw descriptors; primitive only draws | draw logic inline in primitive | Keeps `drawing-primitive.js` ≤150; mirrors SMC descriptor pattern (`smc.js:102`) |
| D8 | Measure readout | DOM `#measure-readout aria-live="polite"` (mirrors `#rsi`, `chart.html:47`) | canvas text only | Canvas is invisible to AT; R6/R9 (`design-system/spec.md:141-151`) |

## Module Decomposition & Line Budget

New files (all pure-core or controller, all ≤300):

| File | Action | Lines | Exports / role |
|---|---|---|---|
| `market/measure-core.js` | **New** | ~100 | `measure(a,b,intervalSeconds)`, `formatMeasure(m)` |
| `market/position-core.js` | **New** | ~130 | `levelsFrom`, `riskReward`, `positionBox`, `positionHandles`, `defaultPositionStyle` |
| `controllers/measure.js` | **New** | ~180 | `createMeasure({store,bus,host,config})` → `{attach,clearForSwitch}` |

Before → after on every **touched** module (baseline `wc -l`, verified):

| File | Now | Δ | After | What changes |
|---|---|---|---|---|
| `controllers/drawings.js` | 240 | +22 | **~262** | `position` branch in `onChartClick` collecting entry→stop→tp (~16); `setups` cache via `bus.on("smc:loaded")` + `seedFromSetup` (~6); `#position-seed` listener (~2, reuses existing `textDialog` listener block 212-225) |
| `drawing-interaction-core.js` | 230 | +20 | **~250** | `position` cases in `handlesFor` (3 handles), `bodyHit` (box), `applyDrag` (level vs body) |
| `drawing-primitive.js` | 135 | +13 | **~148** | `position` branch → `position-core.positionBox` (~11) + import (~1) + `priceRangeFor` pushes `stop`/`take_profit` (~1) |
| `drawing-core.js` | 162 | +4 | **~166** | `"position"` in `DRAWING_KINDS:13` + `defaultStyle` branch (`:25-30`) |
| `tool-icons-core.js` | 69 | +14 | **~83** | +`{label:"Measure",kinds:["measure"]}` +`{label:"Positions",kinds:["position"]}` in `TOOL_GROUPS:14`; +2 `ICON_BODIES:33`; optional `"position"` in `TREE_GROUPS[0].kinds` (non-load-bearing) |
| `controllers/draw-toolbar.js` | 99 | +2 | **~101** | `TOOL_LABELS:17-23` +`measure` +`position` |
| `main.js` | 249 | +6 | **~255** | `createMeasure` import+create; `buildChart` `measure.attach()`; `switchTo` `measure.clearForSwitch()` |
| `chart-host.js` | 267 | **0** | 267 | untouched — measure binds `#chart`, not the host |
| `controllers/smc.js` | 300 | **0** | 300 | **UNTOUCHED** — seed only reads its `smc:loaded` payload |
| `controllers/object-tree.js` | 299 | **0** | 299 | **UNTOUCHED** — generic row renderer already shows `position #id` |
| `chart-store.js` / `chart-bus.js` | 61 / 54 | **0** | 61 / 54 | **UNTOUCHED** — no key, no event (`store.tool` + literal events suffice) |
| `controllers/drawing-interaction.js` | 227 | **0** | 227 | **UNTOUCHED** — `grabHandle`/`applyDrag` are data-driven (`drawing-interaction.js:97,121`) |

**Ceiling proof.** `smc.js` and `object-tree.js` are untouched, so the two modules
at/edge of the ceiling cannot regress. The proof is structural, not a budget target:
(a) measure lives in a *new* controller and never imports `smc.js`; (b) the position
`Drawing` row is rendered by the *kind-agnostic* loops already in `object-tree.js`
(`drawingRow` at `:106-144` keys off `row.kind`/`row.id`, never an exhaustive kind match).
The largest touched module is `drawings.js` at ~262, 38 lines under the ceiling.

## Layer Compliance

| New module | F0 layer | Allowed imports | DI |
|---|---|---|---|
| `measure-core.js` | Pure core | `chart-core.js` (`intervalSeconds`) only | — |
| `position-core.js` | Pure core | nothing | — |
| `controllers/measure.js` | Controller | cores, host, store, bus — **never `main`** | `create({store,bus,host,config})` |

`drawings.js`/`drawing-interaction-core.js`/`drawing-primitive.js` stay in their
existing layers; the only new cross-core edge is `drawing-primitive →
position-core` (core→core, allowed) and `drawings`/`measure` (controller→core).
No controller imports `main` (`docs/architecture/chart-modules.md:16,20-21`).

## Data Flow

**(a) Measure gesture → ephemeral readout** (no store/seam/server):

    #chart pointerdown (state.tool==="measure")
      └─▶ measure: a = {time: map.time(x), price: map.price(y)}
    #chart pointermove
      └─▶ b = same; m = measure-core.measure(a, b, intervalSeconds(state.interval))
            ├─▶ attachPrimitive (once) → requestUpdate()   (autoscaleInfo → null)
            └─▶ #measure-readout.textContent = formatMeasure(m)   (aria-live)
    #chart pointerup  → measurement stays (readable)
    new pointerdown | Esc | tool-change | symbol-switch
      └─▶ detachPrimitive + clear #measure-readout            (no persist anywhere)

**(b) Position 3-click → POST → fromApi → primitive** (reuses existing path):

    host.subscribeClick → drawings.onChartClick(param)   [main.js:116]
      click 1: pendingPosition.entry = {time, price}
      click 2: pendingPosition.stop  = price
      click 3: pendingPosition.take_profit = price
        └─▶ createDrawing("position", {entry,stop,take_profit}, defaultPositionStyle)
              └─▶ POST /market/api/drawings  [drawings.js:134-155, no new route]
                    └─▶ _post_drawing → parse_drawing("position",…)   [views.py:446]
              └─▶ Draw.fromApi(row) → currentDrawings.push → attachAllDrawings()
                    └─▶ makeDrawingPrimitive → renderShape position branch

**(c) Position drag (level vs body) → partial PUT** (kind-agnostic controller):

    #chart pointerdown (state.tool===null)
      └─▶ grabHandle(rows, …) → handlesFor("position") → {id, target:0|1|2|"body"}
    pointermove → applyDrag(row,target,dx,dy,map) → fresh points
      target entry → entry.{time,price};  stop/tp → price (y) only;  body → all three
      └─▶ bus.emit("drawing:changed",{id,points,persist:false}) → requestUpdate()
    pointerup → bus.emit("drawing:changed",{id,points,persist:true})
      └─▶ drawings.js → PUT {points}  [drawings.js:109-114, 126-132]

**(d) SMC seed verbatim → createDrawing**:

    smc:loaded {payload}  ──▶ drawings.setups = payload.setups   (cached)
    #position-seed click
      └─▶ s = setups[setups.length-1]   (most recent for the active key)
      └─▶ createDrawing("position", {entry:{time:s.time, price:s.entry},
                                     stop:s.stop, take_profit:s.take_profit}, style)
            (no re-derivation; the client only re-derives R:R while the user drags — D5)

## Interfaces / Contracts

```js
// measure-core.js — pure, never throws; off-value → null field, not a throw.
export function measure(a, b, intervalSeconds) {
  // a,b = {time:int|null, price:number|null}
  // -> { priceDelta, pricePct, timeDelta, bars, candles }
  // timeDelta/bars/candles are null when a.time or b.time is null (off-bar).
  // negative deltas are kept (direction by sign); bars = round(timeDelta/iv).
  // candles === bars in v1 (one candle per bar); kept as a named key for parity.
}
export function formatMeasure(m) {
  // -> { price:string, pct:string, time:string, bars:string } for the DOM readout.
}

// position-core.js — pure, never throws.
export const BOX_WIDTH = 120;               // px, right from the entry column
export function levelsFrom(points) {
  // {entry:{time,price}, stop, take_profit} -> {entry:number, stop, takeProfit, long}
  // long = stop < entry; null when points invalid (missing/non-numeric levels).
}
export function riskReward(entry, stop, tp) {
  // long  (stop < entry): rr = (tp - entry) / (entry - stop)
  // short (stop > entry): rr = (entry - tp) / (stop - entry)     [mirrors smc R3]
  // -> {risk, reward, rr}; rr === null when entry === stop (degenerate).
}
export function positionBox(points, map) {
  // -> { left,right, riskBand:{top,bottom}, rewardBand:{top,bottom},
  //      levels:[{id,price,y,label}], rr, long }  | null when entry.x off-bar.
}
export function positionHandles(points, map) {
  // -> [{id:"entry",x,y}, {id:"stop",x,y}, {id:"take_profit",x,y}] (off-bar omitted)
}
export function defaultPositionStyle(points) {
  // -> { color, lineWidth:1 }  (direction color is presentation-only; never the
  //    sole cue — the render always draws a "LONG"/"SHORT" text label + arrow)
}
```

`handlesFor("position", points, map)` delegates to `positionHandles`;
`applyDrag` position case returns fresh `{entry, stop, take_profit}` (never mutates),
keeping the old component on a null inverse (mirrors `applyDrag` `:148-186`).
`bodyHit("position",…)` is the `BOX_WIDTH`-wide band spanning the three levels.

## Server Design

**Migration `0015_drawing_kind_position`** (choices-only `AlterField`, reversible):

```python
class Migration(migrations.Migration):
    dependencies = [("trading", "0014_drawing_visible_locked")]
    operations = [migrations.AlterField(
        model_name="drawing", name="kind",
        field=models.CharField(choices=Drawing.Kind.choices, max_length=16),
    )]
```

No column/row change; `migrate trading 0014` reverses with zero loss
(mirrors the additive precedent `0014:18-28`). `DRAWING_KINDS`
(`quotes.py:402`) auto-includes `"position"` once the model choice lands.

**`parse_drawing` position branch** (one `elif` after `text`, `quotes.py:453`):

```python
elif kind == "position":
    if set(points) != {"entry", "stop", "take_profit"}:
        raise ValueError("position requires entry, stop, take_profit")
    _parse_point(points["entry"], require_time=True, where="position entry")
    if not _is_number(points.get("stop")):
        raise ValueError("invalid position stop")
    if not _is_number(points.get("take_profit")):
        raise ValueError("invalid position take_profit")
    if points["stop"] == points["entry"]["price"]:
        raise ValueError("position stop must differ from entry")
```

**400 matrix** (all raise before any write; view maps `ValueError`→400,
`views.py:453,523`):

| Body | Result |
|---|---|
| `{entry:{time:int,price:num}, stop:num, take_profit:num}` | 201/200 |
| missing `stop` / `take_profit` | 400 (`invalid position …`) |
| `entry` not dict / missing `time` / non-int `time` / non-num `price` | 400 |
| non-numeric or bool `stop`/`take_profit` | 400 |
| `entry.price == stop` (degenerate) | 400 |
| extra/missing keys | 400 |
| `kind` without migration applied | 400 (`unknown kind`) |

No new route (`urls.py:20-24` reused). `for_user` unchanged (`views.py:491,457`) —
cross-user id → 404, R14 preserved.

## Render + Interaction

- **Measure primitive** (`controllers/measure.js`): one `ISeriesPrimitive` attached
  while a measurement exists, mirroring `makeDrawingPrimitive` (`drawing-primitive.js:98-133`)
  and the SMC primitive (`smc.js:185-216`). `paneViews` draws a vertical span + shaded
  box + `formatMeasure` text; `autoscaleInfo` returns `null` (a measure MUST NOT move
  the scale); redraw only via `requestUpdate`.
- **Position `renderShape` branch** (`drawing-primitive.js`): `const box = Pos.positionBox(row.points, map)`;
  fill the risk band (entry→SL) and reward band (entry→TP) at low alpha, stroke the
  three level lines, write the `LONG`/`SHORT` label + arrow and the `R:R` text
  (reuses the rect draw pattern `:61-70`). `priceRangeFor` (`:13-27`) gains `stop`/`take_profit`
  so the box is not clipped.
- **3-click collection** in `drawings.js onChartClick` (`:171-200`): a `pendingPosition`
  object parallel to `pendingAnchor`; each click fills one level; the third finalizes
  via `createDrawing`. `clearForSwitch`/`store.subscribe` reset (`:205-210,230-237`)
  also clear `pendingPosition`.
- **Toolbar**: two groups + two icons in `tool-icons-core` (`TOOL_GROUPS:14`, `ICON_BODIES:33`);
  `draw-toolbar.js` renders them from the core with no new wiring.
- **Stale-anchor reset**: the existing `store.subscribe` tool-change guard
  (`drawings.js:205-210`) is extended to drop a half-collected `pendingPosition`,
  not only `pendingAnchor`.

## a11y + CSP

- Measure numbers live in `#measure-readout aria-live="polite"` (mirrors `#rsi`,
  `chart.html:47`); Esc cancels (documented key). Position `R:R` in a
  `aria-live="polite"` DOM node.
- **Not color-only** (design-system R6/R9, `spec.md:141-151`): the box always draws a
  `LONG`/`SHORT` **text label + directional arrow**; the tree row shows `position #id`
  as text; handles are canvas dots (R9), never DOM.
- Toolbar buttons keep the existing `aria-label`/`aria-pressed` + roving tabindex
  (`draw-toolbar.js:44-58`); measure is selectable/cancellable via Esc, position via
  the tree + Delete/Escape.
- **CSP**: icons are JS-built SVG strings with no `on*` (`tool-icons-core.js:28-46`);
  readouts are `textContent`; canvas draws use `CanvasRenderingTarget2D`. No inline
  script/handler; `requirements.txt` and `script-src` unchanged.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit (node) | `measure-core.measure` deltas/%-null/bars, `formatMeasure`; `position-core.levelsFrom`/`riskReward` (long+short+degenerate)/`positionBox`/`positionHandles`; position `handlesFor`/`applyDrag`/`bodyHit`; `drawing-core.fromApi` accepts `position`; `tool-icons-core` new groups/icons (no `on*`) | `node --test "tests/js/**/*.test.js"` (mirror `drawing-core.test.js` mapper + null-guard style) |
| Integration (pytest) | position POST/PUT/GET round-trip; 400 matrix incl. degenerate `entry==stop`; A≠B→404; full branch coverage of `parse_drawing` | `test_market_api.py` (`diff-cover` 100%) |
| Migration | `0015` forward adds the choice, reverse returns to `0014`, `makemigrations --check` green | new `test_migration_0015.py` (copy `test_migration_0014.py`) |
| Contract | `CONTROLLER_ALLOWLIST == 12`; `+2` modules served JS; `STORE_KEYS == 11`; `window.marketChart` 8 keys | `test_market_ux.py:146`, `chart-store.test.js`, E2E seam |
| E2E | measure drag → DOM readout + no POST/PUT; tool click → captured position POST; drag → ONE PUT; seed copies a setup's levels; `setData` spy green; readiness-gated `_wait_ready`, DOM+network only, never pixels (#149) | `test_market_e2e.py` (mirrors `:976-1015`) |
| Guard | no module >300 (esp. `smc.js`=300, `object-tree.js`=299) | `test_module_size_guard.py` |

## Migration / Rollout

Feature-branch chain off tracker `feat/f6-measure-position` (proposal §Delivery;
>400 lines, `chained-pr`): **S1** pure cores + node tests (revert = delete 2 files,
no app impact); **S2** `Drawing.Kind.POSITION` + migration `0015` + `parse_drawing`
branch + allowlists + API/migration tests (revert = `migrate trading 0014`, drop
one `elif`); **S3** `controllers/measure.js` + toolbar + position render/interaction
+ `drawings.js` flow + E2E (revert = revert S3 slice; nothing persisted that S2
didn't already allow). Each slice independently revertible; no CSP, dependency,
`src/`, or destructive-schema change.

## Risks & Mitigations

Carried from `explore.md §7`: **R1** 300-ceiling — `smc.js`/`object-tree.js`
byte-untouched, largest touched module ~262; **R2** 8-key seam — assert via
DOM/bus/captured POST; **R3** `STORE_KEYS` 11 — no store key added; **R4** #68 —
primitives + `requestUpdate`, `setData` spy; **R5** single-source — seed copies
`setups` verbatim via `smc:loaded`; **R6** `parse_drawing` branch — full 400 matrix;
**R7** migration `0015` — round-trip test; **R8** patch 100% — degenerate `entry==stop`
in the matrix; **R9** R14 `for_user` — unchanged path; **R10** E2E flake (#149) —
readiness gate, DOM+network assertions; **R11** two `#chart` listeners —
`drawing-interaction.js:94` bails in tool mode, measure guards on tool. **New**:
**R12** seed picks the most-recent setup for the active key (v1 simplification;
per-setup selection is a future additive feature, not a rework).

## Open Questions

None blocking. Explore §8 forks resolved: Q1→D6, Q2→D1/D4, Q3→D5, Q4→proposal
`chart-measure` + `chart-drawings` extension, Q5→two toolbar groups.
