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

`/market/api/kline?symbol=&interval=[&limit][&before][&indicators][&<param>]` MUST
be GET-only, login-required (anonymous → 302). `before` is an optional
UNIX-seconds int exclusive upper bound; omitted = latest page. `indicators` is an
optional comma-separated list of indicator tokens; omitted = default set
`{sma20, ema20, rsi14}` (backward compatible). Per-indicator params are flat query
params (e.g. `rsi_len`, `sma_len`, `bb_len`, `bb_std`, `macd_fast`, `macd_slow`,
`macd_signal`, `stoch_k`, `stoch_d`, `atr_len`); invalid values → 400. An unknown
indicator token MUST return 400 `{"error":"..."}` BEFORE the payload builds.
Response MUST be `{"candles":[...],"overlays":{...},"panes":{...}}`:
`overlays` maps a name → `[{time,value}]` on the price scale (`sma`, `ema`,
`bollinger_upper`/`_middle`/`_lower`, `vwap`); `panes` maps a pane name → an object
of series → `[{time,value}]` (`rsi`→`{rsi}`, `atr`→`{atr}`,
`macd`→`{macd,signal,histogram}`, `stochastic`→`{k,d}`, `volume`→`{volume}`).
Candles MUST be EXACTLY `{time,open,high,low,close}` (`quote_vol` stripped —
it travels in `panes.volume`, not in candles), `time` int, ascending, deduped, no
nulls; indicator arrays contain only `{time,value}` (gaps omitted). The endpoint
MUST read `Candle` first (`symbol/interval/time < before ORDER BY time DESC LIMIT
limit+warmup`) and call BitUnix ONLY when the DB lacks the range or the interval is
unpersisted (`client.kline(..., end_time=...)`). Indicators MUST be computed over
the warm-up window, then sliced to the page. The upstream BitUnix request MUST be
clamped to its 200 max; when `limit + warmup > 200` the endpoint relies on the DB
for the older warm-up rows, and if the DB lacks them page-edge indicator values MAY
be omitted (documented, not an error). Empty → 200 with empty candle and indicator
arrays. BitUnix failure with DB rows → 200 degraded; 502 ONLY when both fail and
nothing is served. MUST NOT call any order endpoint.

#### Scenario: Paginated page returns candles strictly older than before

- GIVEN seeded `Candle` rows and `before=1700000000`
- WHEN GET with a valid session
- THEN the page is the newest `limit` candles with `time < 1700000000`, ascending, same shape

#### Scenario: before omitted returns latest page

- GIVEN no `before` param
- WHEN GET
- THEN the latest page is returned (backward compatible)

#### Scenario: Invalid before → 400

- GIVEN `before=abc` (non-int) or non-positive
- WHEN GET
- THEN 400 `{"error": "..."}`

#### Scenario: Default indicator set unchanged

- GIVEN a request with no `indicators` param
- WHEN GET
- THEN `overlays` keys are exactly the default set and `panes` holds the default pane set

#### Scenario: Selected panes returned

- GIVEN `indicators=macd,rsi`
- WHEN GET
- THEN `panes.macd` has `{macd, signal, histogram}` and `panes.rsi` has `{rsi}`

#### Scenario: Invalid indicator name → 400

- GIVEN `indicators=notreal`
- WHEN GET with a valid session
- THEN 400 `{"error": "..."}` and no payload is built

#### Scenario: Candles exactly five keys, no quote_vol leak

- GIVEN any request including `indicators=volume`
- WHEN GET
- THEN every candle has exactly `{time,open,high,low,close}` and no `quote_vol` key

#### Scenario: Volume pane uses quote volume

- GIVEN `indicators=volume` and rows carrying `quote_vol`
- WHEN GET
- THEN `panes.volume.volume` values equal the rows' `quote_vol`

#### Scenario: Full DB page never calls BitUnix

- GIVEN the `Candle` table holds a full page for the range
- WHEN GET
- THEN no `client.kline` call occurs

#### Scenario: Short DB range gap-fills via BitUnix

- GIVEN the DB holds fewer rows than the page needs and older history exists upstream
- WHEN GET
- THEN the client is called with `end_time=(before or now)*1000` and rows are merged DB-first (DB wins on duplicate `time`)

#### Scenario: Upstream request clamped to 200

- GIVEN a selected set whose warm-up makes `limit + warmup > 200`
- WHEN GET
- THEN the BitUnix `limit` passed to `client.kline` is at most 200 and the DB supplies older warm-up rows

#### Scenario: Degradation matrix

