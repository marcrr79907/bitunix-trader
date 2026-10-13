# Exploration: chart-architecture (issue #113, Fase F0 — base sólida)

## Executive Summary

F0 is a **comportamiento-equivalente** refactor with **zero behavior change**:
split the 1137-line `web/market/templates/market/chart.js` IIFE into layered
ESM modules and migrate the JS module system from UMD/globals to **native ESM**.
The contract is frozen: **45 node tests + 24 E2E must stay green without touching
a single assertion**, patch coverage 100% (Python-only gate — JS relies on
`node --test` + E2E), ruff clean.

The approved decision (Ruta B) is: a root `package.json` with ONLY
`{"type":"module"}` (Node metadata, NOT a dependency/build step), pure cores
switch to native `export` (UMD shim removed), `tests/js/*.test.js` move from
`require()` to `import`, Django injects config via a served `market/config.js`
module instead of the `{{ symbols|safe }}` template token, and the entry script
becomes `<script type="module" src="{% url 'market_chart_js' %}">`.

**The single hardest constraint is the test seams.** The E2E suite reads
`window.marketChart.*` (8 keys) AND `window.SmcOverlayCore.setupMarkers(...)`
(two assertions at `test_market_e2e.py:886,929`). Removing the UMD shim kills
`window.SmcOverlayCore`; the ESM migration MUST deliberately re-expose it (or the
E2E contract silently breaks — and assertions may NOT be edited). This is the
one place where "ESM without globals" collides with the frozen E2E contract.

---

## 1. Monolith inventory — responsibility map of `chart.js`

Every seam below is a candidate module boundary. Line ranges are from the
current file (1137 lines). The IIFE wraps everything (L15 open, L1136 `boot()`,
L1137 `})()`).

