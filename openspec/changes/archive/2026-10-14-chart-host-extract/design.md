# Design: chart-host-extract (issue #146, DEBT-5)

## Technical Approach

Mechanical, behavior-equivalent extraction. The candle channel leaves
`chart-host.js` (326 → ~289 lines) and lands in a NEW **host-layer** sub-module
`chart-host-candles.js` (~70 lines). The host keeps the LightweightCharts *chart*
lifecycle, panes/scale/`priceScale`, the `window.marketChart` seam writes,
`addSeries`/`REGISTRY`/`PANE_ORDER`, the `subscribe*` seams and the accessors;
it delegates only the candle series construction, the two write paths, the two
accessors and candle teardown. External callers (`history.js`, `stream.js`,
`legend.js`) and the frozen 8-key seam are byte-identical. No runtime dep, no CSP
change, no behavior assertion touched (138 node + E2E green).

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|---|---|---|---|
| Module home | New host-layer `chart-host-candles.js` | extend pure `chart-types-core.js` | The HA-live path calls `series.setData`/`update` and mutates `lastHa`/`prevHa` across calls. `chart-types-core.test.js` asserts it imports nothing and is deterministic; it cannot own writes or state. It keeps the *math* (`heikinAshi`/`nextHeikinAshi`). |
| `CANDLE_CTORS` | Moves to the new module | stays in host | It exists solely to pick the candle series ctor — its only consumer moves. |
| `SCALE_MODES`/`applyScale`/`setScaleMode` | Stay in host | move | Scale is a `priceScale("right").applyOptions` option, not a candle write. |
| `chartType` closure in host | Dropped; resolved to a build-local `type` | keep closure var | After the move the host only resolves the valid type in `build` and passes it in; no other host site reads it. |
| Seam | Unchanged, exactly 8 keys | 9th key / new bus event | `window.marketChart.candleSeries` keeps the same handle returned by the module. |

## File Changes

| File | Action | Description |
|---|---|---|
| `web/market/templates/market/chart-host-candles.js` | Create | Host-layer candle factory `createCandles(chart, chartType)`. |
| `web/market/templates/market/chart-host.js` | Modify | Delete moved blocks; delegate ctor/writes/accessors/teardown. |
| `web/market/views.py` | Modify | `MODULE_ALLOWLIST += "chart-host-candles"`. |
| `web/market/templates/market/chart.html` | Modify | `modulepreload` for the new module. |
| `tests/web/test_module_size_guard.py` | Modify | Empty `ALLOWLIST`; rewrite the exemption test. |
| `docs/architecture/chart-modules.md` | Modify | Inventory + route note (archive-time delta). |
| `openspec/specs/market-chart/spec.md` | Modify | R14 delta at archive (already drafted in the change specs). |

## Interfaces / Contracts

```js
// web/market/templates/market/chart-host-candles.js  (NEW, host layer)
import * as Core from "./chart-core.js";          // upsertCandle (pure)
import * as Types from "./chart-types-core.js";   // heikinAshi / nextHeikinAshi (pure)

const CANDLE_CTORS = {
  candles: "CandlestickSeries",
  "heikin-ashi": "CandlestickSeries",
  line: "LineSeries",
  area: "AreaSeries",
};

export function createCandles(chart, chartType) {
  const ctor = LightweightCharts[CANDLE_CTORS[chartType] || CANDLE_CTORS.candles];
  let series = chart ? chart.addSeries(ctor) : null;
  const type = chartType;
  let candles = [];
  let lastHa = null, prevHa = null, lastBarTime = 0;

  function setCandles(arr) {
    candles = arr;
    prevHa = null;
    lastHa = null;
    lastBarTime = 0;
    if (!series) return;
    if (type === "heikin-ashi") {
      const out = Types.heikinAshi(candles);
      series.setData(out);
      const n = out.length;
      lastHa = n ? { haOpen: out[n - 1].open, haClose: out[n - 1].close } : null;
      prevHa = n > 1 ? { haOpen: out[n - 2].open, haClose: out[n - 2].close } : null;
      lastBarTime = n ? out[n - 1].time : 0;
    } else {
      series.setData(candles);
    }
  }

  function updateCandle(bar) {
    Core.upsertCandle(candles, bar);
    if (!series) return;
    if (type === "heikin-ashi") {
      const sameBucket = bar.time === lastBarTime;
      const base = sameBucket ? prevHa : lastHa;
      const ha = Types.nextHeikinAshi(base, bar);
      series.update(ha);
      if (!sameBucket) prevHa = lastHa;   // C1: advance prevHa ONLY on a bar close
      lastHa = { haOpen: ha.open, haClose: ha.close };
      lastBarTime = bar.time;
    } else {
      series.update(bar);                  // the ONLY live candle write (#68)
    }
  }

  function getCandleSeries() { return series; }
  function getCandles() { return candles; }
  function remove() { series = null; candles = []; }

  return { getCandleSeries, getCandles, setCandles, updateCandle, remove };
}
```

