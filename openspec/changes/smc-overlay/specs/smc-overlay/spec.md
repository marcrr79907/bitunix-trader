# smc-overlay Specification

## Purpose

Read-only render layer for the frozen SMC core (Fase C1, issue #75): ONE server
endpoint runs the pure `src/smc/` chain over a candle window and returns
time-resolved records; the browser only draws them. New capability — no prior
spec. SMC analysis is **market data**, NOT user-owned: the endpoint reads candles
and computes; it is never scoped per user. Reuses the A1/A2/A3 seams
(`api_kline` candle window, `switchTo`/primitive/`window.marketChart` idioms).

**Frozen payload shape** — response body MUST be exactly this object (keys and
types fixed; no `index` field anywhere):

```json
{
  "symbol": "BTCUSDT",
  "interval": "5m",
  "swings":       [{"kind": "high|low", "time": 1700000300, "price": 50000.0, "label": "HH|HL|LH|LL|null"}],
  "structure":    [{"kind": "bos|choch", "time": 1700000600, "price": 49900.0, "direction": "bullish|bearish", "trend": "up|down"}],
  "order_blocks": [{"kind": "bullish|bearish", "time": 1700000000, "top": 50100.0, "bottom": 49800.0, "anchor_time": 1700000600}],
  "fvgs":         [{"kind": "bullish|bearish", "time": 1700000300, "top": 50050.0, "bottom": 49950.0}],
  "range":        {"high": 51000.0, "low": 49000.0, "equilibrium": 50000.0, "time": 1700000900},
  "setups":       [{"direction": "long|short", "time": 1700000600, "entry": 49900.0, "stop": 49700.0, "take_profit": 50500.0, "rr": 3.0, "score": 4}]
}
```

`range` MUST be `null` when `dealing_range` returns `None`. `label` MUST be
`null` for the first swing of each kind. `setups` is an array (≤1 record).

## Requirements

### Requirement: R1 — Endpoint contract

`GET /market/api/smc?symbol=&interval=[&limit]` MUST be GET-only and
login-required (anonymous → 302 to login). `interval` MUST be validated against
`quotes.INTERVALS` and `symbol` MUST be non-empty BEFORE any work, else
`400 {"error":"..."}`. `limit` MUST be an int in `1..200` (default `200`,
consistent with the A1/A2 clamp); invalid → 400. The endpoint MUST accept no body
and MUST have no writable/CSRF path.

#### Scenario: Anonymous redirected

- GIVEN an anonymous session
- WHEN GET `/market/api/smc`
- THEN 302 to login

#### Scenario: Invalid interval → 400

- GIVEN `interval` outside `INTERVALS`
- WHEN GET with a valid session
- THEN 400 `{"error":"..."}` and no candles/chain run

#### Scenario: Invalid limit → 400

- GIVEN `limit=0`, `limit=201`, or `limit=abc`
- WHEN GET
- THEN 400 `{"error":"..."}`

#### Scenario: Default limit is 200

- GIVEN no `limit` param
- WHEN GET
- THEN the window is the newest 200 candles

### Requirement: R2 — Candle window (DB-first, gap-fill, keeps opens)

The endpoint MUST build its window with the SAME DB-first + gap-fill seam as
`get_kline_payload` (`_db_rows` + `client.kline`, DB wins on duplicate `time`,
merged ascending) over the newest `limit` candles, and MUST keep `opens` (required
by `find_order_blocks`/`find_setups`). All six finders MUST run over ONE shared
window so every record's `index` is consistent. The endpoint MUST NOT write
`Candle` (read-only).

#### Scenario: Full DB window never calls upstream

- GIVEN the `Candle` table holds the full window
- WHEN GET
- THEN no `client.kline` call occurs and indices map into that window

#### Scenario: Short DB gap-fills DB-first

- GIVEN the DB holds fewer rows than the window and older history exists upstream
- WHEN GET
- THEN the client fills the gap and duplicate `time` keeps the DB row

### Requirement: R3 — Payload shape frozen and index→time resolved server-side

The response MUST be EXACTLY the frozen shape above. For EVERY record the server
MUST resolve `time = times[index]` and MUST NOT emit a raw bar `index`. The JS
MUST NOT receive or translate indices.

#### Scenario: No index leaks

- GIVEN any non-empty window
- WHEN the payload is built
- THEN no record contains an `index` (or `anchor`) key and every `time` is a
  member of the window's candle times

#### Scenario: OB anchor resolved to time

- GIVEN an `OrderBlock(kind, index, top, bottom, anchor)`
- WHEN serialized
- THEN `time=times[index]` and `anchor_time=times[anchor]`

#### Scenario: Range null when no range

- GIVEN `dealing_range` returns `None`
- WHEN serialized
- THEN `range` is `null`

### Requirement: R4 — Empty, short, and error degradation

The endpoint MUST mirror `api_kline` degradation and MUST never 500 on thin data.

**Edge-case matrix**

| Condition | Result |
|-----------|--------|
| fewer than 3 candles | 200, all arrays `[]`, `range:null` |
| insufficient warm-up (`< RANGE_LOOKBACK`) | 200, arrays empty or sparse; finders return `[]`/`None` |
| unknown `symbol` (upstream code != 0) with DB rows | 200 degraded over DB rows |
| unknown `symbol`, nothing served, upstream rejects | 400 `{"error":"upstream rejected"}` |
| DB empty + upstream ok | 200 with the upstream window |
| DB empty + upstream transport fails | 502 `{"error":"upstream"}` |

#### Scenario: Empty window is 200

- GIVEN no candles available
- WHEN GET
- THEN 200 with `swings/structure/order_blocks/fvgs/setups: []` and `range: null`

#### Scenario: Upstream failure with DB rows is degraded

- GIVEN DB rows and a failing upstream
- WHEN GET
- THEN 200 computed over the DB rows (never 5xx)

#### Scenario: Nothing served is 502

- GIVEN empty DB and a transport-failing upstream
- WHEN GET
- THEN 502 `{"error":"upstream"}`

### Requirement: R5 — Scoping is market-global, not per-user

SMC analysis is market data: the endpoint MUST NOT call `for_user` and MUST NOT
be scoped to the caller. Any authenticated user MUST receive the same payload for
the same `(symbol, interval, limit)`. No owned model is involved and no per-user
row is created.

#### Scenario: Two users receive identical payloads

- GIVEN users A and B authenticated
- WHEN each GETs the same `(symbol, interval, limit)`
- THEN both payloads are equal (no user-specific filtering)

#### Scenario: No owned model or write

- GIVEN the endpoint code
- WHEN inspected
- THEN it references no `for_user`, no owned model, and performs no write

### Requirement: R6 — Render contract per element type

The browser MUST render each family from the payload only:

| Family | Payload field | Render |
|--------|---------------|--------|
| Swing pivots + labels | `swings` | series primitive: zig-zag polyline, color per `kind`, `fillText(label)` at pivot (label-less first swing still draws) |
| BOS / CHoCH | `structure` | series primitive: short horizontal ray at `price`, colored by `direction`, `fillText("BOS"|"CHoCH")` |
| OB boxes | `order_blocks` | series primitive rect from `time` to `anchor_time`, `top`→`bottom`, tint by `kind` |
| FVG boxes | `fvgs` | series primitive rect spanning the middle candle, `top`→`bottom`, tint by `kind` |
| Premium / discount | `range` | full-width premium (`equilibrium..high`) + discount (`low..equilibrium`) bands + dashed equilibrium line |
| Setup markers | `setups` | `createSeriesMarkers(candleSeries, [...])` — `belowBar`(long)/`aboveBar`(short), arrow shape, text e.g. `"L 4/4"` |

All primitive draws MUST use `useMediaCoordinateSpace`, MUST null-guard every
coordinate (off-series time → skip the leg, never throw), and MUST supply
`autoscaleInfo` for full-width bands/rays. Setups MUST use the single marker
primitive with `setMarkers(...)`, recreated after `buildChart`.

#### Scenario: All six families render on boot

- GIVEN a payload with all six families populated
- WHEN the chart boots
- THEN a primitive/marker exists per family and `window.marketChart.smc` holds the payload

#### Scenario: Off-series time degrades, never throws

- GIVEN a record whose `time` is not on the time scale
- WHEN its primitive draws
- THEN that leg is skipped and no error surfaces

#### Scenario: Rebuild recreates markers

- GIVEN an attached SMC layer
- WHEN `buildChart` rebuilds the chart
- THEN primitives re-attach and the marker primitive is recreated

### Requirement: R7 — Per-element toggles are session-only

The page MUST expose one show/hide checkbox per family
(`swings|structure|order_blocks|fvg|range|setups`), all ON by default. Toggling a
family MUST re-render the SMC layer WITHOUT refetching. Toggle state MUST NOT be
persisted (no model field, no migration) — session-only.

#### Scenario: Toggle hides a family without refetch

- GIVEN the SMC layer rendered and a request count of N
- WHEN a family checkbox is unchecked
- THEN that family's primitive/markers are hidden and request count stays N

#### Scenario: State is not persisted

- GIVEN a family toggled off
- WHEN the page is reloaded
- THEN all families are ON again (no persisted state)

### Requirement: R8 — Multi-TF reload on switch

On `switchTo(symbol, interval)` the overlay MUST clear the previous key's SMC
primitives immediately (generation guard), then refetch `/market/api/smc` for the
new key and re-attach after `buildChart` + history load. The SMC fetch and the
history fetch MUST share the same `(symbol, interval, limit)` so windows coincide.
SMC analysis MUST be recomputed per `(symbol, interval)`.

#### Scenario: Switch clears then reloads

- GIVEN SMC rendered for `(BTCUSDT, 1m)`
- WHEN `switchTo("ETHUSDT", "1h")` runs
- THEN BTCUSDT primitives are cleared and the new key's payload is fetched and drawn

#### Scenario: Shared window

- GIVEN a switch
- WHEN the SMC and history requests are issued
- THEN both use the same `(symbol, interval, limit)`

### Requirement: R9 — Payload ↔ drawn equals contract

What the endpoint returns MUST equal what is drawn. `window.marketChart.smc` MUST
deep-equal the fetched payload, and the pure `smc-overlay-core.js` MUST map a
known payload to exact descriptors. Parity MUST be asserted in `node --test`
(descriptor mapping) and Playwright (seam deep-equal).

#### Scenario: Seam deep-equals fetched payload

- GIVEN a booted chart
- WHEN the SMC payload is fetched
- THEN `window.marketChart.smc` deep-equals the response body

#### Scenario: Pure mapping is deterministic

- GIVEN a known payload
- WHEN `fromApi(payload)` runs
- THEN it yields exact, byte-stable descriptors

### Requirement: R10 — Single source: JS MUST NOT recompute SMC

`src/smc/` MUST remain the sole home of SMC math. `smc-overlay-core.js` MUST only
reshape/serialize records into draw descriptors and MUST NOT recompute swings,
trend, structure, zones, range, or confluence.

#### Scenario: No recomputation in JS

- GIVEN `smc-overlay-core.js`
- WHEN inspected
- THEN it computes no swing/trend/zone/range/setup math (it only maps payload records)

### Requirement: R11 — Read-only, CSP, no new dependency

The change MUST NOT place/modify/cancel orders, MUST NOT relax R11/R14, MUST NOT
add a runtime dependency, and MUST keep `src/` framework-free (`PURE_MODULES`
unchanged). The page MUST add no inline script/handler (same-origin JS served like
`chart-core.js`); `Content-Security-Policy` MUST be unchanged. The order scanner
MUST stay clean.

#### Scenario: CSP unchanged

- GIVEN the rendered `/market/` page
- WHEN the header and templates are inspected
- THEN `Content-Security-Policy` equals the prior value and no inline script/handler exists

#### Scenario: No new dependency or src change

- GIVEN the manifest and `src/`
- WHEN scanned
- THEN `requirements.txt` is unchanged and `src/` imports no framework

#### Scenario: Order scanner clean

- GIVEN the SMC route and client code
- WHEN the order scanner runs
- THEN no order-execution verb or mutating path is matched
