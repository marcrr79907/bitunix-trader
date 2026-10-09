# Exploration: cron-jobs (issue #48)

**Change**: `cron-jobs`
**Date**: 2026-10-09
**Mode**: investigation only. No code written.
**Issues**: gh#48 (this change), gh#45 (snapshot retention), gh#43 (candle-store, closed).

## Executive Summary

Two batch jobs must run reliably on Railway without living inside the worker
container (a redeploy must not kill them): a **convergent candle backfill** (the
existing resumable `backfill_candles` command, now fired on a schedule instead
of one fragile ~23–40 min SSH run) and a **snapshot prune** (`prune_snapshots`,
new, deletes 30s ticks only, never `Candle`). Railway supports cron natively via
`ServiceInstance.cronSchedule`; the CLI has no `railway cron` command, so the job
services are created/configured in the dashboard or via IaC — the repo can only
ship the commands and the docs. The 30s ticks are written but read by nobody and
are no longer the dataset (candles are), so this change also decides their fate:
keep a short 7-day retention window (recommended) rather than delete all ingest.
The `web/scheduler.py` stub stays a stub — Railway cron is the platform-native
mechanism and is decoupled from any long-lived container.

## Current State (read, not guessed)

| Area | Fact | Source |
|---|---|---|
| Backfill command | Exists, idempotent (`ignore_conflicts`), resumable from `Min(time)`, throttled (`DEFAULT_SLEEP=0.15`), monotonic-guard, `--dry-run`. Loop in module-level `run(...)` seam (injectable client/sleep/out) | `web/trading/management/commands/backfill_candles.py` |
| Backfill cost | 5m driver ≈ 6.3k requests of 200 rows; all intervals ≈ 9.4k pages; ~23–40 min at 10 req/s. No page/time budget flag → a cron run could be killed mid-flight | `backfill_candles.py:27,71-108`, candle-store explore §6 |
| Backfill test | Stub client + recording sleep; covers resume/idempotency/dry-run/errors via `run()` + `call_command` | `tests/web/test_backfill_candles.py` |
| Snapshot models | `FundingSnapshot`, `TickerSnapshot` global, `ts` DateTime, `UniqueConstraint(symbol, ts)`. No prune command exists | `web/trading/models.py:16-54` |
| Candle model | Global `Candle`, `time` BigInt seconds; MUST NOT be touched | `web/trading/models.py:57-87` |
| Ingest | `fetch_market`/`persist_market`; nobody reads the tick tables (dataset = candles) | `web/trading/ingest.py` |
| Worker loop | 30s global loop, backoff, injectable; runs candle cycle after ticks | `web/worker.py:40-86` |
| Scheduler | Boot-only stub sharing `worker.idle_loop`; schedules nothing | `web/scheduler.py`, `market-ingestion` R5 |
| Release | `web/start.sh` runs `migrate` then gunicorn; image is one Dockerfile, command per service | `web/start.sh`, `Dockerfile` |
| Railway cron | `ServiceInstance.cronSchedule`; no `railway cron` CLI; `railway.json` deprecated (deadline 2026-12-01 — issue #46) | issue #48, use-railway skill |
| CD | Deploys image to services `web worker scheduler` by loop over names | `.github/workflows/cd.yml:111` |
| Coverage gate | web ≥85% floor + patch diff-cover 100% (new lines need tests) | `.github/workflows/ci.yml:66-70` |

## 1. Cron mechanism (Railway)

**Recommended: a NEW Railway service per job**, not reusing `web`/`worker`/`scheduler`.

- A Railway **cron service** is a normal service with `cronSchedule` set; the
  platform starts the container on schedule, it runs its start command, and it
  exits. It is fully decoupled from the worker container's lifecycle — a worker
  redeploy cannot kill a running cron invocation.
- **Two new services**: `cron-backfill` (hourly) and `cron-prune` (daily
  ~03:00 UTC). One service could run both via a wrapper, but two keeps each
  schedule and its logs independent and each retry isolated. Recommend two.
- **Start commands** (repo-local, reviewable, mirrors `web/start.sh`):
  - backfill: `python web/manage.py backfill_candles --max-pages 3000`
  - prune: `python web/manage.py prune_snapshots --older-than 7`
- **Env**: identical to the other services — `DJANGO_SETTINGS_MODULE=config.settings.prod`,
  `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `SECRET_KEY`, `ALLOWED_HOSTS`. No
  `REDIS_URL` needed (commands do not touch Redis); no `PORT`.
- **No migrations in the cron command** — the `web` service already migrates on
  boot; a cron job runs against the current schema. Keep cron start commands
  migration-free (single writer avoids concurrent `migrate`).
- **Config path**: Railway dashboard (Service → Settings → Cron Schedule) or
  IaC/GraphQL (`serviceInstanceUpdate` with `cronSchedule`). The repo **cannot**
  fully create this — the orchestrator/user MUST create the services and set the
  schedule in the Railway dashboard. `railway.json` is deprecated (issue #46), so
  do not extend it; document the dashboard steps. A future IaC file (`.railway/`)
  could own it, but that is issue #46's scope.
- **CD impact**: CD's deploy loop (`web worker scheduler`) would not deploy the
  new services' images. Either add the cron service names to that loop, or let
  the cron services track `main`'s image separately. Flag for design: decide
  whether CD gains the two names (one-line addition) — recommended, so the cron
  jobs ship the tested image.

## 2. `prune_snapshots` command

**Interface**:

```
manage.py prune_snapshots --older-than 7 [--dry-run] [--batch-size N]
```

- `--older-than` days, **required** (no silent default — a wrong default could
  delete data; require the operator to state the window). Issue text shows
  `<days>`; making it required is safer.
- `--dry-run`: report counts that *would* be deleted; delete nothing.
- `--batch-size` (optional): delete in batches to avoid a long single
  transaction/lock on a large first prune. Default e.g. 10,000. `ponytail`:
  omit if a simple `.delete()` is fast enough — but the first prune may target
  ~161k+ rows, so a batched loop is the safe default; keep it one small
  `while` loop.
- **Models**: `FundingSnapshot` and `TickerSnapshot` **only**. MUST NOT import
  or reference `Candle`. A test must assert `Candle` rows survive.
- **Cutoff**: `ts__lt=now - older_than_days`. Delete via
  `Model.objects.filter(ts__lt=cutoff).delete()` (batched). Idempotent — a
  second run deletes 0.
- **Time seam**: module-level `run(models, cutoff, dry_run, batch_size, out) -> int`
  taking an explicit `cutoff` `datetime`. `Command.handle` computes
  `cutoff = datetime.now(UTC) - timedelta(days=older_than)`. Tests pass a fixed
  `cutoff` — **no wall-clock dependency, no `--now` CLI flag** (mirrors
  `fetch_closed_candles(now=...)` and the backfill `run()` seam). This is the
  cleaner seam than injecting `now`; the cutoff is the real input.
- **Logging**: one line per model (`funding deleted=N`), one summary
  (`prune done cutoff=... total=N`). `dry-run` logs `would_delete=N`.
- **Idempotent + safe**: dry-run writes nothing; unique constraints untouched.

## 3. Backfill convergence

- Add **`--max-pages`** (int, default `None` = unbounded) to `run()`/`Command`.
  Each `_backfill_series` page counts toward a shared budget; when exhausted the
  loop breaks cleanly mid-series and logs `budget exhausted`. A re-run resumes
  from `Min(time)` — convergence is safe by construction.
- **Also** consider a wall-clock budget (`--max-seconds`) so the job exits
  before Railway's kill; `--max-pages` alone is deterministic and testable, so
  recommend `--max-pages` first and let design decide if a time guard is needed.
- **Cron budget**: ~3000 pages/hour. 5m driver ≈ 6.3k pages + other intervals
  ≈ 9.4k total → **2–3 hourly runs converge** the full history (~3y × 4 symbols,
  ~1.87M rows). At 0.15s sleep, 3000 pages ≈ 7.5 min sleep + network — well under
  any platform timeout.
- **Schedule**: hourly (`0 * * * *`). Rationale: converges fast early, then each
  run is a cheap no-op or small gap-repair once depth is exhausted. The worker
  keeps ingesting the newest closed candles forward; backfill walks backward from
  the stored frontier; the two meet and the dataset is complete.
- **Document convergence** in `docs/deployment.md`: mechanism (resume from
  `Min(time)`), budget, schedule, expected run count to converge, and the fact
  that once converged a run exits nearly instantly.

## 4. Tick (30s) ingestion decision

**Recommendation: keep ingesting, retain a short window (7 days).** Do NOT stop
ingest in this change.

- Rationale: nobody reads the ticks today, but stopping ingest is a one-way
  product decision better made explicitly (issue #45 says "acotar o detener",
  recommended: short window). A 7-day window caps growth while preserving a
  recent operational signal (debugging worker health, spot-checking against
  BitUnix) that costs little.
- **If** the user prefers to stop: remove the `fetch_market`/`persist_market`
  call from `run_once` and delete the tick branch — but that must be an explicit
  decision, not the default. Recommend: **out of scope for this change; keep
  ingesting, prune at 7 days.** Revisit stopping later if storage pressure
  appears.
- Either way, `prune_snapshots` is what caps the tables, so the decision does
  not block this change.

## 5. Scheduler stub

**Recommendation: leave `web/scheduler.py` a stub; do NOT activate it.** Railway
native cron is the platform-standard mechanism and is decoupled from containers.
Repurposing the scheduler container into a long-lived in-process cron (APScheduler
style) would reintroduce exactly the coupling this issue removes (a redeploy kills
it), add a dependency, and duplicate Railway's scheduler. `market-ingestion` R5
("scheduler stays a stub") is preserved. Optional future: retire the `scheduler`
service entirely if it stays a stub — out of scope here.

## 6. Volumetry & prune cadence

- 30s interval → 2 rows/min → **2,880 rows/day per table per symbol**.
- 4 symbols: **11,520 rows/day per table**; two tables → **23,040 rows/day**
  combined (matches archive carry-forward).
- 7-day retention → steady state ≈ **80,640 rows/table** (~161k rows total).
- **Cadence**: daily `--older-than 7` at ~03:00 UTC. Each day's prune removes the
  day that fell outside the window (~11,520 rows/table), so the table stays flat.

## Affected Areas

- `web/trading/management/commands/prune_snapshots.py` — new command (create)
- `web/trading/management/commands/backfill_candles.py` — add `--max-pages` budget (modify)
- `tests/web/test_prune_snapshots.py` — new TDD suite (create)
- `tests/web/test_backfill_candles.py` — budget-branch tests (modify)
- `docs/deployment.md` — cron services, schedules, convergence, retention policy (modify)
- `.github/workflows/cd.yml` — optionally add cron services to the deploy loop (modify, pending design)
- `web/trading/models.py`, `web/trading/ingest.py`, `web/worker.py`, `web/scheduler.py`,
  `requirements.txt` — **unchanged** (no model/migration/dep changes)
- Railway dashboard — create `cron-backfill`, `cron-prune` + schedules (external, not repo)

## Recommendation

Proceed to proposal: ship `prune_snapshots` (required `--older-than`, `--dry-run`,
`--batch-size`, `cutoff` seam, snapshots only), add `--max-pages` to
`backfill_candles`, document two new Railway cron services (dashboard-configured,
hourly backfill / daily prune), keep 7-day tick retention, and leave the
scheduler stub untouched. Design resolves: batch-size default, whether a
time-budget guard is needed, and whether CD deploys the cron services.

## Risks

- **Interstitial gap repair** — convergence walks backward from the stored
  `Min(time)`, so a hole between the backfill frontier and the newest candles is
  only filled if the worker was continuously ingesting; a worker outage leaves a
  gap the cron does not detect. Flag for spec/design (a gap-scan mode is out of
  scope; document the residual risk).
- **Cron service not deployed by CD** — the deploy loop hardcodes
  `web worker scheduler`; new cron services may lag on old images unless added.
- **First prune lock/duration** — a large first delete could lock; batch-size
  mitigates.
- **Required `--older-than`** — deviates from a bare default; a conscious safety
  choice, must be reflected in the spec.
- **Railway config is manual** — acceptance ("cron configured and verified") is
  an ops step the orchestrator/user must perform; the repo only ships the
  commands and docs.

## Ready for Proposal

**Yes** — no blockers. Open questions are design-level (batch size, time guard,
CD loop), none block the scope.
