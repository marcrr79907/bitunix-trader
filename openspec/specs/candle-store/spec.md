# candle-store Specification

## Purpose

Persist OHLC candles in a durable, queryable dataset independent of BitUnix's ephemeral ~3-year API depth: one global table, a one-time resumable backfill, and continuous closed-candle ingestion that never disturbs tick ingestion.

## Requirements

### Requirement: R1 — Global Candle model

The `trading` app MUST define a GLOBAL `Candle` model: no `user` FK and MUST NOT inherit `UserOwnedModel`. Entity contract:

| Field | Type | Note |
|---|---|---|
| `symbol` | Char(32) | e.g. `BTCUSDT` |
| `interval` | Char(8) | `5m`,`15m`,`1h`,`2h`,`4h`,`1d`,`1w`,`1M` |
| `time` | BigInt | candle OPEN time, UNIX **seconds** |
| `open`/`high`/`low`/`close` | Float | |
| `quote_vol` | Float(null) | from BitUnix `quoteVol` |

It MUST carry `UniqueConstraint(symbol, interval, time)` and a composite index `(symbol, interval, time)`.

#### Scenario: Global model carries no owner

- GIVEN `Candle`, WHEN inspected, THEN it has no `user` field and does not inherit `UserOwnedModel`

#### Scenario: Unique key is (symbol, interval, time)

- GIVEN a persisted candle, WHEN a row with the same `(symbol, interval, time)` is inserted, THEN the constraint rejects it

#### Scenario: Composite index present

- GIVEN the model metadata, WHEN indexes are inspected, THEN a `(symbol, interval, time)` index exists

### Requirement: R2 — Additive migration

The change MUST add an auto-generated additive migration `trading/0003_*` creating only the `candles` table. Existing tables MUST be untouched and `makemigrations --check` MUST stay green.

#### Scenario: Schema check green

- GIVEN the committed migration, WHEN `makemigrations --check --dry-run` runs, THEN no pending changes are reported

#### Scenario: No destructive operation

- GIVEN the migration, WHEN applied, THEN it only creates the candles table

### Requirement: R3 — Backfill command

`manage.py backfill_candles` MUST paginate **backward** via `endTime`, per symbol × interval (5m, 15m, 1h, 2h, 4h, 1d, 1w, 1M — NOT 1m), until BitUnix depth is exhausted or `--start` is reached. It MUST be idempotent (re-run inserts 0 new rows), resumable (restart from the oldest stored `time`), throttled to ≤10 req/s via an injectable sleep, and MUST persist nothing under `--dry-run`. It MUST log one line per page.

#### Scenario: Backward pagination advances the cursor

- GIVEN a stub client returning 200 rows, WHEN a page is fetched, THEN the next `endTime` is derived from the oldest row's `time`

#### Scenario: Empty page ends the series

- GIVEN the stub returns `[]`, WHEN the loop runs, THEN it stops that series without error

#### Scenario: --start bounds the earliest candle

- GIVEN `--start` set, WHEN pagination reaches it, THEN no earlier candle is requested

#### Scenario: Idempotent re-run

- GIVEN a completed backfill, WHEN the same range is re-run, THEN 0 new rows are inserted

#### Scenario: Resume from oldest stored time

- GIVEN stored candles with `Min(time)=T`, WHEN the command starts, THEN it queries from `T`-1, not from `now`

#### Scenario: --dry-run persists nothing

- GIVEN `--dry-run`, WHEN the command completes, THEN the row count is unchanged

#### Scenario: Throttle without real sleeps

- GIVEN an injected fake sleep, WHEN pages are fetched, THEN sleep is called between requests and no real delay occurs

### Requirement: R4 — Continuous closed-candle ingestion

The worker MUST append a candle cycle to its existing loop that fetches per symbol × interval and persists **only CLOSED candles**. A candle is closed when its bucket window has fully elapsed (`now ≥ time + interval_seconds`); the FORMING candle MUST NOT be persisted. The interval-seconds mapping for 1w/1M MUST use the design-pinned values. A candle-persistence failure MUST NOT degrade existing funding/ticker ingestion (errors isolated per cycle).

#### Scenario: Forming candle not persisted

- GIVEN a fetch whose newest candle bucket has not elapsed, WHEN the cycle runs, THEN that candle is absent from the table

#### Scenario: Closed candle persisted

- GIVEN a fetch containing a candle whose bucket elapsed, WHEN the cycle runs, THEN it is persisted

#### Scenario: Tick ingestion unaffected

- GIVEN candle persistence raises, WHEN the cycle runs, THEN funding/ticker ingestion still completes and the loop survives

#### Scenario: Repeat cycle is idempotent

- GIVEN the same closed candle across two cycles, WHEN both run, THEN only one row exists

### Requirement: R5 — Read-only, no order surface

The change MUST NOT add any order-execution endpoint, verb, or mutating API call; the order scanner MUST stay clean.

#### Scenario: No order surface added

- GIVEN the new model, command, and worker code, WHEN the order scanner runs, THEN no offender is reported

### Requirement: R6 — Boundary and no new runtime dependency

`src/` MUST stay framework-free; `web/` MAY import core. `requirements.txt` MUST remain unchanged.

#### Scenario: Core boundary green

- GIVEN the change, WHEN `tests/test_boundary.py` runs, THEN `src/` imports no framework

#### Scenario: No runtime dependency added

- GIVEN the change, WHEN `requirements.txt` is inspected, THEN no runtime dependency was added

### Requirement: R7 — Volumetry documented

The change MUST document expected volumetry: rows per interval per symbol per year, the total (~623,676 rows/yr across all intervals and symbols), and the backfill estimate (~1.87M rows for ~3y × 4 symbols).

#### Scenario: Volumetry figures recorded

- GIVEN the change docs, WHEN the volumetric section is read, THEN per-interval and total backfill/growth figures are stated