| # | Block | Lines | State it owns | Moves to |
|---|-------|-------|---------------|----------|
| C0 | Module header + consts (`WS_URL`, `REFETCH_DELAY`, `SAVE_DELAY`, `LAYOUT_URL`, `DRAWINGS_URL`, `HISTORY_LIMIT`, `CHANNELS`) | 1–40 | constants | `config.js` / `chart-bus`? → **`chart-host` consts or config** |
| C1 | `REGISTRY`, `PANE_ORDER`, `DEFAULT_INDICATORS` (static presentation metadata) | 42–90 | static registry | **`chart-host.js`** (build needs it) or a `registry.js` |
| C2 | DOM refs + DOM readers: `toggles`, `paramInputs`, `smcToggles`, `readSmc`, `readParams`, `readIndicators`, `buildIndicators`, `applyLayout` | 92–153 | DOM ↔ config mapping | **`controllers/indicators.js`** (panel) |
| C3 | `state` object (symbol, interval, indicators, params, smc, tool) | 155–162 | the observable store | **`chart-store.js`** |
| C4 | `el`, `chart`, `candleSeries`, `activeSeries`, `seriesData` | 164–170 | chart instance refs | **`chart-host.js`** |
| C5 | `window.marketChart` test seam | 172–184 | the E2E contract | **`main.js`** (created once) |
| C6 | WS state (`ws`, `sub`, `retry`, `pingTimer`, `closeTimer`, `lastBucket`) | 186–191 | live-stream state | **`controllers/stream.js`** (or host) |
| C7 | history state (`candles`, `EDGE`, `loadingOlder`, `hasMore`) + `dataKey`, `seriesFromPayload`, `rsiValues`, `setRsi` | 193–222 | history + series payload mapping | **`chart-host.js`** / `controllers/indicators.js` |
| C8 | `buildChart` (chart/series/panes construction, primitive re-attach, click + visible-range subscribe) | 224–282 | chart build/rebuild | **`chart-host.js`** |
| C9 | `backoff` | 284–286 | reconnect timing | **`controllers/stream.js`** |
| C10 | `klineUrl`, `applyHistory`, `fetchHistory` | 288–328 | history load (`setData`) | **`controllers/history.js`** (or host) |
| C11 | `loadOlder` (pagination, `mergeCandles`, viewport preserve) | 330–363 | pagination | **`controllers/history.js`** |
| C12 | `onPush`, `scheduleCloseRefresh` (live `update()` only) | 365–404 | live stream + close refresh | **`controllers/stream.js`** |
| C13 | `sendSubscribe`, `startPing`, `connect` (WebSocket) | 406–443 | WS lifecycle | **`controllers/stream.js`** |
| C14 | `csrfToken`, `loadLayout`, `saveLayout` (R2/R4/R5) | 445–496 | layout persistence | **`controllers/indicators.js`** (or a `layout.js`) |
| C15 | Drawings DOM refs + state (`drawingListEl`, tool buttons, `textDialog`, `currentDrawings`, `attached`, `drawGen`, `pendingAnchor`) | 498–518 | drawings state | **`controllers/drawings.js`** |
| C16 | `priceRangeFor`, `renderShape`, `makeDrawingPrimitive` (canvas + v5 primitive) | 520–635 | drawings render | **`controllers/drawings.js`** |
| C17 | `renderDrawingList`, `attachAllDrawings`, `loadDrawings`, `refreshDrawings`, `createDrawing`, `deleteDrawing` | 637–699 | drawings CRUD + attach | **`controllers/drawings.js`** |
| C18 | `syncToolButtons`, `onChartClick`, tool-button/cancel/dialog listeners | 744–819 | drawing tool interaction | **`controllers/drawings.js`** |
| C19 | SMC state (`smcBody`, `smcPrim`, `smcMarkers`, `smcGen`, `smcCtx`, `MAP_WIDTH`, `RAY_WIDTH`, `FVG_HALF_WIDTH`) | 821–836 | SMC state | **`controllers/smc.js`** |
| C20 | `smcUrl`, `smcMap`, `smcPriceRange`, `renderSmc`, `makeSmcPrimitive`, `attachSmcLayer`, `loadSmc`, `refreshSmc` | 838–1048 | SMC fetch + render | **`controllers/smc.js`** |
| C21 | `rebuild` (config-change path) | 1050–1060 | control action | **`main.js`** (wiring) or `controllers/indicators.js` |
| C22 | `gen`, `switchTo` (race-guarded key switch) | 1062–1097 | switch orchestration | **`main.js`** (boot/switch orchestration) |
| C23 | Pair/interval/toggle/SMC listeners | 1099–1112 | DOM wiring | **`controllers/toolbar.js`** (pair/interval) + `controllers/indicators.js` (toggle) |
| C24 | `boot` (layout → build → connect → drawings → SMC → history, `ready` flip) | 1114–1134 | boot sequence | **`main.js`** |
| C25 | `boot()` invocation | 1136 | entry | **`main.js`** |

**Observations for the split:**
- The cross-cutting mutable `state` (C3) is read/written by nearly every block;
  the store must expose `get`/`set` + `subscribe` so controllers stop reaching
  into a shared closure object.
- `activeSeries`/`seriesData` (C4/C7) couple build (C8), history (C10/C11), and
  the live close refresh (C12) — they belong with the **host**, not a controller,
  because three concerns share them.
- Drawing and SMC state are already fully encapsulated (C15–C20) → clean
  one-controller-per-file seams.
- `gen`/`drawGen`/`smcGen` (C14/C15/C19/C22) are three independent race guards;
  the split must preserve each at its current ownership site.

---

## 2. How JS is served today

**Views** (`web/market/views.py`):
- `chart_js` (L347): renders `market/chart.js` as a Django template with
  `{"symbols": json.dumps(SYMBOLS)}` → `content_type="text/javascript"`,
  `@login_required` GET-only. This is the ONLY file with template tokens
  (`{{ symbols|safe }}`, L21 — verified: no other `{{ }}`/`{% %}`).
- `chart_core_js` (L355) / `drawing_core_js` (L364) / `smc_overlay_core_js` (L373):
  render the pure cores, **not auth-gated**, `text/javascript`.

**URLs** (`web/market/urls.py`): bare names (no `app_name`) —
`market/chart-core.js` → `market_chart_core_js`, `market/drawing-core.js` →
`market_drawing_core_js`, `market/smc-overlay-core.js` →
`market_smc_overlay_core_js`, `market/chart.js` → `market_chart_js`.

**Template** (`chart.html`): `{% block scripts %}` (L83–89) loads, in order:
1. unpkg LightweightCharts 5.2.0 standalone (classic script, defines the
   `LightweightCharts` global);
