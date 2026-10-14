# Proposal: chart-scales (issue #121, Fase F8 — Ola 2)

## Intent

The chart hardcodes `CandlestickSeries` and sets no price-scale options, so users
cannot pick line/area/Heikin Ashi or a log/percentage axis. F8 adds two
user-global, persisted preferences (`scale_mode`, `chart_type`) on the merged
F0–F3 layered ESM chart — no new dep, `src/` untouched, `#68` and the frozen
8-key `window.marketChart` seam held.

## Scope

**In:** pure `chart-types-core.js` (`CHART_TYPES`, `heikinAshi`, `toChartData`);
host picks the series Ctor + applies the scale mode; store gains
`scaleMode`/`chartType`; two accessible native `<select>`s in `toolbar`; new
`scale:changed` bus event (host option only); additive `ChartPreference.scale_mode`/
`chart_type` (migration `0010`) via `/market/api/preference` with partial-body PUT;
node + pytest + E2E coverage.

**Out:** a v5 HA *series* (none exists); per-`(symbol,interval)` scope; any data
rewrite for scaling; new controller; `src/`/new dep/CSP changes; a 9th
`marketChart` key.

## Capabilities

**New:** `chart-scales` — chart-type + price-scale-mode selection, HA transform, persisted user-global.
**Modified:** `market-chart` (R14 — store vocabulary gains two keys; host picks the series Ctor and applies the scale mode; HA rides the candle write path); `chart-shell` (boot reads the two new user-global fields).

## Approach

HA is not a v5 series type, so `heikinAshi()` recursively derives
`haOpen/haClose/haHigh/haLow` and feeds the existing `CandlestickSeries`. A type
switch routes through `build()`/`rebuild()` (types can't change in place;
`buildChart()` already re-attaches drawings/SMC); `toChartData()` maps
candles↔`{time,value}` for line/area. Scale is
`chart.priceScale("right").applyOptions({mode})` — no `setData` (#68), re-applied
in `build()`. HA live updates are incremental host state
(`lastHaOpen`/`lastHaClose`, reset on `setCandles`) via `update()` only.
Persistence mirrors F3: two `CharField`s defaulting `"linear"`/`"candles"`,
per-field 400 validation.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `market/chart-types-core.js` | New | Pure HA + type→data mapping |
| `market/chart-host.js` | Modified | Ctor select, scale option, HA writes |
| `market/chart-store.js` | Modified | `+scaleMode`,`+chartType` |
| `market/controllers/toolbar.js` | Modified | Two `<select>`s |
| `market/chart-bus.js` | Modified | `scale:changed` |
| `market/{views,urls}.py` | Modified | Two pref fields; `+chart-types-core` |
| `web/trading/models.py` + `migrations/0010_*` | Modified | Additive columns |
| `tests/{js,web}/*` | New/Modified | Coverage net |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| HA live recompute breaks #68 | Med | Incremental state, `update()`-only; reset on `setCandles` |
| Type switch detaches drawings/SMC | Med | Route through `rebuild()`/`buildChart()` only |
| Frozen 8-key seam broken | Low | Assert via DOM + `priceScale("right").options().mode` |
| `PriceScaleMode` enum unverified | Med | Read from served v5.2.0 bundle; use symbol, not magic number |
| Migration non-additive / patch gate | Med | Additive `0010` + `makemigrations --check`; test every new branch |

## Rollback Plan

Revert top-down: (3) drop the two pref fields, view branches, migration `0010`;
(2) restore hardcoded `CandlestickSeries`, remove scale apply + `scale:changed` +
selects + store keys; (1) delete `chart-types-core.js` + test + allowlist entry.
Slice 1 alone can't be reverted in isolation (2–3 depend on it). No data loss:
unknown pref fields are ignored by the reverted view.

## Dependencies

F0–F3 layered ESM (MERGED): allowlist, `build()`/`rebuild()` re-attach,
`ChartPreference` (`0009`) + F3 pref API. Lightweight Charts v5.2.0, Node 22,
Playwright. No new runtime dep.

## Read-Only Boundary

No order execution; no `src/` change; no new dep; CSP unchanged; no new `window`
global (8 keys); `Candle` read-only. Python changes limited to `views.py`, model
+ migration, tests.

## Delivery (Feature Branch Chain — 3 slices)

Base = tracker `feat/chart-scales`; child PRs target the tracker.
1. **Pure core** — `chart-types-core.js` + node test + allowlist: ~120 lines.
2. **Host + store + UI** — `chart-host.js` Ctor/scale/HA, `chart-store.js`, `toolbar.js`, `chart.html`, `main.js`, extended host test: ~180 lines. Depends on 1.
3. **Persistence** — model + `0010`, `views.api_preference`, API test, E2E smoke: ~150 lines. Depends on 2.

- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: High

## Success Criteria

- [ ] candlestick/line/area/heikin-ashi each route through `rebuild()`; drawings/SMC re-attach.
- [ ] linear/log/percentage via `priceScale("right").applyOptions`, **no** `setData`; `scale:changed` = host option only.
- [ ] HA matches the recursive formula in `node --test`; live push `update()`-only, state reset on `setCandles`.
- [ ] `scale_mode`/`chart_type` round-trip via partial PUT; invalid → 400, no write.
- [ ] Migration `0010` additive (`makemigrations --check` clean); patch coverage 100%.
- [ ] `marketChart` still 8 keys; no `src/` change; no new dep; CSP unchanged.
