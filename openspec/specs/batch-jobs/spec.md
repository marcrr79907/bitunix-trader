# batch-jobs Specification

## Purpose

Scheduled, container-decoupled batch work on Railway: cap 30s tick tables via prune, converge candles via a bounded backfill. Jobs MUST be platform cron services, not in-process loops. New capability.

## Requirements

### Requirement: R1 — prune_snapshots command

`manage.py prune_snapshots --older-than <days> [--dry-run] [--batch-size N]` MUST delete rows from `FundingSnapshot` AND `TickerSnapshot` where `ts < cutoff`. `--older-than` MUST be required. `--dry-run` MUST delete nothing and report would-delete counts. `--batch-size` (default 5000) MUST delete in chunks; the command MUST log per-model deleted counts and a summary, and MUST be idempotent (re-run deletes nothing new).

The core loop MUST be a module-level function taking an injected timezone-aware `cutoff` (no wall-clock read in the loop); `handle` computes `cutoff = now(UTC) - timedelta(days=older_than)`.

#### Scenario: Deletes old, keeps new (both tables)

- GIVEN one `FundingSnapshot` and one `TickerSnapshot` with `ts < cutoff` and one of each with `ts >= cutoff`
- WHEN `run(cutoff=...)` executes
- THEN the two old rows are deleted and the two new rows remain

#### Scenario: Dry run deletes nothing

- GIVEN prunable rows, WHEN `run(cutoff, dry_run=True)`, THEN row counts are unchanged and the reported would-delete count is correct

#### Scenario: Duplicate run is a no-op

- GIVEN a completed prune, WHEN the same `cutoff` runs again, THEN it deletes 0 and returns 0

#### Scenario: Candle is untouched

- GIVEN `Candle` rows of any `time`, WHEN prune runs, THEN every `Candle` row survives

#### Scenario: --older-than is required

- GIVEN no `--older-than`, WHEN the command runs, THEN argument parsing fails

### Requirement: R2 — Backfill convergence budget

`backfill_candles` MUST accept `--max-pages N` (default `None` = unlimited; backward compatible). Pages across all series MUST count against one shared budget; on exhaustion the loop MUST break cleanly mid-series, log exhaustion, and return rows persisted so far. A later run MUST resume from `Min(time)` and converge. Without the flag it MUST run to exhaustion.

#### Scenario: Budget stops after N pages

- GIVEN a stub client serving more than N pages, WHEN `--max-pages N`, THEN exactly N pages are fetched and the run exits cleanly

#### Scenario: Subsequent run converges

- GIVEN a first run stopped by the budget, WHEN a second run without the flag resumes, THEN it continues from the stored frontier and completes the series

#### Scenario: No flag runs to exhaustion

- GIVEN no `--max-pages`, WHEN the command runs, THEN it paginates until upstream depth is exhausted

### Requirement: R3 — Platform cron scheduling

The jobs MUST be scheduled as Railway cron services (container-decoupled), NOT in-process loops. Each cron service MUST run `python web/manage.py <command>` under prod settings, and MUST NOT run gunicorn, migrations, Redis, or bind a port. The contract MUST be documented in `docs/`. `web/scheduler.py` MUST remain untouched.

#### Scenario: Cron commands are documented

- GIVEN `docs/`, WHEN inspected, THEN the two cron services' start commands, schedules, env, and convergence/retention policy are documented

#### Scenario: Scheduler stub unchanged

- GIVEN the change, WHEN `web/scheduler.py` is inspected, THEN it remains a boot-only stub with scheduled work delegated to the platform

### Requirement: R4 — Tick retention policy

30s tick ingestion MAY continue, but `FundingSnapshot`/`TickerSnapshot` MUST be retained only within a bounded window (7 days) enforced by `prune_snapshots`. `Candle` MUST have indefinite retention.

#### Scenario: Ticks bounded, candles indefinite

- GIVEN the documented policy, WHEN retention is inspected, THEN tick tables use a 7-day window and `Candle` has none

### Requirement: R5 — Read-only, no new dependency, boundary

The change MUST NOT add any order-execution surface; `requirements.txt` MUST remain unchanged (no new runtime dependency); no migrations are introduced. The `web/ → src/` one-way boundary MUST be preserved.

#### Scenario: No dependency or migration added

- GIVEN the change, WHEN `requirements.txt` and migrations are inspected, THEN neither changed

#### Scenario: No order surface

- GIVEN the new commands, WHEN the order scanner runs, THEN no order endpoint or verb is reported
