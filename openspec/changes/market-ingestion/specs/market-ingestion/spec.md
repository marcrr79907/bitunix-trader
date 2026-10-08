# market-ingestion Specification

## Purpose

Turn the boot-only worker into a real **global market ingester**: poll the two read-only public endpoints (tickers + funding) and idempotently persist snapshots shared by all users.

## Requirements

### Requirement: R1 — Global snapshot models

Both models MUST be GLOBAL: no `user` FK, MUST NOT inherit `UserOwnedModel`, each MUST have `UniqueConstraint(fields=["symbol", "ts"])`.

- `FundingSnapshot`: `symbol` Char(32); `ts` DateTime (UTC); `funding_rate`/`mark_price`/`index_price` Float(null); `next_funding_time` BigInt(null, raw epoch ms); `funding_interval` Int(null).
- `TickerSnapshot`: `symbol` Char(32); `ts` DateTime (UTC); `last_price`/`high`/`low`/`quote_vol` Float(null).

#### Scenario: Global models carry no owner

- GIVEN the two models, WHEN inspected, THEN neither has a `user` field nor inherits `UserOwnedModel`

#### Scenario: (symbol, ts) is unique

- GIVEN a persisted `FundingSnapshot`, WHEN a row with the same `(symbol, ts)` is inserted, THEN the constraint rejects it

### Requirement: R2 — Idempotent persistence

Persisting the same rows twice MUST insert **0** new rows via `bulk_create(ignore_conflicts=True)` and the unique constraint.

#### Scenario: Re-persist is a no-op

- GIVEN rows persisted once, WHEN the identical rows are persisted again, THEN the row count is unchanged

### Requirement: R3 — Ingestion service

`fetch_market(client, symbols)` MUST read the funding and ticker endpoints read-only; `persist_market(...)` MUST write model-ready rows. It MUST do no I/O besides read-only GETs, MUST NOT call any order endpoint, MUST convert epoch-ms → UTC once at the boundary (`tz=utc`), and MUST keep `next_funding_time` raw epoch ms.

#### Scenario: Round-trip

- GIVEN a stub client returning funding and ticker fixtures for two symbols, WHEN `fetch_market` then `persist_market` run, THEN the expected counts are persisted

#### Scenario: UTC persisted, epoch kept raw

- GIVEN a row with a millisecond timestamp, WHEN persisted, THEN `ts` is UTC-aware and `next_funding_time` is an integer epoch ms

#### Scenario: Empty input

- GIVEN an empty symbols list or API response, WHEN ingestion runs, THEN it does not raise and persists 0 rows

### Requirement: R4 — Worker loop

The worker MUST run a real loop polling on `INGEST_POLL_SECONDS` (default 30), backing off `min(backoff*2, 300)` on `BitunixError`/`RequestException`, logging one line per cycle, and exiting between cycles (return 0) on SIGTERM/SIGINT. It MUST be testable via an injected stub client and injectable iterations/stop/sleep — no real sleeps or sockets.

#### Scenario: One cycle ingests

- GIVEN a stub client and one iteration, WHEN the loop runs, THEN it ingests the expected counts and returns 0

#### Scenario: Backoff then recovery

- GIVEN a client that raises once, WHEN the loop runs, THEN it backs off, recovers next cycle, and does not crash

#### Scenario: Clean stop

- GIVEN the stop flag is set, WHEN the loop reaches the next boundary, THEN it exits between cycles and returns 0

### Requirement: R5 — Scheduler stays a stub

`web/scheduler.py` MUST remain boot-only; any shared helper (`idle_loop`) MUST stay compatible so both services boot.

#### Scenario: Both services boot

- GIVEN the worker and scheduler modules, WHEN each boots one iteration, THEN both return 0

### Requirement: R6 — Boundary preserved

`src/` MUST remain framework-free. This adds the first `web/ → src/` import; the reverse MUST NOT occur. `tests/test_boundary.py` and `core-isolation` CI MUST stay green; the migration is additive and the owned-model guard is unchanged.

#### Scenario: Core has no Django import

- GIVEN files under `src/`, WHEN the boundary test scans them, THEN none imports Django

#### Scenario: Web may depend on core

- GIVEN worker/ingest importing `src.client`, `src.monitor`, `src.config`, WHEN the boundary test runs, THEN the import is permitted

### Requirement: R7 — Read-only, no new dependency

The change MUST NOT add any order-execution surface; `requirements.txt` MUST remain unchanged (no RQ).

#### Scenario: No order endpoint in new code

- GIVEN the new ingest and worker code, WHEN the order scanner runs, THEN no order endpoint string or verb is reported

#### Scenario: Dependency file unchanged

- GIVEN the change, WHEN `requirements.txt` is inspected, THEN no runtime dependency was added
