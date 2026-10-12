# technical-indicators Specification

## Purpose

Pure, deterministic chart math living in `src/indicators.py`. Lists in, lists/numbers out; no I/O, no network, stdlib only. Functions MUST stay index-aligned with the input so a later chart overlay can zip them directly. New capability — no prior spec.

## Requirements

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

Every series output MUST have the SAME length as its input. Positions that cannot be computed MUST be `None`. The warm-up length per function is fixed and documented:

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

Rationale: index alignment with the input avoids silent truncation and lets charts overlay the series without offset bookkeeping.

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

### Requirement: R3 — Empty input handling

For every function, an empty input MUST return an empty output and MUST NOT raise.

#### Scenario: Empty in, empty out
- GIVEN an empty series
- WHEN any indicator runs
- THEN it returns `[]` (or `[]` for nested inputs) without raising

### Requirement: R4 — Divide-by-zero and zero-range guards

When a position is mathematically undefined, the function MUST return `None` for that position and MUST NOT raise, EXCEPT `bollinger`, which MUST collapse its bands (see below):

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

### Requirement: R5 — Indicator ranges

`rsi` values MUST be within `[0, 100]`. `atr` values MUST be non-negative.

#### Scenario: RSI bounded
- GIVEN any valid price series
- WHEN `rsi` runs
- THEN every non-`None` value is `0 <= value <= 100`

#### Scenario: ATR non-negative
- GIVEN any valid OHLC series
- WHEN `atr` runs
- THEN every non-`None` value is `>= 0`

### Requirement: R6 — VWAP uses typical price

`vwap` MUST compute each bar as the cumulative sum of `typical_price * volume` divided by cumulative volume, where `typical_price = (high + low + close) / 3`.

#### Scenario: Typical-price weighting
- GIVEN a single bar `high=3, low=1, close=2, volume=10`
- WHEN `vwap` runs
- THEN the value is `2.0`

### Requirement: R7 — Rolling Z-score

`zscore(series, window)` MUST be a rolling window statistic. Full-series z-score MAY be obtained by passing `window = len(series)`; no separate flag exists. Standard deviation MUST be the population standard deviation of the window.

#### Scenario: Full-series is a special case
- GIVEN a series of length `n`
- WHEN `zscore(series, window=n)` runs
- THEN only the final position is a number and the value uses the whole series

### Requirement: R8 — Stdlib-only boundary

`src/indicators.py` MUST import only the standard library (`math`, `statistics` allowed). It MUST NOT import Django, `requests`, `rich`, `src.client`, or `src.monitor`, and MUST NOT perform network calls or order operations. `tests/test_boundary.py` MUST remain green.

#### Scenario: Boundary test stays green
- GIVEN the new module
- WHEN `python -m pytest tests/test_boundary.py` runs
- THEN all boundary tests pass

#### Scenario: No forbidden import
- GIVEN a change adding `import requests` to the module
- WHEN the boundary/banned-import check runs
- THEN the check fails
