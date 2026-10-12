# smc-range Specification

## Purpose

Pure, deterministic dealing-range evaluation in `src/smc/range.py`: range
extremes, equilibrium (50%), and premium/discount classification. Consumes OHLC
lists only; no I/O, stdlib only. New capability — no prior spec.

**Frozen shape** (stdlib `NamedTuple`, field order fixed for C1/E1):

| Record | Fields (in order) |
|--------|-------------------|
| `DealingRange` | `high:float, low:float, equilibrium:float, index:int` |

## Requirements

### Requirement: R1 — Dealing range from fixed lookback

`dealing_range(highs, lows, *, lookback=RANGE_LOOKBACK)` MUST evaluate the last
`lookback` bars: `high = max(highs[-lookback:])`, `low = min(lows[-lookback:])`,
`equilibrium = (high + low) / 2`, and `index = len(highs) - 1` (the last bar). It
MUST return `None` when input is empty (never raise). It MUST NOT use structure
extremes in v1. Mismatched-length input MUST return `None` without raising.

#### Scenario: Range over the last N bars

- GIVEN `highs=[1,5,3]`, `lows=[0,2,1]`, `lookback=3`
- WHEN `dealing_range` runs
- THEN `DealingRange(high=5.0, low=0.0, equilibrium=2.5, index=2)` is returned

#### Scenario: Lookback window truncates

- GIVEN `highs=[9,1,5,3]`, `lookback=2`
- WHEN it runs
- THEN only the last 2 bars are used (`high=5.0`, `low=1.0`)

#### Scenario: Empty input returns None

- GIVEN `highs=[]`/`lows=[]`
- WHEN it runs
- THEN it returns `None` without raising

### Requirement: R2 — Premium / discount classification

`classify_price(price, range_)` MUST return `"premium"` when `price >
range_.equilibrium`, `"discount"` when `price < range_.equilibrium`, and
`"equilibrium"` when equal. The function MUST be pure and MUST NOT raise on any
finite input.

#### Scenario: Above equilibrium is premium

- GIVEN `range_` with `equilibrium=100.0`
- WHEN `classify_price(101.0, range_)` runs
- THEN it returns `"premium"`

#### Scenario: Below equilibrium is discount

- GIVEN `range_` with `equilibrium=100.0`
- WHEN `classify_price(99.0, range_)` runs
- THEN it returns `"discount"`

#### Scenario: Exactly at equilibrium

- GIVEN `range_` with `equilibrium=100.0`
- WHEN `classify_price(100.0, range_)` runs
- THEN it returns `"equilibrium"`

### Requirement: R3 — Determinism, purity, never-raise

Every function MUST be pure (same input + params → byte-identical output), MUST
NOT mutate inputs, and MUST NOT use `datetime`, `random`, I/O, or global mutable
state. `DealingRange` MUST be a stdlib `NamedTuple`. Empty or mismatched-length
input MUST return `None` and MUST NOT raise.

#### Scenario: Repeatable and non-mutating

- GIVEN any OHLC lists
- WHEN `dealing_range` runs twice
- THEN outputs are equal and the inputs are unchanged

**Edge-case matrix**

| Input / condition | Result |
|-------------------|--------|
| empty series | `None` |
| `len(highs) != len(lows)` | `None` |
| `lookback <= 0` | `None` (or `[]`-equivalent, no raise) |
| `lookback` larger than series | range over the whole series |
| flat market (`high == low`) | `equilibrium == high == low` |
| price exactly at equilibrium | `"equilibrium"` |