2. `market_chart_core_js`, `market_drawing_core_js`, `market_smc_overlay_core_js`
   (classic scripts, each defines a global via the UMD shim);
3. `market_chart_js` (classic script, the IIFE).

**What breaks under ESM and why:**
- **`<script type="module">` is deferred and runs AFTER classic scripts** — today
  all five run in document order; the cores are already loaded when `chart.js`
  executes. Under ESM the entry becomes a module (deferred) but the cores, if
  left as classic UMD scripts, still define their globals before it — OK, but we
  are removing UMD, so the cores must be imported (not global).
- **Import specifiers need explicit `.js` extensions** in the browser
  (`import { x } from "./chart-core.js"`), and the URL the browser resolves must
  match a Django route. `chart-core.js` is served at `/market/chart-core.js`, so
  the entry importing `"./chart-core.js"` resolves correctly **only if the entry
  itself is served under `/market/`** — and `market_chart_js` indeed maps to
  `/market/chart.js`. So relative `./chart-core.js`, `./drawing-core.js`,
  `./smc-overlay-core.js`, `./config.js` will all resolve to real routes.
  → **Every served JS route MUST be reachable via a relative URL from
  `/market/chart.js`**; new routes (`config.js`, the new modules) need matching
  URL names/paths under `market/`.
- **The `{{ symbols|safe }}` token is illegal in an ES module** if the file is
  loaded as a module by the browser (Django still template-renders it, so it
  works — but the token is literally valid JS only because Django replaces it;
  under `type="module"` this still works). The cleaner Ruta B approach is a
  separate `market/config.js` module that exports the config, so `chart.js`
  itself becomes a pure static file with no template tokens (easier to reason
  about and diff).
- **Ordering**: module execution order is NOT the script order — ESM imports are
  hoisted and resolved before the module body. The `boot()` call at the bottom
  must remain the last side effect; controllers must not self-boot on import.
- **Cache-busting / MIME**: Django serves `text/javascript`; modules require a
  JS MIME type (satisfied). No `nomodule` fallback needed (modern-browser target,
  E2E uses Chromium).

---

## 3. Test harness

- **`tests/js/*.test.js`** (3 files, ~45 tests total): use
  `const test = require("node:test")`, `assert = require("node:assert")`, and
  `require("../../web/market/templates/market/<core>.js")`. Under ESM these
  become `import test from "node:test"`, `import assert from "node:assert"`,
  `import * as core from "...<core>.js"` (or named imports). **Assertions are
  unchanged.**
- **CI** (`.github/workflows/ci.yml`, job `js-core` L72–87): `node-version: "22"`
  (L84) runs `node --test "tests/js/**/*.test.js"` (L87). Node 22 fully supports
  ESM + `node --test`. Local `node` is **v24.14.0**.
- **`package.json {"type":"module"}` is required** because there is **no
  package.json anywhere** in the repo (verified: `find` returns none). Without
  it, `.js` is treated as CommonJS by Node and `import` in the test files fails.
  With `type: module`, all `.js` in scope are ESM. **Caveats:**
  - The pure cores are also served to the browser; `type: module` only affects
    **Node's** interpretation — browsers ignore package.json and use
    `type="module"` on the tag. Consistent.
  - `node --test` glob `tests/js/**/*.test.js`: Node 22+ supports the `**` glob
    in the CLI. The three test files import the cores by relative path; with
    `type: module` those imports resolve as ESM. **No other package.json exists**
    so the scope is the repo root — no nested-type conflicts.
  - **Risk**: any file the tests require that still uses `module.exports` breaks.
    The three cores are the only JS the tests import; all three lose the UMD
    shim and gain `export`.
- **CI never installs browsers**; E2E is deselected via `addopts = "-q -m 'not e2e'"`
  (pyproject). E2E is dev-only (`python -m pytest -m e2e`).
- **Python coverage gate is `--fail-under=100` on changed lines**
  (`diff-cover coverage.xml --compare-branch=origin/develop`) but `chart.js` and
  the cores are **template-side JS, not Python** → not measured. The JS safety
  net is exactly the 45 node tests + 24 E2E. This is the core risk of F0.

---

## 4. Django `{% url %}` and config injection under ESM

