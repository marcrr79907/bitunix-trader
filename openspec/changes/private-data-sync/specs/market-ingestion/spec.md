# Delta for market-ingestion

Fase 6b adds an isolated private-sync step to the existing worker cycle. R1–R3,
R5–R7 are unchanged; R4 gains an ADDED requirement (the loop behavior itself is
not modified).

## ADDED Requirements

### Requirement: R4b — Isolated private-sync step in the cycle

The worker cycle MUST run a private-data-sync step AFTER ticks + candles, in its
own isolated `try/except` (the candle-cycle pattern). A private-sync failure
MUST NOT degrade global ingestion nor kill the loop, and the `(funding, ticker)`
return contract MUST be unchanged. With no active credentials the step MUST be a
no-op and the cycle MUST still succeed.

#### Scenario: Cycle still ingests beside the private step

- GIVEN a stub market client and the private step
- WHEN `run_once` runs
- THEN funding/ticker counts are returned and the private step ran

#### Scenario: Private failure is isolated

- GIVEN the private-sync step raising
- WHEN `run_once` returns
- THEN the `(funding, ticker)` contract is preserved and the loop continues

#### Scenario: No active credentials is a no-op

- GIVEN no active credentials
- WHEN the cycle runs
- THEN the private step performs no fetch and the cycle returns 0 from `run_loop`
