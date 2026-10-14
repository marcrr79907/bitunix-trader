# Exploration: chart-host-extract (issue #146, DEBT-5 — P2 refactor)

## Executive Summary

`web/market/templates/market/chart-host.js` is **326 lines**, 26 over the R14
ceiling (~300). The guard `tests/web/test_module_size_guard.py` already exempts
it via `ALLOWLIST = {"chart-host.js"}` and names DEBT-5/#146 as the tracked
refactor. The intended cut is the **per-`chartType` candle-series construction +
the HA write path** into a dedicated module.

The clean, architecturally faithful cut is a NEW **host-layer sub-module**
`chart-host-candles.js` — NOT an extension of the pure `chart-types-core.js`.
The HA-live path calls `candleSeries.setData`/`update` (LightweightCharts API)
and holds mutable incremental state; a pure core (which imports nothing and is
asserted import-free by `chart-types-core.test.js`) cannot own either. The new
module receives the built `chart` object + the `Types` core, owns the candle
series, the `CANDLE_CTORS` map, the raw `candles` array and the HA state, and
exposes `setCandles(arr)`/`updateCandle(bar)`/`getCandleSeries()`/`getCandles()`/
`remove()`. `chart-host.js` delegates to it, keeping every external caller
(`history.js`, `stream.js`, `legend.js`, `controllers/smc.js`, `drawings.js`)
and the frozen 8-key `window.marketChart` seam unchanged. Net host reduction
≈ 45 lines → ~281, comfortably ≤300.

Behavior-equivalence is guaranteed by **138 node tests + the E2E suite** passing
WITHOUT editing a single JS/E2E assertion. The one intended test edit is to the
DEBT-3 guard's own exemption list + its exemption-specific test — sanctioned,
because satisfying that guard IS DEBT-5.

---

## 1. `chart-host.js` block inventory (line ranges)

Ownership legend: **STAYS** (host) · **MOVES** (to `chart-host-candles.js`).

| # | Block | Lines | State/shape | Verdict |
|---|-------|-------|-------------|---------|
| H0 | Header doc + `import Core` / `import Types` | 1–11 | imports | STAYS (host keeps `Core` for `upsertCandle`? no — moves to candle module; host keeps `Types` for `isValidType`/`isValidScale`) |
| H1 | `REGISTRY` (token → placement + series factory) | 13–53 | static, exported | STAYS (exported, imported by `controllers/indicators.js`) |
| H2 | `PANE_ORDER` | 56 | static, exported | STAYS |
| H3 | `CANDLE_CTORS` (chartType → v5 Ctor name) | 60–65 | static | **MOVES** |
| H4 | `SCALE_MODES` (scaleMode → PriceScaleMode member) | 69–73 | static | STAYS (scale is a host/price-scale concern, not candle) |
| H5 | `createHost()` state: `chart`, `candleSeries`, `activeSeries`, `panes`, `candles`, `seriesData`, `lastBucket` | 76–96 | closures | SPLIT: `chart/activeSeries/panes/seriesData/lastBucket` STAY; `candleSeries` + `candles` + HA state **MOVE** |
| H6 | HA incremental state `lastHa`/`prevHa`/`lastBarTime` | 87–89 | closures | **MOVES** |
| H7 | `dataKey`, `seriesFromPayload`, `rsiValues`, `setRsi` | 100–124 | payload↔series mapping | STAYS (indicator series, not candles) |
| H8 | `addSeries` (indicator series construction) | 131–162 | harness | STAYS |
| H9 | `build(state)` — createChart, `chartType`/`scaleMode` resolve, **candle Ctor pick (L175–176)**, `applyScale`, indicator series, pane map, **8-key seam writes (L201–203)**, return handles | 166–206 | harness | STAYS, but the candle-Ctor lines (175–176) **DELEGATE** to the new module |
| H10 | `remove()` | 208–214 | teardown | STAYS, **DELEGATES** candle teardown |
| H11 | Accessors `getChart`/`getCandleSeries`/`getActiveSeries`/`getPanes`/`getCandles`/`getSeriesData`/`getLastBucket`/`setLastBucket` | 218–230 | public API | STAYS; `getCandleSeries`/`getCandles` **DELEGATE** |
| H12 | `applyScale` (price scale option) | 236–242 | scale | STAYS |
| H13 | `setScaleMode(mode, _autoScale)` | 246–249 | scale | STAYS |
| H14 | `setCandles(arr)` — reset HA state, **HA branch (L259–268)**, else verbatim `setData` | 253–269 | **candle write** | **MOVES** |
| H15 | `updateCandle(bar)` — `Core.upsertCandle` + **HA incremental + C1 same-bucket logic (L274–289)** | 271–290 | **candle write** | **MOVES** |
| H16 | `subscribeClick`/`subscribeCrosshairMove`/`subscribeVisibleRange` | 292–302 | host subscription seam | STAYS (R19; crosshair is host-owned) |
| H17 | `return {…}` public surface | 304–325 | API | STAYS (same keys; two delegate) |

