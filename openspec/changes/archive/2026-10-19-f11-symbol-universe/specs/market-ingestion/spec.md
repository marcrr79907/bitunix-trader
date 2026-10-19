# Delta for market-ingestion

Issue #124 (F11): the worker ingests `config.SYMBOLS` only (`worker.py:43-56` today,
`run_once(client, symbols)` → `fetch_closed_candles`), polling all 8
`CANDLE_INTERVALS` every 30 s. Naively extending that to a 50-symbol watchlist yields
400 requests per cycle ≈ 13.3 req/s, over the exchange's 10 req/s limit. This ADDS R7
(union ingest set), R8 (due-interval scheduling) and R9 (request budget). R1–R6 stay in
force; no schema, no dependency, no order path.

## ADDED Requirements

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
