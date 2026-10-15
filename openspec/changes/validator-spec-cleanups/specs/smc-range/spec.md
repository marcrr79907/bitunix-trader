# Delta for smc-range

Issue #147 (DEBT-6, W2) — **clarifying delta only**: records the `range_ is None`
case that `classify_price` already implements and that `test_smc_range.py` already
asserts. No code change.

## MODIFIED Requirements

### Requirement: R2 — Premium / discount classification

`classify_price(price, range_)` MUST return `"premium"` when `price >
range_.equilibrium`, `"discount"` when `price < range_.equilibrium`, and
`"equilibrium"` when equal. When `range_` is `None` (no dealing range available),
it MUST return `"equilibrium"`. The function MUST be pure and MUST NOT raise on any
finite input.
(Previously: the `range_ is None` case was not stated in the requirement.)

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

#### Scenario: None range is equilibrium

- GIVEN `range_ = None`
- WHEN `classify_price(101.0, None)` runs
- THEN it returns `"equilibrium"` without raising

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
| `range_ is None` passed to `classify_price` | `"equilibrium"` |