**What MUST stay in the host:** the entire LightweightCharts *chart* lifecycle
(`createChart`/`remove`), pane/scale/`priceScale`, the `window.marketChart`
seam writes (chart/candleSeries/panes), `addSeries` + `REGISTRY`/`PANE_ORDER`,
`applyScale`/`setScaleMode`/`SCALE_MODES`, the three `subscribe*` seams,
`dataKey`/`seriesFromPayload`/`rsiValues`/`setRsi`, and the accessors.

**What MOVES:** the candle-series channel — `CANDLE_CTORS`, the candle series
+ raw `candles` array, the HA incremental state, and the two write functions
(`setCandles`/`updateCandle`).

---

## 2. Extraction candidates

### Option A — extend the pure `chart-types-core.js`
- **Verdict: REJECTED.** `chart-types-core.js` is a *pure core*: it imports
  nothing (`chart-types-core.test.js` asserts `no ESM import` / `no require`),
  has no DOM/chart-lib access, and is deterministic. The HA-live path must call
  `candleSeries.setData`/`update` and mutate `lastHa`/`prevHa`/`lastBarTime`
  across calls. A pure core cannot own either without violating its contract.
  It already owns the *math* (`heikinAshi`, `nextHeikinAshi`) — keep it there.

### Option B — new host-layer sub-module `chart-host-candles.js` (RECOMMENDED)
- A **host-layer** module (same layer as `chart-host.js`, may import cores +
  touch the chart lib passed to it). It receives the built `chart` + the `Types`
  core and owns the candle series, the `CANDLE_CTORS` map, the raw candle array
  and the HA state. It is NOT a pure core and NOT a controller.
- **Pros:** architecturally faithful (host layer owns LightweightCharts writes);
  clean interface; removes ≥26 host lines; pure core stays pure; no new layer;
  external callers and the seam unchanged; `test_import_graph_routes_resolve`
  automatically proves the new route resolves.
- **Cons:** one extra served module + one `MODULE_ALLOWLIST` entry + one
  `modulepreload` tag.
- **Effort:** Low.

**Recommendation: Option B** — `chart-host-candles.js`, a host-layer factory.

---

## 3. Interface of the extracted module

```js
// web/market/templates/market/chart-host-candles.js  (NEW, host layer)
import * as Core from "./chart-core.js";          // upsertCandle (pure)
import * as Types from "./chart-types-core.js";   // nextHeikinAshi (pure)

// Candle-series Ctor per chart type (F8). HA wraps CandlestickSeries (D2).
const CANDLE_CTORS = {
  candles: "CandlestickSeries",
  "heikin-ashi": "CandlestickSeries",
  line: "LineSeries",
  area: "AreaSeries",
};

// Factory: receives the ALREADY-CREATED chart + the resolved chartType.
// Owns: the candle series, the raw candle array, the HA incremental state.
export function createCandles(chart, chartType) {
  const ctor = LightweightCharts[CANDLE_CTORS[chartType] || CANDLE_CTORS.candles];
  let series = chart ? chart.addSeries(ctor) : null;
  let type = chartType;
  let candles = [];
  let lastHa = null, prevHa = null, lastBarTime = 0;

  function setCandles(arr) { /* candles=arr; reset HA; HA branch or setData */ }
  function updateCandle(bar) { /* Core.upsertCandle; HA branch (C1) or update */ }
  function getCandleSeries() { return series; }
  function getCandles() { return candles; }
  function remove() { series = null; candles = []; }

  return { getCandleSeries, getCandles, setCandles, updateCandle, remove };
}
```

**Where the host delegates (the only edits inside `chart-host.js`):**

