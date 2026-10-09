# Delta for market-ingestion

## MODIFIED Requirements

### Requirement: R5 — Scheduler stays a stub

`web/scheduler.py` MUST remain boot-only; any shared helper (`idle_loop`) MUST stay compatible so both services boot. Scheduled batch work MUST be delegated to the platform (Railway cron services), NOT implemented as an in-process loop in this service.
(Previously: R5 only stated the scheduler stays a boot-only stub, without naming the platform cron mechanism.)

#### Scenario: Both services boot

- GIVEN the worker and scheduler modules, WHEN each boots one iteration, THEN both return 0

#### Scenario: No in-process scheduling added

- GIVEN `web/scheduler.py`, WHEN inspected, THEN it schedules nothing and Railway cron is the scheduling mechanism

## ADDED Requirements

### Requirement: R8 — Tick retention window

`FundingSnapshot`/`TickerSnapshot` writes MUST remain unchanged, but the tables MUST be bounded by a retention window enforced by `prune_snapshots` (7 days). `Candle` retention MUST remain indefinite.

#### Scenario: Writes unchanged, reads bounded

- GIVEN 30s tick ingestion, WHEN the change is applied, THEN persistence is unchanged and only a periodic prune bounds table size

#### Scenario: Candle retention indefinite

- GIVEN the retention policy, WHEN inspected, THEN no prune touches `Candle`
