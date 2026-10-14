# Design: chart-scales (issue #121, Fase F8 — Ola 2)

## Technical Approach

Thread chart type + price-scale mode through the **existing** seams, never a new
one. A pure `chart-types-core.js` owns the HA transform and type→data mapping; the
host's **single** construction site (`chart-host.js`) picks the v5 series Ctor from
`state.chartType` and re-applies the scale in `build()`; a **scale** change is an
`applyOptions` option (no `setData` → #68 held) on a new `scale:changed` event,
while a **type** change reuses the existing `indicator:changed`→`rebuild()` path
(v5 series cannot change type in place). Two additive `ChartPreference` columns +
partial-body PUT carry persistence, mirroring F3.

## Architecture Decisions

| # | Decision | Choice | Alternatives | Rationale |
|---|---|---|---|---|
| D1 | Core API names | Follow the **delta spec** (`CHART_TYPES, SCALE_MODES, isLineLike, heikinAshi, toChartData`); add `isValidType`/`isValidScale` + `nextHeikinAshi` as the minimal helpers CS4/CS5 need | prompt's `TYPES`/`nextHeikinAshi`-only | Spec is ratified; `nextHeikinAshi` centralizes the recursive live step (host stays thin); `TYPES` realized as `CHART_TYPES`. |
| D2 | Type→series | HA wraps the transform over `CandlestickSeries`; line/area are real Ctors | invented `HeikinAshiSeries` | v5 has exactly six series — no HA type (explore F1). |
| D3 | Scale mode | `chart.priceScale("right").applyOptions({mode: LightweightCharts.PriceScaleMode.X})`; map `linear→Normal, log→Logarithmic, percentage→Percentage` | data rewrite | No `setData` → #68; re-applied in `build()`. Symbol, never a magic number. |
| D4 | Bus events | New `scale:changed` (`{mode}`, host option only); type reuses `indicator:changed` | one event for both | Spec R20 allows exactly one new event; type must rebuild. |
| D5 | HA live | Host carries `lastHaOpen/lastHaClose`; `nextHeikinAshi(prevHa,bar)` transforms each push via `update()` only, reset on `setCandles` | full recompute `setData` | Recursive HA; full `setData` breaks #68 (E2E spy). |
| D6 | UI home | Two native `<select>`s in `controllers/toolbar.js` (88 lines) | new controller | Spec R26: no new controller; toolbar already owns interval controls. |
| D7 | Persistence | Two additive `CharField`s + migration `0010`; partial PUT with per-field 400 | JSON `prefs` blob | Same shape as `last_interval`; typed + MECE. |
| D8 | Control options | `toolbar.js` imports `SCALE_MODES`/`CHART_TYPES` and populates empty markup selects | duplicate options in HTML | One source of truth; import-graph test forces the allowlist entry. |

## Frozen Core API — `chart-types-core.js` (pure, imports nothing)

```js
export const CHART_TYPES = Object.freeze(["candles","line","area","heikin-ashi"]);
export const SCALE_MODES = Object.freeze(["linear","log","percentage"]);
export function isLineLike(type)             // "line"|"area"
export function isValidType(type)            // CHART_TYPES.includes(type)
export function isValidScale(mode)           // SCALE_MODES.includes(mode)
export function heikinAshi(candles)          // -> [{time,open,high,low,close}] (HA values)
export function nextHeikinAshi(prevHa, bar)  // prevHa={haOpen,haClose}|null -> one HA candle
export function toChartData(type, candles)   // candles->OHLC; heikin-ashi->HA; line/area->[{time,value:c}]
```

**HA formulas (exact, round nothing, preserve `time`):** `haClose=(o+h+l+c)/4`;
`haOpen = i===0 ? (o+c)/2 : (prevHaOpen+prevHaClose)/2` (first bar and `prevHa===null`
both take the first-bar branch); `haHigh=max(h,haOpen,haClose)`; `haLow=min(l,haOpen,haClose)`.
Never throws: unknown type → candle mapping; empty/malformed → `[]`.

## Data Flow

    scale <select> ──"scale:changed"{mode}──▶ main ──▶ host.setScaleMode(mode)   (option only, no rebuild)
                                            └──▶ store.set({scaleMode}) ─▶ savePref({scale_mode})
    type  <select> ──store.set({chartType}) + "indicator:changed"──▶ main.rebuild()
                        └─ buildChart(): host.build(state) picks Ctor ─▶ drawings.attachAllDrawings()+smc.attachSmcLayer()
                        └─ history.fetchHistory() ─▶ host.setCandles() (HA/line transform; #68)
    live push ─▶ host.updateCandle(bar) ─▶ toChartData/nextHeikinAshi ─▶ candleSeries.update()  (#68)
    boot: loadPreference() -> {interval,scaleMode,chartType}; fallback linear/candles

## File Changes

| File | Action | Description |
|---|---|---|
| `market/chart-types-core.js` | Create | Pure HA + type→data mapping. |
| `market/chart-host.js` | Modify | Ctor select from `state.chartType`; `setScaleMode`; re-apply scale in `build`; HA write path + state. |
| `market/chart-store.js` | Modify | `STORE_KEYS` +`scaleMode`,`chartType` (7→9). |
| `market/chart-bus.js` | Modify | `EVENTS.scaleChanged = "scale:changed"`. |
| `market/main.js` | Modify | seed keys; `loadPreference` returns all 3; `scale:changed` subscriber; `savePreference` per changed key. |
| `market/controllers/toolbar.js` | Modify | two native selects; options from core; emit events; `setScaleMode`/`setChartType` reflect. |
| `market/chart.html` | Modify | two labelled empty `<select>`s near Interval + core modulepreload. |
| `market/views.py` | Modify | `MODULE_ALLOWLIST += "chart-types-core"`. |
| `market/quotes.py` | Modify | `SCALE_MODES`/`CHART_TYPES` server vocabularies. |
| `trading/models.py` + `migrations/0010_*` | Modify | `scale_mode`/`chart_type` `CharField(max_length=16)`. |
| `docs/architecture/chart-modules.md` | Modify | core inventory row. |
| `tests/js/chart-types-core.test.js` | Create | HA exactness + mapping + edge cases. |
| `tests/js/chart-host.test.js` | Modify | stub `AreaSeries`/`LineSeries` + `priceScale()`; Ctor/scale/HA asserts. |
| `tests/js/chart-store.test.js` | Modify | 9-key assertion. |
| `tests/web/test_market_api.py` | Modify | 4-key GET; partial PUT; per-field 400. **Existing pref GET/round-trip asserts gain 2 keys (spec-sanctioned).** |
| `tests/web/test_market_e2e.py` | Modify | scale→`options().mode`; type→series data shape; reload persists; HA smoke. |
| `tests/web/test_market_ux.py` | Modify | explicit `chart-types-core` served assertion. |

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit (node) | HA exactness (bars 0/1, empty, single, 2-bar chain), mapping, unknown no-throw, `nextHeikinAshi` state chain | `node --test tests/js/chart-types-core.test.js` |
| Unit (node) | Ctor-per-type, `setScaleMode` option-only (no setData/update), scale re-applied on build, HA live `update()`-only | `chart-host.test.js` stub |
| Unit (node) | `STORE_KEYS`=9 | `chart-store.test.js` |
| Integration (pytest) | 4-key GET default/round-trip; partial PUT; invalid scale/type/interval → 400 no-write; A≠B | `test_market_api.py` (covers new Python → 100% patch) |
| E2E | scale select → `priceScale("right").options().mode`; type select → candle series data shape; reload persists; 8-key seam; HA smoke | Playwright DOM/options only |

## Migration / Rollout — Feature Branch Chain (3 slices, base tracker `feat/chart-scales`)

| Slice | Scope | ~Lines | Dependency / rollback |
|---|---|---|---|
| 1 | core + node test + `MODULE_ALLOWLIST` + doc row | ~120 | Autonomous (node green; chart unchanged). Revert → no core/allowlist. |
| 2 | host (Ctor/scale/HA), store, bus, toolbar, `chart.html`, `main.js`, host/store tests | ~180 | Depends on 1. Revert → hardcoded candles, no controls; Slice 1 inert. |
| 3 | model + `0010`, `quotes.py` vocab, `views.api_preference`, api/ux/e2e tests | ~150 | Depends on 2. Revert → no persistence; defaults hold, unknown fields ignored. |

### Guard / Edge Matrix

| Edge | Handling |
|---|---|
| HA live #68 | `lastHaOpen/lastHaClose` reset on `setCandles`; `update()`-only; E2E `setData` spy untouched |
| type-switch rebuild | route through `rebuild()`→`buildChart()`; `attachAllDrawings()`+`attachSmcLayer()` re-attach |
| no data rewrite on scale | `applyOptions` only; test asserts no `setData`/`update` |
| 8-key seam | no new `window.marketChart` key; assert via select value + `options().mode` |
| migration additive | two `CharField`s w/ defaults; `makemigrations --check` |
| vocab validation | JS `isValidType/isValidScale`; Python `CHART_TYPES/SCALE_MODES`; per-field 400 |
| no-new-dep / CSP | pure core + native selects; `requirements.txt` + CSP unchanged |
| unknown type/scale | degrade to candles/linear, never throw |

## Open Questions

None blocking. Locks the prompt-vs-spec naming (D1) in favor of the ratified delta
spec; `autoScale` stays at the v5 default (no explicit toggle — issue does not
require one).