**Frozen module API**: `createCandles(chart, chartType) → {getCandleSeries,
getCandles, setCandles, updateCandle, remove}`. `getCandleSeries`/`getCandles`
return the module's live references (never copies).

### Delegation map (`chart-host.js`)

| Host site | Today | After |
|---|---|---|
| `build()` ctor (L175–176) | `const Ctor = LightweightCharts[CANDLE_CTORS[chartType]]; candleSeries = chart.addSeries(Ctor);` | `candles = createCandles(chart, chartType); candleSeries = candles.getCandleSeries();` (same position: after `createChart`, before `applyScale`) |
| `build()` seam (L202) | `window.marketChart.candleSeries = candleSeries;` | unchanged — same handle |
| `remove()` (L208–214) | `candleSeries = null;` | `candles.remove(); candleSeries = null;` |
| `getCandleSeries()` | `return candleSeries;` | `return candles.getCandleSeries();` |
| `getCandles()` | `return candles;` | `return candles.getCandles();` |
| `setCandles(arr)` | full HA body | `candles.setCandles(arr);` |
| `updateCandle(bar)` | full HA body | `candles.updateCandle(bar);` |

**Deleted from host**: `CANDLE_CTORS` (L60–65), the candle `addSeries` ctor lines
(L175–176), HA state vars `lastHa`/`prevHa`/`lastBarTime` (L87–89), the
`candles` array var (L80), and the two full write bodies (L253–290).
`chart-host.js` keeps a `candles` binding holding the **module handle**; the raw
array now lives inside the module. `setChartType` (toolbar) → `rebuild()` →
`buildChart()` re-creates the candle channel via `createCandles`.

**Candle-series identity**: the module is the single owner of `series` and
`candles`. `build()` reads `candles.getCandleSeries()` **once** into the host
`candleSeries` local and writes that same reference to the seam; the rest of the
app (history/legend/stream/the seam) reads that identical reference. No copy, no
re-wrap.

## Data Flow

    chart.html ──modulepreload──▶ chart-host-candles.js   (route /market/chart-host-candles.js)
    main.buildChart ──host.build(state)──▶ createCandles(chart, chartType)
                                   │
    history.setCandles ──▶ host.setCandles ──▶ module.setCandles ──▶ series.setData
    stream.updateCandle ──▶ host.updateCandle ──▶ module.updateCandle ──▶ Core.upsertCandle + series.update
    module.getCandleSeries/getCandles ──(same refs)──▶ host ──▶ window.marketChart.candleSeries / history / legend

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| JS unit | HA live/history, Ctor pick, scale, style | `tests/js/chart-host.test.js` **unchanged** — its `withChartStub` global `LightweightCharts` is read at call time by the module too, so the delegated host passes every HA test (incl. the C1 same-bucket regression). Kept on the host because they now exercise the delegation seam end-to-end (stronger than a module-local test). No assertion edit. |
| Size guard | R14 | Rewrite `test_allowlist_exempts_chart_host_but_not_others` → `test_no_module_is_exempt_and_chart_host_is_within_ceiling`: (1) `over_ceiling({"chart-host.js": "\n"*326}) == {"chart-host.js": 326}` (no exemption leaks); (2) the real `chart-host.js` is `<= CEILING`; (3) a synthetic non-allowlisted >300 module fails. Empty `ALLOWLIST`; docstring updated. |
| UX (PY) | route 200 + JS MIME | `test_import_graph_routes_resolve` derives routes from the real import graph — the new `./chart-host-candles.js` edge fails unless the allowlist gains the name, so it proves serving automatically. |
| E2E | seam, #68, boot/switch, HA | Unchanged — `Object.keys(window.marketChart).length === 8`, the `setData` spy, HA scenarios. |
| No-dep / CSP | — | Same-origin ESM only; `script-src 'self' https://unpkg.com` unchanged. |

## Guard / Edge Matrix

| Edge | Handling |
|---|---|
| C1 same-bucket HA | `if (!sameBucket) prevHa = lastHa;` moves verbatim; node C1 regression + E2E HA pass. |
| #68 single-write-path | `series.setData` only in `setCandles` / build; `series.update` only in `updateCandle`; E2E spy unchanged. |
| 8-key seam | No new key; `candleSeries` re-written from the module handle after each rebuild. |
| Raw-candle identity | Module holds `let candles`, returns it directly; `upsertCandle` mutates that same array. |
| `remove()` disposes | `candles.remove()` nulls the series and empties the array. |
| Empty allowlist | Guard passes with no exemption; oversize fails. |
| No new dep / CSP | No dependency added; CSP unchanged; route resolves via allowlist + preload. |
| Build order | `createCandles` sits exactly where today's ctor lines are (after `createChart`, before `applyScale`). |

## Migration / Rollout

No migration, model, flag, or CSP change. Single PR (~130–160 lines). Rollback:
`git revert` restores inline `chart-host.js`, removes the module, reverts the
allowlist/preload/guard edits.

## Open Questions

None blocking.
