# Delta for technical-indicators

Issue #70 (Fase A1): the pure module gains `macd`, `bollinger`, `stochastic` with
the SAME contract as the existing functions (index-aligned, leading `None`
warm-up, no mutation, no I/O, stdlib only). R1, R2 and R4 are MODIFIED.

## MODIFIED Requirements

### Requirement: R1 — Pure indicator functions

`src/indicators.py` MUST expose `sma`, `ema`, `rsi`, `atr`, `vwap`, `zscore`,
`macd`, `bollinger`, `stochastic`. Each MUST be pure (same input → same output)
and MUST NOT perform I/O, mutate inputs, or read global state. New functions MUST
have these EXACT contracts:

- `macd(series, fast=12, slow=26, signal=9) -> tuple[list, list, list]` returning
  `(macd_line, signal_line, histogram)`. `macd_line = ema(series, fast) -
  ema(series, slow)` (`None` where either leg is `None`); `signal_line` is `ema`
  over the valid suffix of `macd_line`, left-padded with `slow-1` `None`s;
  `histogram = macd_line - signal_line`.
- `bollinger(series, window=20, num_std=2) -> tuple[list, list, list]` returning
  `(upper, middle, lower)`. `middle = sma(series, window)`;
  `upper = middle + num_std*sd`; `lower = middle - num_std*sd`, where `sd` is the
  window's population standard deviation (`statistics.pstdev`).
- `stochastic(highs, lows, closes, k=14, d=3) -> tuple[list, list]` returning
  `(%K, %D)`. `%K[i] = 100 * (close[i] - min(low[i-k+1:i+1])) /
  (max(high[i-k+1:i+1]) - min(low[i-k+1:i+1]))`; `%D` is `sma` of the valid `%K`
  suffix, left-padded with `k-1` `None`s.

(Previously: exposed only `sma`, `ema`, `rsi`, `atr`, `vwap`, `zscore`.)

#### Scenario: Deterministic output

- GIVEN identical input sequences and parameters
- WHEN a function is called twice
- THEN both results are equal

#### Scenario: Inputs are not mutated

- GIVEN an input list
- WHEN any function runs
- THEN the original list is unchanged

#### Scenario: MACD exact values, small window

- GIVEN `macd([1,2,3,4,5], fast=2, slow=3, signal=2)`
- WHEN it runs
- THEN it returns `([None,None,0.5,0.5,0.5], [None,None,None,0.5,0.5], [None,None,None,0.0,0.0])`
- AND each array length equals the input length

#### Scenario: Bollinger exact values, small window

- GIVEN `bollinger([1,2,3,4,5], window=3, num_std=2)`
- WHEN it runs
- THEN index 2 is `upper≈3.633`, `middle=2.0`, `lower≈0.367` (2/√3 ≈ 1.633 band)
- AND each array length equals the input length

#### Scenario: Stochastic exact values, small window

- GIVEN `stochastic([3,3,3], [1,1,1], [1,2,3], k=2, d=2)`
- WHEN it runs
- THEN `%K = [None, 50.0, 100.0]` and `%D = [None, None, 75.0]`

#### Scenario: Stochastic bounded

- GIVEN any valid OHLC series
- WHEN `stochastic` runs
- THEN every non-`None` `%K`/`%D` value is within `[0, 100]`

#### Scenario: Bollinger band ordering

- GIVEN any valid price series
- WHEN `bollinger` runs
- THEN for every computed index `lower <= middle <= upper`

### Requirement: R2 — Warm-up alignment

Every series output MUST have the SAME length as its input. Positions that cannot
be computed MUST be `None`. The warm-up length per function is fixed and
documented:

