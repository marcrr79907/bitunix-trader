# Design: chart-legend (issue #114, Fase F1)

## Technical Approach

Pure formatter core (`legend-core.js`) + one DI overlay controller (`controllers/legend.js`) +
one host seam (`subscribeCrosshairMove`). The legend is a **pure read-through**: it formats
server-shaped values from the v5 crosshair `param.seriesData` Map (hover) or `host.getSeriesData()`/
`getCandles()` last element (leave). No recompute, no new bus event, no 9th `window.marketChart`
key. Re-subscribe on every `chart:built` (build destroys the chart). `main.js` gains ~1 line.

## Architecture Decisions

| Decision | Choice | Alternative | Rationale |
|---|---|---|---|
| Precision source | Static frozen `DECIMALS` map in legend-core, keyed by **token** | per-series `priceFormat` in host; derive from magnitude; read DOM | Deterministic across ticks; no host/series change. |
| Re-subscribe locus | Controller subscribes to bus `chart:built`; re-binds crosshair on the new chart | edit `main.buildChart`; store chart ref in main | `chart:built` already emitted in `buildChart`; keeps `main` wiring to +1 line. |
| DOM injection | Controller injects `.chart-legend` into `#chart` | template markup in `chart.html` | Fewer files; a11y attrs live with the driver. |
| a11y `aria-live` | `role="status"`; `aria-live="off"` while hovering, `"polite"` idle after 300 ms debounce | live-announce per mousemove | Per-mousemove floods screen readers; idle-only announces the stable summary. |
| Perf | rAF-coalesced `textContent` writes on a fixed node set | `innerHTML` rebuild; write per event | fires per mousemove; fixed nodes + coalescing avoid jank. |
| dataKey in core | `lastValues` recomputes `o:/p:` key locally (2 lines) | pass host.dataKey into the core | Core stays chart-lib-free and Node-testable. |

## Data Flow

    v5 crosshair param ──▶ controller.onMove ──▶ entries[{key,value}] ──┐
    (hover)                  │                                          ├─▶ legend-core.rows ──▶ DOM (rAF)
    host.getSeriesData()/    └─(leave)──▶ legend-core.lastValues ───────┘
    getCandles() last elem
    bus chart:built ──▶ controller: host.subscribeCrosshairMove(onMove) on the NEW chart + render idle snapshot

## Interfaces / Contracts

```js
// legend-core.js — PURE: no DOM, no chart lib, no network, no globals. Never throws.
export const DECIMALS = Object.freeze({ sma:2, ema:2, bollinger:2, vwap:2, rsi:2,
  stochastic:2, atr:2, macd:4, volume:0 });          // fallback 2
export const PLACEHOLDER = "–";                       // null/undefined/NaN -> this
export function formatValue(token, value) -> string;
export function formatOhlc(candle) -> {open,high,low,close,dir}   // strings; dir:"up"|"dn"|"flat" (close vs open); null candle -> nulls + "flat"
export function rows(entries, activeSeries, candle) -> {ohlc, series: [ {token,key,place,pane,label,value} ]}
//   entries:{key:rawValue}  activeSeries: host.getActiveSeries() enriched with {params} by the controller
//   label: TOKEN uppercase + first numeric param (e.g. "SMA 20"); missing key -> PLACEHOLDER
export function lastValues(activeSeries, seriesData, candles) -> {candle, entries:[{key,value}]}
//   candle = last of candles (else null); value = last element of seriesData[dataKey(place,pane,key)]
```

```js
// chart-host.js — add, mirroring subscribeClick (null-guarded) + export in return object:
function subscribeCrosshairMove(fn) { if (chart) chart.subscribeCrosshairMove(fn); }
```

```html
<!-- controllers/legend.js injects once into #chart -->
<div class="chart-legend" role="status" aria-live="polite" aria-label="Chart legend">
  <div class="lg-ohlc num">…open… high… low… close… <span class="up|dn">±change%</span></div>
  <div class="lg-row"><span class="lg-token">SMA 20</span><span class="lg-val num">42.10</span></div>  <!-- one per active series -->
</div>
```

