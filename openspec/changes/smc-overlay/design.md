# Design: smc-overlay (issue #75, Fase C1)

## Technical Approach

Read-only render layer over the frozen `src/smc/` core. One GET endpoint
(`market/api/smc`) reuses the `api_kline` candle seam, runs the frozen chain over
ONE window, resolves every bar `index` → candle `time`, and serializes the frozen
payload. The browser mirrors A3: pure `smc-overlay-core.js` (UMD, `node --test`)
maps payload → draw descriptors; `chart.js` draws v5 primitives + one
`createSeriesMarkers` handle; a `.smc` toggle fieldset re-renders without refetch.

    boot:  layout ─→ buildChart ─→ GET smc ─→ attach primitives+markers ─→ connect ─→ history
    switch: bump smcGen ─→ clear ─→ layout ─→ buildChart ─→ GET smc(new key) ─→ attach ─→ history
    toggle: read .smc-toggle ─→ requestUpdate() + setMarkers() (NO refetch)

## Architecture Decisions

| Decision | Choice + rationale |
|---|---|
| Candle seam | **Extract `_fetch_window(client, symbol, interval, want, before=None)`** from `get_kline_payload`; both kline and SMC call it. Reuse over duplication; pure extraction, existing 52 kline tests are the net. |
| SMC window | **`want = limit` (no warm-up)**, so indices align exactly with the chart's `candles[-limit:]`. Kline keeps `limit+warmup`. |
| Shared window | Adapter adds `HISTORY_LIMIT = 200` to BOTH `klineUrl()` and `smcUrl()` (R8); kline's implicit 100 is replaced by the explicit 200 (matches Q7). |
| `swings` source | **`find_swings` (all pivots)** with `label` looked up from `label_swings` (`null` when absent). `label_swings` omits first-of-kind entirely — using it directly would drop pivots R6 requires drawn. |
| index→time | Server-only `time = times[index]`; out-of-range index skipped defensively. No `index`/`anchor` ever emitted. |
| Render shape | **ONE canvas primitive** renders all enabled canvas families (swings/structure/OB/FVG/range); **ONE** `createSeriesMarkers` handle for setups. Fewest attach/detach cycles; recreated in `buildChart`. |
| Toggles | `state.smc` from `.smc-toggle`; change → descriptor filter + `requestUpdate()` + `setMarkers()`. Session-only, no model. |

## Data Flow

    api_smc ─→ get_smc_payload ─→ _fetch_window ─→ find_swings/label_swings
             ─→ find_structure ─→ find_order_blocks ─→ find_fvg
             ─→ dealing_range ─→ find_setups ─→ serialize(index→time) ─→ JSON
    JSON ─→ SmcOverlayCore.fromApi/descriptors ─→ chart.js primitive + markers

## Interfaces / Contracts

```python
# web/market/quotes.py
def _fetch_window(client, symbol, interval, want, before=None) -> list[dict]
def get_smc_payload(client, symbol, interval, limit) -> dict     # raises like get_kline_payload
def _serialize_smc(rows, swings, labeled, structure, obs, fvgs, range_, setups) -> dict
```

```js
// smc-overlay-core.js — FROZEN API (UMD; no DOM/chart/network)
window.SmcOverlayCore = {
  FAMILIES,                 // ["swings","structure","order_blocks","fvg","range","setups"]
  COLORS,                   // per kind/direction palette
  fromApi(payload),         // normalized {symbol,interval,swings,structure,orderBlocks,fvgs,range,setups}; never throws
  visibleFamilies(toggles), // enabled families; empty/absent toggles => all ON
  descriptors(payload, map),// {per family: draw specs} from {x(time),y(price)}; null-guards off-series
  setupMarkers(payload),    // createSeriesMarkers marker array
  counts(payload),          // {family: drawn-record count} (parity)
};
```

Seam: `window.marketChart.smc` = fetched payload; `window.marketChart.smcToggles`.

## File Changes

| File | Action | Description |
|---|---|---|
| `web/market/quotes.py` | Modify | `_fetch_window` extract; `get_smc_payload` + `_serialize_smc` |
| `web/market/views.py` | Modify | `api_smc` (GET-only); `smc_overlay_core_js` |
| `web/market/urls.py` | Modify | `market/api/smc`; `market/smc-overlay-core.js` |
| `web/market/templates/market/smc-overlay-core.js` | Create | pure mapping (frozen API) |
| `web/market/templates/market/chart.html` | Modify | `.smc` fieldset + core `<script>` |
| `web/market/templates/market/chart.js` | Modify | fetch, primitive, markers, toggles, `smcGen`, seams |
| `tests/js/smc-overlay-core.test.js` | Create | descriptors, toggle filter, parity |
| `tests/web/test_market_api.py` | Modify | endpoint contract + index→time |
| `tests/web/test_market_ux.py` | Modify | core JS served |
| `tests/web/test_market_e2e.py` | Modify | boot/toggle/switch + seam deep-equal |

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit (PY) | index→time, no-index, OB anchor, range null, empty/short, degradation | `get_smc_payload` with `StubClient` |
| Endpoint | anon→302, 400s, limit clamp/default 200, shape | `test_market_api.py` |
| JS | deterministic descriptors, toggle filter, parity counts, off-series null | `tests/js/smc-overlay-core.test.js` |
| E2E | all six render on boot, toggle no-refetch, switch clears+reloads, `smc` deep-equals response | `test_market_e2e.py` |

## Guard / Edge Matrix

| Edge | Handling |
|---|---|
| single-source (JS recompute) | core only reshapes (R10); node test + spec scenario |
| index→time alignment | server resolves; SMC `want==limit==HISTORY_LIMIT`; JS null-guards |
| markers teardown | marker handle recreated in `buildChart` (A3 `attachAllDrawings` precedent) |
| CSP | same-origin core view; no inline script/handler |
| read-only | no order verb, no `Candle` write, no `for_user` (R5/R11) |
| no new dep / `src/` | `requirements.txt`, `PURE_MODULES` unchanged |
| payload==drawn | node descriptors + E2E `window.marketChart.smc` deep-equal |

## Delivery (Feature Branch Chain — base = tracker)

1. **Slice 1 — endpoint** (Python): `_fetch_window`, `get_smc_payload`,
   `_serialize_smc`, `api_smc`, route, `test_market_api.py`. ~380 lines. Rollback:
   revert the view/route/payload helpers; no JS touched.
2. **Slice 2 — core + render**: `smc-overlay-core.js` + node test, `.smc`
   fieldset, core view/route, `chart.js` hooks/seams. ~520 lines. Rollback:
   revert core + chart hooks → chart falls back to A3.
3. **Slice 3 — E2E + audit**: `test_market_e2e.py` + `/impeccable`. ~170 lines.
   Rollback: revert E2E additions.

Targets the SAME tracker branch; each child PR bases on the previous slice.

## Migration / Rollout

No migration, no model, no flag. Session-only toggles; `src/`, CSP,
`requirements.txt` unchanged.

## Open Questions

None blocking. Explore decisions Q1–Q12 locked by the delta spec.
