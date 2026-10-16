# Exploration: drawing-interaction (issue #117, Fase F4 — Ola 4)

## Current State

### Drawing creation, render, list, delete (today)

`controllers/drawings.js` (300 lines — AT the R14 ceiling) is the whole drawing
surface. It is a DI factory `createDrawings({store, bus, host, config})`, a LEAF
module that imports only `drawing-core.js`:

- **Create**: a toolbar button sets `state.tool` (`syncToolButtons`, L216-223).
  With a tool active, `onChartClick(param)` (L227-256) is called from
  `host.subscribeClick` (wired in `main.js::buildChart`, L96). `hline` needs one
  click (price only); `trendline`/`fib`/`rect` collect a first `pendingAnchor`
  then finalize on the second click; `text` opens the native `<dialog
  id="text-dialog">` and persists on `returnValue === "ok"`. Each create POSTs
  `{symbol, kind, points, style}` to `config.urls.drawings` and appends the saved
  row to `currentDrawings`.
- **Render**: one v5 `ISeriesPrimitive` per drawing (`makeDrawingPrimitive`,
  L92-116) attached to `candleSeries` (own canvas layer; #68 preserved — never
  `setData`/`update`). `renderShape` (L48-89) draws per kind via the pure
  `Draw.*Path` builders over an `{x(time), y(price)}` map closed over
  `chart.timeScale().timeToCoordinate` / `series.priceToCoordinate`. Off-bar /
  off-scale legs are skipped (null guard). `autoscaleInfo` widens the scale for
  full-width rays/rects (`priceRangeFor`).
- **List**: `renderDrawingList` (L118-132) builds one `<button class="drawing-del"
  data-id>` per row in `#drawing-list`; click → `deleteDrawing(id)`.
- **Delete**: `deleteDrawing` (L204-214) DELETEs `drawings/<id>`, filters
  `currentDrawings`, re-attaches, and re-publishes the seam.
- **Load / seam**: `loadDrawings(symbol)` (monotonic `drawGen` guard) →
  `attachAllDrawings()` (L137-153) rebuilds the whole primitive list and writes
  `window.marketChart.drawings` + `bus.emit("drawings:changed")`. `clearForSwitch`
  resets tool/anchors and bumps `drawGen` on a symbol change.

Crucially: **there is NO selection, NO pointer drag, NO handles, NO keyboard, and
NO properties panel today.** Interactions are click-to-create and
list-click-to-delete only.

### `drawing-core.js` (158 lines) — what exists vs what F4 adds

Pure, DOM-free, no imports. Exports: `DRAWING_KINDS`, `FIB_RATIOS`,
`defaultStyle`, `fromApi`, `toApi`, `pointFromParam`, `hlinePath`,
`trendlinePath`, `fibLevels`, `fibPath`, `rectPath`, `textPath`, `hitTest`.

`hitTest(items, x, y, radius)` (L129-142) is a generic nearest-`{x,y}`-within-
radius scan returning an index or `-1`. Its own comment says "(panel delete is
primary; this is for future canvas selection)" — **it is exactly the F4
selection primitive, already tested** (`tests/js/drawing-core.test.js` L112-121).

What F4 must ADD to the pure layer (none of it exists): per-kind **handle pixel
positions**, **which handle a pointer grabs** (a hit-test over handles), the
**drag math** (apply a pixel/timedelta to `points`, per kind), and a **clamp /
off-axis guard**. The existing `*Path` builders already give the pixel geometry
the handles sit on, so handles can be derived from them.

### `chart-host.js` (297 lines) — the seam F4 depends on

- `subscribeClick(fn)` and `subscribeCrosshairMove(fn)` (L262-269): thin wrappers
  over `chart.subscribeClick`/`subscribeCrosshairMove`, both **null-guarded** on
  `chart` and requiring **re-subscription after every `chart:built`** (build()
  recreates the chart). `subscribeVisibleRange` likewise.
- Coordinates are NOT exposed as host methods — the primitive and the click
  handler use the v5 series/chart objects directly:
  `chart.timeScale().timeToCoordinate(t)` → x|null,
  `chart.timeScale().coordinateToTime(x)` → time|null,
  `series.priceToCoordinate(p)` → y|null, `series.coordinateToPrice(y)` →
  price|null. The click `param.point.{x,y}` is already **pane-relative**.
- `getCandleSeries()` returns the live series (null before the first build).

### `main.js::switchTo` + click wiring

