# chart-live-stream Specification

## Purpose

A framework-free core (pure timeline/series math) plus an adapter that renders a
consistent live chart: one write path for history/pagination (`setData`), one for
the live stream (`update`). New capability — no prior spec.

## Requirements

### Requirement: R1 — Pure series core, no environment dependency

`chart-core.js` MUST be a pure module (no DOM, no chart library, no network,
no global state) exposing `bucketTime`, `upsertCandle`, `mergeCandles`,
`lastPoint`. It MUST load in Node (CommonJS `require`) and in the browser
(`window.ChartCore`) from the same source.

#### Scenario: Loads in Node and browser
- GIVEN the module
- WHEN required in Node and when loaded in a browser
- THEN both expose the same functions

#### Scenario: No environment coupling
- GIVEN the core source
- WHEN inspected
- THEN it references no `document`, `window` (except an export shim), `fetch`, or chart API

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
their latest point (never a full-overlay `setData` mid-stream).

#### Scenario: No setData during the stream
- GIVEN the chart receiving WS pushes
- WHEN several candles arrive
- THEN `setData` is not called; only `update` is (asserted by a spy)

#### Scenario: Live series is monotonic
- GIVEN consecutive pushes
- WHEN the series length is sampled between pushes
- THEN it never decreases

### Requirement: R6 — Overlays reflect the forming/closed candle without deformation

At each bucket close the adapter MUST refresh the overlays (SMA/EMA/RSI) so the
indicator points stay aligned to the candles; it MUST NOT realign overlays via a
full-series `setData` that shifts existing points.

#### Scenario: Overlay point aligns to its candle
- GIVEN a closed candle at time T
- WHEN overlays are refreshed
- THEN the overlay's last point has time T (aligned), with no points moving between bars

### Requirement: R7 — Invariants preserved

`src/` MUST remain framework-free (boundary green); `requirements.txt` MUST be
unchanged; no npm/build; the CSP MUST NOT be relaxed; read-only (no order surface);
the core JS is verified by `node --test` (not Python coverage).

#### Scenario: CSP unchanged, no new dependency
- GIVEN the change
- WHEN CSP and `requirements.txt`/`package.json` are inspected
- THEN CSP equals the prior value and no runtime dependency was added
