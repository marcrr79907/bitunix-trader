# Delta for market-chart

Issue #150 (DEBT-1). Root cause: `stream.js::onPush` filters only `m.symbol`, never
the channel, so a frame from the outgoing channel buffered during `switchTo` is
re-bucketed under the NEW interval → stale `series.update()` → `Cannot update
oldest data` (and `Object is disposed` across `chart.remove()`). R1–R4, R6–R21
stay in force and unmodified.

## MODIFIED Requirements

### Requirement: R5 — Live candles over browser WS

Page JS MUST connect to `wss://fapi.bitunix.com/public/`, subscribe
`market_kline_<interval>`, update the FORMING candle in place via interval
bucketing (no duplicate times), unsubscribe BEFORE subscribing on interval/symbol
switch, reconnect with exponential backoff capped at a fixed maximum,
resubscribing on reopen. Verified by dev-only E2E assertions, not image diffs.
The two live-candle scenarios MUST be driven via `page.route_web_socket` (no live
network/CDN); reconnect is accepted as inspection-verified (single pure capped
expression). **Consistency (fix #68):** the live path MUST use a single writer
(`series.update()`), MUST NOT issue a periodic full-series `setData()`, and the
candle bucket timestamp MUST equal the exchange candle `time` (1w = Monday 00:00
UTC, 1M = calendar month start) — the client MUST NOT invent a divergent timeline.
Bucket/ordering math MUST live in a pure, framework-free core (`chart-core.js`)
exercised by `node --test`. **Frame-channel guard (#150):** each push frame MUST
be applied ONLY when its channel identity `frame.ch` equals the currently
subscribed channel. The active subscription record `sub.interval` MUST be
authoritative for BOTH the channel comparison and the bucket computation in
`onPush` — NOT `state.interval`, which is mutated before the socket confirms the
switch. A frame whose `ch` does not match (or is missing) MUST be dropped before
`updateCandle`: no `update()`, no re-bucket, no `candle:closed` emit, no error.
One guard MUST cover BOTH the out-of-order write (`Cannot update oldest data`) and
the post-`chart.remove()` write (`Object is disposed`). The guard MUST NOT refetch,
rebuild, or issue `setData` (#68 preserved).
(Previously: R5 filtered only `m.symbol`; there was no channel check and `onPush`
bucketed with `state.interval`.)

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
