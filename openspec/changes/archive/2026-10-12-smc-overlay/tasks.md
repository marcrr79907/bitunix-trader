# Tasks: smc-overlay (issue #75, Fase C1)

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

All slice PRs base on the tracker `feat/smc-overlay`; merge each slice into the
tracker before branching the next. Base boundaries: PR1 base = tracker; PR2
base = PR1 branch; PR3 base = PR2 branch.

## Guard/Edge Matrix

- [ ] **single-source**: no SMC math in JS — `smc-overlay-core.js` only reshapes (`fromApi`/`descriptors`); `src/smc/*` untouched; node test + R10 scenario.
- [ ] **index→time alignment**: server resolves `time=times[index]`; no `index`/`anchor` key leaks; SMC `want==limit`; both fetches use the same `(symbol,interval,limit)`; JS null-guards every off-series coordinate.
- [ ] **markers teardown**: one `createSeriesMarkers` handle; recreated in `buildChart`; `switchTo` clears + bumps `smcGen` immediately (no leak/stale draw).
- [ ] **payload↔drawn equals**: `window.marketChart.smc` deep-equals the fetched body; node descriptors are byte-stable.
- [ ] **CSP/no-inline**: `smc-overlay-core.js` served same-origin via view; no inline script/handler; CSP unchanged.
- [ ] **read-only / no new dep**: no order verb, no `Candle` write, no `for_user`; `requirements.txt` + `PURE_MODULES` unchanged; order scanner clean.
- [ ] **`_fetch_window` no-regression**: existing 52 kline tests + `api_kline` behavior unchanged after extraction.
- [ ] **degradation**: empty/short → 200 empty arrays + `range:null`; upstream fail w/ DB rows → 200; nothing served → 502.
- [ ] patch 100% Python; `node --test` green; `pytest` + ruff + `makemigrations --check` green.

## Slice 1 — Endpoint (PR1, Python, patch-100)

Base `feat/smc-overlay` (tracker); branch `feat/smc-overlay-endpoint`; deps none. Rollback: revert view/route/`get_smc_payload`/`_serialize_smc` + endpoint tests; no JS touched. ~380 lines.

- [ ] 1.1 **RED** `tests/web/test_market_api.py` (SMC block): anon→302; missing symbol / interval∉`INTERVALS` / `limit` 0,201,`abc` → 400; default `limit`=200; shape `{symbol,interval,swings,structure,order_blocks,fvgs,range,setups}`. Files: `test_market_api.py`. Acceptance: all cases fail pre-1.3.
- [ ] 1.2 **RED** same file, mapping/degradation: index→time (`time=times[index]`, `anchor_time=times[anchor]`), no `index`/`anchor` key leaks, `range:null`, `<3` candles→200 empty, DB rows+upstream fail→200 degraded, empty DB+transport fail→502. Acceptance: red.
- [ ] 1.3 **GREEN** `web/market/quotes.py`: extract `_fetch_window(client, symbol, interval, want, before=None) -> list[dict]` from `get_kline_payload` (DB-first + gap-fill, DB wins, keeps `open`); `get_kline_payload` calls it (`want=limit+warmup`); add `get_smc_payload(client, symbol, interval, limit)` (`want=limit`, no warm-up) + pure `_serialize_smc(...)` mapping `index→time`. Acceptance: 1.1/1.2 green; kline tests stay green.
- [ ] 1.4 **GREEN** run frozen chain once: `find_swings`+`label_swings` (label `null` for first-of-kind), `find_structure`, `find_order_blocks`, `find_fvg`, `dealing_range`, `find_setups` over the ONE window; empty/short degrade to empty lists. Files: `quotes.py`. Acceptance: 1.2 green.
- [ ] 1.5 **GREEN** `web/market/views.py`: `api_smc` `@login_required @require_http_methods(["GET"])`, validate before work, map `BitunixError`→400 / `RequestException`→502; `web/market/urls.py`: `market/api/smc` (`market_api_smc`). Acceptance: routes resolve; 1.1 green.
- [ ] 1.6 **REFACTOR** ruff clean; patch 100% on new `quotes.py`/`views.py` lines. Acceptance: Slice 1 suite green.

## Slice 2 — Pure core + render (PR2)