`buildChart()` calls `drawings.attachAllDrawings()`, `smc.attachSmcLayer()`, then
`host.subscribeClick(drawings.onChartClick)` and
`host.subscribeVisibleRange(history.onVisibleRange)` — **all re-subscribed after
each rebuild** (L90-103). `switchTo` (L123-151) clears drawings only on a
**symbol** change (`drawings.clearForSwitch()`), then on the load chain calls
`drawings.refreshDrawings()`. Interval-only switches keep shapes attached.

### Backend (only Python that changes)

`views.py`: `api_drawings` (GET list by `symbol`, POST create) and
`api_drawing_detail` (**DELETE only**, L455-467). `urls.py` maps both.
`quotes.parse_drawing(kind, points, style) -> (points, style)` (L415-445) is the
pure raise-`ValueError` validator mirrored by `_post_drawing`. **There is no PUT
by id** — F4's only new server surface.

## Affected Areas

- `web/market/templates/market/drawing-interaction-core.js` — NEW pure interaction
  math (handles, grab resolution, drag-apply, clamp). `node --test`.
- `web/market/templates/market/controllers/drawings.js` — AT 300; must SHRINK or
  the interaction controller takes the new code (see Size below).
- `web/market/templates/market/drawing-core.js` — may gain small pure helpers
  (`spanFor`/per-kind anchor lists) OR stay untouched if the new core owns them.
- `web/market/templates/market/main.js` — wire `subscribeClick` (selection),
  pointer listeners, keyboard listeners, dialog; re-subscribe on rebuild.
- `web/market/templates/market/chart-host.js` — likely a NEW
  crosshair/pointer bridge or expose `getChart()`-based drag tracking; must stay
  ≤300 (297 now — almost no headroom).
- `web/market/templates/market/chart.html` — handles/selection have no DOM; the
  properties `<dialog>` and any focusable container do.
- `web/market/views.py` + `urls.py` — add `PUT` to `api_drawing_detail`.
- `web/market/quotes.py` — extend/reuse `parse_drawing` for the PUT body.
- `web/accounts/templates/registration/theme.css` — properties dialog + focus
  styling.
- `tests/js/drawing-interaction-core.test.js` — NEW pure tests.
- `tests/web/test_market_api.py` — PUT contract (200/400/404/CSRF/A≠B).
- `tests/web/test_market_e2e.py` — select → drag → save E2E (dev-only).
- `tests/web/test_market_ux.py` — `MODULE_ALLOWLIST` +1 (test asserts the exact
  allowlist contents; `test_module_allowlist_routes_serve_javascript` iterates it).

## Key design questions and recommended resolutions

### 1. Pointer mechanism (the load-bearing unknown)

v5 gives **no DOM element for a primitive**; `paneViews` render into the chart's
own canvas via `CanvasRenderingTarget2D`. But the **chart container `#chart` is a
real DOM node** in our template, and the chart's `param.point.{x,y}` from
`subscribeClick`/`subscribeCrosshairMove` is **pane-relative**, matching the same
coordinate space the primitives draw in. Three viable mechanisms:

