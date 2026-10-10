# Tasks: private-data-sync

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

## Guard/Edge Matrix (every row = a test in its WU)

- [ ] 3 models inherit `UserOwnedModel`; FK CASCADE + `for_user` present (R1/R14)
- [ ] Unique `(user,symbol,ts)` / `(user,ts)` / `(user,trade_id)` reject dup (R1)
- [ ] Same `trade_id` allowed A∥B; uniqueness is per user (R1)
- [ ] Re-sync identical payload → 0 new rows; empty → 0, no raise (R2)
- [ ] `sync.py` no `decrypt` import/call/bare/getattr; scanner green (R3/R13)
- [ ] `sync.py` owned models touched only via `bulk_create`/`count`; guard green (R3/R14.3)
- [ ] Worker decrypts active cred, builds client, delegates to `sync_user` (R4/R13)
- [ ] Inactive creds skipped; no active creds → no-op, no fetch (R4)
- [ ] Per-user isolation: A raises, B synced, global ingest intact (R5/R4b)
- [ ] `run_once` return `(funding,ticker)` unchanged; private step isolated (R4b)
- [ ] Read-only: no order surface; no new runtime dep; `src/` framework-free (R6/R11)
- [ ] `OWNED_MODELS` includes the 3 new models; guard fixture flags them (R14.3)

## WU1 (PR1) — data tier: 3 owned models + migration + decrypt-free sync

Base `feat/private-data-sync` (tracker). Depends: none. Strict TDD.

- [ ] 1.1 **RED** `tests/web/test_private_sync.py`: model constraints — unique `(user,symbol,ts)`/`(user,ts)`/`(user,trade_id)` reject dup; `trade_id` shared across A∥B; `for_user(A)` vs B.
- [ ] 1.2 **RED** same file: `persist_*` twice (same `ts`) → 0; empty → 0, no raise.
- [ ] 1.3 **RED** same file: `sync_user` stub client maps position/account/trade payloads (fixtures, no sockets).
- [ ] 1.4 **RED** same file: AST assertion — `sync.py` has no `decrypt` reference.
- [ ] 1.5 **GREEN** `web/trading/models.py`: add `PositionSnapshot`, `AccountSnapshot`, `Trade(UserOwnedModel)` with the 3 `UniqueConstraint`s.
- [ ] 1.6 **GREEN** `web/trading/migrations/0004_private_snapshots.py` additive; `makemigrations --check` green.
- [ ] 1.7 **GREEN** `web/trading/sync.py`: `_f`, `persist_positions/account/trades` (`bulk_create(ignore_conflicts=True)` + count delta), `sync_user`, `_fetch_trades` paginated like `journal.sync`. No `credentials` import.
- [ ] 1.8 Full suite + ruff green.
- [ ] 1.9 **Rollback**: delete `sync.py` + `test_private_sync.py` + migration `0004_*`; revert `models.py`.

## WU2 (PR2) — worker trusted zone: decrypt + private step

Base WU1 branch. Depends: WU1. Strict TDD.

- [ ] 2.1 **RED** `tests/web/test_worker_private_sync.py`: `run_private_sync(stub_factory)` — active cred decrypts (fernet_key fixture) + persists.
- [ ] 2.2 **RED** same file: inactive cred skipped; no creds → no-op, no fetch.
- [ ] 2.3 **RED** same file: A's client raises, B succeeds → B synced; `run_once` contract `(funding,ticker)` intact.
- [ ] 2.4 **GREEN** `web/worker.py`: `run_private_sync(client_factory=None)` — iterate `ExchangeCredential.objects.filter(is_active=True)`, `decrypt` both columns, build client, `try/except` per user (logger.warning).
- [ ] 2.5 **GREEN** `web/worker.py`: `run_once` gains an isolated private step after ticks+candles (candle-cycle pattern); return unchanged.
- [ ] 2.6 Full suite + ruff green.
- [ ] 2.7 **Rollback**: restore `web/worker.py` + `test_worker_private_sync.py`; `sync.py`/`src/` untouched.

## WU3 (PR3) — guard + isolation coverage

Base WU2 branch. Depends: WU2. Strict TDD.

- [ ] 3.1 **RED** `tests/web/test_owned_model_guard.py`: fixture flagging `PositionSnapshot.objects.all()` (or unscoped `AccountSnapshot`/`Trade`).
- [ ] 3.2 **GREEN** `OWNED_MODELS += {"PositionSnapshot","AccountSnapshot","Trade"}`.
- [ ] 3.3 **RED** `tests/web/test_isolation.py`: A≠B via `for_user(B).get(pk=...)` for the 3 models; per-user `trade_id` reuse.
- [ ] 3.4 Full suite + guard + credential scanner green; ruff green.
- [ ] 3.5 **Rollback**: revert `OWNED_MODELS` and `test_isolation.py`; WU1/WU2 unaffected.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | WU1 ~280, WU2 ~180, WU3 ~60 → ~450–600 total |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR2 → PR3 (each targets prior branch) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |
| Tracker branch | `feat/private-data-sync` → merges to `develop` |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High
