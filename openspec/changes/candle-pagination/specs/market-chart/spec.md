# Delta for market-chart

Issue #44: `/market/api/kline` gains `before` pagination and DB-first reads; the chart infinite-scrolls backward. Shape, auth, CSP, WS and `src/` boundaries unchanged.

## MODIFIED Requirements

### Requirement: R3 — Kline JSON endpoint

`/market/api/kline?symbol=&interval=[&limit][&before]` MUST be GET-only, login-required (anonymous → 302). `before` is an optional UNIX-seconds int exclusive upper bound; omitted = latest page. Response MUST be `{"candles":[...],"overlays":{...}}`, candles EXACTLY `{time,open,high,low,close}` (`quote_vol` stripped), `time` int, ascending, deduped, no nulls; overlays `{time,value}` gaps omitted. The endpoint MUST read `Candle` first (`symbol/interval/time < before ORDER BY time DESC LIMIT limit+WARMUP`) and call BitUnix ONLY when the DB lacks the range or the interval is unpersisted (`client.kline(..., end_time=...)`). Overlays MUST be computed over the warm-up window, then sliced to the page. Invalid `before`/symbol/interval → 400 `{"error":"..."}`. Empty → 200 `{"candles":[],"overlays":{"sma20":[],"ema20":[],"rsi14":[]}}`. BitUnix failure with DB rows → 200 degraded; 502 ONLY when both fail and nothing is served. MUST NOT call any order endpoint.
(Previously: single latest page, always live BitUnix; no `before`/DB-first.)

#### Scenario: Paginated page returns candles strictly older than before

- GIVEN seeded `Candle` rows and `before=1700000000`, WHEN GET with a valid session, THEN the page is the newest `limit` candles with `time < 1700000000`, ascending, same `{candles, overlays}` shape

#### Scenario: before omitted returns latest page

