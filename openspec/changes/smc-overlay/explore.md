# Exploration: smc-overlay (issue #75, Fase C1)

## Executive Summary

C1 is the **read-only render layer** for the already-frozen SMC core (B1+B2).
It adds ONE server endpoint, `GET /market/api/smc?symbol=&interval=`, that runs
the pure chain (`find_swings` → `label_swings`/`find_structure` →
`find_order_blocks`/`find_fvg` → `dealing_range` → `find_setups`) over the
candles for that key and serializes `{swings, structure, order_blocks, fvgs,
range, setups}` — **server resolves bar-index → `time`**, so the JS only draws.
The browser side mirrors A3 exactly: a pure `smc-overlay-core.js` (UMD, `node
--test`) maps payload records → deterministic draw descriptors, and `chart.js`
renders them as v5 series primitives + `createSeriesMarkers`, with a
`<fieldset>` of per-type toggles. No new dependency, CSP unchanged, no order
surface, `src/` untouched.

The single hardest constraint is **alignment**: every SMC record carries a
**bar `index`** (positional in the OHLC series), but the chart draws in
**`time` (UNIX seconds)**. The endpoint MUST resolve index→time over the SAME
candle window the chart holds, or records silently fail to render
(`timeToCoordinate` returns `null` for a time not in the series, and
`createSeriesMarkers` drops markers at unknown times).

---

## 1. B1/B2 seam recap (what C1 serializes)

Read from `src/smc/*.py`. All records are stdlib `NamedTuple`, all finders are
pure, never-raise, list-in/sparse-list-out. **Every record's `index` is a
0-based bar index into the OHLC lists passed in** — the single thing C1 must
translate.

### Records (field order frozen)

```python
Swing(kind:str, index:int, price:float)                 # kind "high"|"low"      swings.py
LabeledSwing(kind:str, index:int, price:float, label:str) # label HH|HL|LH|LL    structure.py
StructureEvent(kind:str, index:int, price:float, direction:str, trend:str)
                                                        # kind "bos"|"choch";  structure.py
                                                        # direction bullish|bearish; trend up|down
OrderBlock(kind:str, index:int, top:float, bottom:float, anchor:int)
                                                        # kind bullish|bearish; zones.py
                                                        # anchor = BOS bar index
FVG(kind:str, index:int, top:float, bottom:float)       # kind bullish|bearish;  zones.py
EqualLevel(kind:str, index:int, price:float, twin:int)  # kind "eqh"|"eql"        zones.py
Sweep(kind:str, index:int, level:float, direction:str)  # kind "high"|"low"       zones.py
DealingRange(high:float, low:float, equilibrium:float, index:int)  # range.py
Setup(direction:str, entry:float, stop:float, take_profit:float, rr:float, score:int, index:int)
                                                        # direction long|short;  signals.py
                                                        # score 0..4; index = latest event bar
```

### Signatures

```python
find_swings(highs, lows, *, left=SWING_LEFT, right=SWING_RIGHT) -> list[Swing]
label_swings(swings) -> list[LabeledSwing]
trend_state(labeled) -> list[str | None]
find_structure(highs, lows, closes, *, left, right, use_close=USE_CLOSE) -> list[StructureEvent]
find_order_blocks(opens, highs, lows, closes, structure, *, lookback=OB_LOOKBACK) -> list[OrderBlock]
find_fvg(highs, lows, *, min_gap=FVG_MIN_GAP) -> list[FVG]
find_equal_highs_lows(swings, *, tolerance=EQ_TOLERANCE) -> list[EqualLevel]
find_liquidity_sweeps(highs, lows, closes, swings, *, lookback=SWEEP_LOOKBACK) -> list[Sweep]
dealing_range(highs, lows, *, lookback=RANGE_LOOKBACK) -> DealingRange | None
classify_price(price, range_) -> "premium" | "discount" | "equilibrium"
find_setups(opens, highs, lows, closes, swings, structure, *, range_=None,
            min_rr=MIN_RR, min_confluence=MIN_CONFLUENCE, sl_buffer=SL_BUFFER) -> list[Setup]
```

