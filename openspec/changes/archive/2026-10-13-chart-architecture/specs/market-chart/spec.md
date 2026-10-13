# Delta for market-chart

Issue #113 (Fase F0): the 1137-line `chart.js` IIFE is split into layered ESM
modules; delivery migrates UMD/globals → native ESM. **Behavior-equivalent.**
R14–R18 cover the architecture contract; R1–R13 stay in force and unmodified.

## ADDED Requirements

### Requirement: R14 — Layered ESM module boundary

Modules MUST follow a frozen inventory: entry `chart.js` (thin: Django-injected
`CONFIG` + imports + `boot()`), pure cores `chart-core.js`/`drawing-core.js`/
`smc-overlay-core.js`, `chart-store.js` (UI/config state ONLY — MUST NOT hold
candle data), `chart-bus.js`, `chart-host.js` (chart/series/panes/scales/
crosshair + candle data), `controllers/{indicators,history,stream,drawings,smc,
toolbar}.js`, and `main.js` (ALL orchestration + boot/switch). No module MUST
exceed ~300 lines. Controllers MUST import host/store/bus directly but MUST NOT
import `main`; commands MUST travel the bus, so `main.js` has no circular imports.

#### Scenario: Inventory and no-cycle
- GIVEN the delivered modules, WHEN imports resolve, THEN the inventory exists, no controller imports `main`, and `main.js` has no cycles

#### Scenario: Store never holds candles
- GIVEN `chart-store.js`, WHEN its keys are inspected, THEN it holds only UI/config (`symbol, interval, indicators, params, smc, tool`) — no candle data

#### Scenario: Size ceiling
- GIVEN every new module, WHEN line counts are read, THEN each is ≤ ~300 lines

### Requirement: R15 — ESM loading and module serving

`package.json` MUST be root `{"type":"module"}` (Node metadata only — no
dependency/build). Cores MUST use native `export` (UMD shim removed).
`tests/js/*.test.js` MUST use `import`, assertions unchanged. The entry MUST load
as `<script type="module" src="{% url 'market_chart_js' %}">`; the
LightweightCharts CDN MUST stay a classic global script. Every imported module
MUST be served same-origin under `/market/` via its own Django route with a JS
MIME type. Execution MUST be deferred; `boot()` MUST be the last side effect and
controllers MUST NOT self-boot on import.

#### Scenario: ESM test run
- GIVEN `package.json {"type":"module"}` and converted tests, WHEN `node --test "tests/js/**/*.test.js"` runs, THEN all 45 pass with unedited assertions

#### Scenario: Module routes serve JS
- GIVEN each module route, WHEN GET same-origin under `/market/`, THEN 200 with a JS MIME type (missing route → import 404 → blank chart)

#### Scenario: Deferred order preserved
- GIVEN the page loads, WHEN modules execute, THEN no controller self-boots and `boot()` is the final side effect

### Requirement: R16 — Config injection

Django MUST inject config through the ESM entry `chart.js` (rendered by Django)
exporting `CONFIG` (`CONFIG.symbols` = the symbol array). There MUST be NO inline
script and NO `window` global for config. Because config lives in the entry,
`/market/chart.js` MUST contain the literals `BTCUSDT` and `market_kline` so the
existing `test_market_ux.py` assertions hold unedited.

#### Scenario: Config is an ESM export
- GIVEN `/market/chart.js`, WHEN fetched, THEN it is a JS module exporting `CONFIG.symbols`; no inline/window config exists

#### Scenario: Entry keeps the symbol literal
- GIVEN `/market/chart.js`, WHEN fetched, THEN it contains `BTCUSDT` and `market_kline`

### Requirement: R17 — Preserved behavior invariants

The refactor MUST preserve verbatim: single-write-path (#68) — `setData()` only in
build/history, candle `update()` only in stream, no periodic full-series
`setData`; single-source — JS MUST NOT compute indicators or SMC; the
`gen`/`drawGen`/`smcGen` race guards at their ownership; and the boot/switch
`.then()` order: layout → build (reattach drawings) → drawings fetch → SMC fetch
→ history, `ready` after history, `switchTo` clearing the previous key BEFORE
reload.

#### Scenario: No setData from the live path
- GIVEN the split modules, WHEN the WS live path runs, THEN no full-series `setData` is issued

#### Scenario: Guards and ordering intact
- GIVEN `switchTo(symbol, interval)`, WHEN orchestration executes, THEN `gen`/`drawGen`/`smcGen` guard their paths and the `.then()` order + `ready` timing are byte-equivalent

### Requirement: R18 — Test-seam preservation

The refactor MUST expose `window.marketChart` with frozen keys `{chart,
candleSeries, panes, ready, drawings, smc, smcCounts, smcToggles}` and equivalent
update-timing, and MUST re-expose `window.SmcOverlayCore` as the sanctioned test
seam. `tests/web/test_market_e2e.py` MUST stay green with NO assertion edits.

#### Scenario: Seam shape frozen
- GIVEN a booted chart, WHEN `window.marketChart` is read, THEN all eight keys exist and update as before

#### Scenario: SMC core reachable
- GIVEN the ESM entry loaded, WHEN `window.SmcOverlayCore.setupMarkers(...)` is called, THEN it returns the marker array as before

## Non-Applicable Domains

- **core-domain-boundary**: N/A — change touches served JS under `web/market/templates`, not `src/`; boundary unchanged.
- **security-invariants**: no new CSP surface — `script type="module"` from `'self'` is covered by existing `script-src 'self'`; R11 read-only scanner stays clean.