| Mechanism | Pros | Cons |
|---|---|---|
| **A. DOM pointer listeners on `#chart`** (`pointerdown/move/up/cancel`) + convert via `host` (chart's `getBoundingClientRect` offset, then `timeScale().coordinateToTime` + `series.coordinateToPrice`) | Real `pointerdown/move/up`; pointer capture; works while the mouse is held (crosshair-move fires on hover, which is fine but not guaranteed during a drag); CSP-clean `addEventListener` | Must translate page→pane coords (subtract `#chart` rect); must guard the price-scale gutter vs plot area |
| **B. `subscribeCrosshairMove` during a held drag** | Zero coordinate math (`param.point` is pane-relative); the archive explore's original recommendation | `subscribeCrosshairMove` is a hover signal, not a pointer-capture signal; a drag outside the pane/away from a bar can drop frames; no `pointerup` event to end the drag — you must pair with a DOM `pointerup` anyway |
| **C. `ISeriesPrimitive.hitTest(x, y)`** (v5 hook returning `PrimitiveHoveredItem`) | Cursor feedback + hovered-item plumbing is native | Does not carry the drag gesture; still needs DOM pointer events to drag. Overkill for our needs |

**Recommendation: A (DOM `pointerdown/move/up` on `#chart`) as the gesture
driver, using the host's own converters.** It is the only mechanism that gives a
true `pointerdown → pointermove → pointerup` lifecycle (essential for drag), it
is CSP-clean (the legend already proves `addEventListener` on `#chart` works),
and it reuses `coordinateToTime`/`coordinateToPrice` (which the create path
already uses). `subscribeClick` stays the create path; `pointerdown` on `#chart`
is the NEW selection/drag path. Because `#chart` is `position:relative`
(`theme.css` L79) the pane origin is its bounding rect; the price-scale gutter is
a ~60px right strip to exclude from hit-tests (or rely on
`coordinateToPrice` returning null outside the plot, which it does).

Fallback if the gutter/offset math proves brittle in E2E: B+C hybrid (DOM
`pointerdown`/`pointerup` to bracket the gesture + `subscribeCrosshairMove` for
the live point). The pure core is identical either way — only the thin controller
adapter changes, so this choice is cheap to defer to design.

### 2. Interaction home: pure core + thin controller split (SIZE — decisive)

`controllers/drawings.js` is **exactly 300 lines** and `test_module_size_guard`
fails ANY market JS module over 300 with an EMPTY allowlist. F4 adds selection,
handle geometry, drag state, keyboard, and a dialog — far more than 0 lines of
headroom. Two options:

- **Option 1 — extract + thin extension**: pull the ~90 lines of pure-ish
  creation/geometry helpers out of `drawings.js` into the new
  `drawing-interaction-core.js` (or reuse `drawing-core.js`), then add selection/
  drag/keyboard there. Keeps ONE drawings controller.
- **Option 2 — NEW controller** `controllers/drawing-interaction.js` (allowlist
  7→8) that owns selection/drag/keyboard/dialog, leaving `drawings.js` as the
  create/list/render CRUD controller, with the two coordinated through the store
  + bus.

**Recommendation: a pure `drawing-interaction-core.js` (MODULE allowlist +1,
node-tested) + Option 2's NEW thin controller `controllers/drawing-interaction.js`
(CONTROLLER allowlist 7→8), and SHRINK `drawings.js`** by moving
`renderShape`/`makeDrawingPrimitive`/`priceRangeFor` into a small
`drawing-primitive.js` module (pure-ish, still ≤300) that both controllers import.
Rationale: `drawings.js` is already at the ceiling and genuinely owns two
concerns (primitive rendering + CRUD); splitting render out gives BOTH controllers
headroom and matches the F0 layered pattern ("pure core at the center, adapters
at the edges"). The new controller is a NEW allowlist entry, so
`test_market_ux.py`'s `len(CONTROLLER_ALLOWLIST) == 7` assertion MUST be bumped to
8, and the new MODULE added to `views.MODULE_ALLOWLIST` + a `<link
rel="modulepreload">` in `chart.html`. Selection/drag state lives in the new
controller's closure (see Q6).

### 3. Handles per kind + drag math

Schemas are frozen by `parse_drawing` (quotes.py L415-445) and the archive design
(design.md L51-60). Handles and drag behaviour per kind:

| kind | `points` shape | Draggable handles | Body drag (translate all) |
|---|---|---|---|
| `hline` | `{price: float}` | 1 handle on the line (y from `priceToCoordinate(price)`); drag → new `price` via `coordinateToPrice(y)` | same as handle (only price moves); no x |
| `trendline` | `{p1:{time,price}, p2:{time,price}}` | 2 anchors (`trendlinePath.a`/`.b`); drag endpoint i → set `points.pi = {time: coordinateToTime(x), price: coordinateToPrice(y)}` | shift BOTH `p1`,`p2` by (Δtime, Δprice) |
| `fib` | same 2 anchors as trendline | 2 anchors (`fibPath.x1/x2`, level y's from `p1`/`p2`) | same shift of `p1`,`p2` |
| `rect` | `{p1:{time,price}, p2:{time,price}}` | 4 corner handles from the normalized box (`rectPath.left/top/width/height`) → each corner maps back to a `p1`/`p2` corner | shift BOTH corners by (Δtime, Δprice) |
| `text` | `{time:int, price:float, text:str}` | 1 anchor (`textPath.x/y`); drag → new `{time,price}`, `text` unchanged | same as handle |

**Drag semantics (pure)**:
- `handlesFor(drawing, map)` → `[{id, x, y}]` where `id` encodes which field(s)
  the handle edits (e.g. `"p1"`, `"p2"`, `"corner:tl"`, `"price"`, `"anchor"`),
  reusing the existing `*Path` builders for pixel geometry.
- `grabHandle(drawing, map, px, py, radius)` → the grabbed handle id or a
  `"body"` marker if the pointer is within `handleRadius` of a handle or within a
  body threshold of the shape, else `null`. This is `hitTest` generalized to a
  typed result (nearest handle should win over body).
- `applyDrag(drawing, grabId, fromXY, toXY, map, inverse)` → a NEW `points`
  object. `fromXY`/`toXY` are pane px; `map` converts time↔x and price↔y; `inverse`
  converts x→time, y→price. Pure, returns fresh `points` (no mutation), so tests
  are trivial and the caller serializes via `drawing-core.toApi`.
- `clampPoint(p, map)`-style guard: if `coordinateToTime(x)` is null (off-bar,
  e.g. dragged past the last bar into empty space), clamp to the nearest valid
  bar OR keep the last valid time rather than writing `null` (which the server
  `_parse_point` would 400 and which would break the render). **This is a real
  edge — dragging an endpoint into the future/empty area is common.**

Body-vs-handle precedence: handles first (bigger grab radius), then body. Kind
`hline` has no body distinct from its single handle.

### 4. Time↔x coupling + null guard

Confirmed exposed (used today by the create path and the primitives):
`chart.timeScale().coordinateToTime(x)` and `series.coordinateToPrice(y)`. Both
return `null` off-bar / off-scale. `drawing-core.anchor()` already null-guards its
legs; the drag math MUST do the same and MUST NOT persist a `null` `time`/`price`.
**Open sub-question**: after a symbol switch or pan, a stored `time` may have no
bar (`timeToCoordinate`→null) — the drawn shape already degrades; the drag path
must too (skip a handle whose anchor is currently null, never crash).

### 5. Delete / Escape + keyboard scope

The chart canvas is not focusable. Keyboard handlers should attach on a container
that **can** hold focus. Options: (a) add `tabindex="0"` to `#chart` and listen on
it (focus ring via `:focus-visible` per design-system R, keeps keystrokes scoped
to the chart, and makes the chart a landmark the user can Tab into); or (b)
`document`-level `keydown` with a guard (`if (state.tool) return; if
(selection === null) return;`). **Recommendation: (a) `#chart` gets
`tabindex="0"` + an `aria-label`**, listeners on `#chart` `keydown`
(`Delete`/`Backspace` → delete selected, `Escape` → deselect OR cancel a pending
anchor). Backspace must `preventDefault` to stop the browser navigating back.
This keeps scope tight and satisfies the a11y invariant (foco/teclado) without a
document-wide listener that could swallow typing in the properties dialog.

### 6. Properties dialog (double-click → color/lineWidth)

Reuse the **F2 indicator-settings `<dialog>` pattern** (native `<dialog>`,
`form method="dialog"`, `close` handler applies on `returnValue==="ok"`,
focus-trap + Escape for free). A NEW `<dialog id="drawing-settings-dialog">` with
a `<input type="color">` + a line-width `<input type="number" min=1 max=4>`,
mirroring `#indicator-settings-dialog` (chart.html L102-115). Double-click is a
`dblclick` listener on `#chart`; the selected drawing's `style` seeds the inputs;
confirm → merge into `style`, re-render, and PUT. `rect` also has `fill` and
`text` has `fontSize` — v1 MAY expose only color+lineWidth (issue scope) and
leave `fill`/`levels`/`fontSize` untouched. The F2/F5 promise ("engancha con
F2/F5") is satisfied by reusing the same dialog *pattern*, not the same DOM node.

### 7. Persistence — the only Python change

A NEW `PUT /market/api/drawings/<id>`. Extend `api_drawing_detail` to accept
`["GET","PUT","DELETE"]`? **No GET-by-id exists and none is needed** — add
`["PUT","DELETE"]` (or keep DELETE and add PUT). Contract:

- `@login_required @require_http_methods(["PUT","DELETE"])`.
- Resolve `Drawing.for_user(request.user).filter(pk=id).first()`; miss → 404 (same
  no-leak rule as DELETE).
- Body: `{points, style}` (partial — either or both). Validate via
  `parse_drawing(drawing.kind, points or drawing.points, style or drawing.style)`
  — `kind` is IMMUTABLE (not in the body); a body that includes `kind` differing
  from the stored kind → 400 (or ignore, matching the `interval`
  accept-and-ignore precedent — recommend reject-or-ignore decided in spec).
- Write only validated fields; return the updated row `{id, kind, points, style}`
  (200). CSRF enforced by middleware (client sends `X-CSRFToken`).
- A≠B: B's PUT of A's id → 404, A unchanged.
- **Reuse `parse_drawing`** so the PUT path is patch-covered by the same pure
  validator (100% patch gate). Mirror `_put_layout`/`_put_preference` structure.

### 8. Does selection/tool state go in the store?

The store holds UI/config state with a frozen `STORE_KEYS` list (10 keys today).
Adding `selection` risks perturbing `chart-store.test.js`'s key-count assertions
and the #68 "store never holds data" boundary. **Recommendation: keep selection
and drag state in the new controller's closure** (like `currentDrawings`,
`pendingAnchor` do in `drawings.js` today), publishing a `bus.emit(
"drawing:selected", {id})` notification for any observer. Only add a store key if
a second consumer genuinely needs it (YAGNI). If a key is added, `STORE_KEYS` and
its test MUST be updated in lockstep.

## Approaches (interaction layer)

1. **Pure core + new thin controller (RECOMMENDED)** — `drawing-interaction-core.js`
   (pure, node-tested) + `controllers/drawing-interaction.js` (thin DI factory) +
   `drawing-primitive.js` (render extracted) so `drawings.js` drops below 300.
   - Pros: keeps every module ≤300; matches the layered F0 pattern; pure drag
     math is fully unit-testable; smallest per-file diffs.
   - Cons: +1 module allowlist entry, +1 controller allowlist entry (two test
     constants bump), one more `modulepreload`.
   - Effort: Medium.

2. **Grow `drawings.js` + extract only the pure math** — move enough out of
   `drawings.js` into a pure core to fit the interaction code.
   - Pros: no new controller/allowlist entry.
   - Cons: fights the ceiling; `drawings.js` stays a god-module; the extraction
     boundary is arbitrary.
   - Effort: Medium.

3. **Everything inline, bump the guard ceiling** — NOT viable: the guard's
   allowlist is empty by design and the R14 rule is a hard invariant.
   - Effort: N/A (rejected).

## Recommendation

Adopt Approach 1. Ship a pure `drawing-interaction-core.js` (handles, grab,
drag-apply, clamp — `node --test`) plus a NEW thin `controllers/drawing-interaction.js`
(DOM pointer/keyboard/dblclick + dialog + PUT), and **extract the primitive
renderer out of `controllers/drawings.js` into `drawing-primitive.js`** so both
controllers clear the 300 ceiling. Selection/drag state stays in the controller
closure; a `bus.emit` notification suffices. Add `PUT` to
`api_drawing_detail`, reusing `parse_drawing`. Pointer mechanism: DOM
`pointerdown/move/up` on `#chart` + the host's existing coordinate converters
(fallback to a crosshair hybrid if E2E proves the offset brittle). Keyboard on a
focusable `#chart` (`tabindex="0"`). Properties via a NEW native `<dialog>`
mirroring F2. No new runtime deps; CSP unchanged; #68 preserved (drag re-renders
via the primitive's `requestUpdate`, never `setData`/`update`).

## Risks

- **#68 (drag re-render)**: dragging MUST re-render the primitive (its
  `requestUpdate`), never touch the series data path. The E2E `setData`-spy tests
  (`test_ws_stream_never_calls_setdata`) MUST stay green.
- **`drawings.js` ceiling**: it is AT 300 today; ANY addition fails
  `test_module_size_guard`. The extraction is not optional — it is a hard
  precondition. Also `chart-host.js` is 297 (3 lines of headroom) if a host bridge
  is added.
- **Pointer offset math**: page→pane translation (`#chart` rect + price-scale
  gutter) is the likeliest source of off-by-N drags; must be exercised by E2E and
  ideally minimized by using pane-relative coordinates where possible.
- **E2E testability of drag**: Playwright `page.mouse.move/down/up` over the
  canvas works, but canvas pixels are not DOM-assertable — assert via the
  `window.marketChart.drawings` seam (post-PUT `points`) + network
  (`page.on("request")` PUT), matching the established pattern.
- **E2E flake (DEBT-8 / #149, class-C)**: the E2E WS harness flakes under
  live-server contention; the new drag E2E MUST be readiness-gated
  (`window.marketChart.ready`) and dev-only, and MUST NOT be relied on in CI.
- **a11y**: focus ring on `#chart`, keyboard-operable select/drag-less paths
  (Delete/Escape), the dialog's native focus trap. Drag itself is pointer-only —
  provide a keyboard/no-drag path to delete (list + Delete key) so the feature is
  not pointer-exclusive.
- **Frozen 8-key seam**: `window.marketChart` MUST keep exactly 8 keys only. Any
  selection id exposed for tests MUST live INSIDE the existing `drawings` array
  (e.g. a `selected` flag) or on a NEW non-seam object, never a 9th key.
- **No-deps / CSP**: DOM pointer/keyboard listeners via `addEventListener` in
  same-origin controllers only; the new `<dialog>` is native. No inline handler.
- **Patch 100%**: the PUT view is the only new Python; it MUST be exercised by
  pytest (success/400/404/CSRF/A≠B) or `diff-cover --fail-under=100` fails.
- **Backspace navigation**: `keydown` on Delete/Backspace must `preventDefault`
  when a drawing is selected.
- **`interval`-only vs symbol**: interaction must survive an interval-only switch
  (shapes stay attached — no refetch, no clear) and a symbol switch (selection
  MUST clear with the drawings; a stale selected id MUST NOT linger).

## Proposed PR shape + size

The F4 surface (pure core + render extraction + new controller + PUT + E2E) is
well over the 400-line review budget. Recommend a **3-slice Feature Branch Chain**
mirroring the project's precedent:

| Slice | Scope | ~Lines | Autonomous? |
|---|---|---|---|
| **1 — pure core + render extraction** | `drawing-interaction-core.js` (handles/grab/drag/clamp) + `drawing-primitive.js` (renderer extracted from `drawings.js`) + allowlist/preload wiring + `drawings.js` shrunk ≤300 + `tests/js/drawing-interaction-core.test.js` | ~250 | Yes — node tests green; chart still renders/creates unchanged. Revert → no core/primitive split. |
| **2 — controller + selection/drag/keyboard/dialog** | `controllers/drawing-interaction.js` (selection via `hitTest`, DOM pointer drag, Delete/Escape, dblclick dialog, `#chart` focusable) + `main.js` wiring + `chart.html` dialog + CSS + controller-allowlist bump | ~300 | Depends on Slice 1. Revert → no interaction; Slice 1 still pure. |
| **3 — PUT + E2E** | `api_drawing_detail` PUT + `parse_drawing` reuse + `test_market_api.py` PUT cases + `test_market_e2e.py` select→drag→save (dev-only) | ~200 | Depends on Slice 2. Revert → no persistence; in-session drag still works (unsaved). |

Total ≈ 750 lines → **chained PRs recommended; 400-line budget risk: High.**

Decision needed before apply: Yes
Chained PRs recommended: Yes
400-line budget risk: High

## Open Questions (for spec / design)

1. **Pointer mechanism**: commit to DOM `pointerdown/move/up` on `#chart`
   (converter-based) vs a crosshair-hybrid vs primitive `hitTest`? Recommend the
   former; confirm in design after a spike if the offset math is uncertain.
2. **Drag persistence cadence**: PUT on `pointerup` (one write per drag — RECOMMEND)
   vs debounced during drag vs live-per-move. One PUT on `pointerup` is the
   smallest, matches the "one write per gesture" spirit.
3. **Selection highlight rendering**: a highlight stroke in the SAME drawing
   primitive vs a SEPARATE always-present selection primitive/overlay. Recommend
   extending the existing primitive render (draw handles + a thicker stroke when
   `selected`) to avoid a second attach path.
4. **Kind field on PUT**: reject a body `kind`/`style` unknown-key, or
   accept-and-ignore (the `interval` precedent)? Recommend reject unknown `kind`
   (immutable) but validate `style` keys as `parse_drawing` already does.
5. **Properties scope**: color+lineWidth only (issue verbatim) vs also `fill`
   (rect) / `fontSize` (text) / `levels` (fib)? Recommend color+lineWidth v1.
6. **Store vs closure for selection**: closure + `bus.emit` (RECOMMEND) vs a new
   `STORE_KEYS` entry.
7. **Handles as DOM vs canvas**: canvas (drawn in the primitive) — RECOMMEND;
   DOM handles would need absolute-positioned divs and re-layout on every
   pan/zoom.
8. **Backspace scope**: only when focused on `#chart` (RECOMMEND) vs global.

## Ready for Proposal

YES — the architecture is a direct extension of the F0 layered seams
(`drawing-core` pure + controllers + host converters) and the F2 `<dialog>` /
`for_user` / CSRF patterns. The main unknowns are (a) the pointer-offset
mechanics (bounded, with a documented fallback) and (b) the exact `drawings.js`
extraction boundary — both belong to design. The spec MUST lock: the PUT contract
(kind immutable, partial points/style, 400/404/CSRF/A≠B), the pointer mechanism,
the per-kind handle/drag table, and the keyboard/a11y scope.