Config defaults (`src/smc/config.py`): `SWING_LEFT=2`, `SWING_RIGHT=2`,
`USE_CLOSE=True`, `OB_LOOKBACK=10`, `FVG_MIN_GAP=0.0`, `EQ_TOLERANCE=0.0`,
`SWEEP_LOOKBACK=20`, `RANGE_LOOKBACK=50`, `SL_BUFFER=0.0`, `MIN_RR=2.0`,
`MIN_CONFLUENCE=3`.

### Issue #75 render list vs the full B2 surface

Issue #75 asks to render: **swings, BOS/CHoCH, OB/FVG boxes, premium/discount
zones, and setup markers**. `EqualLevel` (EQH/EQL) and `Sweep` are **not** in
the issue's list. They are cheap to compute but out of the stated render scope
→ recommend the endpoint payload exposes ONLY the six rendered families
(YAGNI; EQH/EQL/sweeps can be added when a chart element needs them).

### Chain the endpoint runs (exact call order)

```
highs/lows/opens/closes := candle columns
swings     = find_swings(highs, lows)
labeled    = label_swings(swings)          # for HH/HL/LH/LL labels
structure  = find_structure(highs, lows, closes)
obs        = find_order_blocks(opens, highs, lows, closes, structure)
fvgs       = find_fvg(highs, lows)
range_     = dealing_range(highs, lows)
setups     = find_setups(opens, highs, lows, closes, swings, structure, range_=range_)
```

All six calls share ONE candle window, so all indices are consistent with each
other and with the chart.

---

## 2. Existing web patterns to mirror

### 2.1 Candle source — `api_kline` / `get_kline_payload`

`web/market/views.py:api_kline` validates `symbol`/`interval` (against
`quotes.INTERVALS`) + `limit` (1..200) then calls
`quotes.get_kline_payload(BitunixClient(), symbol, interval, limit, before,
indicators)`. `get_kline_payload` (`web/market/quotes.py:430`):

- DB-first (`_db_rows`, `Candle.objects.filter(symbol, interval, time<before)`,
  newest-first, reversed to ascending) for **persisted** intervals
  (`trading.candles.CANDLE_INTERVALS`); unpersisted intervals fall through to
  upstream.
- Gap-fiils from `client.kline(..., end_time=...)` ONLY when the DB is short;
  DB wins on duplicate `time`; merged ascending.
- Strips to exactly `{time,open,high,low,close}` for `candles` (drops
  `quote_vol`); `_ctx_rows` keeps `quote_vol` only for the volume pane.

**C1 needs OHLC including `opens`** — `find_order_blocks` and `find_setups`
require opens. `_db_rows` already returns `open`, and `client.kline` maps opens
(market-chart R1). So the SMC endpoint can reuse the same DB-first + gap-fill
seam as `get_kline_payload` and build columns
`opens/highs/lows/closes` + the `times` array. **Recommend extracting a small
shared "fetch window rows" helper** from `get_kline_payload` (`_db_rows` +
upstream + merge) so kline and SMC share the exact same window logic — a couple
of lines of refactor, not a rewrite. If refactoring the hot kline path is
undesirable, C1 MAY call `_db_rows` + `client.kline` directly in a new
`get_smc_payload` in `quotes.py` (duplicated ~15 lines) — the pragmatic,
lower-risk option.

### 2.2 Layout endpoint pattern — `api_layout`

`web/market/views.py:api_layout` (`GET`/`PUT`) is the thin-view template:
`@login_required` + `@require_http_methods([...])`; validate
`symbol`/`interval ∈ INTERVALS` **before** any work → `400
{"error":"..."}`; delegate to a pure validator in `quotes.py` that raises
`ValueError` (view maps to 400); never 404 on a miss. Routes are bare names in
`web/market/urls.py`. **SMC is GET-only and read-only → even simpler: no body,
no CSRF write path.**

