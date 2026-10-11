# Design: cron-jobs

## Technical Approach

Railway native cron (`ServiceInstance.cronSchedule`) runs two container-decoupled
jobs from the tested image: an hourly bounded `backfill_candles` converging via
`Min(time)` resume, and a daily `prune_snapshots` capping the 30s tick tables at
7 days, never touching `Candle`. Both are `trading` management commands with a
module-level `run(...)` seam (injected time/IO) so tests need no clock or socket.
Repo ships commands, the CD loop entry, and docs; service creation + schedules
happen in the Railway dashboard (no `railway cron` CLI; `railway.json` deprecated
— #46).

## Architecture Decisions

| # | Decision | Choice | Alternatives | Rationale |
|---|----------|--------|--------------|-----------|
| D1 | Prune home | `trading/management/commands/prune_snapshots.py` | New app | Models live in `trading`; mirrors `backfill_candles`, zero wiring. |
| D2 | Prune execution | Batched pk-loop, `.filter(ts__lt=cutoff)` | Single `.delete()` | First prune ≈161k rows; one DELETE holds one long lock. `--batch-size` 5000 bounds each tx. |
| D3 | Time seam | Injected `cutoff: datetime`; `handle` = `now(UTC)-older_than` | Inject `now`; `--now` | The cutoff is the real input; today's date is not. No clock in tested path. |
| D4 | Backfill budget | `--max-pages N` shared counter | `--max-seconds` | Deterministic, testable, no wall clock; 3000×0.15s ≈7.5 min ≪ any kill. |
| D5 | Cron mechanism | Railway native cron services | Activate `scheduler.py` loop | Platform-native, decoupled from a redeployable container; keeps R5. |
| D6 | CD loop | Add both names to the loop | Manual pinning | One-line config-driven change; cron images run only on schedule. |

## prune_snapshots

Top-level `from trading.models import FundingSnapshot, TickerSnapshot` — **never
imports `Candle`**. Sliced querysets can't `.delete()`, so materialise pks then
delete by `pk__in`:

```python
def run(cutoff, batch_size, dry_run, out) -> int:
    total = 0
    for model in (FundingSnapshot, TickerSnapshot):
        qs = model.objects.filter(ts__lt=cutoff)
        if dry_run:
            n = qs.count()
            out(f"{model.__name__}: would_delete={n}")
        else:
            n = 0
            while True:
                pks = list(qs.values_list("pk", flat=True)[:batch_size])
                if not pks:
                    break
                n += model.objects.filter(pk__in=pks).delete()[0]
            out(f"{model.__name__}: deleted={n}")
        total += n
    out(f"prune done cutoff={cutoff.isoformat()} total={total}")
    return total
```

Idempotent (second run finds `count()==0`). `handle` computes
`cutoff = datetime.now(UTC) - timedelta(days=older_than)`. Args: `--older-than`
`required=True` (int days), `--dry-run`, `--batch-size` default 5000.

## backfill_candles --max-pages

`run` owns the shared counter; `_backfill_series` gets a local `page_budget` and
stops *before* a fetch that would exceed it:

```python
def run(..., delay=DEFAULT_SLEEP, max_pages=None):
    total, used = 0, 0
    for symbol in symbols:
        for interval in intervals:
            remaining = None if max_pages is None else max_pages - used
            if remaining is not None and remaining <= 0:
                out("budget exhausted"); return total
            p, n = _backfill_series(..., page_budget=remaining)
            total += p; used += n
    return total
```

Loop: check `count >= page_budget` before `client.kline(...)`; on exhaustion log
and `break` mid-series. Default `None` preserves current unbounded behavior
(existing tests untouched). **Convergence**: full depth ≈9.4k pages (5m ≈6.3k);
`--max-pages 3000` → ~2–3 hourly runs; afterward each run is near-instant.

## Platform manifestations

| Item | Value |
|------|-------|
| `cron-backfill` | `0 * * * *` · `python web/manage.py backfill_candles --max-pages 3000` |
| `cron-prune` | `0 3 * * *` · `python web/manage.py prune_snapshots --older-than 7` |
| Env (both) | `DJANGO_SETTINGS_MODULE=config.settings.prod`, `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `SECRET_KEY`, `CREDENTIALS_FERNET_KEY`, `ALLOWED_HOSTS`, `DEBUG=false` |
| Env NOT set | `PORT`, `REDIS_URL`, migrate, gunicorn |

`web/start.sh` (migrate+gunicorn) MUST **not** be the cron start command: `web`
is the single migrator; cron runs against the current schema.
**Orchestrator must do (dashboard, not repo):** create both services from the
repo image; set start command + Cron Schedule; set env above; disable GitHub
autodeploy on both; trigger each once and confirm logs.

## Tick retention

7 days confirmed. `ingest.py`/`worker.py` unchanged (still write ticks);
`prune_snapshots` is the only retention mechanism; `Candle` indefinite.
~11,520 rows/table/day → steady state ≈80,640/table.

## Boundary Note

`src/` unchanged and framework-free; `web/ → src/` one-way preserved; no new
dependency, no migration, no order surface (`test_no_order_surface.py` green).
Prune touches only `trading` models.

## Data Flow

    Railway cron ─▶ container ─▶ manage.py <command> ─▶ trading models
      cron-backfill ─▶ run(max_pages) ─▶ kline ─▶ Candle (resume forward)
      cron-prune    ─▶ run(cutoff)    ─▶ DELETE ts<cutoff (tick tables only)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `web/trading/management/commands/prune_snapshots.py` | Create | retention command + `run` seam |
| `web/trading/management/commands/backfill_candles.py` | Modify | `--max-pages` shared budget |
| `tests/web/test_prune_snapshots.py` | Create | R1 contract (+ batching) |
| `tests/web/test_backfill_candles.py` | Modify | budget-exhaustion + converge + no-flag |
| `.github/workflows/cd.yml` | Modify | add two names to deploy loop (line 111) |
| `docs/deployment.md` | Modify | cron services, schedules, commands, retention, convergence |
| `models.py`, `ingest.py`, `worker.py`, `scheduler.py`, `requirements.txt` | Unchanged | no model/migration/dep change |

## Testing Strategy (Strict TDD, `python -m pytest`)

| Layer | What | Approach |
|-------|------|----------|
| Unit | prune deletes old / keeps new (both tables); dry-run reports + deletes nothing; re-run deletes 0; `Candle` survives; batching clears >batch_size | `@pytest.mark.django_db`, fixed injected `cutoff`; no clock/network |
| Unit | `--older-than` required → `CommandError` | `call_command` without arg |
| Unit | budget stops after exactly N pages; resume converges; no flag exhausts | existing `SeriesClient` stub |
| Regression | order surface, boundary, `makemigrations --check`, scheduler stub | unchanged suites |

Patch gate 100% on new lines (diff-cover).

## ADRs

Railway cron over in-process scheduler (D5); batched prune over one DELETE (D2);
`--max-pages` over wall clock (D4); cron services in the CD loop so they never
run a stale image (D6).

## Task Breakdown Hint

Chained PRs (orchestrator confirms, ask-on-risk): **PR1** prune command + tests
(~150); **PR2** `--max-pages` + tests (~60); **PR3** `cd.yml` + docs (~65). Each
boots and reverts cleanly; PR1 alone delivers retention value.

## Migration / Rollout

No migration. Deploy, then create + schedule the two cron services and verify one
run each. Rollback: revert branch, disable/remove the cron services — schedules
removing stops both jobs instantly and no schema change means no data loss.

## Open Questions

None blocking. Resolved: home = `trading`; batch-size 5000; `--max-pages` only;
CD gains both names; 7-day retention.
