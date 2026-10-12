# Exploration: chart-drawings (issue #72, Fase A3)

## Current State

### The chart today (baseline)

- `web/market/templates/market/chart.html` loads **Lightweight Charts v5.2.0**
  from the pinned CDN in `{% block scripts %}` (L56):
  `https://unpkg.com/lightweight-charts@5.2.0/dist/lightweight-charts.standalone.production.js`
  → global `window.LightweightCharts`. **No new dependency is needed** — the
  plugin API (`attachPrimitive`) ships in this build. A `{% block head %}`
  already carries the CSRF meta `<meta name="csrf-token">` (added in A2, L5).
- `web/market/templates/market/chart.js` (519 lines) is the adapter:
  - **Async boot (A2, L506–518)**: `boot()` → `loadLayout(symbol,interval)` →
    `buildChart()` → `connect()` → `fetchHistory()`; sets
    `window.marketChart.ready = true`. A failed layout fetch falls back to DOM
    defaults (never blank).
  - **`switchTo(symbol, interval)` (L476–489)**: monotonic `gen` guard, loads
    THAT chart's layout first, then `buildChart()` + `fetchHistory()`.
  - **Single-write-path (#68)**: history/config → `setData`; live WS → `update()`
    only. `buildChart()` (L197–245) tears down (`chart.remove()`) and rebuilds.
  - **`state`** = `{symbol, interval, indicators, params}` (L138–143).
  - **Panes/overlays**: static `REGISTRY` (L40–80); `chart.addSeries(Ctor,
    {color}, paneIndex)`; index 0 = price scale, `PANE_ORDER` panes 1..n.
  - **CSRF/PUT seam (A2, L409–458)**: `csrfToken()` reads the meta; `saveLayout()`
    debounce-PUTs `{symbol,interval,indicators}` with `X-CSRFToken`. `LAYOUT_URL
    = "/market/api/layout"` (L23).
  - **Test seam**: `window.marketChart = {chart, candleSeries, panes, ready}`
    (L155) — the DOM-only hook E2E asserts against (no image diffs).

### A2 persistence pattern to mirror (chart-config)

- **Model** `ChartLayout(UserOwnedModel)` in `web/trading/models.py` (L210–230):
  `symbol`(32), `interval`(8), `indicators` JSONField, `updated_at` auto_now,
  `UniqueConstraint(["user","symbol","interval"])`. Migration `0005_chartlayout.py`
  (latest; drawings → `0006`).
- **Endpoint** `api_layout` in `web/market/views.py` (L87–163): `@login_required`
  + `@require_http_methods([...])`; every access via
  `ChartLayout.for_user(request.user)`; PUT validates BEFORE write, CSRF enforced
  by middleware; GET-miss → `200` with a built-in default + `exists:false` (never
  404). Route in `web/market/urls.py` (L12).
- **Validation** in `web/market/quotes.py`: `DEFAULT_LAYOUT`, `parse_indicators`,
  `parse_layout_indicators` (L276–328) — a pure raise-`ValueError` validator the
  view maps to 400.
- **Guard** `tests/web/test_owned_model_guard.py`: `OWNED_MODELS` frozenset
  (L22–31) MUST list every owned model; `REQUEST_PATH` scans
  `web/{config,accounts,trading,market}` (L19). **`Drawing` MUST be added to
  `OWNED_MODELS`** or the scanner is blind to it.
- **Intervals**: `INTERVALS` tuple in `web/market/quotes.py` (L32–47) — the
  canonical interval vocabulary to validate against.

## Feasibility of v5 primitives

Confirmed against the v5.2 docs (Series primitives, `ISeriesApi`,
`ITimeScaleApi`):

- **Attach**: `series.attachPrimitive(primitive)` / `detachPrimitive` on
  `candleSeries` (or any series). `ISeriesPrimitive` = optional getters
  `paneViews` (main pane), plus `updateAllViews`, `autoscaleInfo`, and lifecycle
  `attached({chart, series, requestUpdate})` / `detached()`. Nothing new to load.
- **Views/renderers**: a `paneViews` entry returns a renderer with
  `draw(target: CanvasRenderingTarget2D)`. Draw uses `target.useMediaCoordinateSpace`
  / `useBitmapCoordinateSpace` (canvas 2D API) — **no DOM**, so CSP is untouched.
- **Coordinate mapping**:
  - price↔pixel: `candleSeries.priceToCoordinate(price)` /
    `candleSeries.coordinateToPrice(y)`.
  - time↔pixel: `chart.timeScale().timeToCoordinate(time)` /
    `coordinateToTime(x)` (returns `null` when no bar sits on `x`).
- **Per drawing kind** (all pure canvas draws inside one renderer each):
  - **horizontal ray**: `priceToCoordinate(p)` → full-width line, `autoscaleInfo`
    so pan/zoom keeps it.
  - **trendline**: two `{time,price}` → `timeToCoordinate`+`priceToCoordinate`
    per endpoint; skip a leg that maps to `null`.
  - **Fibonacci retracement**: two anchors → 7 horizontal levels at
    `p1+(p2-p1)*ratio`, each a line + `fillText` label.
  - **rectangle** (OB/FVG): two corners → `ctx.strokeRect`/`fillRect` over the
    mapped rect.
  - **text**: `ctx.fillText` at the mapped point (trivially feasible).
- **Redraw on pan/zoom**: the primitive calls `requestUpdate()` from its
  `attached` param; the library re-invokes `updateAllViews` and the renderers.
  Drawing storage is in `chart.js` state (not series data), so the #68
  single-write-path is untouched (primitives are a separate canvas layer).

## Interaction model

- **Pointer → data**: the cleanest capture is the chart's own events —
  `chart.subscribeClick(param)` / `chart.subscribeCrosshairMove(param)`, where
  `param.point = {x,y}` is already pane-relative and `param.time` is the horz
  item (UNIX seconds for our int-time series). Price = `candleSeries
  .coordinateToPrice(param.point.y)`. This avoids manual
  `getBoundingClientRect` offset math.
- **Drag**: mousedown on `#chart` → `subscribeCrosshairMove` (live preview) →
  mouseup finalizes. Native DOM listeners on the chart container are the
  fallback if crosshair events prove insufficient during a drag; both are
  CSP-clean (`addEventListener`, no inline handler).
- **Toolbar**: a new design-system `<fieldset class="drawings">` of
  `<button type="button" class="draw-tool" data-kind="trendline">` (mirrors the
  `.pair` button pattern, L491–495). Active-tool state in `state.tool`
  (`null` = pan). A "select/delete" mode: click near a drawing's handle
  (hit-test in CSS px) → delete. All listeners attached in `chart.js`.
- **CSP-safe**: every handler is `addEventListener` in the same-origin
  `chart.js`; no inline `on*`, no `<script>` in the markup. No CSP change.

## Persistence contract

- **Model** `Drawing(UserOwnedModel)` in `web/trading/models.py` (the R14 seam;
  `market → trading.models` is the existing direction). Fields per issue:
  `symbol`(32), `interval`(8), `kind`(CharField), `points` JSONField,
  `style` JSONField; `updated_at` auto_now. Migration `0006_drawing.py`
  (additive, depends `0005_chartlayout`).
- **KEY DIVERGENCE from A2**: a chart holds **many** drawings, so there is
  **no unique constraint** on `(user,symbol,interval)` — use a plain index on
  `(symbol, interval)` and key CRUD by `id`. A2's one-row-per-key upsert does
  not transfer; drawings are a collection (POST/PATCH/DELETE by id).
- **`points`/`style` JSON per kind** (schema frozen in spec, validated on write):
  - `hline`: `points=[{time,price}]` (anchor time optional), `style={color,width}`.
  - `trendline`: `points=[{time,price},{time,price}]`.
  - `fib`: `points=[{time,price},{time,price}]`, `style={levels:[...]}`.
  - `rect`: `points=[{time,price},{time,price}]`, `style={color,fill}`.
  - `text`: `points=[{time,price}]`, `style={color}`, plus a `text` field
    (or fold into `style`).
- **Endpoint** `/market/api/drawings` in `web/market/views.py`, mirroring
  `api_layout`:
  - **GET** `?symbol=&interval=` → `{"drawings":[{id,kind,points,style}]}`
    (empty list when none; never 404), `@login_required`.
  - **POST** body `{symbol,interval,kind,points,style}` → validate `kind` ∈ a
    registry, `points`/`style` shapes per kind, `interval ∈ INTERVALS`,
    `symbol` non-empty → **400 before write**; create via
    `Drawing.for_user(request.user)`; return the created row (with `id`).
  - **DELETE** by `?id=` (or JSON `{id}`) → `Drawing.for_user(user).filter(id=…)
    .delete()`; 404/200 idempotent on miss. A≠B: B's id resolves to nothing for A.
  - CSRF enforced by middleware; client sends `X-CSRFToken` (meta already present).
- **Validation lives in `quotes.py`** (pure, raise-`ValueError`), matching
  `parse_layout_indicators` — a new `parse_drawing(kind, points, style)`, so
  `views.py` stays thin and the logic is patch-covered.

## Open Questions / Decisions for the spec

1. **Per-drawing storage (recommended) vs per-chart blob.** Issue names a
   `Drawing` row per shape with `kind`/`points`/`style` → one row per drawing,
   CRUD by `id`, no unique constraint. (A blob would be one row per chart, but
   then DELETE granularity and concurrent edits are worse.)
2. **Per interval vs shared across intervals.** The model carries `interval`
   (issue text), so **per-interval is the literal read**, BUT a drawing's
   `points` are `{time,price}` and `time` is interval-bucketed — the same shape
   drawn on 1m will not line up on 1h. TradingView shares across intervals by
   anchoring to time+price. **Recommendation: store `interval` but treat `""`/
   `null` as "shared across all intervals for this symbol" only if the user
   wants it later; v1 fences to per-interval** (matches A2's `(user,symbol,
   interval)` mental model). This is the decision the spec MUST lock.
3. **Delete semantics.** By `id` (recommended) vs "clear all for chart". Issue
   says DELETE (singular) → by id, `for_user`-scoped.
4. **Time-axis on interval switch / null mapping.** A drawing whose anchor
   `time` has no bar (`timeToCoordinate` → `null`) MUST degrade gracefully
   (skip that leg / clamp) — spec a scenario.
5. **Text rendering**: `ctx.fillText` is feasible; decide whether text needs an
   input (prompt via a native `<dialog>`/input) or a fixed label. Low risk.
6. **Selection/hit-test scope in v1**: delete-by-click-handle vs a "delete all"
   button. Recommend delete-by-id from a small list in the panel (simplest,
   fully DOM-testable) over canvas hit-testing (untestable in DOM).
7. **E2E approach**: canvas is not DOM-observable → expose a
   `window.marketChart.drawings` seam (array of persisted shapes) and assert it
   after a simulated drag + reload; also assert the POST/DELETE requests via
   `page.on("request")`.

## Risks

- **v5 primitive quirks**: renderers get `CanvasRenderingTarget2D`, not a raw
  2D context (must use `useMediaCoordinateSpace`/`useBitmapCoordinateSpace`);
  primitives only redraw when `requestUpdate()` is called; `autoscaleInfo` is
  needed or full-width rays/rects clip on zoom-out. Mitigation: one primitive
  class per kind, exercised by E2E.
- **Coordinate↔price round-trip**: `timeToCoordinate` returns `null` off-bar and
  after interval switches; a stored `time` may not map. Mitigation: null-guard
  the draw and a spec scenario.
- **E2E testability**: canvas pixels can't be asserted in DOM. Mitigation: a JS
  seam + network assertions (the established A2 pattern). Playwright
  `page.mouse` needs the chart's bounding box → expose it or use `param.point`
  events.
- **Patch-coverage for JS**: `diff-cover --fail-under=100` covers Python only;
  `chart.js` is template-side and out of it. Mitigation: extract the pure
  geometry (normalize points, fib levels, hit-test) into a `drawing-core.js`
  UMD module covered by `node --test` (mirrors `chart-core.js`), and let E2E be
  the integration net.
- **Guard blind spot**: forgetting `Drawing` in `OWNED_MODELS` leaves it
  unscanned. Mitigation: explicit task + negative-control fixture.
- **Scope creep into SMC (Fase C)**: no auto OB/FVG detection — manual
  rectangle only. Fence in the proposal.

## Proposed scope boundary + rough size (3-PR chain, à la A2)

- **PR1 — model**: `Drawing(UserOwnedModel)` (no unique constraint) +
  migration `0006` + `OWNED_MODELS` + isolation/guard tests. ~90 lines.
- **PR2 — endpoint**: `/market/api/drawings` GET/POST/DELETE in `views.py` +
  route + `parse_drawing`/`DRAWING_KINDS` in `quotes.py` + endpoint tests.
  ~150 lines.
- **PR3 — primitive + UI**: `drawing-core.js` (pure, node `--test`), the v5
  primitive classes + attach/load/save in `chart.js`, the toolbar in
  `chart.html`, and the Playwright E2E + DOM seam. ~200 lines.

Total ≈ 400–440 lines → **400-line budget risk: Medium**, chained PRs
recommended (same slicing as A2). Each slice autonomous, own-tested,
trivially revertible.

## Affected Areas

- `web/trading/models.py` — add `Drawing(UserOwnedModel)`.
- `web/trading/migrations/0006_drawing.py` — additive.
- `web/market/views.py` — add `api_drawings` (GET/POST/DELETE).
- `web/market/urls.py` — add `market/api/drawings`.
- `web/market/quotes.py` — add `DRAWING_KINDS`, `parse_drawing`.
- `web/market/templates/market/chart.html` — drawings toolbar.
- `web/market/templates/market/chart.js` — primitive attach, pointer capture,
  load/save, JS seam.
- `web/market/templates/market/drawing-core.js` — NEW pure geometry (node-tested).
- `tests/web/test_owned_model_guard.py` — `OWNED_MODELS` + fixture.
- `tests/web/test_isolation.py` — `Drawing` A≠B.
- `tests/web/test_market_api.py` — drawings endpoint contract.
- `tests/web/test_market_e2e.py` — draw/save/restore E2E.
- `tests/js/drawing-core.test.js` — pure geometry.
- `openspec/specs/per-user-isolation/spec.md` — R14.2 model list (archive time).

## Recommendation

Mirror A2 end to end: `Drawing(UserOwnedModel)` in `web/trading/models.py`
(one row per shape, keyed by `id`, indexed on `(user,symbol,interval)`, **no
unique constraint**), a `market/api/drawings` GET/POST/DELETE endpoint scoped by
`for_user` with a pure `parse_drawing` validator, and a v5 series primitive per
kind (`attachPrimitive`) driven by chart `subscribeClick`/`subscribeCrosshairMove`
pointer events, persisting through the existing CSRF/debounce seam. Extract the
pure geometry to `drawing-core.js` for `node --test`. No new dependency, CSP
unchanged, read-only, #68 single-write-path preserved.

## Ready for Proposal

YES — architecture is a direct extension of the A2 persistence seam and the
already-loaded v5.2 plugin API. The spec MUST lock: **per-interval vs shared**
(Q2), **delete-by-id vs clear-all** (Q3), and the **`points`/`style` schema per
`kind`**.