| Function | Warm-up (leading `None`s) | First valid index |
|---|---|---|
| `sma(series, window)` | `window - 1` | `window - 1` |
| `ema(series, window)` | `window - 1` (seed = SMA) | `window - 1` |
| `rsi(series, window)` | `window` (needs `window` deltas = `window + 1` prices) | `window` |
| `atr(highs, lows, closes, window)` | `window` (TR needs a prior close) | `window` |
| `vwap(highs, lows, closes, volumes)` | `0` (cumulative per bar) | `0` |
| `zscore(series, window)` | `window - 1` | `window - 1` |
| `macd(series, fast, slow, signal)` | line `slow-1`; signal/histogram `slow-1 + signal-1` | line 25 / signal 33 (defaults) |
| `bollinger(series, window, num_std)` | `window - 1` | 19 (default) |
| `stochastic(highs, lows, closes, k, d)` | `%K` `k-1`; `%D` `k-1 + d-1` | `%K` 13 / `%D` 15 (defaults) |

Rationale: index alignment with the input avoids silent truncation and lets charts
overlay the series without offset bookkeeping. (Previously: table covered only the
six original functions.)

#### Scenario: Length preserved for every function

- GIVEN a series of length `n`
- WHEN any indicator runs
- THEN the output length equals `n`

#### Scenario: Leading warm-up is `None`

- GIVEN `sma([1,2,3,4], 3)`
- WHEN it runs
- THEN the result is `[None, None, 2.0, 3.0]` (length 4, warm-up 2)

#### Scenario: RSI warm-up

- GIVEN `rsi(prices, 14)` with at least 15 prices
- WHEN it runs
- THEN the first 14 positions are `None` and index 14 is the first number

#### Scenario: MACD warm-up is 33 with defaults

- GIVEN `macd(series)` with defaults and at least 34 values
- WHEN it runs
- THEN `macd_line[24]` is `None` and `macd_line[25]` is the first number
- AND `signal_line[32]` is `None` and `signal_line[33]` is the first number

#### Scenario: Bollinger and Stochastic warm-up

- GIVEN `bollinger(series, 20, 2)` and `stochastic(h, l, c, 14, 3)` on series of sufficient length
- WHEN they run
- THEN Bollinger index 18 is `None` and index 19 is the first number
- AND Stochastic `%K[12]` is `None`/`%K[13]` first, `%D[14]` is `None`/`%D[15]` first

### Requirement: R4 — Divide-by-zero and zero-range guards

When a position is mathematically undefined, the function MUST return `None` for
that position and MUST NOT raise, EXCEPT `bollinger`, which MUST collapse its
bands (see below):

- `rsi`: average loss is `0` → `None` for that position.
- `zscore`: rolling standard deviation is `0` → `None`.
- `vwap`: cumulative volume is `0` → `None`.
- `sma`/`ema`/`atr`: `window < 1` → `None` for all positions.
- `bollinger`: rolling standard deviation is `0` (flat window) → the bands MUST
  collapse to the middle: `upper == middle == lower == sma`. It MUST NOT return
  `None` and MUST NOT raise — a flat market legitimately has zero deviation.
- `stochastic`: `max(high) - min(low)` over the window is `0` → `%K` is `None`
  for that position (and `%D` follows from the valid `%K` suffix). It MUST NOT
  raise.

(Previously: guards covered only `rsi`, `zscore`, `vwap`, `sma`/`ema`/`atr`.)

#### Scenario: RSI with no losses

- GIVEN a strictly rising price series
- WHEN `rsi` runs
- THEN positions with zero average loss are `None` (never a raise or `inf`)

#### Scenario: Z-score on a flat window

- GIVEN a window where every value is equal
- WHEN `zscore` runs
- THEN that position is `None`

#### Scenario: VWAP with zero volume

- GIVEN bars whose cumulative volume is `0`
- WHEN `vwap` runs
- THEN those positions are `None`

#### Scenario: Bollinger flat window collapses bands

- GIVEN a flat window (every value equal, so `sd == 0`)
- WHEN `bollinger` runs
- THEN that position has `upper == middle == lower` (no `None`, no raise)

#### Scenario: Stochastic zero range is `None`

- GIVEN a window where `max(high) == min(low)`
- WHEN `stochastic` runs
- THEN that `%K` position is `None` and no exception is raised