- GIVEN DB has rows + BitUnix ok, WHEN GET, THEN 200
- GIVEN DB has rows + BitUnix fails, WHEN GET, THEN 200 with the available rows (degraded), never 5xx
- GIVEN DB empty + BitUnix fails, WHEN GET, THEN 502 `{"error": "upstream"}`
- GIVEN DB empty + BitUnix ok, WHEN GET, THEN 200 with the upstream page

#### Scenario: Candles sorted and deduplicated

- GIVEN rows unsorted or duplicated by `time`
- WHEN it responds
- THEN `candles` ascending with unique `time` values

#### Scenario: Indicator gaps omitted

- GIVEN indicators with `None` warm-up positions
- WHEN it responds
- THEN overlay/pane arrays contain only `{time, value}` — no nulls

#### Scenario: Invalid interval → 400

- GIVEN `interval` outside the allowed set
- WHEN GET with valid session
- THEN 400 `{"error": "..."}`

#### Scenario: Invalid symbol → 400

- GIVEN a symbol the upstream rejects (code != 0)
- WHEN GET
- THEN 400 `{"error": "..."}`

#### Scenario: Empty result → 200 empty

- GIVEN no candles in DB or upstream for the cursor
- WHEN GET
- THEN 200 with `"candles": []` and empty overlay and pane objects

#### Scenario: Unauthenticated → redirect

- GIVEN anonymous session
- WHEN GET `/market/api/kline`
- THEN 302 to login

### Requirement: R4 — Indicators single-source and derived warm-up

Indicator values MUST come from `src/indicators.py` server-side; math MUST NOT be
duplicated in JS. The warm-up window MUST be DERIVED from the selected set:
`warmup = max(20, max(first_valid_index for each requested series))` — MACD → 33,
Bollinger → 19, Stochastic → 15, RSI/ATR → 14. Per page the server MUST fetch
`limit + warmup` candles before the page boundary, compute indicators over the
full window, then slice to the page. Payload MUST NOT contain null indicator
values.

#### Scenario: Page-edge overlay is defined, not omitted

- GIVEN a page whose window includes ≥ the derived warm-up prior candles
- WHEN payload builds
- THEN the page's first candle has non-null values for the selected overlays

#### Scenario: Derived warm-up for MACD

- GIVEN `indicators=macd` and ≥ 33 prior candles available
- WHEN GET builds the payload
- THEN the MACD series has a non-null value on the first returned candle

#### Scenario: Genuine series-start gap stays omitted

- GIVEN the page is at the oldest available candle
- WHEN payload builds
- THEN leading indicator points lacking warm-up are omitted — no nulls

#### Scenario: SMA point count

- GIVEN N candles and SMA window w in the window
- WHEN payload builds
- THEN the sma overlay has exactly N−w+1 points, none null

#### Scenario: RSI bounded or omitted

- GIVEN N candles
- WHEN payload builds
- THEN every rsi value is within [0, 100] or the point is omitted

### Requirement: R5 — Live candles over browser WS

