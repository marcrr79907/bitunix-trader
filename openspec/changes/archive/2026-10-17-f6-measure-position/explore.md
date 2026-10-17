# Exploration: f6-measure-position

Issue #119, Fase F6. Branch `develop` @ `80070c0`. Read-only — no code changed,
no branch created. This explore builds directly on the archived F5 chain
(`openspec/changes/archive/2026-10-16-f5-chart-toolbar/`).

## 1. Problem framing

Two distinct TradingView instruments, not one:

- **Measure tool** — a *gesture*: press-drag across the chart, release, and see
  the delta between the two points: price Δ (abs + %), elapsed time, bar count,
  candle count. TradingView's measure is **ephemeral** — it lives only while the
  pointer is down (or until the next measure) and is never saved. It answers
  "how far did this move?"; deleting it is done by simply starting a new one.
- **Position tool** — an *object*: a Long/Short box with three levels
  (entry / stop-loss / take-profit). It shows the risk leg, the reward leg, and
  the **R:R ratio** live as the user drags a level. TradingView's long-position
  tool is a **saved** object — it belongs in the object tree, is draggable, and
  persists across reloads, exactly like a rectangle.

**Why align with SMC setups.** The server already computes — deterministically,
single-source — a `Setup` for the active `(symbol, interval)` with exactly the
fields a position needs: `direction, entry, stop, take_profit, rr, score, index`
(`src/smc/signals.py:26-33`, spec `openspec/specs/smc-signals/spec.md:14`). The
payload reaches the chart as `setups` inside `window.marketChart.smc`
(`web/market/quotes.py:697-708`, `controllers/smc.js:230,240`). So the position
tool can be **seeded from the server's levels verbatim** — no JS recompute of
entry/SL/TP/R:R. The client only re-derives R:R while the user *edits* the box,
which is inherent to a draggable drawing, not a duplication of the SMC engine.