**Today**: `chart.js` is a Django template; `{{ symbols|safe }}` (L21) injects
`["BTCUSDT", ...]`. `views.chart_js` passes `json.dumps(SYMBOLS)`.

**Under ESM (Ruta B)**: a served module `market/config.js`, rendered by Django,
exports the config the entry imports:

```js
// web/market/templates/market/config.js (Django-rendered)
export const CONFIG = {
  symbols: {{ symbols|safe }},
  csrf: "{{ csrf_token }}",              // optional — csrfToken() already reads <meta>
  urls: {
    kline: "{% url 'market_api_kline' %}",
    smc: "{% url 'market_api_smc' %}",
    layout: "{% url 'market_api_layout' %}",
    drawings: "{% url 'market_api_drawings' %}",
  },
  wsUrl: "wss://fapi.bitunix.com/public/",
};
```

- The entry (`chart.js` / `main.js`) does `import { CONFIG } from "./config.js";`.
- **`{% url %}` tags inside config.js are fine** — Django template-renders the
  file before serving; the browser only ever sees concrete URL strings.
- **Verify**: no other template tokens exist in `chart.js` (grep: only L21). So
  the only token that MUST survive is `symbols`; optionally `csrf_token` and
  `{% url %}` names. **Recommendation**: keep only `symbols` + explicit `{% url %}`
  strings, since `csrfToken()` already reads `<meta name="csrf-token">` (L447–450)
  and hard-coded `/market/api/...` paths already work (L25–26). Minimal change:
  `config.js` exports `symbols` (+ optionally the URLs); everything else stays
  literal. This reduces the diff and the template-token surface.
- **`chart.html`** becomes:
  ```html
  {% block scripts %}
  <script src="https://unpkg.com/lightweight-charts@5.2.0/dist/lightweight-charts.standalone.production.js"></script>
  <script type="module" src="{% url 'market_chart_js' %}"></script>
  {% endblock %}
  ```
  The three core `<script>` tags are dropped — the entry imports them. The
  LightweightCharts CDN script stays a classic script (defines the global the
  modules consume).
- **`market_chart_js` keeps working as the entry**: the view no longer needs to
  inject `symbols` (config.js does), so `chart_js` becomes `render(request,
  "market/chart.js")` → `text/javascript`. **Caveat**: `test_market_ux.py:49`
  asserts `b"BTCUSDT" in response.content` for `/market/chart.js`. If symbols
  move to `config.js`, that assertion breaks. **Two options**: (a) keep the
  `{{ symbols|safe }}` token in `chart.js` (re-exported or re-imported), or
  (b) move the symbol injection to `config.js` and the test's BTCUSDT check
  would move to the config.js route — **but assertions may not be edited**. So:
  **`chart.js` (or the served entry) MUST still contain the literal `BTCUSDT`**.
  Cleanest: keep `chart_js` rendering `chart.js` with `symbols`, and have
  `chart.js` be the entry that also contains the injected symbols (it can
  `export` nothing and just be the module that wires config). **This is a
  decision the spec must lock.**
- **`test_market_ux.py:34`** asserts the market page contains
  `market_chart_js` or `chart.js` — `{% url 'market_chart_js' %}` still renders
  to `/market/chart.js` and satisfies it.
- **No other template tokens** in the JS (verified). `invite.js`
  (`web/accounts/templates/accounts/invite.js`, 10 lines) is a separate classic
  script with no template tokens and no ESM involvement — **out of scope**.

---

## 5. Layering plan (module boundaries)

Proposed file layout under `web/market/templates/market/` (served via new Django
routes) — each file <~300 lines:

```
market/
  chart.js          # ENTRY: imports config + main; boots. Keeps `{{ symbols }}`
                    #   token (or imports config.js) — entry URL unchanged.
  config.js         # Django-rendered: export const CONFIG = {symbols, urls, wsUrl}
  chart-core.js     # pure: export (UMD removed)
  drawing-core.js   # pure: export (UMD removed)
  smc-overlay-core.js # pure: export (UMD removed)
  chart-store.js    # observable state: get/set/subscribe, no lib
  chart-bus.js      # event emitter: on/off/emit, no lib
  chart-host.js     # chart/series/panes/scales/crosshair encapsulation
  controllers/
    indicators.js   # panel DOM <-> state; layout fetch/save; rebuild trigger
    history.js      # klineUrl, fetchHistory, loadOlder (pagination), applyHistory
    stream.js       # WebSocket connect/ping/backoff, onPush, close refresh
    drawings.js     # drawing state, primitives, CRUD, tools, click handler
    smc.js          # SMC fetch, primitive, markers, toggles
    toolbar.js      # pair buttons + interval select wiring
    legend.js       # (F0 stub? see below)
    a11y.js         # (F0 stub? see below)
  main.js           # wiring: build store/host/bus/controllers, boot(), switchTo()
```

**Ownership (concrete function moves):**

- **`chart-store.js`** (C3): holds `{symbol, interval, indicators, params, smc,
  tool}`. API: `get()`, `set(patch)`, `subscribe(fn)`. No framework. The store
  emits on change so legend/toolbar can react. **Single-write-path #68 note**: the
  store is config/UI state — it NEVER holds candle series data (that stays in the
  host). This keeps #68 intact: the only writers of series data are the history
  controller (`setData`) and the stream controller (`update`).
- **`chart-bus.js`** (new): `on(event, fn)`, `off`, `emit(event, payload)`, no
  lib. Event names (proposed, frozen by spec):
  - `config:changed` `{symbol, interval}` — switchTo requested
  - `layout:loaded` `{indicators, params}`
  - `layout:saved`
  - `chart:built` `{chart, candleSeries, panes}`
  - `history:loaded` `{candles}`
  - `candle:closed` `{time}`
  - `drawings:changed` `{rows}`
  - `smc:loaded` `{payload}`
  - `smc:toggles` `{families}`
  - `ready` — boot finished (mirrors `window.marketChart.ready`)
- **`chart-host.js`** (C4/C7/C8): `createChart(el, registry)`,
  `buildChart(state)`, `removeChart()`, owns `chart`, `candleSeries`,
  `activeSeries`, `seriesData`, `candles`, `dataKey`, `seriesFromPayload`,
  `rsiValues`, `setRsi`, `subscribeClick`, `subscribeVisibleRange`. Exposes
  accessors for controllers (`getSeries()`, `getPanes()`, `getCandles()`,
  `setCandles()`). This is the ONLY module that touches the LightweightCharts API
  for chart construction — though drawings/SMC still create primitives on the
  series it hands them.
- **`controllers/indicators.js`** (C2/C14/C21): `readIndicators`, `readParams`,
  `readSmc`, `buildIndicators`, `applyLayout`, `loadLayout`, `saveLayout`,
  `syncToolButtons`?? (tool buttons are drawings — see toolbar). Owns the panel
  DOM and the layout REST calls.
- **`controllers/history.js`** (C10/C11): `klineUrl`, `applyHistory`,
  `fetchHistory`, `loadOlder`. The ONLY `setData` caller besides build.
- **`controllers/stream.js`** (C6/C9/C12/C13): `connect`, `sendSubscribe`,
  `startPing`, `backoff`, `onPush`, `scheduleCloseRefresh`. The ONLY `update()`
  caller for candles; iterates `host.getActiveSeries()` for close refresh.
- **`controllers/drawings.js`** (C15–C18): all drawing functions. Needs the host
  (`getCandleSeries()`) for primitive attach; needs the store for `state.tool`.
- **`controllers/smc.js`** (C19/C20): all SMC functions. Same host dependency.
- **`controllers/toolbar.js`** (C23 pair/interval): `.pair` clicks + `#interval`
  change → emits `config:changed` (or calls `main.switchTo`). If controllers
  import `main`, that's circular — see below.
- **`controllers/legend.js` / `controllers/a11y.js`**: the approved layering
  names these, but **no behavior is assigned to them in the source** (the RSI
  text is `controllers/indicators`; there is no legend component today). **Do
  NOT create empty files** — YAGNI. Either fold legend into `indicators.js`
  (the RSI text update) and a11y into `main.js`/`toolbar.js`, or defer them to
  F1+. **Recommend: skip legend.js/a11y.js in F0; flag as roadmap placeholders.**
