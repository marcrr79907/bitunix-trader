# Delta for market-chart

R1's client method gains `quote_vol` (and optional range params); the endpoint payload shape is unchanged because the new key is stripped before serialization. R3 is restated to make that exactness explicit.

## MODIFIED Requirements

### Requirement: R1 — Read-only kline client method

`src/client.py` MUST expose `kline(symbol, interval, limit, start_time=None, end_time=None)` calling `GET /api/v1/futures/market/kline` via the public unsigned path, mapping `time` ms → UNIX seconds (int), prices to floats, and `quoteVol` → `quote_vol` float (or `None` when absent). Optional `start_time`/`end_time` MUST pass through as epoch-ms `startTime`/`endTime` params and MUST be omitted when `None` (backward compatible). Empty upstream MUST return `[]`; API failures MUST surface as `BitunixError`. MUST NOT call any order endpoint.
(Previously: `kline(symbol, interval, limit)` with no range params and no `quoteVol` mapping.)

#### Scenario: Correct URL and params

- GIVEN a captured public GET, WHEN `kline("BTCUSDT", "1m", 100)` runs, THEN it hits `/api/v1/futures/market/kline` with `symbol`/`interval`/`limit` params, no signing

#### Scenario: Mapping ms→s, floats, and quote_vol

- GIVEN row `{"time": 1700000000000, "open": "50000.5", "high": "51000", "low": "49000", "close": "50500", "quoteVol": "3880565.68"}`, WHEN mapped, THEN the result includes `"quote_vol": 3880565.68` alongside the int `time` and float prices

#### Scenario: Range params pass through

- GIVEN `start_time`/`end_time`, WHEN `kline` runs, THEN the GET carries `startTime`/`endTime` epoch-ms params

#### Scenario: Range params omitted when None

- GIVEN both range args omitted, WHEN `kline` runs, THEN the params are identical to today (no `startTime`/`endTime`)

#### Scenario: Missing quoteVol maps to None

- GIVEN a row without `quoteVol`, WHEN mapped, THEN `quote_vol` is `None` and no `KeyError` is raised

#### Scenario: API error surfaces as BitunixError

- GIVEN upstream API code != 0, WHEN `kline` runs, THEN raises `BitunixError`

#### Scenario: Empty upstream returns empty list

- GIVEN upstream `data` empty, WHEN `kline` runs, THEN returns `[]` without raising

### Requirement: R3 — Kline JSON endpoint

`/market/api/kline?symbol=&interval=` MUST be GET-only, require login (anonymous → 302 to login). Success returns `{"candles": [...], "overlays": {...}}`; candles EXACTLY `{time, open, high, low, close}` — the client's `quote_vol` key MUST be stripped in `quotes.get_kline_payload` and MUST NOT reach the response. `time` UNIX-seconds int, ascending, deduplicated. Overlays are `{time, value}` lists, gaps omitted. Invalid symbol/interval → 400 `{"error": "..."}` (generic). Empty upstream → 200 empty arrays. Upstream network failure → 502 `{"error": "upstream"}`, never 500. MUST NOT call any order endpoint.
(Previously: candle shape stated but not explicitly pinned against the new `quote_vol` key.)

#### Scenario: Payload candle is exactly five fields

- GIVEN upstream rows now carrying `quoteVol`, WHEN the endpoint responds, THEN every candle has exactly `{time, open, high, low, close}` with no `quote_vol` key

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