Page JS MUST connect to `wss://fapi.bitunix.com/public/`, subscribe `market_kline_<interval>`, update the FORMING candle in place via interval bucketing (no duplicate times), unsubscribe BEFORE subscribing on interval/symbol switch, reconnect with exponential backoff capped at a fixed maximum, resubscribing on reopen. Verified by dev-only E2E assertions, not image diffs. The two live-candle scenarios MUST be driven via `page.route_web_socket` (no live network/CDN); reconnect is accepted as inspection-verified (single pure capped expression). **Consistency (fix #68):** the live path MUST use a single writer (`series.update()`), MUST NOT issue a periodic full-series `setData()`, and the candle bucket timestamp MUST equal the exchange candle `time` (1w = Monday 00:00 UTC, 1M = calendar month start) — the client MUST NOT invent a divergent timeline. Bucket/ordering math MUST live in a pure, framework-free core (`chart-core.js`) exercised by `node --test`.

#### Scenario: Forming candle updates in place

- GIVEN latest candle shown
- WHEN two WS pushes in the same bucket are injected via `page.route_web_socket`
- THEN the series grows by exactly 1 and the last `time` is unchanged (bucketed in place)

#### Scenario: Switch unsubscribes before subscribing

- GIVEN active subscription
- WHEN `#interval` switches interval
- THEN parsed JSON frames show `{op:"unsubscribe", ch:"market_kline_<old>"}` strictly before `{op:"subscribe", ch:"market_kline_<new>"}`

#### Scenario: Reconnect after drop with capped delay

- GIVEN WS drops
- WHEN the client reconnects
- THEN `backoff()` is `min(1000·2^n, 60000)·(0.5..1.5)` and resubscribes on reopen; verified by inspection of `backoff`/`onclose`, MAY add a deterministic cap assertion if `backoff` is exposed on the `window.marketChart` seam; in-browser timing is NOT asserted

#### Scenario: E2E DOM smoke

- GIVEN logged-in browser on `/market/`, WHEN page loads, THEN `LightweightCharts` defined, canvas exists, `/market/api/kline` returns JSON with `candles`

### Requirement: R6 — Minimal CSP header

Market pages MUST carry `Content-Security-Policy` allowing `connect-src wss://fapi.bitunix.com`, script/style from the pinned CDN, and `self`. `/admin/*` and `/healthz` MUST be unaffected.

#### Scenario: Header present on market page

- GIVEN authenticated GET `/market/`, WHEN response arrives, THEN it carries CSP with wss + CDN + self allowlist

#### Scenario: Admin unaffected

- GIVEN GET on admin login page, WHEN it renders, THEN status 200, inline handlers not broken

#### Scenario: healthz unaffected

- GIVEN GET `/healthz`, WHEN it responds, THEN status 200

### Requirement: R7 — Boundary, read-only, no new runtime dependency

`src/` MUST stay framework-free (`tests/test_boundary.py` green). `/market/kline` MUST match no order-scanner forbidden fragment. `requirements.txt` MUST be unchanged (`pytest-playwright` is dev-only). No schema field/migration; auth, CSRF, CSP and the WS path unchanged. The "no new runtime dependency" invariant MUST be enforced by an AST guard over `web/**/*.py` + `src/**/*.py` failing when a top-level import root is outside `stdlib ∪ declared-deps ∪ local`; a requirements-sync test MUST keep manifest and guard from diverging.

#### Scenario: No schema change or migration

- GIVEN the change, WHEN migrations are inspected, THEN no new migration or model field exists; `Candle` is read-only

#### Scenario: Auth, CSRF, CSP, WS unchanged

- GIVEN the new params and JS, WHEN exercised, THEN login/302, CSRF, market CSP and the WS path behave as before

#### Scenario: Core boundary stays green

- GIVEN new client method and market app, WHEN boundary suite runs, THEN `src/` imports no framework; `web/market` → `src/` permitted

#### Scenario: Order scanner clean

- GIVEN new routes and code, WHEN order scanner runs, THEN `/market/kline` matches no forbidden fragment

#### Scenario: Guard passes on the current tree

- GIVEN the change, WHEN the dependency guard runs
- THEN it passes: stdlib, declared deps (`requests`, `rich`, `django`, `psycopg`, `dj_database_url`, `gunicorn`, `redis`, `cryptography`) and local modules (`web/` packages + `src`) are allowed; relative imports excluded

#### Scenario: Guard fails on an unknown import (negative control)

- GIVEN an injected `import pandas` in a scanned file, WHEN the guard runs, THEN it reports that file as an offender

#### Scenario: Requirements sync enforced

- GIVEN a declared dist with no import-root mapping, or a mapped root absent from the allowlist
- WHEN the sync test runs
- THEN it fails; the map (`psycopg[binary]→psycopg`, `dj-database-url→dj_database_url`, …) MUST cover every declared dist

#### Scenario: Runtime dependencies unchanged

- GIVEN the change, WHEN `requirements.txt` inspected, THEN no runtime dependency added

### Requirement: R8 — Infinite-scroll history in the chart

`chart.js` MUST detect when the visible logical range nears the left edge and fetch `before=<oldest loaded time>`; on response it MUST prepend older candles+overlays (deduped by `time`, existing newer entry wins), then preserve the viewport by shifting the logical range by the prepended count. It MUST keep a single in-flight guard (no duplicate concurrent loads) and MUST NOT clobber WS live updates. The bucket-close refetch MUST deliberately reset pagination anchors. Verified by dev-only DOM E2E assertions, not image diffs. **Consistency (fix #68):** pagination MUST use `setData` with a MERGE (never replace), so already-loaded older candles and the live tip are preserved.

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

### Requirement: R9 — manage.py coverage contract

`web/manage.py` MUST stay in coverage `omit`; its contract is the subprocess test `tests/web/test_manage_boot.py` (stronger than line coverage — dropping `omit` adds uncovered import-time lines without instrumenting the child).

#### Scenario: Documented omission

- GIVEN `pyproject.toml`, WHEN `[tool.coverage.run].omit` is read, THEN `web/manage.py` is omitted with a comment naming `tests/web/test_manage_boot.py`

#### Scenario: Boot behavior locked

- GIVEN the subprocess test, WHEN `python web/manage.py check` runs in a minimal env, THEN the bootstrap succeeds
