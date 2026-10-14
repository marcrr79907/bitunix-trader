# chart-live-stream Specification

## Purpose

A framework-free core (pure timeline/series math) plus an adapter that renders a
consistent live chart: one write path for history/pagination (`setData`), one for
the live stream (`update`). New capability — no prior spec.

## Requirements

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

### Requirement: R2 — Exchange-aligned bucketing

`bucketTime(tsMs, interval)` MUST return the UNIX-seconds start of the candle
bucket, aligned the way BitUnix aligns:
- intraday (1m…12h) and `1d`: `floor(sec / n) * n`;
- `1w`: Monday 00:00 UTC (BitUnix uses `t % 604800 == 345600`);
- `1M`: calendar month start (UTC), NOT a fixed 30-day window.

A push's bucket MUST equal the exchange candle's `time` for every interval.

#### Scenario: 1w bucketed to Monday
- GIVEN a Thursday timestamp
- WHEN `bucketTime(ts, "1w")` runs
- THEN it returns the Monday 00:00 UTC of that week (`t % 604800 == 345600`)

#### Scenario: 1M bucketed to calendar month start
- GIVEN a mid-month timestamp
- WHEN `bucketTime(ts, "1M")` runs
- THEN it returns the 1st of that month 00:00 UTC

#### Scenario: intraday matches floor
- GIVEN any timestamp
- WHEN `bucketTime(ts, "5m")` runs
- THEN it equals `floor(sec/300)*300`

### Requirement: R3 — Upsert is in-place and monotonic

`upsertCandle(candles, bar)` MUST dedupe by `time`: replace the last bar in place
when `bar.time` equals the current last, append when greater, and ignore
strictly-older bars (never insert out of order). The array MUST remain sorted and
free of duplicate `time`.

#### Scenario: Same bucket updates in place
- GIVEN a series whose last candle has time T
- WHEN a bar with time T is upserted
- THEN the last element is replaced, length unchanged

#### Scenario: New bucket appends
- GIVEN last time T
- WHEN a bar with time T+interval is upserted
- THEN it is appended, length grows by one

#### Scenario: Older bar ignored
- GIVEN last time T
- WHEN a bar with time < T is upserted
- THEN the series is unchanged (no reorder, no duplicate)

### Requirement: R4 — Pagination merge is lossless and ordered

`mergeCandles(older, existing)` MUST return the union deduped by `time`, ascending,
with `existing` winning on duplicates (the newer/fresher record is authoritative).

#### Scenario: Prepend keeps history
- GIVEN an existing series and an older page overlapping one candle
- WHEN merged
- THEN the result is ascending, unique by time, and existing values win on the overlap

### Requirement: R5 — Single write path in the adapter

The adapter (`chart.js`) MUST call `setData` ONLY for the initial history load and
for pagination prepends. During the live stream it MUST use `update()` exclusively
and MUST NOT issue a periodic `setData`. Overlays MUST advance via `update()` of
their latest point (never a full-overlay `setData` mid-stream). **Frame-channel
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
### Requirement: R6 — Active series reflect the forming/closed candle without deformation

At each bucket close the adapter MUST refresh EVERY active indicator series — the
price overlays (SMA, EMA, Bollinger, VWAP, …) AND the sub-pane series (RSI, MACD,
Stochastic, ATR, Volume) — so their points stay aligned to the candles. The refresh
MUST advance each active series via `update()` of its LAST point and MUST NOT
realign any series via a full-series `setData` that shifts existing points. A
toggle or per-indicator param change is a CONFIG change: it MUST rebuild the request
set and refetch via the history path (`setData`), exactly like a symbol/interval
switch — that is not a mid-stream write.

#### Scenario: Every active series advances on close

- GIVEN the chart with multiple overlays and panes active
- WHEN a candle closes
- THEN each active series' last point is updated via `update()` to time T (aligned)

#### Scenario: No mid-stream setData

- GIVEN the chart streaming with panes active
- WHEN several candles close
- THEN `setData` is not invoked by the close refresh (spy); only `update` is

#### Scenario: Toggle uses the history path

- GIVEN an active chart
- WHEN an indicator toggle or param changes
- THEN the adapter refetches history and applies it via `setData` (allowed config path), with no incremental pane surgery

#### Scenario: No series deforms on refresh

- GIVEN a closed candle at time T
- WHEN overlays/pane series are refreshed
- THEN no existing point moves between bars (only the last point advances)

### Requirement: R7 — Invariants preserved

`src/` MUST remain framework-free (boundary green); `requirements.txt` MUST be
unchanged; no npm/build; the CSP MUST NOT be relaxed; read-only (no order surface);
the core JS is verified by `node --test` (not Python coverage).

#### Scenario: CSP unchanged, no new dependency
- GIVEN the change
- WHEN CSP and `requirements.txt`/`package.json` are inspected
- THEN CSP equals the prior value and no runtime dependency was added