- GIVEN no `before` param, WHEN GET, THEN the latest page is returned (backward compatible with pre-#44 behavior)

#### Scenario: Invalid before → 400

- GIVEN `before=abc` (non-int) or non-positive, WHEN GET, THEN 400 `{"error": "..."}`

#### Scenario: Full DB page never calls BitUnix

- GIVEN the `Candle` table holds a full page for the range, WHEN GET, THEN no `client.kline` call occurs

#### Scenario: Short DB range gap-fills via BitUnix

- GIVEN the DB holds fewer rows than the page needs and older history exists upstream, WHEN GET, THEN the client is called with `end_time=(before or now)*1000` and rows are merged DB-first (DB wins on duplicate `time`)

#### Scenario: Overlay warm-up correct at page edge

- GIVEN ≥ WARMUP prior candles exist, WHEN a page is built, THEN its first candle has non-null sma20/ema20 (rsi14 where defined); at the series start genuine warm-up gaps stay omitted (no nulls)

#### Scenario: Degradation matrix

- GIVEN DB has rows + BitUnix ok, WHEN GET, THEN 200
- GIVEN DB has rows + BitUnix fails, WHEN GET, THEN 200 with the available rows (degraded), never 5xx
- GIVEN DB empty + BitUnix fails, WHEN GET, THEN 502 `{"error": "upstream"}`
- GIVEN DB empty + BitUnix ok, WHEN GET, THEN 200 with the upstream page

#### Scenario: Candles sorted and deduplicated

- GIVEN rows unsorted or duplicated by `time` (DB/upstream join at a boundary), WHEN it responds, THEN `candles` ascending with unique `time` values

#### Scenario: Overlay gaps omitted

- GIVEN indicators with `None` warm-up positions, WHEN it responds, THEN overlay arrays contain only `{time, value}` — no nulls

#### Scenario: Invalid interval → 400

- GIVEN `interval` outside the allowed set, WHEN GET with valid session, THEN 400 `{"error": "..."}`

#### Scenario: Invalid symbol → 400

- GIVEN a symbol the upstream rejects (code != 0), WHEN GET, THEN 400 `{"error": "..."}`

#### Scenario: Empty result → 200 empty

- GIVEN no candles in DB or upstream for the cursor, WHEN GET, THEN 200 with `"candles": []` and empty overlay arrays

#### Scenario: Unauthenticated → redirect

- GIVEN anonymous session, WHEN GET `/market/api/kline`, THEN 302 to login

### Requirement: R4 — Indicators single-source

Overlay values MUST come from `src/indicators.py` server-side; math MUST NOT be duplicated in JS. Per page, the server MUST fetch `limit + WARMUP (20)` candles before the page boundary, compute indicators over the full window, then slice overlays to the page. Payload MUST NOT contain null indicator values.
(Previously: single-page indicators; no warm-up window or slice.)

#### Scenario: Page-edge overlay is defined, not omitted

- GIVEN a page whose window includes ≥ WARMUP prior candles, WHEN payload builds, THEN the page's first candle HAS non-null sma20/ema20 (rsi14 where defined)

#### Scenario: Genuine series-start gap stays omitted

- GIVEN the page is at the oldest available candle, WHEN payload builds, THEN leading overlay points lacking warm-up are omitted — no nulls

#### Scenario: SMA point count

- GIVEN N candles and SMA window w in the window, WHEN payload builds, THEN sma overlay has exactly N−w+1 points, none null

#### Scenario: RSI bounded or omitted

- GIVEN N candles, WHEN payload builds, THEN every rsi value is within [0, 100] or the point is omitted

### Requirement: R7 — Boundary, read-only, no new runtime dependency

`src/` MUST stay framework-free (`tests/test_boundary.py` green). `/market/kline` MUST match no order-scanner forbidden fragment. `requirements.txt` MUST be unchanged. This change MUST add no schema field or migration; auth, CSRF, CSP and the browser WS path MUST be unchanged.
(Previously: did not pin "no schema/migration" or auth/CSRF/CSP/WS-unchanged.)

#### Scenario: No schema change or migration

- GIVEN the change, WHEN migrations are inspected, THEN no new migration or model field exists; `Candle` is read-only

#### Scenario: Auth, CSRF, CSP, WS unchanged

- GIVEN the new params and JS, WHEN exercised, THEN login/302, CSRF, the market CSP allowlist and the WS path behave as before

#### Scenario: Core boundary stays green

- GIVEN new endpoint and market code, WHEN the boundary suite runs, THEN `src/` imports no framework and `web/market` → `src/` is permitted

#### Scenario: Order scanner clean

- GIVEN new routes and code, WHEN the order scanner runs, THEN `/market/kline` matches no forbidden fragment, no order verb reported

#### Scenario: Runtime dependencies unchanged

- GIVEN the change, WHEN `requirements.txt` is inspected, THEN no runtime dependency was added

## ADDED Requirements

### Requirement: R8 — Infinite-scroll history in the chart

`chart.js` MUST detect when the visible logical range nears the left edge and fetch `before=<oldest loaded time>`; on response it MUST prepend older candles+overlays (deduped by `time`, existing newer entry wins), then preserve the viewport by shifting the logical range by the prepended count. It MUST keep a single in-flight guard (no duplicate concurrent loads) and MUST NOT clobber WS live updates. The bucket-close refetch MUST deliberately reset pagination anchors. Verified by dev-only DOM E2E assertions, not image diffs.

#### Scenario: Left-edge scroll loads older page

- GIVEN the chart has loaded a page, WHEN the visible range `from` drops below the edge threshold and more history may exist, THEN GET `...&before=<oldestTime>` is issued and returned candles are prepended

#### Scenario: Viewport preserved on prepend

- GIVEN a prepend of N older candles, WHEN data is re-set, THEN the logical range is shifted by N so the same bars remain visible (no jump)

#### Scenario: Single in-flight guard

- GIVEN a load is already in flight, WHEN more left-edge events fire, THEN no duplicate concurrent fetch occurs

#### Scenario: WS live update not clobbered

- GIVEN a forming-candle WS push arrives, WHEN the left-side prepend runs, THEN the live rightmost candle is preserved

#### Scenario: Bucket-close refetch resets anchors

- GIVEN the latest page is refetched on bucket close, WHEN it completes, THEN pagination anchors are reset so a later scroll fetches the correct older page

#### Scenario: E2E DOM smoke

- GIVEN a logged-in browser on `/market/`, WHEN the time scale is scrolled left, THEN a `before=` request is observed and the candle series grows (DOM/evaluate, no image diffs)
