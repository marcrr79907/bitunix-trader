# Tasks: cron-jobs

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Low

## Guard/Edge Matrix (each row = a test)

- [x] prune deletes only `ts < cutoff`, both tables
- [x] `--dry-run` reports counts, deletes nothing
- [x] idempotent: same `cutoff` re-run deletes 0
- [x] `Candle` survives AND source never references it
- [x] batched loop clears > `--batch-size` rows
- [x] `--older-than` missing → `CommandError`
- [x] `--max-pages N` fetches exactly N pages, breaks mid-series
- [x] resume after budget continues, converges
- [x] no `--max-pages` → paginates to exhaustion
- [x] CD loop deploys both cron services
- [x] no new dep, no migration, boundary, no order surface

## WU1 (PR1) — prune command + tests

Base `feat/cron-jobs` (tracker). Depends: none. Strict TDD.
- [x] 1.1 **RED** `tests/web/test_prune_snapshots.py`: old vs new both tables → old deleted, new kept; `Candle` survives.
- [x] 1.2 **RED** same: `dry_run=True` deletes nothing; same `cutoff` re-run deletes 0.
- [x] 1.3 **RED** same: > `batch_size` rows clears all; missing `--older-than` raises `CommandError`; source has no `Candle` import.
- [x] 1.4 **GREEN** `prune_snapshots.py`: `run(cutoff, batch_size, dry_run, out) -> int` (pk-batch loop, both models) + `handle` (`--older-than` required, `--dry-run`, `--batch-size` 5000).
- [x] 1.5 Full suite + ruff; 100% patch coverage.
- [x] 1.6 **Rollback**: delete command + test.

## WU2 (PR2) — backfill `--max-pages`

Base WU1 branch. Depends: WU1. Strict TDD.

- [x] 2.1 **RED** `test_backfill_candles.py`: stub serving > N pages → exactly N pages, clean exit.
- [x] 2.2 **RED** same: second run without flag resumes from `Min(time)`; no flag exhausts.
- [x] 2.3 **GREEN** `backfill_candles.py`: `run()` gains `max_pages=None` shared counter; `_backfill_series` local `page_budget` checked before `client.kline`; `handle` `--max-pages`.
- [x] 2.4 Full suite + ruff; no-flag tests untouched.
- [x] 2.5 **Rollback**: revert `backfill_candles.py` + test additions.

## WU3 (PR3) — CD loop + docs

Base WU2 branch. Depends: WU1+WU2. No tests (config/docs).

- [x] 3.1 `.github/workflows/cd.yml`: add `cron-backfill cron-prune` to the `for svc in …` loop (line 111).- [x] 3.2 `docs/deployment.md`: services (names, `0 * * * *` / `0 3 * * *`, start commands, prod env, no PORT/REDIS/migrate/gunicorn), 7-day retention, convergence, `Candle` indefinite.
- [x] 3.3 Verify: pytest, ruff, `makemigrations --check`, `test_no_order_surface.py`, `test_boundary.py`.
- [x] 3.4 **Rollback**: revert `cd.yml` + `docs/`.

## Orchestrator follow-up (NOT an apply task — dashboard-only)

Create both Railway cron services from the repo image, set start command + Cron Schedule + env, disable autodeploy, trigger once. `sdd-apply` cannot do this.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | PR1 ~150, PR2 ~60, PR3 ~65 → ~275 |
| 400-line budget risk | Low |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR2 → PR3 (each targets prior branch) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |
| Tracker branch | `feat/cron-jobs` → `develop` |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Low