Base: PR1 branch; deps Slice 1. Rollback: delete `smc-overlay-core.js` + node test; revert fieldset + core view/route + `chart.js` hooks → chart falls back to A3. ~520 lines.

- [ ] 2.1 **RED** `tests/js/smc-overlay-core.test.js` (`node --test`): `FAMILIES`, `COLORS`, `fromApi` normalize/reject-unknown/never-throw, `visibleFamilies` (absent→all ON), `descriptors` exact per-family draw specs, off-series `time`→skipped leg (no throw), `setupMarkers`, `counts` parity. Acceptance: fails pre-2.2.
- [ ] 2.2 **GREEN** `web/market/templates/market/smc-overlay-core.js` (NEW UMD, mirror `drawing-core.js`): frozen API `{FAMILIES, COLORS, fromApi, visibleFamilies, descriptors, setupMarkers, counts}` — reshape only, null-guard, no chart/DOM/network, no SMC math. Acceptance: 2.1 green.
- [ ] 2.3 **GREEN** `web/market/views.py` `smc_overlay_core_js` (mirror `drawing_core_js`, same-origin, `text/javascript`) + `web/market/urls.py` `market/smc-overlay-core.js`. Acceptance: core served.
- [ ] 2.4 **GREEN** `web/market/templates/market/chart.html`: `<script src="{% url 'market_smc_overlay_core_js' %}">` + `<fieldset class="smc" aria-labelledby="smc-heading">` one `.smc-toggle` checkbox per family, all `checked`. Acceptance: no inline handler; CSP-safe.
- [ ] 2.5 **GREEN** `chart.js`: `smcUrl()` (`symbol/interval/limit=HISTORY_LIMIT=200`) + `loadSmc()` (own `smcGen` guard); `state.smc` from `.smc-toggle`; ONE canvas primitive (swings line+labels, BOS/CHoCH rays, OB/FVG rects, premium/discount full-width bands + equilibrium line, `autoscaleInfo`, `useMediaCoordinateSpace`, null-guard); ONE `createSeriesMarkers` for setups (belowBar long/aboveBar short), recreated in `buildChart`; toggle → `requestUpdate()`+`setMarkers()` no refetch; hook `boot`/`switchTo` (clear then reload after build); seam `window.marketChart.smc` / `.smcToggles`. Acceptance: node + manual smoke.
- [ ] 2.6 **GREEN** `tests/web/test_market_ux.py`: core JS served same-origin; `/market/` CSP unchanged; no inline script/handler. Acceptance: green.
- [ ] 2.7 **REFACTOR** no console errors; JS outside patch gate → all pure mapping in core + node test. Acceptance: Slice 2 suite green.

## Slice 3 — E2E + UI audit (PR3)

Base: PR2 branch; deps Slice 2. Rollback: revert `test_market_e2e.py` additions + audit edits. ~170 lines.

- [ ] 3.1 **RED** `tests/web/test_market_e2e.py`: boot renders all six families (`window.marketChart.smc` populated, primitive/markers present). Acceptance: red.
- [ ] 3.2 **RED** same file: toggle hides a family with request count unchanged (no refetch); `switchTo` clears previous key then reloads new; `window.marketChart.smc` deep-equals fetched response body. Acceptance: red.
- [ ] 3.3 **GREEN** fix `chart.js` seam/teardown until 3.1/3.2 green; DOM/network assertions only, no image diffs, no console errors. Acceptance: green.
- [ ] 3.4 **AUDIT** `/impeccable` UI audit of the SMC overlay (fieldset, toggles, band/box/marker legibility); apply findings. Acceptance: audit notes addressed.

## Phase 4 — Verification

- [ ] 4.1 `pytest` green; patch 100%; `node --test "tests/js/**/*.test.js"` green; ruff clean; `makemigrations --check` green.
- [ ] 4.2 Order scanner clean; CSP + `requirements.txt` unchanged; `src/` framework-free (`PURE_MODULES` unchanged).
- [ ] 4.3 `_fetch_window` extraction: full existing kline suite green (no regression).

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | Slice1 ~380, Slice2 ~520, Slice3 ~170 → ~1000–1040 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 (endpoint) → PR2 (core+render) → PR3 (E2E+audit) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Each slice is autonomous with its own verification and trivial rollback; slice PRs base on the tracker `feat/smc-overlay` and each child on the previous slice (retarget/rebase if a child diff shows prior slices).
