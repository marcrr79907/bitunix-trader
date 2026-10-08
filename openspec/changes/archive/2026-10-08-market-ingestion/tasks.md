# Tasks: market-ingestion

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

## Guard/Edge Matrix (every row = a test in its WU)

- [x] Global models have NO `user` FK and do NOT inherit `UserOwnedModel` (R1)
- [x] `UniqueConstraint(symbol, ts)` present per model (R1)
- [x] Re-persist identical rows → `(0, 0)` new rows (R2)
- [x] `ts` persisted timezone-aware UTC (R3)
- [x] `next_funding_time` stays raw epoch-ms int (R3)
- [x] Empty symbols/response → `(0, 0)`, no raise (R3)
- [x] `fetch_market` maps `fetch_rows` keys 1:1 (no forked parser) (R3)
- [x] Worker one cycle ingests N rows, returns 0 (R4)
- [x] `BitunixError`/`RequestException` → `min(backoff*2, 300)`, then recovery (R4)
- [x] `stop()` true → exits between cycles, returns 0 (R4)
- [x] Scheduler still boots (`idle_loop` compatible) (R5)
- [x] `tests/test_boundary.py` green; `src/` framework-free (R6)
- [x] No order-execution surface; no new runtime dep (R7)

## WU1 (PR1) — data path: global snapshots + ingest service

Base `feat/market-ingestion` (tracker). Depends: none. Strict TDD.

- [x] 1.1 **RED** `tests/web/test_ingest.py`: persist round-trip; re-persist → `(0,0)`; UTC-aware `ts`; `next_funding_time` raw int; empty → `(0,0)`.
- [x] 1.2 **RED** same file: `fetch_market` with stub client (fixtures, no sockets) splits/maps keys for two symbols.
- [x] 1.3 **GREEN** `web/trading/models.py`: add `FundingSnapshot` + `TickerSnapshot` (global, no FK, `unique_together`/`UniqueConstraint(symbol,ts)`).
- [x] 1.4 **GREEN** `web/trading/ingest.py`: `fetch_market` (reuse `src.monitor.fetch_rows`, epoch-ms→UTC once) + `persist_market` (`bulk_create(ignore_conflicts=True)`, 1 tx).
- [x] 1.5 **GREEN** `web/trading/migrations/0002_market_snapshots.py` additive; `makemigrations --check` green.
- [x] 1.6 Full suite + ruff green.
- [x] 1.7 **Rollback**: delete `ingest.py` + `test_ingest.py` + migration `0002_*`; revert `models.py`.

## WU2 (PR2) — real worker loop

Base WU1 branch. Depends: WU1. Strict TDD.

- [x] 2.1 **RED** `tests/web/test_service_stubs.py`: worker ingests N rows on one cycle (`iterations=1`).
- [x] 2.2 **RED** same file: client raises once → backoff then recovery, no crash; `stop` flag → return 0.
- [x] 2.3 **RED** same file: keep scheduler boot test (`main(iterations=1) == 0`).
- [x] 2.4 **GREEN** `web/worker.py`: `INGEST_POLL_SECONDS`, `_bootstrap`, `run_once`, `run_loop(client, symbols, iterations, stop, sleep)`, `_install_signal_handlers`, `main`; keep `idle_loop` for `scheduler.py`.
- [x] 2.5 Full suite + `test_boundary.py` + ruff green.
- [x] 2.6 **Rollback**: restore `web/worker.py` + `test_service_stubs.py`; scheduler/`src/` untouched.

## Phase 3 — Verification

- [x] 3.1 `python -m pytest` green under Strict TDD.
- [x] 3.2 `ruff check . && ruff format --check .` + `makemigrations --check` green.
- [x] 3.3 No order-execution surface; no new runtime dependency; boundary green.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | WU1 ~250, WU2 ~150 → ~350–450 total |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR2 (each targets prior branch) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |
| Tracker branch | `feat/market-ingestion` → merges to `develop` |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium
