# Delta for chart-scales

Issue #146 (DEBT-5): the candle-series construction and the HA live write path
move into the new host-layer sub-module `chart-host-candles.js` (interface
frozen: `createCandles(chart, chartType) -> {getCandleSeries, getCandles,
setCandles, updateCandle, remove}`).

**Boundary note only — NO behavioral requirement changes.** CS1, CS2, CS3, CS5,
CS6, CS7 stay in force and unmodified. Only CS4 (HA live contract) gains a
module-location note; the contract itself (HA math, incremental state, `update()`
only) is preserved verbatim.

## MODIFIED Requirements

### Requirement: CS4 — Heikin Ashi live contract

The host MUST carry incremental HA state (`lastHaOpen`/`lastHaClose`) and MUST
apply HA to both history and live data. History (`setCandles`) MUST reset the HA
state and write the transformed series via `setData`; each live `updateCandle` MUST
transform the forming/current bar via `update()` only (#68). A new bar MUST derive
its `haOpen` from the previous bar's HA state.

As of #146 the candle series construction, the raw candle array, and this
incremental HA state MUST live in the host-layer sub-module
`chart-host-candles.js` (`createCandles(chart, chartType)`), with `chart-host.js`
delegating `setCandles`/`updateCandle`/`getCandleSeries`/`getCandles`/teardown to
it. This is a module-boundary move with NO behavior change: the HA transform
still comes from the pure `chart-types-core.js` core, the raw candle array is
still returned by reference, and the C1 same-bucket `prevHa` rule MUST be
preserved verbatim.

(Previously: the candle channel and HA state lived inline in `chart-host.js`.)

#### Scenario: Live push uses update only

- GIVEN an active HA chart
- WHEN a WS push arrives
- THEN the transformed bar is applied via `update()` and no full-series `setData` occurs

#### Scenario: New bar chains HA state

- GIVEN HA history ending at bar N
- WHEN the first push of bar N+1 arrives
- THEN its `haOpen = (prevHaOpen+prevHaClose)/2`

#### Scenario: setCandles resets HA state

- GIVEN prior HA state
- WHEN `setCandles` loads a fresh page
- THEN the HA state is recomputed from the new first bar

#### Scenario: Non-HA types are untouched

- GIVEN `chartType="candles"`
- WHEN history/live writes run
- THEN bars are written verbatim (no transform)

#### Scenario: HA live contract is unchanged after extraction

- GIVEN an HA chart after the candle channel moved to `chart-host-candles.js`
- WHEN history loads and a live push lands on a new bar
- THEN behavior is byte-identical to before (C1 same-bucket `prevHa` rule
  preserved) and the raw candle array is the same reference that `upsertCandle`
  mutates