**What is NOT to be duplicated:**
- No SMC math in JS (`docs/architecture/chart-modules.md` "Single source": "JS
  never computes indicators or SMC — those are computed server-side"). The
  position tool must **read** `setups`, never re-run `find_setups`.
- No new order path. A position is a *drawing*, never an order (read-only repo,
  `chart-drawings` R8 boundary, `openspec/specs/chart-drawings/spec.md:403`).
- No new dependency, no bundler, no CSP relaxation.

## 2. Codebase map (exact files/functions, cited)

### 2a. The F5 architecture this feature extends
- **ADR / layers**: `docs/architecture/chart-modules.md` — Pure cores (no DOM) /
  State / Host / Controllers (DI `create({store,bus,host,config})`, never import
  `main`) / Orchestration. "Single write path (#68)", "Single source", "Size
  ceiling: no module exceeds ~300 lines".
- **Toolbar (where a new tool is added)**: `controllers/draw-toolbar.js:14,68-92`
  renders every button from `TOOL_GROUPS` (`tool-icons-core.js:14-19`); the
  active tool is written with `store.set({ tool })` (`draw-toolbar.js:41`).
  A new tool = one new group/kind in `tool-icons-core.js` + one `TOOL_LABELS`
  entry (`draw-toolbar.js:17-23`). No new bus event (design D3).
- **Drawings lifecycle**: `controllers/drawings.js` — `attachAllDrawings()`
  `32-47` (one `makeDrawingPrimitive` per row, writes `window.marketChart.drawings`
  `45`, emits `drawings:changed` `46`); `loadDrawings` `53-72`;
  `createDrawing(kind,points,style)` `134-155` (POST → `fromApi`);
  `deleteDrawing` `157-167`; `onChartClick(param)` `171-200` (per-kind click
  flow: hline=1 click, text=dialog, trendline/fib/rect=2 clicks);
  `persistDrawing` `126-132`; `bus.on("drawing:changed")` `93-117` (partial PUT).
- **Primitive render**: `drawing-primitive.js` — `renderShape(ctx,size,row,map,selected)`
  `32-80` (per-kind canvas draws; hidden early-return `37-40`),
  `drawHandles` `83-93`, `makeDrawingPrimitive(row,selection)` `98-133`
  (`paneViews` + `autoscaleInfo` + `requestUpdate`). Geometry delegated to
  `drawing-core.js`.
- **Pure geometry**: `drawing-core.js` — `DRAWING_KINDS` `13`, `defaultStyle`
  `25-30`, `fromApi` `37-47`, `anchor` `83-89`, `rectPath` `114-124`,
  `hitTest` `133-146`. `drawing-interaction-core.js` — `handlesFor` `30-56`,
  `rectCorners` `60-74`, `grabHandle` `81-100`, `bodyHit` `103-132`,
  `applyDrag` `148-186`, `HANDLE_RADIUS`/`BODY_RADIUS` `14-15`.
- **Pointer/gesture path**: `controllers/drawing-interaction.js` — `onPointerDown`
  `93-108` (bails when a tool is active `94`; `grabHandle(pointerRows(rows),…)`
  `97`), `onPointerMove` `110-124`, `endDrag` `126-141`, `onKeyDown` Escape/Delete
  `149-167`, `attach()` `206-217` (binds `#chart` **once**; `#chart` survives a
  rebuild). `map()` `70-79` builds `{x,y,time,price}` converters from the host.
- **Host converters + seam**: `chart-host.js` — `getChart` `171`,
  `getCandleSeries` `172`, `subscribeClick` `231-233`,
  `subscribeVisibleRange` `239-241`, `setSeriesVisible` `190-196`; the frozen
  8-key seam is written `152-154`; `main.js:55-64` initializes it.
- **Store / bus**: `chart-store.js` `STORE_KEYS` **11** `13-27` (last is
  `indicatorVisible`; `tool` at `23`); `chart-bus.js` `EVENTS` `9-24`
  (`drawing:selected/changed/delete` are **string literals**, not in `EVENTS`).
- **Orchestration**: `main.js` — store init `34-48`, controllers `67-99`,
  `buildChart` `107-123` (`drawings.attachAllDrawings()` `111`,
  `drawingInteraction.attach()` `115`, `host.subscribeClick(drawings.onChartClick)`
  `116`), `switchTo` `143-174`, boot `211-246`.

### 2b. Persistence precedent (the model to reuse)
- **Model**: `web/trading/models.py` — `Drawing` `233-265` (`Kind` choices
  `244-249`, `points` JSON `253`, `style` JSON `254`, `visible` `255`,
  `locked` `256`, index `(user,symbol)` `260-265`). This is *the* collection to
  reuse for a position.
- **Migration precedent**: `0014_drawing_visible_locked.py` (two additive
  `AddField`) — for a new `Kind` choice the change is a choices-only
  `AlterField` (`makemigrations` emits it because `choices` changed) → `0015`.
- **Views**: `web/market/views.py` — `MODULE_ALLOWLIST` `44-61`,
  `CONTROLLER_ALLOWLIST` `62-73` (**11**), `api_drawings` `397-429`,
  `_post_drawing` `432-476`, `api_drawing_detail` `481-497` (`for_user` scoped),
  `_put_drawing` `500-529` (partial `{points?,style?,visible?,locked?}`).
- **Validator**: `web/market/quotes.py` — `DRAWING_KINDS = frozenset(Drawing.Kind.values)`
  `402`, `parse_drawing(kind,points,style,visible,locked)` `422-461`
  (per-kind `points` schema + bool flags). **A new `Kind` must gain a `points`
  schema branch here or its POST 400s.**
- **Endpoints**: `web/market/urls.py` `20-24` (`market_api_drawings`,
  `market_api_drawings_detail`) — a reused `Kind` needs **no new route**.
  `chart.js` `CONFIG.urls.drawings` `33` already points at it.

### 2c. SMC levels (the seed source — read-only)
- **Engine**: `src/smc/signals.py` `find_setups` `36-129`; `Setup` fields
  `26-33`; R3 derivation `spec/smc-signals/spec.md:75-84`.
- **Payload**: `web/market/quotes.py:697-708` emits
  `{direction,time,entry,stop,take_profit,rr,score}` per setup;
  `get_smc_payload` `722-753` runs `find_setups` once.
- **UI**: `smc-overlay-core.js` `fromApi` `40-52`, `setupMarkers` `217-230`;
  `controllers/smc.js` writes `window.marketChart.smc = smcBody` `230,239`
  and emits `smc:loaded` `241`. The position tool reads `state.smc` /
  `window.marketChart.smc.setups` — it never fetches or recomputes.

### 2d. Existing measure-like math (ladder rule: reuse first)
A repo-wide grep for `measure|barCount|bar_count|percent|distance` found **no
JS helper** for price/time/% distance or bar counting. The only analog is a
Python liquidation-distance (`src/monitor.py:142-143`) on the trading side —
unrelated and server-only. `chart-core.js:16-38` `intervalSeconds`/`bucketTime`
are the *only* reusable primitives (bar spacing in seconds); everything else for
a measure must be new. **Verdict: no duplication risk; `measure-core.js` is
genuinely new, and it MUST reuse `intervalSeconds` from `chart-core.js` for the
bar count rather than re-deriving interval math.**

### 2e. Tests to mirror
- **Pure-core node tests**: `tests/js/drawing-core.test.js` (identity-ish
  `mapper`, `deepStrictEqual` on geometry, null-guard cases), `drawing-interaction-core.test.js`,
  `drawing-primitive.test.js`, `draw-toolbar.test.js`, `object-tree.test.js`.
- **E2E**: `tests/web/test_market_e2e.py` — boot restores drawings `961-973`;
  tool click → POST body `976-1010`; toolbar groups/`aria-pressed`/roving
  `1024-1062`; object-tree row delete/eye/lock `1068-1215`; interaction ONE-PUT
  `1309+`. Assert via `window.marketChart.drawings` + captured POST/PUT — never
  pixels (readiness-gated `_wait_ready`).
- **API**: `tests/web/test_market_api.py` (drawings CRUD/isolation),
  `tests/web/test_market_ux.py:127-170` (allowlist route coverage;
  `len(CONTROLLER_ALLOWLIST) == 11` `146`; import-graph resolver `153-175`).
- **Guard**: `tests/web/test_module_size_guard.py` `CEILING=300`, `ALLOWLIST` EMPTY.

### 2f. Module line counts (ceiling 300 — the tight ones)
`controllers/smc.js=300` (AT ceiling) · `controllers/object-tree.js=299` (AT edge)
· `chart-host.js=267` · `main.js=249` · `controllers/drawings.js=240` ·
`drawing-interaction-core.js=230` · `controllers/drawing-interaction.js=227` ·
`controllers/toolbar.js=187` · `drawing-core.js=162` · `drawing-primitive.js=135`.

## 3. Design options + recommendation

### 3a. Measure: ephemeral vs persisted — **RECOMMEND EPHEMERAL**
| Option | Shape | Verdict |
|---|---|---|
| **A. Ephemeral overlay** | own primitive attached only while a measure exists; cleared on Esc / tool change / symbol switch; **no server, no store key, no seam key** | **RECOMMEND** — TradingView parity; zero persistence surface; zero migration; nothing to keep in sync |
| B. Persisted `Drawing` kind | a `measure` drawing row saved like any other | Rejected — a measure is a transient readout, not an annotation; saving it pollutes the object tree and costs a migration + CRUD branch for no user value |

Ephemeral measure **does not touch `STORE_KEYS`** (the active tool is already
`store.tool`), **does not add a `window.marketChart` key** (seam stays 8), and
**does not hit `setData`/`update`** (#68 — draws on its own primitive, exactly
like SMC `controllers/smc.js:185-216`).

### 3b. Position: new `Drawing.Kind` vs separate model — **RECOMMEND new Kind**
| Option | Shape | Verdict |
|---|---|---|
| **A. `Drawing.Kind.POSITION`** | persisted row; reuses `api_drawings` CRUD, `drawing-primitive` paneView, `drawing-interaction` grabHandle/applyDrag, object-tree row, `visible/locked`; adds one `points` schema branch in `parse_drawing` | **RECOMMEND** — the deletion test passes hard: deleting this path reappears as a whole CRUD+primitive+tree stack; reusing the collection is the lazy, correct seam |
| B. Separate `Position` model | new table, new endpoints, new primitive path, new tree group | Rejected — duplicates #68 write path, CRUD, isolation, migration, and the tree; far more code for identical behaviour |

Cost of A: new `Kind` choice + `0015` choices-only `AlterField` (no data loss),
one `parse_drawing` branch (`quotes.py:422-461`), `DRAWING_KINDS` +
`defaultStyle` in `drawing-core.js`, one `renderShape` branch in
`drawing-primitive.js`, position cases in `handlesFor`/`applyDrag`/`bodyHit` in
`drawing-interaction-core.js`, and the 3-click collection in `drawings.js`.

### 3c. Pulling SMC levels without duplicating server math (single-source)
The position tool exposes a **"seed from setup"** action that copies the server's
`entry/stop/take_profit` **verbatim** from the already-fetched payload
(`window.marketChart.smc.setups`, `controllers/smc.js:230`). Boundary:
- **Seed** = server values, read-only, never recomputed (single source preserved).
- **Live edit** = while the user drags a level, the client recomputes the *box
  geometry and displayed R:R* (`position-core.js`). This is not SMC duplication:
  the SMC engine's job (score/confluence/structural target) is untouched; the
  client only does what every draggable drawing does — map pixels to prices and
  re-derive a ratio from three user-set prices.
- If no setup exists for the key, the tool still works from a user-drawn box.

## 4. Pure-core split (CRITICAL for the ceiling)

Two new pure cores, mirroring `drawing-core`/`drawing-interaction-core`. Every
touched controller stays ≤300 by **extracting geometry into the cores** and
**placing the measure overlay in its own controller**.

### 4a. New pure cores (node-tested, no DOM)
| Module | Responsibility | ~Lines |
|---|---|---|
| `market/measure-core.js` | `measure(a, b, intervalSeconds)` → `{priceDelta, pricePct, timeDelta, bars, candles}`; `formatMeasure(m)` → label strings. Pure; imports `intervalSeconds` from `chart-core.js`. Never throws; off-value → degrade. | ~110 |
| `market/position-core.js` | `levelsFrom(points)` → `{entry,stop,takeProfit,long}`; `riskReward(entry,stop,tp)` → `{risk,reward,rr}`; `positionBox(points,map)` → normalized pixel box (`|entry..stop|` risk zone + `|entry..tp|` reward zone); `positionHandles(points,map)`; `defaultPositionStyle`. Pure. | ~130 |

### 4b. New controller
| Module | Responsibility | ~Lines |
|---|---|---|
| `controllers/measure.js` | Ephemeral measure overlay: its own `#chart` pointer listeners (guarded by `state.tool==="measure"`; `drawing-interaction.onPointerDown` already bails when a tool is active — `drawing-interaction.js:94`), a primitive that draws the two-point span + readout, Esc/tool-change/symbol-switch cancel. Owns a `#measure-readout` DOM node (accessible). No persistence, no store key, no seam key. | ~180 |

### 4c. Line budget on every touched module
| File | Now | Change | Result |
|---|---|---|---|
| `controllers/drawings.js` | 240 | +position 3-click branch in `onChartClick` (~15) + seed helper (~10) + `defaultStyle` seed | ~265 |
| `drawing-interaction-core.js` | 230 | +`position` in `handlesFor`/`applyDrag`/`bodyHit` (~20) | ~250 |
| `drawing-primitive.js` | 135 | +`position` branch delegating to `position-core.positionBox` (~12) | ~147 |
| `drawing-core.js` | 162 | +`"position"` in `DRAWING_KINDS` + `defaultStyle` branch (~4) | ~166 |
| `tool-icons-core.js` | 69 | +2 kinds in `TOOL_GROUPS` + 2 `ICON_BODIES` | ~85 |
| `main.js` | 249 | +`createMeasure(...)` + wire (~6) | ~255 |
| `chart-host.js` | 267 | **untouched** (measure uses #chart pointer events, not the host) | 267 |
| `controllers/smc.js` | 300 | **untouched** (read-only seed) | 300 |
| `controllers/object-tree.js` | 299 | **untouched** (position rows appear in the existing `Drawings` group; label `kind #id`, `object-tree.js:130` already generic) | 299 |
| `chart-store.js` | 61 | **untouched** (tool value only) | 61 |

`smc.js` (300) and `object-tree.js` (299) MUST NOT grow — the design keeps both
untouched, which is the whole reason the position is a `Drawing` kind and the
measure overlay is its own controller. If the object-tree needs a Long/Short
label later, that label must come from a **pure helper in `position-core.js`**,
not new lines in the tree.

## 5. Render + interaction plan

### 5a. Render (primitive layer, #68-clean)
- **Measure**: `controllers/measure.js` attaches **one** `ISeriesPrimitive` to
  `host.getCandleSeries()` while a measurement exists (mirroring
  `drawing-primitive.makeDrawingPrimitive` `98-133` and the SMC primitive
  `smc.js:185-216`). Its `paneViews` draws a vertical span between the two
  points, a shaded box, and text (`measure-core.formatMeasure`). `autoscaleInfo`
  returns `null` (measurement must not move the scale). Redraw via
  `requestUpdate` only. Detached/cleared on release-end + Esc.
- **Position**: a `Drawing` kind → the existing `drawing-primitive.renderShape`
  gains a `position` branch that calls `position-core.positionBox(row.points,map)`
  and draws the risk zone (entry→SL), the reward zone (entry→TP), three level
  lines with labels, and the R:R text — reusing the rect draw pattern
  (`drawing-primitive.js:61-70`). `autoscaleInfo` (`priceRangeFor` `13-27`) must
  include `stop`/`take_profit` prices.

### 5b. Interaction
- **Measure drag**: measure controller's own `#chart` `pointerdown/move/up`
  (guarded by the active tool). It builds its own `map()` identical to
  `drawing-interaction.map()` `70-79`. Esc cancels (`measure` owns its keydown
  or reuses the interaction controller's Escape — see Open Q2).
- **Position draw**: a 3-click flow through the existing `host.subscribeClick`
  → `drawings.onChartClick` path (like trendline/fib/rect `drawings.js:193-199`,
  but collecting entry time+price, then stop price, then TP price). On finalize
  it POSTs a `kind="position"` row via `createDrawing` — no new endpoint.
- **Position drag**: reuse `drawing-interaction-core` — `handlesFor` returns the
  three level handles + the entry anchor; `applyDrag` moves a level's `price`
  (y only) or the whole box (x+y). `drawing-interaction.js` needs **no change**
  (it is kind-agnostic: `grabHandle`+`applyDrag` are data-driven) — only the
  core gains the `position` cases.

### 5c. Toolbar integration
Add a group to `tool-icons-core.TOOL_GROUPS` (e.g. `{label:"Measure", kinds:["measure"]}`
and add `"position"` to `Shapes` or a new `{label:"Positions", kinds:["position"]}`),
plus two `TOOL_LABELS` entries and two `ICON_BODIES`. `draw-toolbar.js` renders
them automatically. Activating writes `store.tool` (the existing command).
`drawings.js`'s `store.subscribe` already drops a stale two-point anchor on tool
change (`drawings.js:205-210`) — extend it to also cancel a pending position.

## 6. a11y + CSP

### a11y
- **Measure**: the on-canvas span is not DOM, so the numbers live in a DOM
  readout (`#measure-readout`, `aria-live="polite"`, mirroring `#rsi`
  `chart.html:47`). Esc cancels (documented key). The measure tool button carries
  `aria-label` + `aria-pressed` via the existing toolbar pattern.
- **Position**: R:R readout in a DOM node (`aria-live="polite"`); the three level
  handles are **canvas-drawn** (like drawing handles, `drawing-primitive.js:83-93`
  — `chart-drawings` R9 "handles are not DOM nodes"). Long/Short MUST NOT be
  **color-only**: the box carries a text label ("LONG"/"SHORT") + a directional
  arrow (design-system R6/R9, `design-system/spec.md:141-144,160-163`). Position
  rows in the object tree carry the kind + a long/short label as text.
- **Keyboard**: Esc cancels measure/position draft; the position is selectable/
  deletable through the tree and the existing interaction keys (Delete/Escape)
  since it is a normal drawing.

### CSP
- No inline handler, no inline script. Icons are SVG **strings** from
  `tool-icons-core` (`tool-icons-core.js:28-46`, no `on*`), injected via
  `innerHTML` on a native `<button>` (`draw-toolbar.js:80`). Readouts are
  `textContent`. Canvas draws use `CanvasRenderingTarget2D` — no DOM
  (`chart-drawings` R6). `requirements.txt` unchanged; no new dep.

## 7. Risk list

| # | Risk | Sev | Evidence / mitigation |
|---|---|---|---|
| R1 | **300-line ceiling** — `smc.js`=300, `object-tree.js`=299 | **High** | `test_module_size_guard.py`; design keeps both untouched; new geometry lives in the cores, measure in its own controller |
| R2 | **Seam freeze** — no 9th `window.marketChart` key | High | `market-chart` R18/R20 (`spec.md:753-809`); measure asserts via DOM/bus, position via `window.marketChart.drawings` (existing) + captured POST |
| R3 | **`STORE_KEYS` frozen 11** (R14) | High | `chart-store.js:13-27`, `market-chart` R14 (`spec.md:622-660`); measure/position add **no** store key (tool value only) |
| R4 | **#68 single-write-path** — measure/position must never `setData`/`update` | High | E2E `setData` spy (`docs/architecture/chart-modules.md` "Preserved invariants"); both render on primitives + `requestUpdate` |
| R5 | **Single-source** — position must not recompute SMC | Med | `docs/architecture/chart-modules.md`; seed copies server `setups` verbatim; only drag re-derives R:R |
| R6 | **New `Kind` needs a `parse_drawing` schema branch** or POST 400s | High | `quotes.py:402,422-461`; add a `position` branch + full branch matrix |
| R7 | **`Kind` choices change → `AlterField` migration `0015`** | Med | model is "source of truth" (`models.py:244-249`); `makemigrations --check` must stay green; add a `0015` round-trip test mirroring `test_migration_0012.py`. Choices-only, no data loss |
| R8 | **Patch coverage 100%** on new Python + `parse_drawing` | High | `diff-cover`; full branch matrix (valid/bad position points, missing levels, degenerate `entry==stop`) |
| R9 | **R14 `for_user`** — position CRUD routes through `Drawing.for_user` | Med | `api_drawing_detail:491`, `_post_drawing:457` already scoped; reuse the path untouched |
| R10 | **E2E class-C flake (#149)** — SQLite threaded `live_server` | Med | `test_market_e2e.py:13`; assert DOM + captured network, never pixels; readiness-gate `_wait_ready` |
| R11 | **Measure gesture vs interaction controller** — two `#chart` pointer listeners | Med | `drawing-interaction.js:94` bails in tool mode; measure guards on `state.tool==="measure"`; no shared capture conflict |
| R12 | **Ephemeral-vs-persisted migration impact** | Low | Ephemeral measure = no migration; position = choices-only `AlterField` (R7). A future "save a measure" would be an additive new feature, not a rework |
| R13 | **3-click position UX ambiguity** | Low | Settle the click flow in design (Open Q1); fall back to entry/SL/TP or entry+SL with fixed-R TP |

## 8. Open questions (real forks for proposal/design)

1. **Position point schema.** `{entry:{time,price}, stop:number, take_profit:number}`
   (prices are levels, entry carries time) vs three `{time,price}` anchors vs
   `{p1,p2,p3}`. Affects `parse_drawing`, `handlesFor`, `applyDrag`, and the
   3-click flow. (Recommend the level-based schema — SL/TP are horizontal levels,
   only entry needs a time.)
2. **Measure cancel ownership.** Does `controllers/measure.js` own its own
   Escape keydown, or does it subscribe to the existing `drawing-interaction`
   Escape (`drawing-interaction.js:149-157`)? (Recommend measure owns it — no
   cross-controller coupling; interaction already bails in tool mode.)
3. **SMC seed UX.** An explicit "position from setup" button/menu vs
   auto-seeding the first position drawn while a setup is on screen. (Recommend
   explicit — auto-seeding is surprising and hard to test.)
4. **Capability shape.** New `chart-measure` + `chart-position` capabilities vs
   extending `chart-drawings` (+ `chart-toolbar` for the new tool) + `market-chart`
   inventory. (Recommend: extend `chart-drawings`/`chart-toolbar`; add
   `measure-core`/`position-core` to the `market-chart` R14 inventory + allowlists.)
5. **measure vs position as one tool or two.** One group "Tools" with two kinds,
   or two groups. (Recommend two entries — they are distinct instruments.)

## Prioritized brief for the next phase (sdd-propose)

- **Intent**: TradingView-parity **ephemeral measure** (price %/Δ, time, bars,
  candles) + a **persisted Long/Short position** box (entry/SL/TP + live R:R),
  seedable from the single-source SMC `setups` and rendered on the primitive layer.
- **In scope**: new pure `measure-core.js` + `position-core.js`; new
  `controllers/measure.js`; `Drawing.Kind.POSITION` + choices-only migration
  `0015`; `parse_drawing` position schema; `drawing-core`/`-primitive`/
  `-interaction-core` position branches; `drawings.js` 3-click flow + SMC seed;
  `tool-icons-core` +2 tools; allowlists +2 modules, +1 controller; CSS tokens;
  specs `market-chart`(R14/R18/R20), `chart-drawings`(R1/R2/R5/R6/R10),
  `chart-toolbar`, `design-system`(R6/R9).
- **Out of scope**: order execution (HARD, read-only), SMC internals,
  undo/versioning, shared drawings, any new dependency/build, CSP relaxation,
  `src/` changes.
- **Delivery**: likely a chained PR (≥3 slices: (1) cores + node tests;
  (2) `Drawing.Kind.POSITION` + migration + `parse_drawing` + API round-trip;
  (3) measure controller + toolbar + position render/interaction + E2E) — over
  the 400-line budget; `sdd-tasks` should forecast `Chained PRs recommended: Yes`,
  `400-line budget risk: High`.

### Ready for Proposal
**Yes.** Both instruments are framed against the real F5 primitive/gesture/
persistence paths, the two at-ceiling modules are kept untouched by construction,
the pure-core split is sized, and the only blocking forks are enumerated in §8
(chiefly the position point schema and the SMC-seed UX).