| Host site | Today | After |
|---|---|---|
| `build()` candle ctor (L175–176) | `const Ctor = LightweightCharts[CANDLE_CTORS[chartType]]; candleSeries = chart.addSeries(Ctor);` | `candles = createCandles(chart, chartType); candleSeries = candles.getCandleSeries();` |
| `build()` seam (L202) | `window.marketChart.candleSeries = candleSeries;` | unchanged (still the same handle) |
| `remove()` (L208–214) | `candleSeries = null; …` | `candles.remove(); candleSeries = null; …` |
| `getCandleSeries()` (L219) | `return candleSeries;` | `return candles.getCandleSeries();` (or keep the mirrored var) |
| `getCandles()` (L222) | `return candles;` | `return candles.getCandles();` |
| `setCandles(arr)` (L253–269) | full HA body | `candles.setCandles(arr);` |
| `updateCandle(bar)` (L271–290) | full HA body | `candles.updateCandle(bar);` |

`chartType` becomes a build-time argument; the host no longer needs the
`chartType` closure variable for the write path (it still resolves the valid
type in `build` before constructing). `SCALE_MODES`/`setScaleMode`/`applyScale`
STAY in the host (scale is a price-scale option, not a candle write).

**External API is byte-identical:** `history.js` (`host.setCandles`,
`host.getCandles`), `stream.js` (`host.updateCandle`, `host.getCandles`), and
`legend.js` (`host.getCandles`) keep calling the same host methods. The raw
candle array is still returned **by reference** (history/legend read it), and
`Core.upsertCandle` still mutates that same array.

---

## 4. Size-guard change — sanctioned?

**Yes.** Two edits, both to `tests/web/test_module_size_guard.py`:

1. `ALLOWLIST = {"chart-host.js"}` → `ALLOWLIST = frozenset()` (or drop the
   entry), plus the docstring update (it currently names the exemption).
2. **The exemption-specific test must be rewritten/removed.**
   `test_allowlist_exempts_chart_host_but_not_others` asserts
   `over_ceiling({"chart-host.js": "\n"*326}) == {}`. With an empty allowlist
   this returns `{"chart-host.js": 326}` → the assertion FAILS. The test's
   purpose ("the documented exception holds") is exactly what DEBT-5 retires,
   so it must be replaced by an assertion that the allowlist is now empty /
   that no module is exempt (or folded into the negative-control test, which
   already proves a synthetic oversized module fails and is allowlist-free).

**Why this is allowed:** the issue's "no assertion edits" constraint is scoped
to the **behavior network — 138 node tests + the E2E suite**. The DEBT-3 size
guard is not part of that network; it is the *mechanism DEBT-5 is defined
against*. Removing `chart-host.js` from its exemption list IS the deliverable.
Editing its own exempt-specific assertion is required cleanup, not a
weakening of a behavior test.

---

## 5. Open questions / decisions

| # | Question | Recommendation |
|---|----------|----------------|
| Q1 | Module home: new `chart-host-candles.js` vs extend `chart-types-core.js` | **New host-layer module.** Pure core can't write. (Option A rejected.) |
| Q2 | Does `CANDLE_CTORS` move or stay? | **Moves** to the candle module (it exists only to pick the candle series ctor). |
| Q3 | Do `SCALE_MODES`/`setScaleMode`/`applyScale` stay? | **Stay in host** — scale is a `priceScale("right").applyOptions` option, not a candle write; no reason to move. |
| Q4 | ES-module serving | Add `"chart-host-candles"` to `views.MODULE_ALLOWLIST`; add a `modulepreload` line in `chart.html`. **Mandatory:** `test_import_graph_routes_resolve` derives routes from the real import graph, so the new `./chart-host-candles.js` import from `chart-host.js` will 404-test unless the allowlist gains the name. |
| Q5 | Does the seam change? | **No.** Still exactly 8 keys (`candleSeries` is written from the same handle). No 9th key, no new bus event. |
| Q6 | Does `chart-host.js` keep a `candles` variable name clash? | Host renames its candle-holding local to the module handle (`candles` → the candle-module object); the raw array now lives in the module. Verify `getCandles()` delegation keeps the by-reference array (history/legend depend on it). |
| Q7 | Is `chartType` closure var still needed in host? | Only in `build` to resolve the valid type; the write branch now lives in the module. Keep resolution in `build`, pass the resolved type in. |

