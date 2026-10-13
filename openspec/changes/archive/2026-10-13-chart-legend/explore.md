# Exploration: chart-legend (issue #114, Fase F1 — Ola 1)

## Executive Summary

F1 adds a TradingView-style floating legend + crosshair readout to the market
chart. The F0 layered ESM architecture (MERGED) already provides every seam the
legend needs: `chart-host.js` owns the LightweightCharts instance and the
per-series data maps (`activeSeries`, `seriesData`), the bus carries
`chart:built` / `indicator:changed`, and controllers are leaf DI factories
(`create({store, bus, host, config})`).

The two load-bearing findings:

1. **The legend can be pure read-through — no recompute.** v5's
   `subscribeCrosshairMove` gives a `param.seriesData` **Map keyed by the series
   object** (confirmed: `param.seriesData.get(series)`). The candle OHLC under
   the cursor comes from the SAME map
   (`param.seriesData.get(host.getCandleSeries())`); active indicator values come
   from `param.seriesData.get(a.series)` for each entry in `host.getActiveSeries()`.
   On crosshair leave (`param.point === undefined`) the last value comes from
   `host.getSeriesData()[dataKey]` (last element). Single-source is satisfied:
   the legend only formats server-shaped values.

2. **The crosshair price/time axis labels already exist by default in v5.**
   `vertLine` shows the time label and `horzLine` shows the price label with no
   opt-in; `chart-host.js` creates the chart with `{height:480, timeScale:{timeVisible:true}}`
   and does NOT disable them. So the "crosshair readout labels" requirement is
   largely free — F1 only needs optional theming (label background) via
   `host.build` and the floating panel itself.

`chart-host.js` does NOT currently expose a crosshair subscription (only
`subscribeClick` + `subscribeVisibleRange`). **One host method must be added**
(`subscribeCrosshairMove(fn)`) — crosshair is already host-owned per R14.

---

## 1. F0 architecture recap (verified against merged code)

### Host crosshair surface — `chart-host.js`

Current public API (`createHost()` return):
`build`, `remove`, `getChart`, `getCandleSeries`, `getActiveSeries`, `getPanes`,
`getCandles`, `getSeriesData`, `getLastBucket`, `setLastBucket`, `setCandles`,
`updateCandle`, `dataKey`, `seriesFromPayload`, `rsiValues`, `setRsi`,
`subscribeClick`, `subscribeVisibleRange`.

- **No crosshair subscription exists.** `subscribeClick`/`subscribeVisibleRange`
  wrap `chart.subscribeClick` / `chart.timeScale().subscribeVisibleLogicalRangeChange`.
  F1 adds `subscribeCrosshairMove(fn) → chart.subscribeCrosshairMove(fn)` (mirror
  of the existing two, null-guarded on `chart`).
- **`getActiveSeries()`** → `[{ token, key, place, pane, series }]` (built in
  `addSeries`, line 108). This is the series-object → indicator-token map the
  legend needs.
- **`getSeriesData()`** → `{ [dataKey]: [{time,value}] }` where
  `dataKey = "o:"+key` (overlay) or `"p:"+pane+":"+key` (pane) (line 73). Shared,
  returned by reference, written by history/stream. Last element = last value.