CSS (`theme.css`): `#chart{position:relative}`; `.chart-legend{position:absolute; top:var(--sp-2);
left:var(--sp-2); pointer-events:none; background:var(--surface); border:1px solid var(--border);
border-radius:var(--r); padding:var(--sp-1) var(--sp-2); font-family:var(--mono); font-size:var(--fs-3);
max-width:min(90%,320px); overflow:hidden; white-space:nowrap}`; `.lg-token{color:var(--muted)}`;
`.up{color:var(--up)} .dn{color:var(--dn)}`. No layout shift; never eats chart pointer events.

## File Changes

| File | Action | Description |
|---|---|---|
| `web/market/templates/market/legend-core.js` | Create | Pure formatters (`DECIMALS`/`formatValue`/`formatOhlc`/`rows`/`lastValues`). |
| `web/market/templates/market/controllers/legend.js` | Create | `createLegend({store,bus,host,config})`; overlay DOM; rAF updates; `chart:built` re-subscribe. |
| `web/market/templates/market/chart-host.js` | Modify | Add `subscribeCrosshairMove(fn)`. |
| `web/market/templates/market/main.js` | Modify | `createLegend(...)` after `createToolbar`. |
| `web/market/views.py` | Modify | `MODULE_ALLOWLIST += "legend-core"`, `CONTROLLER_ALLOWLIST += "legend"`. |
| `web/market/templates/market/chart.html` | Modify | Two `modulepreload` links. |
| `web/accounts/templates/registration/theme.css` | Modify | `#chart{position:relative}` + `.chart-legend` block. |
| `tests/js/legend-core.test.js` | Create | Formatter exactness + edge cases. |
| `tests/web/test_market_e2e.py` | Modify | Add one DOM-only legend test (no edits to existing). |

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| JS unit | `formatValue`/`formatOhlc`/`rows`/`lastValues` exactness; null/NaN/gap -> `–`; never throws | `node --test tests/js/legend-core.test.js` |
| Route | new modules served JS MIME; relative imports resolve | existing `test_import_graph_routes_resolve` (derives routes — no edit) |
| E2E | hover -> `.chart-legend` shows OHLC; leave -> last values; `Object.keys(window.marketChart).length === 8` | new `@p` test, `page.mouse.move` over `#chart`, DOM-only |

## Delivery (Feature Branch Chain — 2 slices; all PRs base on tracker `feat/chart-legend`)

| Slice | Scope | ~Lines | Rollback boundary |
|---|---|---|---|
| 1 | `legend-core.js`; host `subscribeCrosshairMove`; allowlists + preloads; `legend-core.test.js` | ~220 | revert -> no core/seam/allowlist; chart unchanged |
| 2 | `controllers/legend.js`; `main.js` wire; `theme.css`; E2E | ~205 | revert -> no overlay; chart unchanged |

### Guard / Edge Matrix

| Edge | Handling |
|---|---|
| single-source | core formats only; imports nothing; no indicator math |
| rAF / no jank | fixed nodes + `textContent`; one pending frame max |
| re-subscribe on rebuild | re-bind on every `chart:built`; old handler dies with `chart.remove()` |
| no 9th seam key | legend writes DOM only; E2E asserts 8 keys |
| a11y | `role="status"`; `aria-live` off on hover, polite idle (300 ms); signed change + tabular `.num` |
| allowlist route | `legend-core` + `legend` added; import-graph test fails loudly if missed |
| no new dep / CSP | ESM + `theme.css`, no inline, no npm; `script-src 'self'` unchanged |
| responsive | `max-width:min(90%,320px)`; verified at 375px |

## Migration / Rollout

No migration, model, flag, data, or CSP change. Per-slice `git revert`. JS is Python-coverage-invisible
(`diff-cover` Python-only) -> safety net = `node --test` + E2E.

## Open Questions

None blocking. Locks explore Q1/Q3/Q4/Q6/Q7: idle-only `aria-live`; frozen `DECIMALS`; all active
series in `getActiveSeries()` order; responsive overlay; **no** custom price/time formatters (stock v5
axis labels suffice).
