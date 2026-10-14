# Exploration: chart-scales (issue #121, Fase F8 — Ola 2)

## Executive Summary

F8 adds **two user-global, persisted preferences** on top of the MERGED
F0/F1/F2/F3 layered ESM chart: a **price-scale mode** (linear/log/percentage,
plus autoScale) and a **chart type** (candles/line/area/Heikin Ashi).

Three load-bearing findings, all verified against the current tree and the v5.2.0
API:

1. **Heikin Ashi is NOT a v5 series type.** v5 offers exactly six series:
   `Area`, `Bar`, `Baseline`, `Candlestick`, `Histogram`, `Line`. There is no
   `HeikinAshiSeries`. Heikin Ashi MUST be a **deterministic OHLC→HA transform in
   a pure core** (`chart-types-core.js`) feeding the existing `CandlestickSeries`.
   Line/Area/Baseline ARE real series types — they can be created directly, but
   a series **cannot change type in place** (`addSeries` docs: "a series cannot be
   transferred from one type to another"), so a chart-type switch is a rebuild.

2. **Scale mode is a price-scale OPTION, not a data rewrite.** The v5
   `chart.priceScale('right').applyOptions({ mode })` (or
   `chart.applyOptions({ rightPriceScale: { mode } })`) changes linear↔log↔%
   without touching candle data — so #68 single-write-path is preserved: a scale
   change is `applyOptions`, never `setData`.

3. **`ChartPreference` is the correct home and the migration is additive.** The
   model already exists (`user` OneToOne + `last_interval`, migration `0009`).
   Adding two columns (`scale_mode`, `chart_type`) → migration `0010`, no new
   model, mirroring the F3 preference pattern exactly.

The chart type IS currently hardcoded: `chart-host.js:146` builds
`LightweightCharts.CandlestickSeries` unconditionally, and `build()` sets NO
price-scale options today.

---

## Current State

### Chart construction (`chart-host.js`)

```js
function build(state) {
  const el = document.getElementById("chart");
  if (chart) chart.remove();
  chart = LightweightCharts.createChart(el, {
    autoSize: true,
    timeScale: { timeVisible: true },
  });
  candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries); // L146 — HARDCODED
  activeSeries = [];
  // ... overlay series (paneIndex 0) + pane series (paneIndex i+1) via addSeries
  // writes window.marketChart.{chart,candleSeries,panes}
  return { chart, candleSeries, activeSeries };
}
```

- **No price-scale options are set anywhere** (grep: zero `priceScale`/`mode`/
  `autoScale` in the tree). No `priceFormat` is set on the candle series either
  (only per-indicator `precision` via `applyOptions`).
- The candle series is the **price-scale owner** (default right scale, paneIndex 0).
- Overlays/pane series are independent `addSeries(LineSeries|HistogramSeries, ...,
  paneIndex)` calls — they do NOT depend on the candle series type. **They stay
  unchanged across chart types.**
- `build()` is a **full teardown + recreate**: `chart.remove()` then
  `createChart`. `main.js buildChart()` re-attaches drawings + SMC primitives and
  re-subscribes click/visible-range after every build (drawings/SMC live on the
  **candleSeries** primitive layer via `candleSeries.attachPrimitive`).

### Data write path (#68)

- `host.setCandles(arr)` → `candleSeries.setData(candles)` — the ONLY history/config write.
- `host.updateCandle(bar)` → `Core.upsertCandle(candles, bar)` + `candleSeries.update(bar)` — the ONLY live write.
- `history.js applyHistory` calls `host.setCandles(payload.candles.slice())`; the live `stream.js onPush` builds a raw OHLC bar and calls `host.updateCandle(bar)`.
- E2E spy `test_ws_stream_never_calls_setdata` guards this; 15+ E2E reads of
  `window.marketChart.candleSeries.data()` depend on it.

### Preference persistence (F3 pattern)

- `ChartPreference(UserOwnedModel)`: `user` OneToOne(`related_name="chart_preference"`), `last_interval` CharField(max_length=8, default "1m"), `updated_at`. Migration `0009` (latest existing).
- `GET/PUT /market/api/preference` (`views.api_preference`): GET → `{interval, exists}` (never 404, default "1m"); PUT validates `interval in INTERVALS` → 400 else, `for_user(request.user).update_or_create(user=..., defaults={"last_interval": interval})`.
- `main.js`: `loadPreference()` reads `interval` before first build, falls back "1m"; `savePreference(interval)` debounced PUT (`config.saveDelay`=500ms), silent on failure.

### The store

`chart-store.js` `STORE_KEYS = ["symbol","interval","indicators","params","styles","smc","tool"]`. Any other key in a patch is silently dropped. Adding `scaleMode`/`chartType` requires extending `STORE_KEYS`.

### Seams (frozen)

- `window.marketChart` — **8 keys** (`chart, candleSeries, panes, ready, drawings, smc, smcCounts, smcToggles`). Adding a key would break "8 keys" invariants; verify the exact E2E assertion before touching.
- `window.SmcOverlayCore`.
- Module allowlist in `views.MODULE_ALLOWLIST`: `chart-core, drawing-core, smc-overlay-core, legend-core, indicator-settings-core, chart-store, chart-bus, chart-host, main`. A new `chart-types-core` MUST be added here (and `ControllerAllowlist` if a controller is added).

---

## Affected Areas

- `web/market/templates/market/chart-host.js` — candle series construction (L146); add chart-type Ctor selection + scale-mode apply; new `setScaleMode`/re-apply on build; HA-aware `setCandles`/`updateCandle`.
- `web/market/templates/market/chart-types-core.js` — **NEW** pure core (HA transform + type→data mapping).
- `web/market/templates/market/chart-store.js` — add `scaleMode`, `chartType` to `STORE_KEYS`.
- `web/market/templates/market/controllers/` — a small UI controller (extend `toolbar.js` OR new `scales.js`) owning the scale/type controls.
- `web/market/templates/market/chart.html` — controls markup + modulepreload for the new core/controller.
- `web/market/templates/market/main.js` — wire the new controls; boot reads `scale_mode`/`chart_type` from the preference; on change emit a bus command; chart-type → rebuild, scale-mode → host option.
- `web/market/{views,urls}.py` — `api_preference` extended for the two new fields; module allowlist `+chart-types-core`.
- `web/trading/models.py` + `migrations/0010_*` — `scale_mode`, `chart_type` columns (additive).
- `web/market/templates/market/chart.js` — no change expected (no new URL).
- `tests/js/chart-types-core.test.js` — **NEW** (HA + mapping).
- `tests/js/chart-host.test.js` — extend the stub (`AreaSeries`/`LineSeries`/`CandlestickSeries` + `priceScale()` on the chart stub) + type/scale assertions.
- `tests/web/test_market_api.py` — preference round-trip for the two new fields; invalid values → 400.
- `tests/web/test_market_e2e.py` — DOM/computed-style assertions (scale mode via `chart.priceScale('right').options().mode`; chart type via `candleSeries` existence + a DOM control value); HA must be node-tested (transform) + an E2E smoke.
- `openspec/specs/*` — `chart-config` (extend R1/R2/R5) or a new `chart-scales` domain; `market-chart` host layer.
- `docs/architecture/chart-modules.md` — inventory row for `chart-types-core`.

---

## Approaches

### 1. Heikin Ashi: transform core vs. attempt a series type

| Approach | Pros | Cons | Complexity |
|---|---|---|---|
| **A. OHLC→HA in `chart-types-core.js`, feed `CandlestickSeries`** (recommended) | Only v5-correct option; deterministic + node-testable; no dep; reuse existing candle write path | Must handle live incremental HA (recursive `haOpen`) | Med |
| B. Assume a `HeikinAshiSeries` exists | n/a | **Does not exist in v5** — invented API | — |

### 2. Chart type: single rebuild path vs. per-type special-casing

| Approach | Pros | Cons | Complexity |
|---|---|---|---|
| **A. All type switches go through `build()` (rebuild + re-attach), type→Ctor/data mapping in the core** (recommended) | One code path; drawings/SMC re-attach already proven; series type can't change in place anyway | Rebuild cost on switch (rare user action) | Med |
| B. Add/remove series in place | n/a | v5 forbids type transfer; would duplicate series ownership logic | High |

### 3. Scale mode: price-scale option vs. data rewrite

| Approach | Pros | Cons | Complexity |
|---|---|---|---|
| **A. `chart.priceScale('right').applyOptions({ mode, autoScale })`** (recommended) | No data rewrite → #68 preserved; instant; v5-native | Must re-apply on rebuild (chart is recreated) | Low |
| B. Rewrite values into a new price scale | Violates #68; wrong | — | — |

### 4. Persistence: two columns vs. JSON `prefs`

| Approach | Pros | Cons | Complexity |
|---|---|---|---|
| **A. `scale_mode` + `chart_type` CharFields (additive migration 0010)** (recommended) | Same shape as `last_interval`; per-field validation in the view (mirrors `INTERVALS`); MECE; typed | One migration | Low |
| B. A JSON `prefs` field | One column | Unvalidated blob; new pattern; no precedent | Low-Med |

### 5. HA live update: incremental vs. full recompute

| Approach | Pros | Cons | Complexity |
|---|---|---|---|
| **A. Incremental HA (host carries `lastHaOpen`/`lastHaClose`; `updateCandle` transforms the forming bar)** (recommended) | O(1); keeps `update()`-only write path (#68) | Host must reset HA state on `setCandles`/switch | Med |
| B. Recomputed full `setData` on each push | Simple | **Violates #68** (live `setData`); E2E spy fails | — |

---

## Recommendation

- **`chart-types-core.js`** (pure, no imports): export a frozen `CHART_TYPES`
  (`["candles","line","area","heikin-ashi"]`), `isLineLike(type)`,
  `heikinAshi(candles) -> candles`, and `toChartData(type, candles) -> data` where:
  - candles/heikin-ashi → `[{time,open,high,low,close}]`
  - line/area → `[{time,value}]` (value = close)
  HA formulas (exact, first-bar special case):
  - `haClose = (o+h+l+c)/4`
  - `haOpen = i===0 ? (o+c)/2 : (prevHaOpen + prevHaClose)/2`
  - `haHigh = max(h, haOpen, haClose)`
  - `haLow  = min(l, haOpen, haClose)`
  Round nothing (server already shapes floats); preserve `time`.
- **`chart-host.js`**: `build(state)` picks the Ctor from `state.chartType`
  (candles/ha → `CandlestickSeries`, line → `LineSeries`, area → `AreaSeries`) and
  applies the scale mode after construction; expose `setScaleMode(mode,
  autoScale)` (chart-level `priceScale('right').applyOptions`). `setCandles`/`updateCandle`
  route the raw candle through `toChartData(state.chartType, ...)`; carry HA
  incremental state (`lastHaOpen`/`lastHaClose`) reset on `setCandles`.
- **`chart-store.js`**: `STORE_KEYS += "scaleMode","chartType"`; defaults
  `"linear"`/`"candles"`.
- **UI**: two native `<select>`s in the panel (near Interval), CSP-safe, labelled
  (`aria-label`), following the existing interval-select pattern (a hidden select
  is NOT required here — no E2E dependency on these controls). Recommendation:
  **`toolbar.js`** already owns interval+chips; adding the two selects there keeps
  the diff in one controller (lazy) — a new `scales.js` is justified only if
  `toolbar.js` exceeds the ~300-line ceiling (it is at 88).
- **Bus**: a new event, e.g. `scale:changed` / `charttype:changed`, is unnecessary —
  reuse `config:changed` semantics? No: `config:changed` carries `{symbol,interval}`
  and triggers a full `switchTo`. Use **`indicator:changed`** (→ `rebuild()`) for
  chart type, and a **new lightweight `scale:changed`** (host option only, NO
  rebuild, NO `fetchHistory`). This is the single smallest new bus event and it
  precisely encodes "no data rewrite".
- **Persistence**: extend `ChartPreference` with `scale_mode`
  (default `"linear"`, validated against the scale vocabulary) + `chart_type`
  (default `"candles"`); migration `0010`. `api_preference` GET returns both
  (with defaults on a miss); PUT accepts partial bodies (only the keys present)
  so `last_interval` and the two new fields save independently, each validated →
  400 before write. `main.js loadPreference()` returns all three; `savePreference`
  sends the changed key.

---

## Risks

- **live HA recompute**: HA is recursive (`haOpen` depends on the previous HA bar).
  A naive full `setData` on each push breaks #68. Incremental state in the host is
  required; reset it on `setCandles` and on switch.
- **rebuild on chart-type change**: `build()` recreates the chart; drawings/SMC
  primitives are attached to `candleSeries`. The existing `buildChart()` re-attach
  (`drawings.attachAllDrawings()` + `smc.attachSmcLayer()`) already covers this —
  the type change MUST route through `rebuild()`/`buildChart()`, never a partial
  rebuild, or drawings/SMC silently detach.
- **frozen seam**: `window.marketChart` is "8 keys". Do NOT add `chartType`/`scaleMode`
  to it. Assert type/scale via the DOM control value and
  `chart.priceScale('right').options().mode`. Verify the E2E assertion that counts
  keys before writing any test.
- **hardcoded CandlestickSeries**: L146 is THE change point; every caller uses
  `host.getCandleSeries()` and `candleSeries.data()`. A non-OHLC series (line/area)
  has `.data()` as `{time,value}` — E2E reads that only for the default candle type,
  so E2E stays green as long as the default is candles and tests don't switch type.
- **PriceScaleMode enum values** (`Normal=0, Logarithmic=1, Percentage=2`) could not
  be read from local typings (LWC is a CDN global, not `node_modules`). MUST be
  confirmed against the served `lightweight-charts@5.2.0` bundle at implementation
  time; set via the `LightweightCharts.PriceScaleMode` symbol, not a magic number.
- **patch coverage 100%** (Python-only gate): the new model fields, migration, and
  the extended `api_preference` branches (GET-with/without row, PUT valid/invalid
  per field, partial body) need tests or the gate fails.
- **no-deps / CSP**: pure core + native selects only; no inline handler; CDN
  unchanged.
- **`autoScale`**: v5 `PriceScaleOptions.autoScale` exists but the issue's
  "auto-escala" toggle may be redundant with the default (autoScale defaults true).
  Scope it as an explicit boolean only if the issue demands a manual toggle.
- **indicator/SMC values stay on real OHLC**: they are computed server-side and
  rendered on their own series — HA affects the candle series only. Confirm the
  spec states this so F8 does not imply re-deriving indicators from HA.

---

## Ready for Proposal

**Yes.** Verified: v5 has no Heikin Ashi series (transform core required);
scale mode is a price-scale option (no data rewrite); `ChartPreference` + additive
migration `0010` is the correct home; chart-type switch routes through the
existing rebuild/re-attach path. One decision to pin in the proposal: the exact
bus event for a scale change (recommend new `scale:changed`, host-option only) and
whether "auto-escala" is an explicit user toggle or left at the v5 default.
The orchestrator should tell the user F8 is feasible as a single change with a
pure core, a host/UI slice, and a persistence slice.

---

## Proposed PR Shape

Honest size estimate:

| Slice | Content | ~Lines (add+del) |
|---|---|---|
| 1 — pure core | `chart-types-core.js` + `chart-types-core.test.js` + allowlist entry | ~120 |
| 2 — host + store + UI | `chart-host.js` (Ctor/scale/HA), `chart-store.js`, `toolbar.js`, `chart.html`, `main.js` wiring, extend `chart-host.test.js` | ~180 |
| 3 — persistence | model + migration `0010`, `views.api_preference`, `test_market_api.py`, E2E smoke | ~150 |
| 4 — specs/docs | delta specs + `chart-modules.md` | ~80 |

**Total ≈ 450–550 changed lines → exceeds the 400-line review budget.**

Recommendation: **chained PRs (3 slices)**, not a single PR:
1. `chart-types-core` (pure core + node tests) — self-contained, no behavior change until wired.
2. host + store + UI (type/scale live, in-session) — depends on slice 1.
3. persistence (model/migration/view + tests) — depends on slice 2.

Slices are strictly ordered (each builds on the previous), each independently
verifiable (`node --test` for 1; E2E for 2; `pytest` for 3). If the delivery
strategy resolves to `single-pr` or `exception-ok`, it is deliverable in one PR
but with a real reviewer-load cost.

---

## Decisions resolved (for the proposal)

- **ChartPreference shape**: two `CharField`s (`scale_mode` default `"linear"`,
  `chart_type` default `"candles"`), migration `0010`, per-field view validation.
  (`last_interval` stays column #1.)
- **Persistence granularity**: user-global (same home/scope as `last_interval`),
  NOT per-`(symbol, interval)`.
- **Scale change = price-scale option** (`priceScale('right').applyOptions`),
  never a data write; re-applied inside `build()` after `createChart`.
- **Chart-type change = config rebuild** (→ `rebuild()`), preserving drawings/SMC
  re-attach.
- **HA live update = incremental** host state, `update()`-only.
