# Delta for market-chart

Issue #75 (Fase C1): the chart gains a read-only SMC overlay. A new requirement
**R12** covers the `/market/api/smc` endpoint contract plus the v5 render /
toggle / switch behavior. Existing requirements (R1–R11: kline shape,
single-source math, live stream, CSP, boundary, pagination, layout, drawings)
stay in force and unmodified.

## ADDED Requirements

### Requirement: R12 — SMC overlay endpoint and render contract

`/market/api/smc?symbol=&interval=[&limit]` MUST be GET-only and login-required
(anonymous → 302), validate `symbol`/`interval` against `quotes.INTERVALS` and
`limit` int `1..200` (default 200, A1/A2 clamp) BEFORE any work (invalid → 400
`{"error":"..."}`), then build the candle window with the SAME DB-first +
gap-fill seam as `api_kline` (DB wins on duplicate `time`, `opens` retained) and
run the frozen `src/smc/` chain ONCE over that single window. The response MUST be
exactly `{symbol, interval, swings, structure, order_blocks, fvgs, range, setups}`
with **server-resolved `time`** (`time = times[index]`; no bar `index` leaked),
`range` `null` when no dealing range exists. Empty/short window → 200 with empty
arrays + `range:null`; upstream failure with DB rows → 200 degraded; nothing
served → 502 (mirror `api_kline`). SMC is market data, NOT user-owned — the
endpoint MUST NOT call `for_user` and MUST NOT write. The market page MUST render
all six families via the already-loaded Lightweight Charts v5.2.0 series primitive
(swings line+labels, BOS/CHoCH rays, OB/FVG rects, premium/discount full-width
bands) and `createSeriesMarkers` for setups, null-guarding every off-series
coordinate and recreating the marker primitive after `buildChart`; MUST expose one
show/hide toggle per family, **session-only** (no persistence, no migration),
re-rendering without refetch; MUST reload the overlay on
`switchTo(symbol, interval)` clearing the previous key's primitives and sharing
the fetch `(symbol, interval, limit)` with the history window; and MUST expose
`window.marketChart.smc` deep-equal to the fetched payload (payload↔drawn parity,
asserted in `node --test` and Playwright). The JS MUST NOT recompute SMC math
(`src/smc/` stays the sole home). MUST NOT introduce inline script/handlers or a
runtime dependency; CSP MUST be unchanged and the read-only boundary preserved.

#### Scenario: Endpoint returns the frozen, time-resolved payload

- GIVEN an authenticated user and a candle window for `(symbol, interval)`
- WHEN GET `/market/api/smc?symbol=BTCUSDT&interval=1m`
- THEN 200 with exactly `{symbol, interval, swings, structure, order_blocks, fvgs, range, setups}`, every record carrying `time` and no raw `index`

#### Scenario: Anonymous → redirect, invalid params → 400

- GIVEN anonymous, WHEN GET, THEN 302 to login
- GIVEN an invalid `interval` or out-of-range `limit`, WHEN GET, THEN 400 `{"error":"..."}` before any chain runs

#### Scenario: Degradation matrix

- GIVEN DB rows + upstream ok, WHEN GET, THEN 200
- GIVEN DB rows + upstream fails, WHEN GET, THEN 200 degraded (never 5xx)
- GIVEN empty window, WHEN GET, THEN 200 with empty arrays and `range:null`
- GIVEN nothing served + upstream transport fails, WHEN GET, THEN 502 `{"error":"upstream"}`

#### Scenario: Six families render and reload per switch

- GIVEN a populated payload
- WHEN the chart boots or `switchTo("ETHUSDT","1h")` runs
- THEN all six families render, the previous key's primitives are cleared, and `window.marketChart.smc` holds the payload

#### Scenario: Toggles are session-only

- GIVEN rendered overlays
- WHEN a family checkbox is unchecked
- THEN that family hides without a new fetch; a reload shows all families ON again

#### Scenario: Payload equals drawn

- GIVEN a booted chart
- WHEN the SMC payload is fetched
- THEN `window.marketChart.smc` deep-equals the response body

#### Scenario: Market page stays CSP-clean and boundary-safe

- GIVEN the rendered `/market/` page
- WHEN the header, templates, manifest and `src/` are inspected
- THEN `Content-Security-Policy` is unchanged, no inline script/handler exists, no runtime dependency was added, and the order scanner is clean
