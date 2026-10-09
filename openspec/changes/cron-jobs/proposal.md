# Proposal: cron-jobs

## Intent

The candle dataset must converge over its full BitUnix depth (~1.87M rows, ~9.4k requests, ~23–40 min) but a single SSH/one-shot run is fragile and a redeploy kills it. Meanwhile the 30s `FundingSnapshot`/`TickerSnapshot` tables grow ~23k rows/day with no reader and no cleanup. Issue #48 unifies both under **Railway native cron** (`ServiceInstance.cronSchedule`): a periodic, container-independent backfill that converges and self-heals, plus a prune command that caps the tick tables while **never touching `Candle`**.

## Scope

### In Scope
- New `manage.py prune_snapshots --older-than <days> [--dry-run] [--batch-size N]`; deletes `FundingSnapshot` + `TickerSnapshot` only, cutoff seam (no wall-clock dependency), idempotent, batched, logged.
- `backfill_candles --max-pages <N>` budget so a cron run exits cleanly before any platform kill; convergence documented (2–3 hourly runs).
- Two new Railway cron services (`cron-backfill` hourly, `cron-prune` daily ~03:00 UTC), dashboard/IaC-configured; repo ships start commands + docs.
- Decision: **keep 30s tick ingestion, retain 7 days** (issue #45 recommended short window).
- `docs/deployment.md`: cron setup, schedules, convergence, retention policy.

### Out of Scope
- Stopping tick ingestion entirely (`worker.py`/`ingest.py` unchanged).
- Activating `web/scheduler.py` (stays a stub; Railway cron is the mechanism).
- Chart pagination (#44); candle retention (indefinite); patterns.
- `railway.json`/IaC migration (issue #46). New runtime dependencies. Migrations. **Order execution (hard invariant).**

## Capabilities

### New Capabilities
- `batch-jobs`: Railway cron mechanism + `prune_snapshots` retention command + convergent backfill budget and schedule.

### Modified Capabilities
- `market-ingestion`: R5 clarified — scheduler remains a stub; scheduled batch work is delegated to Railway cron, not the scheduler service. Snapshot tables gain a bounded retention policy (writes unchanged).

## Approach

Reuse-first: `prune_snapshots` mirrors the `backfill_candles` `run(...)` seam (module-level function with injected `cutoff`/`out`, `Command.handle` parses args only) so tests need no clock and no sockets. Prune is `.filter(ts__lt=cutoff).delete()` in `--batch-size` chunks across the two tick models; `Candle` is never imported. Backfill gains a shared `--max-pages` counter in `_backfill_series`; exhaustion breaks cleanly and the existing `Min(time)` resume guarantees convergence. Cron jobs are plain Railway services whose start commands run `manage.py` with the same prod env as `web`; no schema or dependency change.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/trading/management/commands/prune_snapshots.py` | New | retention command |
| `web/trading/management/commands/backfill_candles.py` | Modified | `--max-pages` budget |
| `tests/web/test_prune_snapshots.py` | New | TDD: retention, dry-run, Candle-safe, idempotent |
| `tests/web/test_backfill_candles.py` | Modified | budget-exhaustion branch |
| `docs/deployment.md` | Modified | cron services + schedules + convergence + retention |
| `.github/workflows/cd.yml` | Modified | optionally deploy the two cron services |
| `web/trading/models.py`, `ingest.py`, `worker.py`, `scheduler.py`, `requirements.txt` | Unchanged | no model/migration/dep change |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| First prune deletes ~161k rows, long lock | Med | `--batch-size` default (e.g. 10k) |
| Backfill frontier leaves a gap from a worker outage | Med | Document residual gap risk (gap-scan out of scope) |
| Cron services not deployed by CD (hardcoded loop) | Med | Add names to deploy loop or document manual pinning |
| Railway cron is dashboard-only (no CLI) | High | Document exact dashboard steps; user performs them |
| Required `--older-than` vs a silent default | Low | Required by design (safety); reflected in spec |

## Rollback Plan

Revert the branch: delete `prune_snapshots.py` and its test, restore `backfill_candles.py` (drop `--max-pages`), restore `docs/`/`cd.yml`. The prune cron service is disabled/removed in the Railway dashboard; no schema change means no data loss and no migration rollback. Removing the cron schedules instantly stops both jobs; the worker and its tick/candle ingestion are untouched throughout.

## Dependencies

- Railway native cron (`ServiceInstance.cronSchedule`) — configured in the dashboard by the user/orchestrator.
- Current schema (no migration); `web` service continues to run migrations.

## Open Questions

- `--batch-size` default value (10k?) and whether a wall-clock budget guard is also needed.
- Add `cron-backfill`/`cron-prune` to the CD deploy loop, or pin manually?
- Confirm 7-day tick retention vs stopping ingest (recommendation: 7-day).

## Success Criteria

- [ ] `prune_snapshots` deletes `ts < cutoff` in both tables, preserves `Candle`, `--dry-run` deletes nothing, idempotent.
- [ ] `backfill_candles --max-pages N` exits cleanly at the budget; a re-run resumes and converges.
- [ ] `python -m pytest` green (Strict TDD); patch coverage 100%; ruff clean; no new dependency.
- [ ] Railway cron configured and verified with a real run log (ops step).
- [ ] Retention + convergence policy documented in `docs/`.

## Review Workload Forecast

- Estimated diff: **~250–350 changed lines** (prune command + tests ~150, backfill budget + tests ~60, docs ~60, cd.yml ~5).
- Decision needed before apply: No
- Chained PRs recommended: No
- 400-line budget risk: Low
