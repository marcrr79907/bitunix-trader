# market-chart Specification

## Purpose

Auth-gated market dashboard: OHLC history + overlays from Django, live candles from BitUnix's public WebSocket in the browser. Personal-first, read-only, candles ephemeral.

## Requirements

### Requirement: R1 — Read-only kline client method

`src/client.py` MUST expose `kline(symbol, interval, limit)` calling `GET /api/v1/futures/market/kline` via the public unsigned path, mapping `time` ms → UNIX seconds (int), prices to floats. Empty upstream MUST return `[]`; API failures MUST surface as `BitunixError`. MUST NOT call any order endpoint.

#### Scenario: Correct URL and params

- GIVEN a captured public GET, WHEN `kline("BTCUSDT", "1m", 100)` runs, THEN it hits `/api/v1/futures/market/kline` with `symbol`/`interval`/`limit` params, no signing

#### Scenario: Mapping ms→s and floats

- GIVEN row `{"time": 1700000000000, "open": "50000.5", "high": "51000", "low": "49000", "close": "50500"}`, WHEN mapped, THEN `{"time": 1700000000, "open": 50000.5, "high": 51000.0, "low": 49000.0, "close": 50500.0}` (int time, float prices)

#### Scenario: API error surfaces as BitunixError

- GIVEN upstream API code != 0, WHEN `kline` runs, THEN raises `BitunixError`

#### Scenario: Empty upstream returns empty list

- GIVEN upstream `data` empty, WHEN `kline` runs, THEN returns `[]` without raising

### Requirement: R2 — Auth-gated chart page

`/market/` MUST be GET-only, require login (`login_required`); anonymous MUST 302-redirect to login (pinned). Authenticated MUST render the chart-first layout with chart container.

#### Scenario: Anonymous redirected to login

- GIVEN anonymous session, WHEN GET `/market/`, THEN 302 to login

#### Scenario: Authenticated renders chart page

- GIVEN logged-in user, WHEN GET `/market/`, THEN 200 and page contains chart container

### Requirement: R3 — Kline JSON endpoint

`/market/api/kline?symbol=&interval=` MUST be GET-only, require login (anonymous → 302 to login). Success returns `{"candles": [...], "overlays": {...}}`; candles EXACTLY `{time, open, high, low, close}`, `time` UNIX-seconds int, ascending, deduplicated. Overlays are `{time, value}` lists, gaps omitted (no nulls). Invalid symbol/interval → 400 `{"error": "..."}` (generic). Empty upstream → 200 with empty arrays. Upstream network failure → 502 `{"error": "upstream"}`, never 500. MUST NOT call any order endpoint.

#### Scenario: Candles sorted and deduplicated

- GIVEN upstream rows unsorted or duplicated by `time`, WHEN it responds, THEN `candles` ascending with unique `time` values

#### Scenario: Overlay gaps omitted

- GIVEN indicators with `None` warm-up positions, WHEN it responds, THEN overlay arrays contain only `{time, value}` — no nulls

#### Scenario: Invalid interval → 400

- GIVEN `interval` outside the allowed set, WHEN GET with valid session, THEN 400 `{"error": "..."}`

#### Scenario: Invalid symbol → 400

- GIVEN a symbol the upstream rejects (code != 0), WHEN GET, THEN 400 `{"error": "..."}`

#### Scenario: Empty upstream → 200 empty

- GIVEN upstream returns no candles, WHEN GET, THEN 200 with `"candles": []` and empty overlay arrays

#### Scenario: Unauthenticated → redirect

- GIVEN anonymous session, WHEN GET `/market/api/kline`, THEN 302 to login

### Requirement: R4 — Indicators single-source

Overlay values MUST come from `src/indicators.py` server-side; indicator math MUST NOT be duplicated in JS. Payload MUST NOT contain null indicator values.

#### Scenario: SMA point count

- GIVEN N candles and SMA window w, WHEN payload builds, THEN sma overlay has exactly N−w+1 points, none null

#### Scenario: RSI bounded or omitted

- GIVEN N candles, WHEN payload builds, THEN every rsi value is within [0, 100] or the point is omitted

### Requirement: R5 — Live candles over browser WS

Page JS MUST connect to `wss://fapi.bitunix.com/public/`, subscribe `market_kline_<interval>`, update the FORMING candle in place via interval bucketing (no duplicate times), unsubscribe BEFORE subscribing on interval/symbol switch, reconnect with exponential backoff capped at a fixed maximum, resubscribing on reopen. Verified by E2E DOM assertions, not image diffs.

#### Scenario: Forming candle updates in place

- GIVEN latest candle shown, WHEN a WS push lands in the same interval bucket, THEN candle updates in place (unique times preserved)

#### Scenario: Switch unsubscribes before subscribing

- GIVEN active subscription, WHEN interval or symbol switches, THEN `unsubscribe` sent before the new `subscribe`

#### Scenario: Reconnect after drop with capped delay

- GIVEN WS drops, WHEN client reconnects, THEN delay grows exponentially up to the cap and client resubscribes after reopening

#### Scenario: E2E DOM smoke

- GIVEN logged-in browser on `/market/`, WHEN page loads, THEN global `LightweightCharts` defined, chart canvas exists, `/market/api/kline` returns JSON with `candles` key

### Requirement: R6 — Minimal CSP header

Market pages MUST carry `Content-Security-Policy` allowing `connect-src wss://fapi.bitunix.com`, script/style from the pinned CDN, and `self`. `/admin/*` and `/healthz` MUST be unaffected.

#### Scenario: Header present on market page

- GIVEN authenticated GET `/market/`, WHEN response arrives, THEN it carries CSP with wss + CDN + self allowlist

#### Scenario: Admin unaffected

- GIVEN GET on admin login page, WHEN it renders, THEN status 200, inline handlers not broken

#### Scenario: healthz unaffected

- GIVEN GET `/healthz`, WHEN it responds, THEN status 200

### Requirement: R7 — Boundary, read-only, no new runtime dependency

`src/` MUST stay framework-free (`tests/test_boundary.py` green). `/market/kline` MUST match no order-scanner forbidden fragment. `requirements.txt` MUST be unchanged — `pytest-playwright` is dev-only.

#### Scenario: Core boundary stays green

- GIVEN new client method and market app, WHEN boundary suite runs, THEN `src/` imports no framework and `web/market` → `src/` permitted

#### Scenario: Order scanner clean

- GIVEN new routes and code, WHEN order scanner runs, THEN `/market/kline` matches no forbidden fragment, no order verb reported

#### Scenario: Runtime dependencies unchanged

- GIVEN the change, WHEN `requirements.txt` inspected, THEN no runtime dependency added
