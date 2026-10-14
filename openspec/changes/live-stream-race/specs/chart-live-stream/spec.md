# Delta for chart-live-stream

Issue #150 (DEBT-1): the live adapter applied every push regardless of whether the
frame's channel still matched the active subscription, producing `Cannot update
oldest data` / `Object is disposed`. R2–R4, R6–R7 stay in force and unmodified.

## MODIFIED Requirements

### Requirement: R1 — Pure series core, no environment dependency

`chart-core.js` MUST be a pure module (no DOM, no chart library, no network,
no global state) exposing `bucketTime`, `upsertCandle`, `mergeCandles`,
`lastPoint`, and the frame predicate `isFrameForChannel`. It MUST load in Node
(native ESM `import`) and in the browser from the same source.
(Previously: the exposed set had no `isFrameForChannel`.)

The predicate `isFrameForChannel(frame, expectedChannel)` MUST return `true` iff
`frame.ch` is a non-empty string strictly equal to `expectedChannel`; any missing
or empty `ch`, or missing/empty `expectedChannel`, MUST return `false`
(fail-closed). It MUST NOT mutate inputs. Signature is FROZEN:
`isFrameForChannel(frame, expectedChannel) -> boolean`.

#### Scenario: Loads in Node and browser

- GIVEN the module
- WHEN imported in Node and loaded in a browser
- THEN both expose `bucketTime`, `upsertCandle`, `mergeCandles`, `lastPoint`, `isFrameForChannel`

#### Scenario: No environment coupling

- GIVEN the core source
- WHEN inspected
- THEN it references no `document`, `window`, `fetch`, or chart API

#### Scenario: Predicate matches only the exact channel

- GIVEN `isFrameForChannel({ch:"market_kline_5min"}, "market_kline_5min")`
- WHEN called, THEN it returns `true`
- AND `isFrameForChannel({ch:"market_kline_1min"}, "market_kline_5min")` returns `false`

#### Scenario: Missing channel fails closed

- GIVEN `{}` or `{ch:null}` or `{ch:""}` or an empty `expectedChannel`
- WHEN the predicate runs
- THEN it returns `false` (no throw)

### Requirement: R5 — Single write path in the adapter

The adapter MUST call `setData` ONLY for the initial history load and for
pagination prepends. During the live stream it MUST use `update()` exclusively and
MUST NOT issue a periodic `setData`. Overlays MUST advance via `update()` of their
latest point (never a full-overlay `setData` mid-stream). **Frame-channel
invariant (#150):** the live handler MUST apply a push ONLY when
`isFrameForChannel(frame, config.channels[sub.interval])` holds; `sub.interval` is
authoritative for the channel comparison AND for `bucketTime`, never
`state.interval`. A frame that fails the predicate (foreign channel, or missing
`ch`) MUST be dropped BEFORE `updateCandle` — no `update()`, no re-bucket, no
`candle:closed`, no error — and the drop MUST cost no network work and MUST NOT
issue `setData`. The same single guard MUST also absorb the post-`chart.remove()`
`Object is disposed` case.
(Previously: R5 had no frame-channel guard; the handler applied every push once
`m.symbol` matched.)

#### Scenario: No setData during the stream

- GIVEN the chart receiving WS pushes
- WHEN several candles arrive
- THEN `setData` is not called; only `update` is (asserted by a spy)

#### Scenario: Live series is monotonic

- GIVEN consecutive pushes
- WHEN the series length is sampled between pushes
- THEN it never decreases

#### Scenario: Stale-channel frame fails the invariant and is dropped

- GIVEN `sub.interval="5m"` and a frame `ch:"market_kline_1min"` whose `bucketTime(ts,"5m")` is at/behind the series last time
- WHEN the push is handled
- THEN no `update()` occurs, the series is unchanged, and no `Cannot update oldest data` pageerror is raised

#### Scenario: Same-channel same-bucket frame still applied

- GIVEN `sub.interval="5m"` and a frame `ch:"market_kline_5min"` in the current bucket
- WHEN the push is handled
- THEN it is applied via `update()` in place (length unchanged)

#### Scenario: Guard survives chart rebuild

- GIVEN a stale frame arriving across `switchTo`'s `chart.remove()`/rebuild window
- WHEN the push is handled
- THEN it is dropped by the predicate and no `Object is disposed` error is raised

#### Scenario: E2E contract — drop, apply, update-only

- GIVEN a logged-in `/market/` page with a `5m` subscription and a `setData` spy
- WHEN a stale `1min` frame then a valid `5min` frame are injected via `page.route_web_socket`
- THEN no `pageerror` occurs, the series grows by exactly 1 from the valid frame, the final candle time is the correct `5m` bucket, and the spy reports `setData === 0`