### 2.3 Same-origin JS serving — `chart_js` / `drawing_core_js`

`chart_core_js` and `drawing_core_js` (`views.py:264,273`) serve the pure JS
**same-origin, unauthenticated, `content_type="text/javascript"`** (no
static/collectstatic infra exists in prod; inline JS would force
`script-src 'unsafe-inline'`). `chart.html` loads them via
`{% url 'market_chart_core_js' %}` / `{% url 'market_drawing_core_js' %}` with
the pinned CDN script first. **C1 adds `market/smc-overlay-core.js` + a
`smc_overlay_core_js` view + route, loaded the same way.**

### 2.4 `chart.js` adapter structure (the A3 render precedent)

- **`boot()`** (L855): `loadLayout → buildChart → connect → refreshDrawings →
  fetchHistory` — strictly sequential so no two fetches race the single-session
  E2E server; `window.marketChart.ready = true` only at the end.
- **`switchTo(symbol, interval)`** (L813): monotonic `gen` guard, resets
  `currentDrawings=[]` and bumps `drawGen` immediately (shapes never cross
  keys), reloads layout → build → drawings → history. **SMC must hook here
  identically (own generation guard, clear immediately, reload after build).**
- **`buildChart()`** (L206): `chart.remove()` then rebuild; calls
  `attachAllDrawings()` so primitives re-attach after a rebuild; subscribes
  click + visible-range.