- **`getCandles()`** → the candle array (owned by host, #68). Last element = last
  bar for the leave-state OHLC.
- **`REGISTRY`** (exported) maps `token → {place, pane, series:[{key,type,color}]}`.
  It carries **no precision/formatting metadata** — so legend precision must be a
  legend-core concern (or a new host-side addition; see Q3).
- `build(state)` calls `chart.remove()` first → a **new chart object each build**;
  any crosshair handler registered on the old chart dies with it. The legend MUST
  re-subscribe after every `chart:built`.

### Store / bus API

- **Store** (`chart-store.js`): `get()` (same ref), `set(patch)` (merge+emit),
  `subscribe(fn)`. Keys frozen: `["symbol","interval","indicators","params","smc","tool"]`.
  Holds config only — never candles (#68).
- **Bus** (`chart-bus.js`): `on(name,fn)→unsub`, `off`, `emit`. Frozen events:
  `config:changed`, `indicator:changed`, `layout:loaded`, `chart:built`, `history:loaded`,
  `candle:closed`, `drawings:changed`, `smc:loaded`, `smc:toggles`, `ready`.
  **`chart:built` payload = `{chart, candleSeries, panes}`** (emitted in
  `main.buildChart`, line 78). No legend-specific event exists or is needed.

### Controller DI factory pattern

Every controller is a leaf module: `export function createX({store, bus, host, config})`,
never imports `main`. `main.boot` constructs them (lines 57–62) and `main.buildChart`
calls the attach hooks (`drawings.attachAllDrawings()`, `smc.attachSmcLayer()`,
`host.subscribeClick(...)`, `host.subscribeVisibleRange(...)`). Commands travel the
bus; `main` subscribes (`config:changed`→switchTo, `indicator:changed`→rebuild).

### How a new controller + pure core gets served and tested

- **Serving** (`web/market/views.py`): pure core → add name to `MODULE_ALLOWLIST`
  (served at `/market/<name>.js` via `market_chart_module_js`); controller → add
  name to `CONTROLLER_ALLOWLIST` (served at `/market/controllers/<name>.js` via
  `market_controller_js`). Both parameterized allowlist views, 404 on unknown
  name, `text/javascript` MIME, not auth-gated. Routes already exist in `urls.py`.
- **`chart.html`**: add `<link rel="modulepreload" href="{% url 'market_chart_module_js' name='legend-core' %}">`
  and the controller preload, following the existing F0 pattern.
- **UX test**: `test_market_ux.py::test_import_graph_routes_resolve` **derives the
  expected routes from the real import graph** and will automatically cover the
  new `./legend-core.js` / `../legend.js` specifiers — no test edit needed.
  `test_module_allowlist_routes_serve_javascript` iterates the allowlist constant.
- **JS tests**: `node --test "tests/js/**/*.test.js"` — add `tests/js/legend-core.test.js`
  (pure core) and optionally extend `chart-controllers.test.js` for pure helpers.
- **E2E**: `tests/web/test_market_e2e.py` — ADD a DOM-only test (no image diffs),
  assertions may not be edited.
- **Patch gate**: `diff-cover --fail-under=100` is **Python-only** — JS changes are
  invisible to it. The JS safety net is `node --test` + E2E.

### Frozen seams (do NOT break)

- `window.marketChart` **8 keys** `{chart, candleSeries, panes, ready, drawings, smc, smcCounts, smcToggles}`.
  **Do NOT add a `legend` key** — R18 froze the shape; assert the legend via its
  DOM, not the seam.
- `window.SmcOverlayCore`. No new global.

---

## 2. Legend data source (single-source confirmed)

### v5 crosshair param shape (verified via Context7, v5.2.0)

```js
chart.subscribeCrosshairMove((param) => {
  // param.point, param.time  -> undefined when the cursor leaves the data range
  // param.seriesData         -> Map<ISeriesApi, dataItem>   // .get(series)
});
```

- `param.seriesData.get(host.getCandleSeries())` → `{time,open,high,low,close}` at
  the cursor, or `undefined` outside range.
- `param.seriesData.get(a.series)` → `{time,value}` for each active indicator
  series, or `undefined` (gap / outside range). Same pattern already documented
  in the codebase's SMC controller for coordinate mapping.
- Outside the data range, `param.time` and every `seriesData.get(...)` are
  `undefined` → the legend MUST null-check.

### Mapping a series back to its indicator token + params

`host.getActiveSeries()` already carries `{token, key, place, pane, series}` — the
exact mapping. Params live in the store (`state.params[token]`) for the legend
*label* (e.g. "SMA 20"), not for any value computation.

### "Last value" when not hovering

`host.getSeriesData()[dataKey(a.place, a.pane, a.key)]` → array; last element's
`.value`. Candles: `host.getCandles()` last element. **No recompute** — the arrays
are written by `history.applyHistory` (setData path) and `stream.scheduleCloseRefresh`
(update path), so they are the single source of truth already on the chart.

### Single-source guarantee

The legend reads only: (a) `param.seriesData` (live hovering), (b) `host.getSeriesData()`
/ `host.getCandles()` (leave state), (c) `REGISTRY` + `store.params` (labels). It
imports **no** `src/` math, calls no server, performs **no** indicator formula.
This is directly testable: `legend-core.js` exports only formatters/assemblers and
contains no numeric window/EMA/RSI logic.

---

## 3. `legend-core.js` design (propose — pure, freeze signatures)

Framework-free: no DOM, no chart lib, no network, no globals. Native ESM `export`.
Unit-tested with `node --test`.

```js
// --- precision (single static map, live token vocabulary from chart-host REGISTRY) ---
// Price-like overlays -> 2; oscillators -> 2; MACD family -> 4; ATR -> 2; volume -> 0.
export const DECIMALS = Object.freeze({
  sma: 2, ema: 2, bollinger_upper: 2, bollinger_middle: 2, bollinger_lower: 2, vwap: 2,
  rsi: 2, stochastic_k: 2, stochastic_d: 2, atr: 2,
  macd: 4, macd_signal: 4, macd_histogram: 4,
  volume: 0,
});

// value -> display string; null/undefined -> "–" (en-dash, mirrors #rsi placeholder)
export function formatValue(value, decimals) -> string

// candle -> {open,high,low,close} formatted strings + change sign vs previous close
// (prevClose optional; omit -> no change field). No rounding of the raw numbers elsewhere.
export function formatOHLC(candle, decimals, prevClose) -> {
  open, high, low, close, change, changePct   // all strings; change signed
}

// One active series -> a display row. `entry` is the controller-extracted
// {token, key, place, pane, value} (value already read from param/host).
// `label` from token + store params (e.g. "SMA 20"); `decimals` from DECIMALS[key]||2.
export function seriesRow(entry, params) -> {
  token, key, place, pane, label, value /*string*/, color /*from caller?*/
}

// Assemble the whole legend from a snapshot (controller gathers the raw data).
// snapshot = { candle, prevClose, entries:[{token,key,place,pane,value}] }
export function legendRows(snapshot, params) -> {
  ohlc: {open,high,low,close,change,changePct},
  series: [ {token,key,place,pane,label,value} ]
}

// Crosshair label formatters (used only if we override v5 defaults; see §5).
export function formatPrice(price, decimals) -> string
export function formatTime(time /*UNIX s*/, interval) -> string  // "1m"->HH:MM, "1d"->YYYY-MM-DD
```

**Design rule:** `legend-core` never sees a LightweightCharts object — the
controller converts `param.seriesData` (Map keyed by series object) into a plain
`entries` array using `host.getActiveSeries()`. That keeps the core testable in
Node with zero mocks.

**Precision rationale:** v5 series currently have no `priceFormat` set, so the axis
uses an auto precision. A static token→decimals map is the minimal, frozen rule;
it is deliberately NOT derived from value magnitude (unstable across ticks) and
NOT read from the DOM (fragile). Validated in the design phase (Q3).

**Output shapes** are plain data (no DOM nodes) so tests assert objects, and the
controller alone writes text into nodes.

---

## 4. `LegendController` design (propose)

New leaf controller `controllers/legend.js`, `export function createLegend({store, bus, host, config})`,
never imports `main`.

### DOM overlay

- A single `<div class="chart-legend" role="status">` appended inside the
  `#chart` container. `#chart` currently has **no `position`** in `theme.css`
  (`#chart{min-height:460px}`) → **add `position:relative`** so the overlay
  anchors top-left without layout shift.
- `position:absolute; top:var(--sp-2); left:var(--sp-2); pointer-events:none;`
  so it never eats chart mouse events (critical: a hover readout must let the
  crosshair track). Uses design-system tokens (`--surface`, `--text`, `--mono`,
  `--up/--dn`, `.num` for tabular-nums). Styled in `theme.css` (same-origin,
  CSP-safe).
- Cheap re-render: fixed set of text nodes updated via `textContent` (never
  `innerHTML` rebuild), coalesced with `requestAnimationFrame` because
  `subscribeCrosshairMove` fires per mousemove (perf guard).

### Subscription + lifecycle

- On `create`, subscribe to the bus `chart:built` event (already emitted by
  `main.buildChart`). In the handler: `host.subscribeCrosshairMove(onMove)` on the
  **new** chart, then render the leave-state snapshot (last values).
  This means `main.js` needs **only one added line** (`createLegend(...)`) — no
  edit to `buildChart`.
- `onMove(param)`:
  - if `param.point` (hovering): snapshot candle = `param.seriesData.get(host.getCandleSeries())`;
    entries = `host.getActiveSeries().map(a => ({...a, value: (param.seriesData.get(a.series)||{}).value}))`.
  - else (leave): candle = last of `host.getCandles()`; entries' values = last
    element of `host.getSeriesData()[dataKey]`.
  - render `legendRows(snapshot, store.params)`.
- Also re-render leave-state on `indicator:changed` (series set changed → rebuild →
  `chart:built` fires again) and on `candle:closed` (live tip advanced) so the
  idle legend shows the current last value.

### a11y

- The legend region is a `role="status"` landmark. **Open decision (Q1):** an
  aggressive `aria-live` on a per-mousemove readout floods screen readers with
  announcements. Recommended: **do NOT live-announce hover**; make the panel a
  labelled, focusable-adjacent static readout (`aria-label="Chart legend"`) and, if
  `aria-live` is required, throttle it to state changes (symbol/interval/indicator),
  never to crosshair movement. The issue names `aria-live` as an invariant — the
  design phase must reconcile "aria-live" with "no screen-reader spam" (likely
  `aria-live="polite"` only on the *idle* summary, or `aria-atomic` off + a
  debounced update).
- No layout shift: absolute overlay, `pointer-events:none`.
- Non-color state cue: the OHLC change carries a signed value (`.num`), color only
  tints — consistent with the analytics chart precedent in `theme.css`.

### Re-render triggers (bus)

| Event | Legend behavior |
|---|---|
| `chart:built` | re-subscribe crosshair on new chart; render last-value snapshot |
| `indicator:changed` | (rebuild → `chart:built`) rows change automatically |
| `candle:closed` | refresh idle last values (live tip) |
| `history:loaded` | refresh idle last values (full reload / switch) |

No new bus events required.

---

## 5. Crosshair labels (price/time)

- **Verified:** v5 shows `vertLine` (time) and `horzLine` (price) axis labels by
  default; `chart-host.js` does not disable them, and `timeVisible:true` is
  already set. So the "líneas guía + etiquetas de precio/tiempo" requirement is
  **already met by stock v5**.
- What F1 *may* add for TradingView parity (optional, host-owned since R14 assigns
  crosshair to host): `chart.applyOptions({ crosshair: { mode: Normal, vertLine:
  { labelBackgroundColor }, horzLine: { labelBackgroundColor } } })` in
  `host.build`, themed to `--accent`. This is new behavior (not in R17's verbatim
  list) and is E2E-safe (no E2E asserts crosshair style).
- Custom formatters (`localization.priceFormatter` / `timeFormatter`) are
  available but **not required** — the axis auto-formats. Only add if the design
  wants a fixed time format. This keeps the crosshair readout work small.

---

## 6. Open questions / decisions (lock in design)

| # | Question | Recommendation |
|---|---|---|
| Q1 | `aria-live` on a per-mousemove readout → screen-reader spam. | Do NOT live-announce hover; `role="status"` static region; if aria-live is mandated, restrict it to state changes (symbol/interval/indicator), debounced. Lock wording in design. |
| Q2 | Legend on hover vs pinned. | Follow TradingView: **live on hover, fall back to last values on leave** (issue spec). No pin toggle in F1. |
| Q3 | Precision per indicator. | Static `DECIMALS` map in legend-core (frozen). Alternative: set `priceFormat` per series in the host — rejected (duplicates metadata, touches host/series construction). |
| Q4 | Which indicators show. | **All active series** (overlays + panes), grouped/ordered by `getActiveSeries()` order (overlays first, then pane order). No filtering in F1. |
| Q5 | Last value when not hovering. | `host.getSeriesData()` last element + `host.getCandles()` last bar. Refresh on `candle:closed` / `history:loaded`. |
| Q6 | Mobile/responsive. | Overlay must not overflow the chart at 375px; theme.css already collapses `.market-layout` at 820px. Use `max-width:min(90%, 320px)` + `overflow:hidden`/wrap. Design to verify at 375px via Playwright + `/impeccable`. |
| Q7 | Do we need `formatPrice`/`formatTime` at all? | Only if axis-label theming/format is overridden. If stock labels suffice, ship them unused or omit (YAGNI) — decide in design after a visual check. |
| Q8 | Where to add `subscribeCrosshairMove`. | In `chart-host.js` (crosshair is host's per R14), mirroring `subscribeClick`. One null-guarded 3-line method. |

---

## 7. Risks

1. **Crosshair perf (HIGH).** `subscribeCrosshairMove` fires per mousemove; a naive
   full re-render will jank. *Mitigation*: `textContent` updates on a fixed node
   set + `requestAnimationFrame` coalescing; no innerHTML, no allocation-heavy work.
2. **Re-subscription across rebuilds (MED-HIGH).** `host.build` destroys the chart;
   a stale handler from the previous build would throw or double-render.
   *Mitigation*: re-subscribe on every `chart:built`; the OLD chart's handler dies
   with `chart.remove()`, so no leak — but the legend must always bind to the
   current chart object.
3. **Single-source discipline (MED).** Any temptation to recompute (e.g. derive
   change %, average) in the legend violates the invariant. *Mitigation*: legend-core
   contains only formatting; add a test asserting it imports nothing and has no
   indicator formulas; `%` change is pure arithmetic on server-shaped values (not an
   indicator).
4. **E2E seam coupling (MED).** Do NOT add a `window.marketChart` key (R18 froze 8).
   *Mitigation*: assert the legend through its DOM (`.chart-legend` text) in a new E2E test.
5. **Patch coverage (MED).** `diff-cover` is Python-only; JS has no coverage gate.
   *Mitigation*: `node --test` for legend-core + pure controller helpers + one E2E.
6. **No-deps / CSP (LOW).** Overlay is ESM + theme.css, no inline, no npm.
   *Mitigation*: existing `test_market_page_has_no_inline_script_or_handler` + CSP test.
7. **Relative-import route resolution (LOW).** New `legend-core.js` +
   `controllers/legend.js` MUST be allowlisted or the import 404s → blank chart.
   *Mitigation*: `test_import_graph_routes_resolve` derives and asserts every
   relative import automatically — it will fail loudly if the allowlist is missed.

---

## 8. Proposed PR shape + size

Scope: one pure core (`legend-core.js`), one controller (`controllers/legend.js`),
one host method (`subscribeCrosshairMove`), allowlist entries + `chart.html`
preloads, `theme.css` overlay styles, one node test file, one E2E test. `main.js`
gains ~1 line.

Rough diff estimate:

| Area | Lines |
|---|---|
| `legend-core.js` | ~90 |
| `controllers/legend.js` | ~140 |
| `chart-host.js` (+subscribe) | ~8 |
| `main.js` (wire) | ~3 |
| `views.py` allowlists + `chart.html` preloads | ~6 |
| `theme.css` overlay | ~18 |
| `tests/js/legend-core.test.js` | ~110 |
| `tests/web/test_market_e2e.py` (add) | ~50 |
| **Total** | **~425** |

**400-line budget risk: Medium/High.** F1 is one cohesive feature, but it lands
just over budget once tests are counted. Honest options:

- **Chained 2 slices (recommended):**
  1. **Slice 1 — pure core + host seam + serving.** `legend-core.js`, host
     `subscribeCrosshairMove`, allowlists/preloads, node tests. ~220 lines,
     autonomous (node green; no browser behavior change yet).
  2. **Slice 2 — controller + overlay + E2E.** `controllers/legend.js`, `main.js`
     wire, `theme.css`, E2E test. ~205 lines.
- **Single PR** is plausible (~425) if the delivery strategy resolves to
  `single-pr` or `size:exception`; the feature is cohesive and reversible as one
  unit, but it exceeds the default 400 review budget.

Recommendation to the orchestrator: **chained 2-slice** unless `single-pr` /
`size:exception` is explicitly chosen.

---

## Affected Areas

- **NEW** `web/market/templates/market/legend-core.js` — pure formatters/assemblers.
- **NEW** `web/market/templates/market/controllers/legend.js` — DI overlay controller.
- `web/market/templates/market/chart-host.js` — add `subscribeCrosshairMove(fn)`.
- `web/market/templates/market/main.js` — construct `createLegend(...)`.
- `web/market/views.py` — `MODULE_ALLOWLIST += "legend-core"`, `CONTROLLER_ALLOWLIST += "legend"`.
- `web/market/templates/market/chart.html` — modulepreload links.
- `web/accounts/templates/registration/theme.css` — `#chart{position:relative}` + `.chart-legend`.
- **NEW** `tests/js/legend-core.test.js`.
- `tests/web/test_market_e2e.py` — add one DOM-only legend test (no edits to existing).
- Archive-time: `openspec/specs/market-chart/spec.md` (+ a legend requirement) or a
  new `chart-legend` domain.

No `src/` change, no migration, no model, no order surface, no new runtime
dependency, CSP unchanged, no new `window` global, `window.marketChart` stays 8 keys.

## Ready for Proposal

**YES.** The host crosshair surface, the v5 `seriesData` Map contract, the store/bus
API, the controller DI pattern, the serving/allowlist path and the test harness are
all verified against merged F0 code. The one host method to add is trivial and
mirrors an existing one. The design phase must lock Q1 (aria-live scope), Q3
(precision map), Q4 (which series), Q6 (responsive) and the slice split.
