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

Page JS MUST connect to `wss://fapi.bitunix.com/public/`, subscribe `market_kline_<interval>`, update the FORMING candle in place via interval bucketing (no duplicate times), unsubscribe BEFORE subscribing on interval/symbol switch, reconnect with exponential backoff capped at a fixed maximum, resubscribing on reopen. Verified by dev-only E2E assertions, not image diffs. The two live-candle scenarios MUST be driven via `page.route_web_socket` (no live network/CDN); reconnect is accepted as inspection-verified (single pure capped expression). **Consistency (fix #68):** the live path MUST use a single writer (`series.update()`), MUST NOT issue a periodic full-series `setData()`, and the candle bucket timestamp MUST equal the exchange candle `time` (1w = Monday 00:00 UTC, 1M = calendar month start) — the client MUST NOT invent a divergent timeline. Bucket/ordering math MUST live in a pure, framework-free core (`chart-core.js`) exercised by `node --test`. **Frame-channel guard (#150):** each push frame MUST be applied ONLY when its channel identity `frame.ch` equals the currently subscribed channel. The active subscription record `sub.interval` MUST be authoritative for BOTH the channel comparison and the bucket computation in `onPush` — NOT `state.interval`, which is mutated before the socket confirms the switch. A frame whose `ch` does not match (or is missing) MUST be dropped before `updateCandle`: no `update()`, no re-bucket, no `candle:closed` emit, no error. One guard MUST cover BOTH the out-of-order write (`Cannot update oldest data`) and the post-`chart.remove()` write (`Object is disposed`). The guard MUST NOT refetch, rebuild, or issue `setData` (#68 preserved).
(Previously: R5 filtered only `m.symbol`; there was no channel check and `onPush` bucketed with `state.interval`.)

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

#### Scenario: Stale-channel frame during switch is dropped

- GIVEN an active `5m` subscription
- WHEN a frame with `ch:"market_kline_1min"` is injected
- THEN `update()` is not called, the series length is unchanged, and the last `time` is the correct `5m` bucket

#### Scenario: Valid-channel frame still applies

- GIVEN an active `5m` subscription
- WHEN a frame with `ch:"market_kline_5min"` in the next bucket is injected
- THEN the series grows by exactly 1

#### Scenario: Disposed chart never receives the stale frame

- GIVEN a frame buffered across `switchTo`'s `chart.remove()`/rebuild
- WHEN that frame carries the outgoing channel
- THEN it is dropped by the same guard and no `Object is disposed` error is raised

#### Scenario: Guard is update-only

- GIVEN the stale-reject and valid-apply paths
- WHEN the live path runs
- THEN no full-series `setData` is issued (spy === 0), preserving #68

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

### Requirement: R10 — Layout endpoint and restore contract

`/market/api/layout` MUST expose the caller's persisted chart layout.
`GET ?symbol=&interval=` MUST be GET-only and login-required (anonymous → 302),
and MUST return the caller's layout for that `(symbol, interval)` or the built-in
DEFAULT set with `exists:false` when none exists (never 404). `PUT` MUST be
login-required and CSRF-protected, upsert the caller's layout for the payload's
`(symbol, interval)` through `ChartLayout.for_user(request.user)`, validate every
indicator `token` against `quotes.REGISTRY` (unknown token or bad param → 400
before any write), and return the saved layout. The `(user, symbol, interval)`
key is unique. The market page MUST NOT introduce inline script/handlers; the
layout fetch/save uses same-origin JS with the page CSRF token (CSP unchanged,
no new dependency).

#### Scenario: GET default when no layout

- GIVEN an authenticated user with no saved layout
- WHEN GET `?symbol=BTCUSDT&interval=1m`
- THEN 200 with the default set and `exists:false` (no 404)

#### Scenario: PUT then GET returns the saved layout

- GIVEN a PUT with a valid indicator set
- WHEN GET the same symbol and interval
- THEN 200 with the saved set and `exists:true`

#### Scenario: Invalid indicator → 400

- GIVEN PUT `indicators=[{"token":"notreal"}]`
- WHEN handled
- THEN 400 `{"error":"..."}` before any write

#### Scenario: Per-user isolation

- GIVEN user A's saved layout
- WHEN user B GETs the same symbol and interval
- THEN B receives the default set, never A's layout

#### Scenario: Market page stays CSP-clean

- GIVEN the rendered `/market/` page
- WHEN the response header and templates are inspected
- THEN `Content-Security-Policy` is unchanged and no inline script/handler exists

### Requirement: R11 — Drawings endpoint and render/restore contract

`/market/api/drawings` MUST expose the caller's persisted drawings for a chart.
`GET ?symbol=&interval=` MUST be GET-only and login-required (anonymous → 302)
and MUST return the caller's drawings for that `(symbol, interval)` as
`{"drawings":[...]}`, or an empty list when none exist (never 404). `POST` MUST be
login-required and CSRF-protected, validate `kind`/`interval`/`symbol`/`points`/
`style` before any write (unknown `kind`, bad shape, or invalid `interval` → 400),
create through `Drawing.for_user(request.user)`, and return the created row with
its `id`. `DELETE /market/api/drawings/<id>` MUST be login-required and
CSRF-protected, delete through `Drawing.for_user(request.user)` (miss → 404), and
never touch another user's row. The market page MUST render saved drawings via the
already-loaded Lightweight Charts v5.2.0 series primitive (no new dependency, no
DOM access — CSP unchanged), restore them after `buildChart` and on
`switchTo(symbol, interval)` (clearing the previous key's primitives), and MUST
NOT introduce inline script/handlers or relax the read-only boundary.

#### Scenario: GET empty when no drawings

- GIVEN an authenticated user with no drawings
- WHEN GET `?symbol=BTCUSDT&interval=1m`
- THEN 200 `{"drawings":[]}` (no 404)

#### Scenario: POST then GET returns the drawing

- GIVEN a valid drawing payload
- WHEN POST then GET the same key
- THEN 201 with an `id`, and GET lists that drawing

#### Scenario: Invalid kind → 400 before write

- GIVEN POST `kind="notreal"`
- WHEN handled
- THEN 400 `{"error":"..."}` before any write

#### Scenario: DELETE by id is idempotent-by-id

- GIVEN the caller's drawing `d`
- WHEN DELETE `/market/api/drawings/<d.id>`
- THEN 200 and the row is removed; a second DELETE of the same id yields 404

#### Scenario: Per-user isolation

- GIVEN user A's drawing `d`
- WHEN user B GETs the same key or DELETEs `<d.id>`
- THEN B sees no drawing and B's DELETE returns 404; A's row is unchanged

#### Scenario: Drawings render and restore

- GIVEN saved drawings for the active key
- WHEN the page loads or `switchTo` changes symbol/interval
- THEN primitives attach for the new key, previous primitives are cleared, and `window.marketChart.drawings` lists the loaded shapes

#### Scenario: Market page stays CSP-clean

- GIVEN the rendered `/market/` page
- WHEN the response header and templates are inspected
- THEN `Content-Security-Policy` is unchanged and no inline script/handler exists

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

### Requirement: R13 — `/signals/` route is registered in the market app

`market/urls.py` MUST register a GET-only `signals` route serving the
`signals-screen` capability at `/signals/`, without altering any existing market
route. The new page MUST carry the SAME `Content-Security-Policy` header as the
market page (R6) — no relaxation — and MUST NOT introduce inline script/handlers
or a runtime dependency (R7). The route MUST match no order-scanner forbidden
fragment.

#### Scenario: Route registered and namespaced

- GIVEN the market URL configuration
- WHEN it is resolved
- THEN `/signals/` maps to the signals view and every existing market route is unchanged

#### Scenario: CSP and boundary unchanged

- GIVEN a rendered `/signals/` response
- WHEN the header and manifest are inspected
- THEN the CSP is unchanged (no relaxation), no inline script exists, no runtime dependency was added, and the order scanner is clean

### Requirement: R14 — Layered ESM module boundary

Modules MUST follow a frozen inventory: entry `chart.js` (thin: Django-injected
`CONFIG` + imports + `boot()`), pure cores `chart-core.js`/`drawing-core.js`/
`smc-overlay-core.js`/`legend-core.js`/`indicator-settings-core.js`/
`chart-types-core.js`/`theme-core.js`, `chart-store.js` (UI/config state ONLY —
MUST NOT hold candle data; its vocabulary is
`symbol, interval, indicators, params, styles, smc, scaleMode, chartType, theme,
tool`), `chart-bus.js`, `chart-host.js` (chart/series/panes/scales/crosshair +
candle data), the
host-layer sub-module `chart-host-candles.js` (candle channel: `CANDLE_CTORS`,
the candle series, the raw `candles` array, and the incremental HA state;
factory `createCandles(chart, chartType) -> {getCandleSeries, getCandles,
setCandles, updateCandle, remove}`),
`controllers/{indicators,history,stream,drawings,smc,toolbar,legend}.js`,
and `main.js` (ALL orchestration + boot/switch). No module MUST exceed ~300 lines.
Controllers MUST import host/store/bus directly but MUST NOT import `main`;
commands MUST travel the bus, so `main.js` has no circular imports. Every imported
module MUST be served same-origin under `/market/` via its Django route (core →
`MODULE_ALLOWLIST`, controller → `CONTROLLER_ALLOWLIST`). The size rule MUST be
enforced by the committed guard `tests/web/test_module_size_guard.py`
(`CEILING = 300`; scans `web/market/templates/market/**/*.js` via `rglob` +
`splitlines()`). The guard's `ALLOWLIST` MUST be empty — no module is exempt.
`chart-host.js` MUST be ≤ ~300 lines (back under the ceiling after the
extraction). Any module above `CEILING` MUST fail the guard.

(Previously: the store vocabulary had no `theme` and the pure-core list had no
`theme-core.js`.)

#### Scenario: Inventory and no-cycle

- GIVEN the delivered modules, WHEN imports resolve, THEN the inventory (including `chart-types-core.js`, `chart-host-candles.js`, and `theme-core.js`) exists, `theme-core.js` imports nothing, no controller imports `main`, and `main.js` has no cycles

#### Scenario: Store never holds candles

- GIVEN `chart-store.js`, WHEN its keys are inspected, THEN it holds only UI/config (`symbol, interval, indicators, params, styles, smc, scaleMode, chartType, theme, tool`) — no candle data

#### Scenario: Size ceiling with empty allowlist

- GIVEN every module, WHEN `tests/web/test_module_size_guard.py` reads line counts
- THEN it passes at `CEILING = 300` with an EMPTY `ALLOWLIST` (no exemption), `chart-host.js` stays ≤ ~300 lines, and any module above the ceiling fails

#### Scenario: New theme core is served

- GIVEN `theme-core`, WHEN requested under `/market/` with a JS MIME type, THEN it is served 200 (missing from the allowlist → 404 → blank chart)

#### Scenario: New candle sub-module is served

- GIVEN `chart-host-candles`, WHEN requested under `/market/` with a JS MIME type, THEN it is served 200 (the name MUST be in `MODULE_ALLOWLIST`; missing → import 404 → blank chart)

#### Scenario: No behavior change

- GIVEN the change, WHEN the node tests and the E2E suite run
- THEN they pass with NO behavior-assertion edits, the 8-key seam
  (`window.marketChart`) is unchanged, the C1 same-bucket HA fix is preserved
  verbatim, and the HA contract (`chart-types-core`) is untouched

### Requirement: R15 — ESM loading and module serving

`package.json` MUST be root `{"type":"module"}` (Node metadata only — no
dependency/build). Cores MUST use native `export` (UMD shim removed).
`tests/js/*.test.js` MUST use `import`, assertions unchanged. The entry MUST load
as `<script type="module" src="{% url 'market_chart_js' %}">`; the
LightweightCharts CDN MUST stay a classic global script. Every imported module
MUST be served same-origin under `/market/` via its own Django route with a JS
MIME type. Execution MUST be deferred; `boot()` MUST be the last side effect and
controllers MUST NOT self-boot on import.

#### Scenario: ESM test run

- GIVEN `package.json {"type":"module"}` and converted tests, WHEN `node --test "tests/js/**/*.test.js"` runs, THEN all 45 pass with unedited assertions

#### Scenario: Module routes serve JS

- GIVEN each module route, WHEN GET same-origin under `/market/`, THEN 200 with a JS MIME type (missing route → import 404 → blank chart)

#### Scenario: Deferred order preserved

- GIVEN the page loads, WHEN modules execute, THEN no controller self-boots and `boot()` is the final side effect

### Requirement: R16 — Config injection

Django MUST inject config through the ESM entry `chart.js` (rendered by Django)
exporting `CONFIG` (`CONFIG.symbols` = the symbol array). There MUST be NO inline
script and NO `window` global for config. Because config lives in the entry,
`/market/chart.js` MUST contain the literals `BTCUSDT` and `market_kline` so the
existing `test_market_ux.py` assertions hold unedited.

#### Scenario: Config is an ESM export

- GIVEN `/market/chart.js`, WHEN fetched, THEN it is a JS module exporting `CONFIG.symbols`; no inline/window config exists

#### Scenario: Entry keeps the symbol literal

- GIVEN `/market/chart.js`, WHEN fetched, THEN it contains `BTCUSDT` and `market_kline`

### Requirement: R17 — Preserved behavior invariants

The refactor MUST preserve verbatim: single-write-path (#68) — `setData()` only in
build/history, candle `update()` only in stream, no periodic full-series
`setData`; single-source — JS MUST NOT compute indicators or SMC; the
`gen`/`drawGen`/`smcGen` race guards at their ownership; and the boot/switch
`.then()` order: layout → build (reattach drawings) → drawings fetch → SMC fetch
→ history, `ready` after history, `switchTo` clearing the previous key BEFORE
reload. A style change MUST follow the config-change `rebuild()` path (build +
history `setData`); it MUST NOT introduce a second full-series `setData` writer or
mutate `DECIMALS`.
(Previously: the invariant applied to toggles/params; style is now explicitly covered.)

#### Scenario: No setData from the live path

- GIVEN the split modules, WHEN the WS live path runs, THEN no full-series `setData` is issued

#### Scenario: Guards and ordering intact

- GIVEN `switchTo(symbol, interval)`, WHEN orchestration executes, THEN `gen`/`drawGen`/`smcGen` guard their paths and the `.then()` order + `ready` timing are byte-equivalent

#### Scenario: Style change uses the rebuild path

- GIVEN a confirmed style edit
- WHEN it applies
- THEN the chart follows `indicator:changed` → `rebuild()` (build + history `setData`) and no live-path full `setData` occurs

#### Scenario: Style never leaks into the kline query

- GIVEN `styles[token]` populated
- WHEN the kline URL is serialized
- THEN no `color`/`lineWidth`/`precision` key is appended (style is not in `params`)

### Requirement: R18 — Test-seam preservation

The refactor MUST expose `window.marketChart` with frozen keys `{chart,
candleSeries, panes, ready, drawings, smc, smcCounts, smcToggles}` and equivalent
update-timing, and MUST re-expose `window.SmcOverlayCore` as the sanctioned test
seam. `tests/web/test_market_e2e.py` MUST stay green with NO assertion edits.

#### Scenario: Seam shape frozen

- GIVEN a booted chart, WHEN `window.marketChart` is read, THEN all eight keys exist and update as before

#### Scenario: SMC core reachable

- GIVEN the ESM entry loaded, WHEN `window.SmcOverlayCore.setupMarkers(...)` is called, THEN it returns the marker array as before

### Requirement: R19 — Host crosshair subscription seam

`chart-host.js` MUST expose `subscribeCrosshairMove(fn)` (crosshair is host-owned
per R14), null-guarded on `chart`, mirroring `subscribeClick`. Because `build()`
calls `chart.remove()` and creates a new chart, any crosshair handler registered
on a prior chart MUST be considered dead; consumers MUST re-subscribe after each
`chart:built`. No new bus event is introduced.

#### Scenario: Method mirrors subscribeClick

- GIVEN a built chart, WHEN `subscribeCrosshairMove(fn)` is called, THEN it delegates to `chart.subscribeCrosshairMove(fn)` and is a no-op when `chart` is null

#### Scenario: Handler re-binds after rebuild

- GIVEN `chart:built` fires again after `build()`, WHEN the legend subscribes, THEN the handler is bound to the current chart object

### Requirement: R20 — Shell change stays inside the frozen host/seam envelope

The `autoSize: true` host option, the `#chart` markup change, the F8 chart-type
and scale controls, and the theme control MUST stay within R14 (host owns
construction) and MUST NOT add a `window.marketChart` key. `window.marketChart`
MUST keep exactly its 8 frozen keys `{chart, candleSeries, panes, ready,
drawings, smc, smcCounts, smcToggles}` and `window.SmcOverlayCore` MUST be
untouched. The E2E seam shape and timing (R18) and the single-write-path
invariants (R17) MUST be preserved; the existing E2E assertions MUST stay green
with NO edits. F8 added exactly one bus event, `scale:changed` (`{mode}`); this
change MUST NOT add another bus event — the live theme flip MUST go through the
host's option-only `setTheme` method, not a new event. The theme value MUST live
in the store (`state.theme`) and/or `data-theme`, never in the seam.
(Previously: the envelope covered type/scale; theme was not present.)

#### Scenario: Seam stays 8 keys

- GIVEN a booted chart after the theme control
- WHEN `window.marketChart` is read
- THEN exactly the 8 frozen keys exist and no theme key was added

#### Scenario: No new bus event

- GIVEN the change
- WHEN the bus events are inspected
- THEN the only events are the pre-existing set plus `scale:changed`; no `theme:*` event was added

#### Scenario: Existing E2E stays green unedited

- GIVEN the existing E2E assertions
- WHEN the suite runs after the change
- THEN they pass with no assertion edits and the default type stays candles

### Requirement: R21 — Chart type and scale host contract

`chart-host.js` `build()` MUST choose the candle-series Ctor from `state.chartType`
(`candles`/`heikin-ashi` → `CandlestickSeries`, `line` → `LineSeries`, `area` →
`AreaSeries`) at its single construction site, and MUST apply the price-scale mode
after `createChart` via `priceScale("right").applyOptions({mode})` using the
`LightweightCharts.PriceScaleMode` symbol. It MUST expose
`setScaleMode(mode, autoScale)` (chart option only; no data write) and route the
candle write path through `toChartData(state.chartType, …)`, carrying incremental
HA state (`lastHaOpen`/`lastHaClose` reset on `setCandles`). A chart-type change
MUST go through `build()`/`rebuild()`; scale MUST NOT.

#### Scenario: Ctor from state

- GIVEN each `chartType` in `candles,line,area,heikin-ashi`
- WHEN `build(state)` runs
- THEN the candle series is the matching v5 type

#### Scenario: setScaleMode is option-only

- GIVEN a built chart
- WHEN `setScaleMode("log")` runs
- THEN the right price scale mode changes and neither `setData` nor `update` is called

#### Scenario: Build re-applies the scale

- GIVEN `state.scaleMode="percentage"`
- WHEN `build(state)` runs
- THEN the new chart's right price scale mode is Percentage

#### Scenario: Rebuild preserves drawings and SMC

- GIVEN loaded drawings/SMC
- WHEN a chart-type change rebuilds the chart
- THEN `buildChart()` re-attaches both primitives

#### Scenario: HA live is update-only

- GIVEN an HA chart with fresh `setCandles` history
- WHEN a live push lands on a new bar
- THEN the bar is transformed with chained HA state and applied via `update()` only

### Requirement: R22 — Theme host contract

`chart-host.js` `build()` MUST read `state.theme` and pass the theme option set
built by `theme-core.optionsFor` into `createChart` at its single construction
site, so every rebuild is born themed (no separate re-apply). It MUST expose
`setTheme(resolved)` (chart option only; no data write) applying
`chart.applyOptions({layout, grid, crosshair, rightPriceScale, timeScale})`
mirroring `setScaleMode`; it MUST pass full values, never `undefined` keys. A
theme change MUST NOT introduce a second full-series `setData` writer.

#### Scenario: Build is born themed

- GIVEN `state.theme="light"`
- WHEN `build(state)` runs
- THEN the created chart's `layout.background.color` and `layout.textColor` are the light values

#### Scenario: setTheme is option-only

- GIVEN a built chart
- WHEN `setTheme("dark")` runs
- THEN the chart options swap to the dark set and neither `setData` nor `update` is called

#### Scenario: Rebuild preserves theme

- GIVEN `state.theme="dark"`
- WHEN a chart-type change rebuilds the chart
- THEN the new chart's options are the dark set and drawings/SMC re-attach

### Requirement: R23 — E2E readiness for the WS verification scenarios

The dev-only E2E scenarios verifying R5 (`Forming candle updates in place`, `Switch unsubscribes before subscribing`, `Stale-channel frame during switch is dropped`, `Valid-channel frame still applies`) MUST be readiness-gated: each MUST await boot readiness before switching interval or injecting frames, and MUST NOT rely on a retry. The `page.route_web_socket` mock and its frame-ordering assertions MUST be unchanged.

#### Scenario: R5 E2E scenarios wait for readiness
- GIVEN the R5 E2E scenarios in `tests/web/test_market_e2e.py`
- WHEN each test enters its switch/inject phase
- THEN it has awaited `ready` first, and the mocked frame-ordering assertions run unchanged