---

## 6. Risks

1. **HA live drift (HIGH) — C1 fix must survive verbatim.** `updateCandle`'s
   `if (!sameBucket) prevHa = lastHa;` (advance `prevHa` ONLY on a new bucket)
   is the fix verified in `chart-scales`. It MUST move unchanged. Guarded by
   `tests/js/chart-host.test.js` (incl. the "MULTIPLE same-bucket ticks (C1
   regression)" test) and the E2E HA tests. *Mitigation:* mechanical move; run
   both suites.
2. **`build()` teardown/re-attach order (MED).** `build()` does
   `chart.remove()` → `createChart` → candle series → `applyScale()` → indicator
   series → seam. The candle-module construction must sit exactly where the
   current candle ctor lines are (after `createChart`, before `applyScale`).
   *Mitigation:* preserve statement order; E2E `build`/`switch` scenarios.
3. **Frozen 8-key seam (MED).** No new seam key; `candleSeries` keeps updating
   after rebuild. *Mitigation:* E2E `Object.keys(window.marketChart).length === 8`.
4. **Raw-candle reference identity (MED).** `history.js`/`legend.js` read
   `host.getCandles()` and rely on the SAME array that `upsertCandle` mutates
   and `setCandles` replaces. Delegation must return the module's live array by
   reference, never a copy. *Mitigation:* keep `let candles` in the module and
   return it directly.
5. **Module route missing (MED).** A missing `MODULE_ALLOWLIST` entry → import
   404 → blank chart, caught only by E2E/`test_import_graph_routes_resolve`.
   *Mitigation:* add the allowlist entry + preload in the same PR.
6. **No-deps / CSP (LOW).** No new dependency; same-origin ESM only; CSP
   `script-src 'self' https://unpkg.com` unchanged. *Mitigation:* none needed.
7. **Size-guard test rewrite (LOW).** `test_allowlist_exempts_chart_host_but_not_others`
   must be updated or it fails after the allowlist empties. *Mitigation:* Q in
   §4 — replace with an "allowlist is empty" assertion.

---

## 7. Proposed PR shape + size

**Single PR.** Behavior-equivalent move; no functional change; under the
400-line budget.

Estimated diff:
- `chart-host.js`: −≈45 host lines, +≈8 delegate lines (net ≈ −37 → ~289 lines).
- **NEW** `chart-host-candles.js`: ≈70 lines.
- `views.py`: +1 (`MODULE_ALLOWLIST`).
- `chart.html`: +1 (modulepreload).
- `test_module_size_guard.py`: allowlist emptied + exemption test rewritten (≈±12).
- Docs/ADR: `docs/architecture/chart-modules.md` module inventory + `market-chart`
  R14 spec note (archive-time delta).

Total changed ≈ 130–160 lines → **single PR**, `400-line budget risk: Low`,
`Chained PRs recommended: No`, `Decision needed before apply: No`.

---

## Affected Areas

- `web/market/templates/market/chart-host.js` — extract the candle channel; delegate.
- **NEW** `web/market/templates/market/chart-host-candles.js` — the moved code.
- `web/market/views.py` — `MODULE_ALLOWLIST += "chart-host-candles"`.
- `web/market/templates/market/chart.html` — `modulepreload` for the new module.
- `tests/web/test_module_size_guard.py` — empty `ALLOWLIST`; rewrite the
  exemption test.
- `openspec/specs/market-chart/spec.md` — R14 delta at archive (new module in
  inventory; `chart-host.js` no longer exempt).
- `docs/architecture/chart-modules.md` — inventory/route note.

Unchanged: `chart-core.js`, `chart-types-core.js`, `chart-store.js`,
`chart-bus.js`, `main.js`, every controller, `tests/js/*.test.js`,
`tests/web/test_market_e2e.py`, the 8-key seam, `src/`, `requirements.txt`, CSP,
models/migrations.

## Ready for Proposal

**YES** — the seam map is verified against real code; the extraction boundary
(host-layer `chart-host-candles.js`) is forced by the purity of
`chart-types-core.js`; the external API and 8-key seam are provably unchanged;
and the one test edit (the DEBT-3 guard's own exemption list + test) is both
required and sanctioned. The proposal MUST lock: Q1 (module home), Q4 (allowlist
+ preload), and the §4 guard-test rewrite.
