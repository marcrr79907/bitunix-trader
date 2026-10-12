# Delta for market-chart

Issue #70 (Fase A1): `/market/api/kline` gains selectable indicators, a `panes`
bucket and a volume pane; warm-up becomes indicator-derived instead of a fixed 20.
R3 and R4 are MODIFIED. Shape invariants (5 candle keys, DB-first, single source
of math, CSP, boundary, no new dep) stay in force.

## MODIFIED Requirements

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
(Previously: fixed `{candles, overlays}` with exactly `{sma20, ema20, rsi14}`, no
selection, no `panes`, no params.)

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
values. (Previously: fixed `WARMUP = 20` regardless of the requested set.)

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
