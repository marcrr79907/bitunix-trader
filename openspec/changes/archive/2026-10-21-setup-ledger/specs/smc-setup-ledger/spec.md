# smc-setup-ledger Specification

## Purpose

Persist each SMC setup as emitted, so its policy becomes measurable. Rows are
observations, never orders; point-in-time only.

## Requirements

### Requirement: R1 — Global Setup model

`trading` MUST define a GLOBAL `Setup`: no `user` FK, MUST NOT inherit
`UserOwnedModel`, MUST NOT be in `OWNED_MODELS`. Fields: `symbol` Char(32),
`interval`/`direction` Char(8), `anchor_time` BigInt (candle OPEN, UNIX s),
`entry`/`stop`/`take_profit`/`rr` Float, `score` Int, `atr` Float nullable,
`engine_version` Char(16), `created_at` DateTime(auto_now_add).

It MUST carry `UniqueConstraint(symbol, interval, anchor_time, engine_version)`
plus a matching index: direction comes from the latest `StructureEvent`, and
each event needs a new closed candle, so two events cannot share a bar. The
`engine_version` component is REQUIRED — without it a bumped version could never
insert (R4), and the ledger would silently freeze on its first rows.

It MUST NOT store zone bounds, range extremes, or `has_ob`/`has_fvg`: `score`
encodes the OB/FVG flags and nothing reads the rest.

#### Scenario: Global and minimal

- GIVEN `Setup`, WHEN inspected, THEN it has no `user`, is absent from `OWNED_MODELS`, and lacks those six fields

#### Scenario: One row per anchor per engine

- GIVEN a persisted setup, WHEN a same-key row is inserted under conflict-ignore, THEN one row remains

### Requirement: R2 — Additive migration

Migration `0018_*` MUST create only `setups`, keep `makemigrations --check
--dry-run` green, and migration tests MUST assert the leaf with `>=`, never `==`.

#### Scenario: Migration green

- GIVEN `0018`, WHEN applied and checked, THEN only `setups` is created and nothing pends

### Requirement: R3 — Point-in-time only

Rows MUST come only from the live capture seam. The system MUST NOT reconstruct
rows retroactively and MUST NOT expose a backfill command.

#### Scenario: No backfill surface

- GIVEN the change, WHEN commands and worker steps are inspected, THEN none rebuilds setups from history

### Requirement: R4 — Engine versioning

`SMC_ENGINE_VERSION` MUST live in `src/smc/config.py` as a hand-bumped
non-empty `str`; each row MUST record its emitter in a Char(16) column. Changing
the engine without bumping MUST be a spec violation.

#### Scenario: Mixed engines coexist

- GIVEN rows from version `"1"`, WHEN the constant becomes `"2"` and capture reruns, THEN new rows carry `"2"` and old rows stay `"1"`

### Requirement: R5 — Capture seam

The seam MUST read persisted candles via `_db_rows(symbol, interval, None, N)`
with ZERO network calls and run the same chain `get_smc_payload` runs through
the shared helper. `N` MUST be `SETUP_CANDLE_WINDOW = 100`. It MUST persist with
`bulk_create(ignore_conflicts=True)`. It MUST use `SETUP_CAPTURE_INTERVALS` only
(env-tunable, default `("1h",)`), preserving order and removing duplicates.

Config resolution MUST validate every entry against `CANDLE_INTERVALS` and
raise `ValueError` naming the offending values. It MUST NOT silently skip an
unknown entry: a quietly narrowed ledger defeats its purpose. To keep the loud
failure safe, the import that parses this config MUST live INSIDE the capture
step's own `try` (R6), so a typo disables capture without touching ingestion.

#### Scenario: One row, then none

- GIVEN a setup-producing window, WHEN capture runs twice, THEN the first inserts one matching row and the second inserts zero

#### Scenario: No network, ATR anchored

- GIVEN a client that raises on any call, WHEN capture runs, THEN no network call is made and the stored `atr` equals `atr(...)[setup.index]`, or is null inside the warm-up

#### Scenario: Bad interval fails loudly, safely

- GIVEN `SETUP_CAPTURE_INTERVALS="1h,bogus"`, WHEN a worker cycle runs, THEN capture is disabled with a logged error and funding, ticker, candles, private sync and alerts still complete

### Requirement: R6 — Isolation, degradation, boundary

Capture MUST be its own `try/except` step in `run_once`; failure MUST be logged
and MUST NOT degrade funding, ticker, candle, private-sync, or alerts, nor kill
the loop. Empty input, short windows, mismatched lengths, and unpersisted
intervals MUST yield no rows and MUST NOT raise. Any new `src/smc/` helper MUST
be pure, deterministic, stdlib-only, clock-free, and in `PURE_MODULES`. No order
surface, dependency, or `src/` Django import may be added.

#### Scenario: Failure contained

- GIVEN capture raises, WHEN a cycle runs, THEN every other step still completes

#### Scenario: Degrades quietly

- GIVEN empty input, a short window, or malformed config, WHEN capture runs, THEN zero rows are written and the cycle survives

#### Scenario: Guards stay green

- GIVEN the helper and model, WHEN `test_boundary.py` and `test_no_order_surface.py` run, THEN both pass

**Edge-case matrix**

| Condition | Result |
|---|---|
| no setup / short window | 0 rows |
| `setup.index` out of bounds | skipped |
| ATR index invalid | `atr = null` |
| interval not persisted | 0 rows |
| duplicate anchor key | ignored |
| unknown capture interval | `ValueError` at parse, capture disabled |
| capture raises | logged |
