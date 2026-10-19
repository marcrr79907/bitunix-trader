# market-ingestion Specification

## Purpose

Turn the boot-only worker into a real **global market ingester**: poll the two read-only public endpoints (tickers + funding) and idempotently persist snapshots shared by all users. New capability — no prior spec.

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

> **F11 (#124) delta.** R7–R9 add the watchlist ingest set, due-interval
> scheduling, and the request budget. R1–R7 are unchanged; no schema change.

### Requirement: R7 — Union ingest set

The worker MUST ingest the union of `config.SYMBOLS` (always included first, never
starved) and every user's watchlist symbols, sorted for determinism, capped at
`MAX_INGEST_SYMBOLS = 50` (the same value reused by `MAX_WATCHLIST_SYMBOLS`). The union
MUST be read in `web/worker.py` (trust zone, unscoped allowed per R14.4), mirroring
`run_alert_rules` (`worker.py:162`). A removal from one user's watchlist MUST NOT stop
ingestion of a symbol that remains in `config.SYMBOLS`.

#### Scenario: Union is ordered and defaults first

- GIVEN `config.SYMBOLS = ["BTCUSDT"]` and watchlists containing `SOLUSDT`, `ETHUSDT`
- WHEN the cycle builds its ingest set
- THEN the set is `["BTCUSDT", "ETHUSDT", "SOLUSDT"]`

#### Scenario: Cap is enforced

- GIVEN 60 distinct symbols across defaults and watchlists
- WHEN the ingest set is built
- THEN it contains exactly 50 and every `config.SYMBOLS` entry is present

#### Scenario: A watchlist symbol is ingested

- GIVEN `DOGEUSDT` is in a user's watchlist but not in `config.SYMBOLS`
- WHEN a full cycle runs
- THEN closed candles are fetched for `DOGEUSDT`

#### Scenario: One symbol's failure is isolated

- GIVEN an upstream that raises for one ingest symbol
- WHEN the cycle runs
- THEN the remaining symbols are still ingested and the loop continues

### Requirement: R8 — Due-interval scheduling

A pure `due_intervals(now, last_poll)` in `web/trading/candles.py` MUST return only the
intervals whose bucket rolled over since `last_poll` (`now // span != last_poll //
span`). Each cycle MUST request only due intervals per symbol. `last_poll` MUST be
in-memory (no new table or column). A restart MAY produce one catch-up burst, absorbed
by the existing cycle throttle (`worker.py:220`).

#### Scenario: Nothing due inside a bucket

- GIVEN `last_poll` and `now` in the same 1h bucket
- WHEN `due_intervals` is called
- THEN `1h` is not returned

#### Scenario: Due at the bucket boundary

- GIVEN `last_poll` in the previous 1h bucket and `now` in the next
- WHEN `due_intervals` is called
- THEN `1h` is returned and `5m` is returned when its buckets also differ

#### Scenario: Restart burst is accepted

- GIVEN a fresh process with no `last_poll`
- WHEN the first cycle runs
- THEN every interval is due once and the throttle absorbs the burst without exceeding the budget

### Requirement: R9 — Request budget

Naive all-intervals polling MUST be replaced by R8. At the 50-symbol cap the
steady-state request rate MUST stay well under the exchange's 10 req/s (measured
≈ 0.25 req/s). The worker MUST NOT backfill exchange history into SQLite; older bars
stay upstream-served via `_fetch_window` (`quotes.py:558-587`).

#### Scenario: Steady state is under the budget

- GIVEN 50 ingest symbols and a 30 s cycle with due-interval scheduling
- WHEN requests per cycle are counted
- THEN the derived rate is below 1 req/s (≈ 0.25 req/s)

#### Scenario: Negative control — bypassing `due_intervals` exceeds the limit

- GIVEN all 8 intervals requested every cycle for 50 symbols
- WHEN the request rate is computed
- THEN it exceeds 10 req/s, proving the guard is the scheduling, not the throttle

#### Scenario: No history backfill

- GIVEN a chart request for a symbol with little persisted history
- WHEN the window is served
- THEN older bars come from upstream via `_fetch_window` and no bulk history write occurs
