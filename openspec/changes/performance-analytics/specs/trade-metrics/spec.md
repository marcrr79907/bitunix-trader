# Delta for trade-metrics

E1 ADDS three scalar metrics to `src/metrics.py`. R1–R7 are unchanged: the frozen
four (`expectancy`, `profit_factor`, `r_multiple`, `equity_curve`) and
`journal.metrics()` MUST NOT change. All additions are pure, stdlib-only and
never raise.

## ADDED Requirements

### Requirement: R8 — Max drawdown

`max_drawdown(equity: list[float]) -> float | None` MUST return the worst
peak-to-trough decline of an equity curve as a **non-positive** number
(`min(e - peak)` over the running peak, e.g. `-12.5`), not a ratio. The first
point is the initial peak. Empty input MUST return `None`. A monotonically
non-decreasing curve MUST return `0.0`.

#### Scenario: Peak then trough
- GIVEN `equity = [10.0, 5.0, 8.0, 2.0]`
- WHEN `max_drawdown` runs
- THEN the result is `-8.0` (peak 10 → trough 2)

#### Scenario: Empty input
- GIVEN `equity = []`
- WHEN it runs
- THEN the result is `None`

#### Scenario: All-win curve has no drawdown
- GIVEN `equity = [1.0, 2.0, 3.0]`
- WHEN it runs
- THEN the result is `0.0`

### Requirement: R9 — Win rate

`win_rate(pnls: list[float]) -> float | None` MUST return `wins / total * 100`,
where a win is `pnl > 0` (net semantics, mirroring `journal.metrics`). Empty input
MUST return `None`. An all-win input MUST return `100.0`; an all-loss input
(`pnl <= 0`) MUST return `0.0`.

#### Scenario: Mixed wins and losses
- GIVEN `pnls = [10.0, -5.0, 5.0]`
- WHEN `win_rate` runs
- THEN the result is `66.666...` (2/3 × 100, within tolerance)

#### Scenario: All-win and all-loss
- GIVEN `pnls = [1.0, 2.0]`, WHEN it runs, THEN `100.0`
- GIVEN `pnls = [0.0, -1.0]`, WHEN it runs, THEN `0.0` (a zero is not a win)

#### Scenario: Empty input
- GIVEN `pnls = []`
- WHEN it runs
- THEN the result is `None`

### Requirement: R10 — Net PnL

`net_pnl(pnls: list[float]) -> float` MUST return the sum of net realized PnL and
MUST return `0.0` for empty input (never `None`, never raise).

#### Scenario: Sum of nets
- GIVEN `pnls = [10.0, -5.0, 5.0]`
- WHEN `net_pnl` runs
- THEN the result is `10.0`

#### Scenario: Empty input is zero
- GIVEN `pnls = []`
- WHEN it runs
- THEN the result is `0.0`

### Requirement: R11 — Existing behavior preserved

The frozen `expectancy`, `profit_factor`, `r_multiple`, `equity_curve` and
`journal.metrics()` MUST be unchanged; the three additions MUST import stdlib only
and MUST NOT change R1–R7.

#### Scenario: Frozen four untouched
- GIVEN the pre-existing metric tests
- WHEN the full suite runs
- THEN all previously passing tests still pass and `journal.metrics()` is unchanged
