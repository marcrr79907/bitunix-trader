# trade-metrics Specification

## Purpose

Pure performance math living in `src/metrics.py`. Lists of realized-PnL numbers in, numbers or lists out; no I/O, timestamp-agnostic, stdlib only. Complementary to `journal.metrics()` (accounting over SQLite rows) and MUST NOT change it. New capability — no prior spec.

## Requirements

### Requirement: R1 — Pure metric functions

`src/metrics.py` MUST expose `expectancy`, `profit_factor`, `r_multiple`, `equity_curve`. Each MUST be pure and MUST NOT perform I/O or mutate inputs.

#### Scenario: Deterministic output
- GIVEN identical inputs
- WHEN a function is called twice
- THEN both results are equal

### Requirement: R2 — Expectancy

`expectancy(pnls: list[float]) -> float | None` MUST return the mean realized PnL per trade. For an empty sequence it MUST return `None` (no trades → undefined, not a raise).

#### Scenario: Mean of PnL
- GIVEN `pnls = [10.0, -5.0, 5.0]`
- WHEN `expectancy` runs
- THEN the result is `3.333...` (within float tolerance)

#### Scenario: Empty input
- GIVEN `pnls = []`
- WHEN `expectancy` runs
- THEN the result is `None`

### Requirement: R3 — Profit factor

`profit_factor(pnls: list[float]) -> float | None` MUST return `gross_profit / gross_loss`, where `gross_profit` is the sum of positive values and `gross_loss` is the absolute sum of negative values.

When `gross_loss == 0` (no losing trades) the function MUST return `None`. Rationale: `float("inf")` is not serializable to JSON and cannot round-trip through the future API; `None` is an explicit, testable "undefined" signal the UI can render as `—` / "∞".

#### Scenario: Normal ratio
- GIVEN `pnls = [10.0, -5.0, 20.0]`
- WHEN `profit_factor` runs
- THEN the result is `6.0` (30 / 5)

#### Scenario: No losses
- GIVEN `pnls = [10.0, 20.0]`
- WHEN `profit_factor` runs
- THEN the result is `None`

#### Scenario: Empty input
- GIVEN `pnls = []`
- WHEN `profit_factor` runs
- THEN the result is `None`

### Requirement: R4 — R-multiple

`r_multiple(pnl: float, risk: float) -> float | None` MUST return `pnl / risk`, where `risk` is the initial-risk denominator (distance to stop × size, pre-computed by the caller). When `risk == 0` the function MUST return `None` and MUST NOT raise.

#### Scenario: Winning trade
- GIVEN `pnl = 30.0` and `risk = 10.0`
- WHEN `r_multiple` runs
- THEN the result is `3.0`

#### Scenario: Zero risk guard
- GIVEN `risk = 0`
- WHEN `r_multiple` runs
- THEN the result is `None` and no exception is raised

### Requirement: R5 — Equity curve

`equity_curve(pnls: list[float]) -> list[float]` MUST return the cumulative running sum of realized PnL, with the SAME length as the input and starting from the first value. It MUST be timestamp-agnostic: it takes no time argument, because timestamps belong to UI/persistence concerns in later phases. Empty input MUST return `[]`.

#### Scenario: Running sum
- GIVEN `pnls = [5.0, -2.0, 3.0]`
- WHEN `equity_curve` runs
- THEN the result is `[5.0, 3.0, 6.0]`

#### Scenario: Length preserved
- GIVEN a sequence of length `n`
- WHEN `equity_curve` runs
- THEN the output length equals `n`

#### Scenario: Empty input
- GIVEN `pnls = []`
- WHEN `equity_curve` runs
- THEN the result is `[]`

### Requirement: R6 — No overlap with journal metrics

`journal.metrics()` MUST remain unchanged. `src/metrics.py` MUST NOT import `sqlite3`, `src.journal`, or `src.db`; it operates only on caller-supplied sequences.

#### Scenario: Journal untouched
- GIVEN the existing `journal.metrics()` behavior
- WHEN this change ships
- THEN its signature and results are unchanged

### Requirement: R7 — Stdlib-only boundary

`src/metrics.py` MUST import only the standard library (`math`, `statistics` allowed). It MUST NOT import Django, `requests`, `rich`, `src.client`, or `src.monitor`, and MUST NOT perform network calls or order operations. `tests/test_boundary.py` MUST remain green.

#### Scenario: Boundary test stays green
- GIVEN the new module
- WHEN `python -m pytest tests/test_boundary.py` runs
- THEN all boundary tests pass
