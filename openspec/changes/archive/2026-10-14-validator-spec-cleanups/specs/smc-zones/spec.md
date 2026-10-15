# Delta for smc-zones

Issue #147 (DEBT-6, W4) — **clarifying delta only**: records the confirmed-swings
≤2-bar look-ahead nuance as a known intentional simplification. No code change.

## MODIFIED Requirements

### Requirement: R4 — Liquidity sweeps

`find_liquidity_sweeps(highs, lows, closes, swings, *, lookback=SWEEP_LOOKBACK)`
MUST emit a `Sweep` at bar `t` when a confirmed swing within `lookback` bars
before `t` is wicked beyond and price closes back inside the level. A swing low is
swept when `lows[t] < swing.price` AND `closes[t] > swing.price` →
`Sweep("low", t, swing.price, "bullish")`. A swing high is swept when
`highs[t] > swing.price` AND `closes[t] < swing.price` →
`Sweep("high", t, swing.price, "bearish")`. At most the MOST RECENT qualifying
swing per side per bar MUST emit. Output MUST be ordered by `index`.

**Known simplification — confirmed-swings-only, ≤2-bar look-ahead (W4).** The
finder consumes only swings already emitted by B1 (`find_swings` stops at
`n - right`, so a swing at index `s` is confirmed `right` (=2) bars later). It
iterates `t` and considers any `s` with `s.index <= t` and `t - s.index <=
lookback`, with no explicit `s.index + right <= t` guard. Because only confirmed
swings are handed back, a bar `t` can "see" a swing whose confirmation bar is
after `t` only within a ≤2-bar edge window. This is an intentional simplification
(no re-look-ahead guard), documented here, not a defect.

#### Scenario: Bullish sweep of a low

- GIVEN swing low at `100.0`, bar `t` with `lows[t]=99.5`, `closes[t]=100.5`
- WHEN `find_liquidity_sweeps` runs
- THEN `Sweep("low", t, 100.0, "bullish")` is emitted

#### Scenario: Bearish sweep of a high

- GIVEN swing high at `110.0`, bar `t` with `highs[t]=110.5`, `closes[t]=109.0`
- WHEN it runs
- THEN `Sweep("high", t, 110.0, "bearish")` is emitted

#### Scenario: Close does not return inside

- GIVEN `lows[t] < swing.price` but `closes[t] <= swing.price`
- WHEN it runs
- THEN no `Sweep` is emitted

#### Scenario: Stale level outside lookback

- GIVEN a swing more than `lookback` bars before `t`
- WHEN it runs
- THEN it is not considered for a sweep

#### Scenario: ≤2-bar confirmation edge is permitted

- GIVEN a confirmed swing at index `s` whose confirmation bar (`s.index + 2`) is at or after `t`
- WHEN `t - s.index <= lookback` and the wick/close conditions hold
- THEN a `Sweep` MAY be emitted at `t` (≤2-bar look-ahead is by design)

### Requirement: R5 — Determinism, purity, never-raise

Every finder MUST be pure (same input + params → byte-identical output), MUST NOT
mutate inputs, and MUST NOT use `datetime`, `random`, I/O, or global mutable
state. Records MUST be stdlib `NamedTuple`. Empty, too-short, or
mismatched-length input MUST return `[]` and MUST NOT raise.

#### Scenario: Empty in, empty out

- GIVEN empty OHLC lists
- WHEN any finder runs
- THEN it returns `[]` without raising

**Edge-case matrix**

| Input / condition | Result |
|-------------------|--------|
| `len(highs) != len(lows)` | `[]` |
| fewer than 3 bars for FVG | `[]` |
| no `bos` events | no `OrderBlock` |
| no opposite candle in OB window | no `OrderBlock` |
| gap `< min_gap` | no `FVG` |
| `tolerance=0.0`, unequal prices | no `EqualLevel` |
| sweep wick without close-back-inside | no `Sweep` |
| swing older than `lookback` | not sweepable |
| swing within ≤2 bars of confirmation (confirmed-swings-only) | sweepable at the edge bar (by design) |
| overlapping zones | separate records, never merged |