- **`main.js`** (C5/C22/C24/C25): creates `window.marketChart` seam, wires
  controllers to the bus, defines `rebuild()` and `switchTo()`, runs `boot()`.
  `switchTo` orchestration (layout → build → drawings → SMC → history) stays in
  ONE place here so the boot/switch ordering is preserved exactly.

**The `window.marketChart` seam** (E2E-critical): created in `main.js` exactly as
today — an object with `chart`, `candleSeries`, `panes`, `ready`, `drawings`,
`smc`, `smcCounts`, `smcToggles`. The host updates `chart`/`candleSeries`/`panes`
on build; drawings updates `.drawings`; SMC updates `.smc`/`.smcCounts`/
`.smcToggles`; `main` flips `.ready`. **The seam shape and update timing MUST be
byte-for-byte equivalent** — every E2E assertion reads it.

**Circular-import risk (real):**
- `toolbar`/`indicators` need to call `switchTo`/`rebuild` (in `main`), and
  `main` constructs them → circular. **Resolution: use the bus.** Controllers
  emit `config:changed` / `indicator:changed`; `main` subscribes and orchestrates.
  Controllers only import the bus + store + host — never `main`. This preserves
  the "controllers import the host directly or via the bus" decision: **host
  directly (for chart/series access), orchestration via the bus.**
- `drawings`/`smc` need the store (tool/toggles) and host (series) — both are
  leaf imports, no cycle.
- `history`/`stream` need host + config — leaf imports, no cycle.
- **The only cycle risk is `main` ↔ controllers**; the bus breaks it.

---

## 6. Open questions / decisions the spec MUST lock

