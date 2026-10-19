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
login-required and CSRF-protected, validate `kind`/`symbol`/`points`/`style` and
any `visible`/`locked` flags before any write (unknown `kind`, bad shape, or a
non-boolean flag → 400), create through `Drawing.for_user(request.user)`, and
return the created row with its `id`. `PUT /market/api/drawings/<id>` MUST be
login-required and CSRF-protected, resolve through `Drawing.for_user(request.user)`
(miss → 404 and another user's `id` → 404 with no leak), accept a PARTIAL
`{points?,style?,visible?,locked?}` body, keep `kind` immutable, validate via
`parse_drawing` (→ 400 before write), and return the updated row
`{id,kind,points,style,visible,locked}` (200). `DELETE /market/api/drawings/<id>`
MUST be login-required and CSRF-protected, delete through
`Drawing.for_user(request.user)` (miss → 404), and never touch another user's row.
The market page MUST render saved drawings via the already-loaded Lightweight
Charts v5.2.0 series primitive (no new dependency, no DOM access — CSP unchanged),
restore them after `buildChart` and on `switchTo(symbol, interval)` (clearing the
previous key's primitives), render a drawing with `visible:false` blank (primitive
kept attached, `autoscaleInfo` null), exclude a `locked:true` OR `visible:false`
drawing from pointer hit-testing while keeping it tree-selectable, and MUST
support selecting, dragging, keyboard deleting/deselecting, and restyling a
drawing, persisting a drag via ONE `PUT` on `pointerup` through `requestUpdate`
only (never `setData`/`update`; #68). It MUST NOT introduce inline script/handlers
or relax the read-only boundary.
(Previously: no `visible`/`locked`; partial PUT was `{points?,style?}`.)

#### Scenario: GET empty when no drawings

- GIVEN an authenticated user with no drawings
- WHEN GET `?symbol=BTCUSDT&interval=1m`
- THEN 200 `{"drawings":[]}` (no 404)

#### Scenario: POST then GET returns the drawing with flags

- GIVEN a valid drawing payload with `visible:false`
- WHEN POST then GET the same key
- THEN 201 with an `id`, and GET lists that drawing with `visible:false`

#### Scenario: Invalid kind or non-bool flag → 400 before write

- GIVEN POST `kind="notreal"`, or `visible="yes"`
- WHEN handled
- THEN 400 `{"error":"..."}` before any write

#### Scenario: PUT updates a drawing in place

- GIVEN the caller's drawing `d`
- WHEN PUT `/market/api/drawings/<d.id>` with a partial `{points, style, locked}`
- THEN 200 with the updated row; a following GET lists the new coordinates and `locked`

#### Scenario: PUT miss or cross-user is 404

- GIVEN an unknown `id`, or an `id` owned by another user
- WHEN PUT
- THEN 404 and no row is modified

#### Scenario: PUT kind immutable → 400

- GIVEN the caller's drawing `d`
- WHEN PUT carries a differing `kind`
- THEN 400 before any write

#### Scenario: DELETE by id is idempotent-by-id

- GIVEN the caller's drawing `d`
- WHEN DELETE `/market/api/drawings/<d.id>`
- THEN 200 and the row is removed; a second DELETE of the same id yields 404

#### Scenario: Per-user isolation

- GIVEN user A's drawing `d`
- WHEN user B GETs the same key or PUTs/DELETEs `<d.id>`
- THEN B sees no drawing and B's PUT/DELETE returns 404; A's row is unchanged

#### Scenario: Select, drag, and persist round-trips

- GIVEN a rendered drawing
- WHEN it is selected and dragged, then the drag ends
- THEN exactly one `PUT /market/api/drawings/<id>` is issued and the seam shows the new points

#### Scenario: Drawings render and restore

- GIVEN saved drawings for the active key
- WHEN the page loads or `switchTo` changes symbol/interval
- THEN primitives attach for the new key, previous primitives are cleared, and `window.marketChart.drawings` lists the loaded shapes

#### Scenario: Hidden and locked render and restore

- GIVEN a saved drawing with `visible:false, locked:true`
- WHEN the page loads or `switchTo` restores it
- THEN its primitive is attached but draws nothing, it is not pointer-selectable, and its tree row reflects the flags

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
`chart-types-core.js`/`theme-core.js`/`tool-icons-core.js`/`chart-registry-core.js`/
`add-indicator-core.js`/`measure-core.js`/`position-core.js`/`position-draft-core.js`/
`readout-coalesce-core.js`/`history-core.js`/`context-menu-core.js`/
`drawing-tools-core.js`/`fib-tools-core.js`/`drawing-click-flow-core.js`/
`tool-render-core.js`/`object-tree-dom-core.js`/`alert-markers-core.js`/
`alert-condition-core.js`/`alert-ui-core.js`/`alert-markers-view.js`/
`alert-bell-view.js`,
`chart-store.js` (UI/config state ONLY — MUST NOT hold candle data; its vocabulary
is `symbol, interval, indicators, params, styles, smc, scaleMode, chartType, theme,
tool, indicatorVisible`), `chart-bus.js`, `chart-host.js` (chart/series/panes/
scales/crosshair + candle data), the
host-layer sub-module `chart-host-candles.js` (candle channel: `CANDLE_CTORS`,
the candle series, the raw `candles` array, and the incremental HA state;
factory `createCandles(chart, chartType) -> {getCandleSeries, getCandles,
setCandles, updateCandle, remove}`),
`controllers/{indicators,history,stream,drawings,drawing-interaction,smc,toolbar,
legend,draw-toolbar,object-tree,preference,measure,position-seed,undo,context-menu,
draft-preview,alerts}.js`,
and `main.js` (ALL orchestration + boot/switch). No module MUST exceed ~300 lines.
Controllers MUST import host/store/bus directly but MUST NOT import `main`;
commands MUST travel the bus, so `main.js` has no circular imports. Every imported
module MUST be served same-origin under `/market/` via its Django route (core →
`MODULE_ALLOWLIST`, controller → `CONTROLLER_ALLOWLIST`); `MODULE_ALLOWLIST`
(`views.py:44-75`, **33** entries) MUST include `measure-core`, `position-core`,
`position-draft-core`, `readout-coalesce-core`, `history-core`, `context-menu-core`,
`drawing-tools-core`, `fib-tools-core`, `drawing-click-flow-core`,
`tool-render-core`, `object-tree-dom-core`, `alert-markers-core`,
`alert-condition-core`, `alert-ui-core`, `alert-markers-view`, and
`alert-bell-view`; `CONTROLLER_ALLOWLIST`
(`views.py:76-95`, **17** entries) MUST include `measure`, `position-seed`, `undo`,
`context-menu`, `draft-preview`, and `alerts`. The size rule
MUST be enforced by the committed guard `tests/web/test_module_size_guard.py`
(`CEILING = 300`; scans `web/market/templates/market/**/*.js` via `rglob` +
`splitlines()`). The guard's `ALLOWLIST` MUST be empty — no module is exempt.
`chart-host.js` MUST be ≤ ~300 lines. Any module above `CEILING` MUST fail the
guard. `controllers/smc.js` (300) MUST stay byte-untouched; `controllers/
object-tree.js` (299 before F9) SHRINKS to 263 by moving its row-DOM factories to
`object-tree-dom-core.js`, giving the ceiling back its headroom.
(Previously: the pure-core list had no `measure-core`/`position-core`/
`position-draft-core`/`readout-coalesce-core`; the controller inventory had 11
entries and no `measure`/`position-seed`.)
(Previously: the pure-core list had no `history-core`/`context-menu-core`; the
controller inventory had 13 entries and no `undo`/`context-menu`.)
(Previously: the pure-core list had no `drawing-tools-core`/`fib-tools-core`/
`drawing-click-flow-core`/`tool-render-core`/`object-tree-dom-core`; the
controller inventory had 15 entries and no `draft-preview`.)
(Previously: the pure-core list had no `alert-markers-core`/`alert-condition-core`/
`alert-ui-core`/`alert-markers-view`/`alert-bell-view`; the controller inventory
had 16 entries and no `alerts`; `MODULE_ALLOWLIST` was 28.)

#### Scenario: Inventory and no-cycle

- GIVEN the delivered modules, WHEN imports resolve, THEN the inventory (including `drawing-tools-core.js`, `fib-tools-core.js`, `drawing-click-flow-core.js`, `tool-render-core.js`, `object-tree-dom-core.js`, `alert-markers-core.js`, `alert-condition-core.js`, `alert-ui-core.js`, `alert-markers-view.js`, `alert-bell-view.js`, `theme-core.js`, `history-core.js`, `context-menu-core.js`, and `controllers/undo.js`/`controllers/context-menu.js`/`controllers/draft-preview.js`/`controllers/alerts.js`) exists, `theme-core.js` imports nothing, no controller imports `main`, and `main.js` has no cycles (`test_market_ux.py::test_import_graph_routes_resolve`)

#### Scenario: Store never holds candles

- GIVEN `chart-store.js`, WHEN its keys are inspected, THEN it holds only UI/config (`symbol, interval, indicators, params, styles, smc, scaleMode, chartType, theme, tool, indicatorVisible`) — no candle data

#### Scenario: Size ceiling with empty allowlist

- GIVEN every module, WHEN `tests/web/test_module_size_guard.py` reads line counts
- THEN it passes at `CEILING = 300` with an EMPTY `ALLOWLIST`, `drawings.js` SHRINKS (click flow extracted; 298→282), `object-tree.js` SHRINKS (299→263), `smc.js` is byte-untouched, and any module above the ceiling fails

#### Scenario: New cores are served

- GIVEN `drawing-tools-core`, `fib-tools-core`, `drawing-click-flow-core`, `tool-render-core`, `object-tree-dom-core`, `alert-markers-core`, `alert-condition-core`, `alert-ui-core`, `alert-markers-view`, and `alert-bell-view`
- WHEN requested under `/market/` with a JS MIME type
- THEN each is served 200 (present in `MODULE_ALLOWLIST`; missing → 404 → blank chart; `test_market_ux.py::test_f9_cores_are_served`, `test_f10_alerts_are_served`)

#### Scenario: Controller allowlist count is 17

- GIVEN `CONTROLLER_ALLOWLIST`
- WHEN inspected
- THEN it holds **17** entries and `tests/web/test_market_ux.py:146,195` asserts the count `== 17` and passes — F10 adds exactly one controller (`alerts`), prior count 16

#### Scenario: No behavior change

- GIVEN the change, WHEN the node tests and the E2E suite run
- THEN they pass with no behavior-assertion edits beyond the added F10 cases, the 8-key seam (`window.marketChart`) is unchanged, and the HA contract (`chart-types-core`) is untouched

> **Reconciliation note (verify W1, archive 2026-10-16; F9 archive 2026-10-18;
> F10 archive 2026-10-18).**
> The `market-chart` R14 delta originally stated the controller count grew `8→10`;
> the delivered F5 change landed at **11** because of the `preference` extraction.
> F6 grew it to **13** (`measure`, `position-seed`), F7 to **15** (`undo`,
> `context-menu`), F9 to **16** (`draft-preview`, added by the R2 rework slice
> that extracted the pending-draft preview out of `drawings.js`), and F10 to
> **17** (`alerts`). `MODULE_ALLOWLIST` is **33** entries in the delivered tree:
> F10 added `alert-markers-core`, `alert-condition-core`, `alert-ui-core`,
> `alert-markers-view`, and `alert-bell-view` — two more than the delta's `28→30`
> because S3 extracted the UI helpers to `alert-ui-core` to stay under the
> ceiling, and the P1/P2 polish slices (#232–#234) extracted the bell element and
> the marker view into their own adapters. The canonical clause above matches
> reality (`views.py:44-95`, `test_market_ux.py:146,204`). Functional invariant
> holds: every entry is served 200 and the import graph resolves.

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
seam. The toolbar, the object tree, indicator visibility, the F5 vertical toolbar,
the F6 measure/position tools, the F7 undo/context-menu layer, the F9 drawing
tools, and the F10 alert layer MUST NOT add a 9th key; the measure readout MUST be
asserted via its DOM node
(`#measure-readout`) and the position via `window.marketChart.drawings` (existing)
plus the captured POST/PUT, never via a new seam key. The F7 undo layer MUST be
asserted via captured POST/PUT/DELETE and the F7 context menu via its DOM
`role="menu"`, never via a new seam key. The F9 kinds MUST be asserted via
`window.marketChart.drawings` (existing) plus the captured POST/PUT/DELETE and
their rendered DOM/canvas, never via a new seam key. The F10 alert layer MUST be
asserted via `#chart-alert-bell`, `#alert-dialog`, `#alert-status[aria-live]`,
`#alert-confirm`, and the captured POST/PUT/DELETE to `/market/api/alerts`, never
via a new seam key.
`tests/web/test_market_e2e.py` MUST stay green except for the
assertions that covered the DOM this change removes (`#drawing-list`, the
indicators `fieldset`); each such assertion MUST be replaced by equivalent
coverage, and the removal + replacement MUST be documented in the E2E itself
(`test_market_e2e.py:582-620`). Every removed scenario has an equivalent
replacement EXCEPT adding-an-indicator, which became the new `chart-indicator-add`
capability (issue #176, slice S5) — so there is no unreplaced coverage gap.
(Previously: the clause read "green with NO assertion edits"; that was unmeetable
by the slice that deletes the DOM — reconciled here per verify W2 / issue #177.
The F6 clause was added for the measure/position tools.)
(Previously: the clause was silent on the F7 undo/context-menu layer.)
(Previously: the clause was silent on the F9 drawing tools.)
(Previously: the clause was silent on the F10 alert layer.)

#### Scenario: Seam shape frozen

- GIVEN a booted chart after the toolbar and tree exist with the measure, position, undo, context-menu, F9 drawing, and alert layers
- WHEN `window.marketChart` is read
- THEN all eight keys exist and update as before, with no toolbar/tree/visibility/measure/position/undo/menu/F9/alert key added

#### Scenario: Measure has no seam key

- GIVEN a completed measurement
- WHEN `window.marketChart` is read
- THEN it still has exactly 8 keys and the readout is observed through its `aria-live` DOM node (E2E `test_shell_keeps_seam_at_eight_keys`; measure asserts `drawings.length == 0`)

#### Scenario: Undo and menu assert without a seam key

- GIVEN an undo/redo or a context-menu command
- WHEN it is observed
- THEN it is asserted via captured POST/PUT/DELETE and the DOM `role="menu"`, and `window.marketChart` still has exactly 8 keys

#### Scenario: F9 kinds assert without a seam key

- GIVEN an F9 drawing created, moved, then deleted
- WHEN it is observed
- THEN it is asserted via `window.marketChart.drawings` and the captured POST/PUT/DELETE, and `window.marketChart` still has exactly 8 keys (E2E `test_f9_tools_create_their_kind_and_drag_is_one_put`)

#### Scenario: Alerts assert without a seam key

- GIVEN an alert created from the bell and a rendered marker set
- WHEN it is observed
- THEN the bell is found by `#chart-alert-bell`, the dialog by `#alert-dialog`, the state summary by `#alert-status[aria-live]`, the confirmation by `#alert-confirm[role="status"]`, and the write by the captured POST/PUT/DELETE to `/market/api/alerts`, and `window.marketChart` still has exactly 8 keys

#### Scenario: SMC core reachable

- GIVEN the ESM entry loaded
- WHEN `window.SmcOverlayCore.setupMarkers(...)` is called
- THEN it returns the marker array as before

#### Scenario: Existing E2E green except replaced assertions

- GIVEN the existing E2E assertions
- WHEN the suite runs after the change
- THEN it passes except for the assertions covering the removed `#drawing-list`/`fieldset` DOM, each replaced by equivalent coverage and documented in `test_market_e2e.py:582-620` (and the F9 toolbar count assertion moved 7→15)

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
and scale controls, the theme control, the F5 vertical toolbar, the object tree,
the indicator-visibility toggle, the F6 measure/position tools, the F7
undo/context-menu layer, the F9 drawing tools, and the F10 alert bell/dialog/
markers MUST stay within R14
(host owns construction) and MUST NOT add a `window.marketChart` key.
`window.marketChart` MUST keep
exactly its 8 frozen keys `{chart, candleSeries, panes, ready, drawings, smc,
smcCounts, smcToggles}` and `window.SmcOverlayCore` MUST be untouched. The E2E
seam shape and timing (R18) and the single-write-path invariants (R17) MUST be
preserved. F8 added exactly one bus event, `scale:changed` (`{mode}`); F5 added
exactly ONE more, `indicator:visibility` (`{token, visible}`), routed by `main` to
the host's option-only `setSeriesVisible` (mirroring `scale:changed`,
`main.js:179-182`). Drawing hide/lock MUST reuse the existing `drawing:changed`
event and MUST NOT add a drawing event; the live theme flip MUST go through the
host's option-only `setTheme` method, not a new event. The theme value MUST live
in the store (`state.theme`) and/or `data-theme`, never in the seam. The F6
position tool MUST reuse the existing `drawing:changed`/`drawing:selected` events
and the measure tool MUST add NO bus event — no `measure:*`/`position:*` event
exists. The F7 layer MUST add NO bus event to `EVENTS`: undo replays through the
existing `drawing:changed`/`drawing:delete` commands, and the F7 drawing events
`drawing:duplicate`/`drawing:restore`/`drawing:created`/`drawing:create-failed`
are STRING LITERALS handled in `drawings.js` (the same literal convention as
`drawing:changed`/`drawing:delete`) — they are NOT `EVENTS` members. No
`history:*`/`undo:*`/`menu:*` event exists. The F9 tools MUST add NO bus event and
NO store key: activating an F9 tool writes the existing `store.tool` value;
creating reuses `createDrawing` (#68) and the existing `drawing:created` literal;
`STORE_KEYS` MUST stay 11. The F10 alert layer MUST add NO bus event and NO
store key: `controllers/alerts.js` reacts to the existing `chart:built`,
`history:loaded` and `candle:closed` events and its own fetches; the bell,
dialog and marker state live in the controller closure; `STORE_KEYS` MUST stay
11. No `history:*`/`undo:*`/`menu:*`/`tool:*`/`fib:*`/`channel:*`/`alert:*` event
exists.
(Previously: the envelope covered type/scale/theme and forbade a second event; F5
adds exactly one, `indicator:visibility`; the F6 clause was added.)
(Previously: the envelope was silent on the F7 undo/context-menu layer.)
(Previously: the envelope was silent on the F9 drawing tools.)
(Previously: the envelope was silent on the F10 alert layer.)

#### Scenario: Seam stays 8 keys

- GIVEN a booted chart after the toolbar and tree with the measure, position, undo, menu, F9, and alert layers
- WHEN `window.marketChart` is read
- THEN exactly the 8 frozen keys exist and no toolbar/tree/visibility/measure/position/undo/menu/F9/alert key was added

#### Scenario: Exactly one new bus event (unchanged set)

- GIVEN the change
- WHEN the bus events are inspected
- THEN the only `EVENTS` members are the pre-existing set plus `scale:changed` plus `indicator:visibility`; the position tool reuses `drawing:changed`/`drawing:selected`, the measure tool adds none, the F9 tools add none (the F9 create reuses the `drawing:created` string literal), and the F7 `drawing:duplicate`/`drawing:restore`/`drawing:created`/`drawing:create-failed` are string literals (not `EVENTS` members) — no `history:*`/`undo:*`/`menu:*`/`tool:*`/`fib:*`/`channel:*` event, no `measure:*`/`position:*` event, no `drawing:visibility`/`drawing:lock` event, no `alert:*` event (F10 reuses `chart:built`/`history:loaded`/`candle:closed`), and no new `EVENTS` entry exist

#### Scenario: STORE_KEYS stays 11

- GIVEN `chart-store.js` after F10
- WHEN its keys are inspected
- THEN it holds exactly the 11 frozen keys — F9 and F10 add none (new tools reuse `tool`; F10 keeps alert state in the controller closure; `chart-store.test.js` asserts `length === 11`)

#### Scenario: Visibility toggle is option-only

- GIVEN a built chart with the `setData`/`update` spies installed
- WHEN `indicator:visibility` fires for a token
- THEN the host calls `setSeriesVisible` (option-only) and neither `setData` nor `update` is called

#### Scenario: Measure and position render option-only

- GIVEN a built chart with the `setData`/`update` spies installed
- WHEN a measure drag runs or a position is dragged
- THEN each renders via `requestUpdate` (primitive) and neither `setData` nor `update` is called

#### Scenario: Undo and menu never touch the series data path

- GIVEN a built chart with the `setData`/`update` spies installed
- WHEN an undo replays or a menu command runs
- THEN neither spy is called (replay reuses the HTTP verbs; menu reuses the bus commands)

#### Scenario: F9 render is option-only

- GIVEN a built chart with the `setData`/`update` spies installed
- WHEN an F9 drawing is created or dragged
- THEN it renders via `requestUpdate` (primitive) and neither `setData` nor `update` is called (issue #217; `drawing-primitive.test.js::an F9 primitive never calls setData/update (option-only, #68/#217)` — the throwing-stub proof added in the R1 fix slice)

#### Scenario: Alert markers never touch the series data path

- GIVEN a built chart with the `setData`/`update` spies installed
- WHEN the alert markers render on build, on a candle close, on a theme flip, or on a symbol/interval switch
- THEN they render through `createSeriesMarkers`/`setMarkers` and neither spy is called (#68; `controllers/alerts.js` has no writer call, and the controller's series stub exposes only `coordinateToPrice`/`priceToCoordinate`)

#### Scenario: Existing E2E stays green except replaced assertions

- GIVEN the existing E2E assertions
- WHEN the suite runs after the change
- THEN they pass except for the assertions covering the removed DOM (replaced and documented per R18) and the default type stays candles

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

> **F11 (#124) delta.** R19–R20 add the symbol search affordance and pin the
> selector/inventory compatibility. R1–R18 are unchanged.

### Requirement: R19 — Symbol search and watchlist affordance

The chart page MUST offer a search over the exchange-wide catalog
(`symbol-catalog` R3) and a per-user watchlist affordance
(`market-watchlist` R14.8–R14.10).

The search MUST be driven by a pure, framework-free, DOM-free core
`symbol-search-core.js` exporting `filterSymbols(query, symbols, limit)`:
case-insensitive; empty/whitespace query returns all symbols (capped); otherwise
results are ranked **exact match → prefix match → substring match**, then
alphabetically within a tier; the returned length MUST NEVER exceed `limit`
(default 50); a non-matching query MUST return an empty array; the function MUST
NOT throw for any input (non-array, null, non-string query).

The picker MUST live in a NEW leaf controller
`controllers/symbol-picker.js` (factory `create({store, bus, config})`, imports
host/store/bus/cores but NEVER `main`). Selecting a result MUST emit the EXISTING
`config:changed` bus command (`{symbol, interval}`) — no new bus event, no new
store key, no new write path. Follow/unfollow MUST call the watchlist API and
reflect the new state without a page reload.

The picker MUST be an accessible combobox: the input carries `role="combobox"`,
`aria-expanded`, `aria-controls`, `aria-autocomplete="list"` and
`aria-activedescendant`; results render in a `role="listbox"` with one
`role="option"` per result; `ArrowDown`/`ArrowUp` move the active option
(wrapping), `Enter` selects it, `Escape` closes the listbox and clears the active
option. Focus MUST stay in the input (combobox pattern, not roving tabindex). A
result-count change MUST be announced through a polite live region.

#### Scenario: Prefix outranks substring

- GIVEN a catalog containing `BTCUSDT`, `WBTCUSDT` and `ETHUSDT`
- WHEN `filterSymbols("btc", symbols, 50)` runs
- THEN `BTCUSDT` precedes `WBTCUSDT` and `ETHUSDT` is absent

#### Scenario: Empty query returns a capped list

- GIVEN a catalog of 300 symbols
- WHEN `filterSymbols("", symbols, 50)` runs
- THEN exactly 50 symbols are returned

#### Scenario: Case and malformed input never throw

- GIVEN `filterSymbols("BtC", symbols, 50)` and `filterSymbols(null, null, 50)`
- WHEN called
- THEN the first matches case-insensitively and the second returns an array (no throw)

#### Scenario: No match is empty

- GIVEN a catalog without `ZZZ`
- WHEN `filterSymbols("zzz", symbols, 50)` runs
- THEN the result is `[]`

#### Scenario: Selecting a result switches the chart

- GIVEN the picker is open with `DOGEUSDT` in the results
- WHEN the user presses `Enter` on it
- THEN one `config:changed` command with `{symbol: "DOGEUSDT", interval: <current>}` is emitted

#### Scenario: Follow persists without a reload

- GIVEN `DOGEUSDT` is not in the caller's watchlist
- WHEN the user follows it from a result row
- THEN one `POST /market/api/watchlist` is issued and the row reflects the followed state

#### Scenario: Keyboard-only operation

- GIVEN focus in the picker input
- WHEN `ArrowDown`, `ArrowDown`, `Enter` are pressed
- THEN the second result is selected and the listbox closes

### Requirement: R20 — Selector and inventory compatibility

The watchlist section MUST keep rendering symbol buttons carrying
`class="pair"` and `data-symbol="<SYMBOL>"`, and MUST remain inside an element
with `class="pairs"`. `controllers/toolbar.js` MUST NOT be rewritten for this
change: its `.pair` delegation (`toolbar.js:29-33`) and the three existing E2E
selectors (`test_market_e2e.py:1908, :2007, :2176`) MUST keep working unchanged.

The new modules MUST be registered in the serving allowlists
(`views.MODULE_ALLOWLIST` gains `symbol-search-core`;
`views.CONTROLLER_ALLOWLIST` gains `symbol-picker`) and documented in
`docs/architecture/chart-modules.md`. No module MAY exceed the ~300-line ceiling.
`window.marketChart` MUST keep exactly its 8 keys and `STORE_KEYS` its 11 entries.
No inline `<script>` or inline event handler MAY be added, and the market CSP
MUST be unchanged.

#### Scenario: Pair selectors survive

- GIVEN the rendered market page
- WHEN the watchlist markup is inspected
- THEN `.pairs .pair[data-symbol]` still matches one element per listed symbol

#### Scenario: Toolbar delegation is untouched

- GIVEN `controllers/toolbar.js`
- WHEN the change is applied
- THEN its `.pair` click delegation and byte content are unchanged

#### Scenario: New modules are served and allowlisted

- GIVEN `GET /market/symbol-search-core.js` and `GET /market/controllers/symbol-picker.js`
- WHEN fetched
- THEN both are 200 `text/javascript` and both names appear in their allowlists

#### Scenario: Frozen seams hold

- GIVEN the browser build
- WHEN `window.marketChart` and the store vocabulary are inspected
- THEN they carry exactly 8 and 11 keys respectively

#### Scenario: CSP unchanged

- GIVEN the rendered market page
- WHEN the response header and templates are inspected
- THEN `Content-Security-Policy` equals the prior value and no inline handler exists

#### Scenario: Ceiling holds

- GIVEN every module under `web/market/templates/market/`
- WHEN `tests/web/test_module_size_guard.py` runs
- THEN no module exceeds 300 lines and the allowlist stays empty
