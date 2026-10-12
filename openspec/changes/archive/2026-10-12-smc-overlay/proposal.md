# Proposal: smc-overlay (Fase C1, issue #75)

## Intent

B1/B2 froze a pure SMC core (`src/smc/`) that computes swings, BOS/CHoCH,
order blocks, FVG, dealing range and setups — but nothing renders it. C1 is the
**read-only render layer**: one server endpoint runs the frozen chain over a
candle window and returns time-resolved records; the browser only draws them.

## Scope

### In Scope
- `GET /market/api/smc?symbol=&interval=[&limit]` → `{symbol, interval, swings,
  structure, order_blocks, fvgs, range, setups}` with **server-resolved
  `time`** (no bar `index` in the payload).
- Pure `smc-overlay-core.js` (UMD, `node --test`) mapping payload → draw
  descriptors; `chart.js` renders v5.2.0 series primitives +
  `createSeriesMarkers` for setups.
- Per-element **session-only** show/hide toggles (`<fieldset class="smc">`).
- `window.marketChart.smc` test seam; E2E + `/impeccable` audit.

### Out of Scope
- EQH/EQL and sweeps render (not in issue #75's list). Alerts (D), analytics (E),
  toggle persistence, SMC overlay on paginated older bars, endpoint caching,
  any `src/` change, migration, model, new dependency, order surface.

## Capabilities

### New Capabilities
- `smc-overlay`: read-only SMC analysis endpoint + pure JS overlay render layer.

### Modified Capabilities
- `market-chart`: new R12 — SMC endpoint contract + render/toggle/switch behavior.

## Approach

Reuse the exact A3 seams. **Endpoint**: mirror `api_kline` — `@login_required`,
GET-only, validate `symbol`/`interval ∈ quotes.INTERVALS`, `limit` int `1..200`
(default 200, A1/A2 clamp); build the window with the same DB-first + gap-fill
seam (`_db_rows` + `client.kline`, DB wins on dup `time`) keeping `opens`;
run the frozen chain once, then map `index → times[index]` server-side and
serialize. Empty/short → 200 empty arrays + `range:null`; upstream fail with DB
rows → 200 degraded; nothing → 502 (mirror `api_kline`). **Single-source**: the
JS never recomputes — `src/smc/` stays the sole math home. **Render**: one
primitive per family (swings line+labels, BOS/CHoCH rays, OB/FVG rects,
premium/discount full-width bands) via `useMediaCoordinateSpace`, null-guarding
every off-series coordinate; setups via `createSeriesMarkers`. **Toggles**:
`state.smc`, re-render only (no refetch), `smcGen` guard cleared in `switchTo`.

**Locked explore decisions**: Q1 payload shape; Q2 payload==drawn (node +
Playwright deep-equal on `window.marketChart.smc`); Q3 no EQH/EQL/sweeps; Q4
session-only toggles; Q5 setups as markers; Q6 two bands + equilibrium line;
Q7 `limit` 200 clamp, same window as history; Q8 no cache; Q9 degradation matrix;
Q10 `label:null` for first swing; Q11 OB box `time`→`anchor_time`; Q12 full-width
bands.

## Why Now

A-series + B1/B2 are frozen and merged; C1 is the named next phase and the
prerequisite for D/E. The math is pure and already tested — C1 is wiring, not
new domain logic.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/market/quotes.py` | Modified | `get_smc_payload` + serializer (index→time) |
| `web/market/views.py` | Modified | `api_smc` + `smc_overlay_core_js` |
| `web/market/urls.py` | Modified | `/market/api/smc`, core JS route |
| `web/market/templates/market/chart.js` | Modified | fetch, primitives, markers, toggles, seam |
| `web/market/templates/market/chart.html` | Modified | SMC fieldset + core script |
| `web/market/templates/market/smc-overlay-core.js` | New | pure mapping |
| `tests/js/smc-overlay-core.test.js` | New | pure mapping |
| `tests/web/test_market_{api,ux,e2e}.py` | Modified | contract + render + equality |

No `src/` change, no migration, no new dependency.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Index→time misalignment (off-series → no draw) | High | server resolves `time` from the SAME window; both fetches share `(symbol,interval,limit)`; JS null-guards; node+E2E equality |
| JS outside the Python patch gate | Med | all mapping in `smc-overlay-core.js` + `node --test`; adapter covered by E2E |
| Single-source drift (JS recomputes) | Med | spec scenario forbids recomputation; core only reshapes |
| Rebuild teardown drops markers | Med | recreate primitives + `createSeriesMarkers` after `buildChart` (A3 `attachAllDrawings` precedent) |
| CSP / dependency | Low | canvas primitives + same-origin JS; CSP + `requirements.txt` unchanged |

## Rollback Plan

Per slice. **Slice 1**: revert `api_smc` view + route + `get_smc_payload` +
serializer + endpoint tests — no other surface touched. **Slice 2**: revert
`smc-overlay-core.js` + fieldset + core view/route + `chart.js` hooks — the
chart falls back to A3 behavior with no SMC layer. **Slice 3**: revert
`tests/web/test_market_e2e.py` additions + audit edits. No data, migration,
config or CSP change anywhere → nothing irreversible.

## Read-Only Boundary

The endpoint executes NO order surface, holds no owned model, and performs NO
`Candle` write (read-only DB-first fetch). The change MUST NOT place/modify/
cancel orders, MUST NOT relax R11/R14, MUST NOT add a runtime dependency, and
MUST keep `src/` framework-free (`PURE_MODULES` unchanged). The order scanner
MUST stay clean; the JS MUST NOT recompute SMC math.

## Dependencies

- B1/B2 frozen (`src/smc/*` shapes, read-only consume).
- A2/A3 patterns: `api_kline` candle seam, `switchTo`/primitive/seam idioms.
- Lightweight Charts v5.2.0 (pinned CDN; `createSeriesMarkers` present).
- Existing `node --test` (CI job `js-core`) + Playwright. No new runtime dep.

## Delivery (Feature Branch Chain — 3 slices)

Base = tracker branch; each child PR targets the immediate previous slice.

1. **Slice 1 — endpoint** (Python, patch-100): `get_smc_payload` + serializer +
   `api_smc` + route + `test_market_api.py` contract (anon→302, 400s, empty→200,
   degradation, index→time, payload shape). ~380 lines.
2. **Slice 2 — pure core + render**: `smc-overlay-core.js` + `node --test`,
   fieldset + core view/route, `chart.js` rendering/toggles/seam. ~520 lines.
3. **Slice 3 — E2E + audit**: Playwright (boot/toggle/switch/payload==drawn) +
   `/impeccable` UI audit. ~170 lines.

- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: High

## Success Criteria

- [ ] Endpoint returns the frozen payload with server-resolved `time`; no `index` leaked; empty→200, degradation matrix mirrors `api_kline`.
- [ ] Chart renders all six families on boot and on `switchTo`; toggles hide/show per family without refetch.
- [ ] `window.marketChart.smc` deep-equals the fetched payload (node + E2E).
- [ ] No `src/` change, no migration, no new dependency; CSP unchanged.
- [ ] `pytest` green; `node --test` green; patch gate 100%; ruff clean; order scanner clean.