| # | Question | Recommendation |
|---|----------|----------------|
| Q1 | Where does `{{ symbols|safe }}` live? `chart.js` must still contain `BTCUSDT` (test_market_ux.py:49 asserts it on `/market/chart.js`). | Keep the token in `chart.js` (entry) **and/or** ensure the served entry still has the symbol literal. Simplest: `chart.js` renders `symbols` and passes it into `config`/`main`; `config.js` is optional. **Lock the exact mechanism so the UX test stays green.** |
| Q2 | What replaces `window.SmcOverlayCore` for E2E? (test_market_e2e.py:886,929 call `window.SmcOverlayCore.setupMarkers`). | The entry/`main` MUST re-expose `window.SmcOverlayCore` (and, if any test needs it, `window.ChartCore`/`window.DrawingCore`) as an explicit **test seam** after import. This is the one sanctioned global, justified by the frozen E2E contract. **Lock this or the E2E breaks.** |
| Q3 | How many served JS routes / how are modules served? | One Django route per module (mirrors today's pattern), names `market_chart_store_js`, `market_chart_bus_js`, `market_chart_host_js`, `market_chart_config_js`, `market_controllers_*_js`. All under `/market/` so relative imports resolve. **Alternative**: bundle (rejected — no build step allowed). |
| Q4 | Does `config.js` carry `csrf`/`urls` or just `symbols`? | Minimal: `symbols` only; `csrfToken()` stays meta-driven; API paths stay literal (already working). Fewer tokens, smaller diff. Lock it. |
| Q5 | Controllers → host direct vs bus? | **Host direct** (sync data access), **orchestration via bus** (async commands). Lock it. |
| Q6 | `legend.js` / `a11y.js`: create now or defer? | **Defer** — no behavior maps to them. YAGNI. Flag as placeholders for F1+. |
| Q7 | Do the pure cores keep a `window.ChartCore` alias? | **No** for `ChartCore`/`DrawingCore` (no test reads them); **Yes** for `SmcOverlayCore` (E2E reads it). If Q2 re-exposes via main, the cores stay pure `export`. |
| Q8 | `package.json` scope | Root only, ONLY `{"type":"module"}`. Lock that it is Node metadata, not a dependency, and `.dockerignore`/Dockerfile don't need it (JS is served by Django, not built). Confirm it does not trip the "no new runtime dependency" AST guard (that guard scans Python imports only). |
| Q9 | Behavior equivalence of `switchTo`/`boot` ordering | Keep the exact `.then()` chain and `gen` guards in `main.js`. Lock the sequence: layout → build → drawings → SMC → history; `ready` after history. |
| Q10 | `chart.html` script tags | CDN classic script + `<script type="module" src="{% url 'market_chart_js' %}">`. Drop the three core tags. Lock CSP unchanged (`script-src 'self' https://unpkg.com` already allows self modules). |

---

## 7. Risks

1. **`window.SmcOverlayCore` E2E break (HIGH).** Two assertions
   (`test_market_e2e.py:886,929`) call the core through a global. Removing UMD
   without re-exposing kills them, and assertions may not be edited. *Mitigation*:
   Q2 — explicit test seam re-export in `main.js`.
2. **`/market/chart.js` must contain `BTCUSDT` (HIGH).** `test_market_ux.py:49`
   asserts it. Moving symbols to `config.js` alone breaks it. *Mitigation*: Q1.
3. **Behavior drift in the split (HIGH).** #68 single-write-path: `setData` only
   in history/build; `update()` only in stream. If a controller accidentally
   calls `setData`, `test_ws_stream_never_calls_setdata` catches it (E2E spy) —
   good. The `gen`/`drawGen`/`smcGen` race guards and the boot/switch ordering
   must move verbatim. *Mitigation*: keep orchestration only in `main.js`; add a
   design note listing each guard's ownership.
4. **Drawings/SMC teardown order on rebuild (MED-HIGH).** `buildChart` calls
   `attachAllDrawings()` then `attachSmcLayer()`; `switchTo` clears drawings+SMCC
   BEFORE layout/build. Splitting must preserve: clear → loadLayout → build
   (reattach) → drawings fetch → SMC fetch → history. *Mitigation*: E2E
   `test_switch_clears_then_loads_drawings`, `test_smc_switch_refetches_for_new_key`.
5. **ESM in CI / Node 22 (MED).** `package.json {"type":"module"}` + `node --test`
   glob. Node 22 supports both. *Mitigation*: confirm the three test files convert
   cleanly; keep `node-version: "22"`.
6. **Patch coverage is Python-only (MED).** JS changes are invisible to
   `diff-cover`. Safety = 45 node + 24 E2E. *Mitigation*: no assertion edits; each
   slice runs both suites; the split is mechanical (move code, don't rewrite).
7. **Relative import resolution (MED).** Every new module needs a matching Django
   route under `/market/`; a missing route = 404 import = blank page caught only
   by E2E. *Mitigation*: a UX test (`test_market_ux.py`) can GET each module and
   assert 200 — but that ADDS assertions (allowed? adding tests is fine; editing
   existing ones is not). Recommend adding a route-coverage test.
8. **CSP for modules (LOW).** `script-src 'self'` already permits self-hosted
   modules; no `unsafe-inline`. *Mitigation*: none needed; verify via existing
   `test_csp_present_on_market_page`.
9. **`boot()` timing (MED).** ESM defers execution; `DOMContentLoaded` may have
   fired before the module runs (modules execute after parsing, but before
   `DOMContentLoaded` in practice — still, verify). Today the IIFE runs
   immediately after the DOM nodes (script at end of body). *Mitigation*: keep the
   entry at the end of `{% block scripts %}`; the E2E `_wait_ready` polls the seam
   so a slightly later boot is tolerated.
10. **45 node tests count (LOW).** Converting `require`→`import` must not change
    test discovery. `node --test` glob is unchanged.

---

## 8. Proposed slices + size

Baseline: `chart.js` = 1137 lines. Controls/specs: **no file >~300 lines**,
**45 node + 24 E2E green without touching assertions**, patch 100%, ruff clean.

**Estimated resulting file sizes (line counts from the seam map):**

| New file | Approx lines | Source blocks |
|----------|-------------|---------------|
| `chart.js` (entry, thin) | ~40 | imports + `boot()` call + symbols token |
| `config.js` | ~15 | C0 subset |
| `chart-store.js` | ~40 | C3 + subscribe |
| `chart-bus.js` | ~40 | new |
| `chart-host.js` | ~260 | C4, C7, C8 |
| `controllers/indicators.js` | ~180 | C2, C14, C21 |
| `controllers/history.js` | ~120 | C10, C11 |
| `controllers/stream.js` | ~120 | C6, C9, C12, C13 |
| `controllers/drawings.js` | ~300 | C15–C18 |
| `controllers/smc.js` | ~250 | C19, C20 |
| `controllers/toolbar.js` | ~30 | C23 pair/interval |
| `main.js` | ~120 | C5, C22, C24, C25 |

Plus: 3 cores converted (net ~0 line delta), 3 test files converted (`require`→
`import`, net ~0), `chart.html` (script tags swap, ~-3), `views.py` + `urls.py`
routes (~+60), UX route test (~+40).

**Total changed diff ≈ 900–1100 lines (rewrites dominated by moves).**
`400-line budget risk: HIGH. Chained PRs: Yes.`

**Validated 4-slice proposal (feature-branch-chain):**

1. **Slice 1 — ESM scaffold + config + cores + tests.** Add root
   `package.json {"type":"module"}`; convert `chart-core.js`, `drawing-core.js`,
   `smc-overlay-core.js` to `export` (drop UMD); convert `tests/js/*.test.js` to
   `import`; add `market/config.js` + route; keep `chart.js` behavior identical
   (it still carries the `{{ symbols }}` token). Verify: `node --test` 45 green,
   `/market/chart.js` still contains `BTCUSDT`, ruff clean. ~300 lines.
   *Autonomous; no E2E risk yet because `chart.js` is unchanged in behavior.*
2. **Slice 2 — host + store + bus.** Extract `chart-store.js`, `chart-bus.js`,
   `chart-host.js`; `chart.js` imports them and delegates (still an IIFE-free ES
   module now). Preserve the `window.marketChart` seam and `window.SmcOverlayCore`
   re-export. Verify: 45 node + 24 E2E green, no assertion edits. ~450 lines.
3. **Slice 3 — controllers + main.** Extract `indicators/history/stream/drawings/
   smc/toolbar` and `main.js`; `chart.js` becomes the thin entry. Preserve boot/
   switch ordering + all three gen guards. Verify: 45+24 green. ~500 lines.
4. **Slice 4 — cleanup + docs.** Remove any dead code, add module-route
   coverage test, update `chart.html` comments, docs/ADR. ~120 lines.

**Refinement vs issue #113:** the issue's slice 1 already bundles scaffold+config+
cores+tests (matches). Slice 2 (host+store+bus) and slice 3 (controllers+main) are
the natural split at the `main` boundary; slice 4 is cleanup. **Recommend keeping
4 slices**; if slice 2/3 each exceed budget, split controllers into two PRs
(drawings+smc vs indicators+history+stream+toolbar), still targeting the feature
branch.

**Out of scope (fence):** any behavior change; any new runtime dependency or npm
build; `src/` changes; new indicators/SMC math; legend/a11y real components;
persisting SMC toggles; `invite.js`; UI redesign (that's F1+).

---

## Affected Areas

- `web/market/templates/market/chart.js` — the monolith (split into modules).
- `web/market/templates/market/{chart,drawing,smc-overlay}-core.js` — UMD →
  `export`.
- **NEW** `web/market/templates/market/config.js` — Django-rendered config module.
- **NEW** `web/market/templates/market/{chart-store,chart-bus,chart-host,main}.js`.
- **NEW** `web/market/templates/market/controllers/*.js`.
- `web/market/views.py` + `web/market/urls.py` — new JS routes.
- `web/market/templates/market/chart.html` — `<script type="module">` + drop cores.
- `tests/js/*.test.js` — `require` → `import`.
- `tests/web/test_market_ux.py` — route/module serving (existing asserts must hold).
- `tests/web/test_market_e2e.py` — the frozen seam contract (NO edits).
- **NEW** `/package.json` — `{"type":"module"}`.
- Archive-time: `openspec/specs/market-chart/spec.md` (or a new
  `chart-architecture` domain) gains the ESM/layering requirement.

No `src/` change, no migration, no model, no order surface, no new runtime
dependency, CSP unchanged.

## Ready for Proposal

**YES** — the seam map (§1) and serving path (§2) are fully verified against
real code, the ESM migration mechanics are confirmed, and the two blocking
contracts (`window.SmcOverlayCore`, `BTCUSDT` in `/market/chart.js`) have a clear
resolution path. The spec MUST lock: Q1 (symbols token location), Q2 (test-seam
re-export), Q3 (module routes), Q4 (config contents), and Q9 (boot/switch
ordering).