- **Primitive** (`makeDrawingPrimitive`, L572): an object literal with
  `attached({chart, series, requestUpdate})` (captures ctx), `detached()`,
  `paneViews()` → `[{renderer: () => ({draw: target => target.useMediaCoordinateSpace(scope => renderShape(...))})}]`,
  and `autoscaleInfo()` (price range so full-width rays/rects aren't clipped).
  Coordinate map: `{x: t => chart.timeScale().timeToCoordinate(t), y: p =>
  series.priceToCoordinate(p)}`; **nulls degrade the leg, never throw**.
- **Single-write-path #68**: primitives live on their own canvas layer →
  never `setData`/`update` on series data; live WS `update()` is untouched.
- **Test seam** `window.marketChart = {chart, candleSeries, panes, ready,
  drawings}` (L158). E2E asserts against `.drawings`, `.panes`, `.ready` — no
  image diffs. **C1 adds `.smc` (the loaded payload) to this seam.**
- **CSRF/PUT seam**: `csrfToken()` reads `<meta name="csrf-token">`; used by
  layout/drawings writes. SMC is GET-only → no CSRF.

### 2.5 `createSeriesMarkers` — CONFIRMED available in v5.2.0

Verified against the Lightweight Charts v5 docs (library `/tradingview/
lightweight-charts`, version v5.2.0). The v5 markers API is the top-level
function:

```js
const markersPrimitive = LightweightCharts.createSeriesMarkers(series, [
  { time, position: 'aboveBar'|'belowBar'|'inBar', shape: 'circle'|'square'|'arrowUp'|'arrowDown', color, text, size, id, price? }
]);
markersPrimitive.setMarkers(nextMarkers);   // in-place replace, no detach/recreate
```

- `SeriesMarker` fields: `time` (required, in the series' time type — our UNIX
  seconds), `position`, `shape`, `color`, `text`, `size`, `id`, and optional
  `price` (for `atPriceTop|atPriceBottom|atPriceMiddle` positions).
- A marker whose `time` is not on the series is not drawn → **alignment is
  mandatory** (§1).
- Recommended marker usage: create ONCE per chart, then `setMarkers(...)` on
  toggle/switch (no primitive churn). On `buildChart` teardown the marker
  primitive goes with the chart → recreate after rebuild.

---

## 3. Endpoint design (propose)

`GET /market/api/smc?symbol=&interval=[&limit]`

- `@login_required @require_http_methods(["GET"])`; anonymous → 302 (pinned).
- Validate `interval ∈ quotes.INTERVALS` and non-empty `symbol` → `400
  {"error":"..."}`; optional `limit` int in `1..200`, default `200` (the SMC
  window wants ≥ `RANGE_LOOKBACK=50` bars plus structure history; 200 matches
  `MAX_UPSTREAM`). Invalid limit → 400 (mirror `api_kline`).
- Build the candle window with the SAME DB-first + gap-fill seam as
  `get_kline_payload` (reuse `_db_rows` + `client.kline`; DB wins on dup
  `time`), over the newest `limit` candles. `client.kline` failures map exactly
  as in `api_kline`: `BitunixError` → 400 `{"error":"upstream rejected"}`;
  `requests.RequestException` → 502 `{"error":"upstream"}` when nothing is
  served; DB rows available → 200 degraded.
- Empty/short window (fewer than 3 bars) → the pure finders already return
  `[]`/`None`; the endpoint MUST return `200` with empty arrays + `range:null`
  (never 500).
- **Resolve index→time server-side**: `time = times[index]` for every record;
  never leak the raw `index` as the draw key. This is the single-source
  mapping — the JS never translates indices.
- Return `JsonResponse(payload)`.

**Proposed payload (single source; JS draws it verbatim):**

```json
{
  "symbol": "BTCUSDT",
  "interval": "5m",
  "swings":       [{"kind":"high","time":1700000300,"price":50000.0,"label":"HH"}, ...],
  "structure":    [{"kind":"bos","time":1700000600,"price":49900.0,"direction":"bullish","trend":"up"}, ...],
  "order_blocks": [{"kind":"bullish","time":1700000000,"top":50100.0,"bottom":49800.0,"anchor_time":1700000600}, ...],
  "fvgs":         [{"kind":"bullish","time":1700000300,"top":50050.0,"bottom":49950.0}, ...],
  "range":        {"high":51000.0,"low":49000.0,"equilibrium":50000.0,"time":1700000900} ,
  "setups":       [{"direction":"long","time":1700000600,"entry":49900.0,"stop":49700.0,"take_profit":50500.0,"rr":3.0,"score":4}, ...]
}
```

- `swings` uses `label_swings` output so each carries `label` (HH/HL/LH/LL);
  the first swing of each kind has no label → `"label": null`.
- `range` is `null` when `dealing_range` returns `None`.
- `setups` is at most one record (B2 emits ≤1) but stays an array for symmetry.

**Where the code lives:** a new `get_smc_payload(client, symbol, interval,
limit)` + a thin `parse_smc_query`/`serialize_smc` helper in
`web/market/quotes.py` (pure-ish, patch-covered, mirrors `get_kline_payload`),
and a thin `api_smc` view + `market/api/smc` route. The SMC math itself is
untouched `src/smc/*` — `quotes.py` only orchestrates + maps index→time +
serializes.

---

## 4. Render design (propose)

### 4.1 Element → v5 primitive mapping

| Element | Payload field | v5 rendering |
|---|---|---|
| Swing pivots + labels | `swings` | Primitive: zig-zag polyline through consecutive pivots (distinct color per `kind`) + `fillText(label)` at each pivot. A label-less first swing still draws the point/line. |
| BOS / CHoCH | `structure` | Primitive: a short horizontal line at `price` from `time` to `time + N bars`, colored by `direction` (bull/bear); `fillText("BOS"|"CHoCH")`. |
| OB boxes | `order_blocks` | Primitive: `rectPath` from `time` (OB candle) to `anchor_time` (BOS bar), `top`→`bottom`; tinted fill by `kind`. |
| FVG boxes | `fvgs` | Primitive: `rectPath` spanning the middle candle (`time` ± 1 bar width) at `top`→`bottom`; tinted by `kind`. |
| Premium / discount | `range` | Primitive: two translucent full-width bands — premium `equilibrium..high`, discount `low..equilibrium` — plus a dashed line at `equilibrium`. Full-width = `autoscaleInfo` + drawing from x=0 to `size.width` (like the hline precedent). |
| Setup markers | `setups` | `createSeriesMarkers(candleSeries, [...])`; `position` belowBar for `long` / aboveBar for `short`, `shape` arrowUp/arrowDown, `text` e.g. `"L 4/4"`, `time`, `color` by direction. |

All primitive draws are pure canvas inside `useMediaCoordinateSpace` — **no
DOM, CSP untouched**. Reuse the A3 `renderShape` idioms (null-guard every
coordinate, `ctx.save/restore`, tinted fill via `globalAlpha`).

### 4.2 Pure core — `smc-overlay-core.js`

Mirror `drawing-core.js` exactly (UMD, no DOM/chart/network):

- `fromApi(payload)` → normalized `{swings, structure, orderBlocks, fvgs,
  range, setups}` (reject/drop unknown shapes; never throw).
- Per-family descriptor builders that map a payload record → a draw
  descriptor given a `{x(time), y(price)}` map, null-guarding off-series times:
  `swingPath`, `structurePath`, `boxPath` (OB/FVG share a rect builder),
  `rangeBands`, `setupMarkers` (→ `createSeriesMarkers` marker objects).
- `visibleFamilies(toggles)` → the set of enabled families (pure toggle logic).
- Node test asserts payload→descriptor mapping is deterministic and that a
  known payload yields exact descriptors (this is the "payload == drawn"
  contract at the data layer).

### 4.3 Toggles

Add a `<fieldset class="smc" aria-labelledby="smc-heading">` to `chart.html`
with one `<input type="checkbox" class="smc-toggle" value="swings|structure|
order_blocks|fvg|range|setups" checked>` per family (mirrors `.indicator-toggle`
markup + the design-system fieldset). `chart.js` reads them into
`state.smc = {swings:true, ...}`; a toggle change re-renders the SMC layer
**without refetching** (unlike indicator toggles, which rebuild) — SMC data is
independent of the chart config, so toggling only calls `requestUpdate()` /
`setMarkers([])`.

### 4.4 Persistence — DECISION for the spec

Issue #75 says only "Toggle mostrar/ocultar por tipo de elemento" — **no
persistence requirement**. A2 persists indicator layout because v1 asked for
it. **Recommend session-only** (default all-on, not persisted) for C1: no
migration, no new model field, smallest diff. Persisting later is a one-field
addition to `ChartLayout` (additive migration) — defer to a future change.
The spec MUST lock this explicitly.

---

## 5. Multi-TF

- Interval set = `quotes.INTERVALS` (14 values: `1m,5m,15m,30m,1h,2h,4h,6h,
  8h,12h,1d,3d,1w,1M`) — the canonical vocabulary `chart.html` renders.
- The analysis is **recomputed per `(symbol, interval)`**: `switchTo` calls the
  SMC endpoint with the new key, clears the old primitives immediately (bump a
  `smcGen` counter), and re-attaches after `buildChart` + history load.
- Ordering inside `switchTo` (mirrors A3's layout→build→drawings→history):
  `loadLayout → buildChart → loadSmc (fetch) → fetchHistory`. SMC fetch and
  history fetch share the same `(symbol, interval, limit)` so their windows
  coincide.
- On `loadOlder` pagination: SMC is computed over the newest window; older
  prepended bars have no SMC overlay. Acceptable for C1 (analysis anchors to
  recent bars). If the spec wants overlays on paginated bars, re-fetch SMC with
  `before` — **recommend NOT in C1** (fence).

---

## 6. Open questions / decisions the spec MUST lock

| # | Question | Recommendation (freeze) |
|---|---|---|
| Q1 | Payload shape | EXACTLY `{symbol, interval, swings, structure, order_blocks, fvgs, range, setups}` (§3); index→`time` resolved server-side; no `index` in the payload. |
| Q2 | "payload == drawn" contract | (a) node test: `fromApi(payload)` → exact descriptors; (b) Playwright: `window.marketChart.smc` deep-equals the fetched payload. Lock both. |
| Q3 | EPS/CHoCH/sweeps render? | NO — issue lists swings/structure/OB/FVG/range/setups only. EQH/EQL/sweeps fenced out. |
| Q4 | Toggle persistence | **Session-only**; default all-on; no migration. (Additive later.) |
| Q5 | Are setups markers? | YES — `createSeriesMarkers`, ≤1 marker, belowBar(long)/aboveBar(short). |
| Q6 | premium/discount drawing | **Two bands** (premium + discount) + equilibrium dashed line, full width; not a whole-chart tint (a tint needs a custom price-scale background, more complex). |
| Q7 | Warm-up / window | `limit` default **200**, clamp `1..200`; SMC window == chart history window (same `limit` the JS passes). |
| Q8 | Endpoint caching | **No cache** in C1 (add Cache-Control later if latency matters); DB-first already cheap. |
| Q9 | Empty / short / upstream-fail | Empty/short → 200 with empty arrays + `range:null`; upstream fail with DB rows → 200 degraded; nothing served → 502. Mirror `api_kline`. |
| Q10 | Swing labels | Include `label` from `label_swings`; `null` for the first swing of each kind. |
| Q11 | OB box right edge | Extend from the OB candle `time` to `anchor_time` (the BOS bar). Freeze this; alternatives (fixed-width) are arbitrary. |
| Q12 | Full-width vs time-bounded bands | `range` bands full-width (x=0..width); `autoscaleInfo` keeps them on zoom. |

---

## 7. Risks

- **Index→time alignment (highest).** SMC records are index-based; the chart is
  time-based. `timeToCoordinate` is `null` off-series and `createSeriesMarkers`
  drops unknown times. *Mitigation:* server resolves `time` from the SAME
  window; JS null-guards every coordinate; both fetches use the same
  `(symbol, interval, limit)`; node test + E2E assert equality.
- **JS outside the Python patch gate.** `diff-cover --fail-under=100` covers
  Python only; `chart.js` is template-side. *Mitigation:* all pure mapping in
  `smc-overlay-core.js` with a `node --test` suite (CI job `js-core` runs
  `node --test "tests/js/**/*.test.js"`); the adapter is the E2E net.
- **Payload size.** ≤200 candles → tens of records, sub-10 KB. Non-issue, but
  cap `limit` at 200 (mirrors upstream cap).
- **CSP.** Primitives + `createSeriesMarkers` are canvas; all handlers are
  `addEventListener` in same-origin JS; no inline script/handler. CSP
  (`middleware.CSP_POLICY`) unchanged.
- **Single-source discipline.** The JS must NOT recompute swings/trend/
  confluence. *Mitigation:* `smc-overlay-core.js` only reshapes; a spec
  scenario forbids recomputation; `src/smc` stays the sole math home.
- **No runtime dep / boundary.** `src/` untouched (no change to `PURE_MODULES`);
  `requirements.txt` unchanged; `web/market → src/smc` import is the permitted
  direction (core-domain-boundary R9/R11).
- **Rebuild teardown.** `buildChart` removes the chart → marker primitive dies
  with it; the primitive list and `createSeriesMarkers` handle MUST be
  recreated after every rebuild (A3 `attachAllDrawings` precedent).
- **Guard blind spot: none.** SMC has no owned model and no writes, so
  `test_owned_model_guard` / `for_user` are not involved. Explicitly note the
  endpoint performs NO unscoped `Candle` write (read-only).

---

## 8. Proposed PR shape + rough size

| File | Impl | Tests | Total |
|---|---|---|---|
| `web/market/quotes.py` (`get_smc_payload` + serialize) | ~120 | — | ~120 |
| `web/market/views.py` (`api_smc`) + `urls.py` route | ~40 | — | ~40 |
| `web/market/templates/market/smc-overlay-core.js` (NEW pure) | ~130 | `tests/js/smc-overlay-core.test.js` ~130 | ~260 |
| `web/market/templates/market/chart.js` (fetch, primitives, markers, toggles, seam) | ~200 | — | ~200 |
| `web/market/templates/market/chart.html` (SMC fieldset) + core view/route | ~30 | — | ~30 |
| `tests/web/test_market_api.py` (endpoint contract) | — | ~220 | ~220 |
| `tests/web/test_market_ux.py` (core JS served, CSP) | — | ~30 | ~30 |
| `tests/web/test_market_e2e.py` (seam + equality) | — | ~140 | ~140 |

**Total ≈ 1000–1040 changed lines → 400-line budget risk: HIGH.** Chained PRs
recommended.

### Recommended: CHAINED PRs, 3 slices (mirrors A2/A3)

1. **Slice 1 — endpoint (Python, patch-100).** `get_smc_payload` + serializer
   in `quotes.py`, `api_smc` view, route, and `test_market_api.py` endpoint
   contract (anon→302, 400s, empty→200, degradation, index→time mapping,
   payload shape). Autonomous, fully unit-testable, no JS. ~380 lines.
2. **Slice 2 — pure core + render.** `smc-overlay-core.js` + `node --test`,
   the SMC fieldset in `chart.html`, the core view/route, and `chart.js`
   rendering (primitives, `createSeriesMarkers`, toggles, `state.smc`, boot/
   switch hooks, `window.marketChart.smc` seam). ~520 lines.
3. **Slice 3 — E2E + UI audit.** Playwright: boot renders the seam, toggle
   hides a family, switch reloads, payload==drawn equality; `/impeccable` UI
   audit. ~170 lines.

2-slice alternative: fold 3 into 2 (~690 lines, still over budget, one heavier
review). **Recommend 3 slices** — same shape as A2/A3, each autonomous with its
own verification and trivial rollback.

**Out of scope (fence):** alerts (D), analytics (E), EQH/EQL/sweep rendering,
per-interval/shared SMC toggle persistence, SMC overlay on paginated older
bars, endpoint caching, any write path, any order surface, any new dependency,
any `src/` change.

---

## Affected Areas

- `web/market/quotes.py` — `get_smc_payload` + pure serializer (index→time).
- `web/market/views.py` — `api_smc` (GET-only) + `smc_overlay_core_js`.
- `web/market/urls.py` — `market/api/smc`, `market/smc-overlay-core.js`.
- `web/market/templates/market/chart.html` — SMC fieldset + core `<script>`.
- `web/market/templates/market/chart.js` — fetch/render/markers/toggles/seam.
- **NEW** `web/market/templates/market/smc-overlay-core.js` — pure mapping.
- **NEW** `tests/js/smc-overlay-core.test.js` — pure mapping.
- `tests/web/test_market_api.py` — SMC endpoint contract.
- `tests/web/test_market_ux.py` — core served + CSP unchanged.
- `tests/web/test_market_e2e.py` — render/toggle/switch/equality.
- **ARCHIVE-TIME**: `openspec/specs/market-chart/spec.md` (new SMC requirement);
  possibly a new `openspec/specs/smc-overlay/` domain.

No `src/` change, no migration, no model, no order surface, no new dependency.

## Ready for Proposal

**YES** — architecture is a direct extension of the A3 render seam and the
`api_kline` candle seam; the SMC math is frozen and pure. The spec MUST lock:
the payload shape + equality contract (Q1/Q2), toggle persistence (Q4),
premium/discount drawing (Q6), the window/limit (Q7), and the OB box extent
(Q11).
