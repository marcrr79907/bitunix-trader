# Proposal: private-data-sync

## Intent

Fase 6a can provision encrypted credentials but nothing consumes them: the
worker ingests only public market data, and the dashboard has no per-user data.
Fase 6b (#57) makes the worker **decrypt active credentials and sync read-only
private data** (positions, account, trades) into per-user models — the first
real use of `credentials.decrypt` and the private API, and the data source for
Fase 6c's UI (#58). Strictly read-only (R11): no order surface, ever.

## Scope

### In Scope
- 3 new `UserOwnedModel`s (FK `user`, idempotent `(user, …)` unique constraints):
  `PositionSnapshot` `(user,symbol,ts)`, `AccountSnapshot` `(user,ts)`,
  `Trade` `(user,trade_id)`; additive migration.
- `web/trading/sync.py`: **persistence + read-only fetch only, NO `decrypt`** —
  `persist_positions/account/trades` via `bulk_create(ignore_conflicts=True)`,
  `sync_user(user, client)` orchestrating `positions()/account()/history_trades()`
  (paginated like `journal.sync`).
- `web/worker.py`: isolated private-sync step — decrypts, builds `BitunixClient`,
  delegates to `sync_user`; **per-user error isolation**; `(funding, ticker)`
  return contract unchanged.
- Add the 3 models to the R14.3 guard's `OWNED_MODELS`.
- Tests: constraints, R14 A≠B, idempotent re-sync, per-user isolation, worker
  cycle with stub client; patch coverage 100%; ruff clean.

### Out of Scope
- UI/views/templates (6c); alerts (Fase 7).
- Private-snapshot retention/decimation (documented follow-up).
- Credential rotation; self-service provisioning.
- **Any order execution — HARD invariant (R11).**

## Capabilities

### New Capabilities
- `private-data-sync`: worker-zone decryption + read-only private sync into
  per-user position/account/trade models.

### Modified Capabilities
- `per-user-isolation`: R14 applies to three new owned models (A≠B + guard set).
- `user-credentials`: R13.4 decryption is now **consumed** by the worker.
- `market-ingestion`: worker loop gains an isolated private-sync step (R4).

## Approach

The two live scanners dictate one seam. `web/trading/` is inside the credential
scanner's `REQUEST_PATH`, so `sync.py` must never reach `decrypt`; `worker.py`
is outside every scanned request path, so it owns decryption and the
`ExchangeCredential.objects.filter(is_active=True)` read (R14.4 trusted zone).
Persist exactly like `ingest.py`/`candles.py`: model-ready dicts +
`bulk_create(ignore_conflicts=True)` (not in the guard's `UNSCOPED_VERBS`) +
count delta. Field mapping reuses `src.monitor.position_row` / `src.journal.trade_row`.
Per-user `try/except` wraps each credential so one bad key never degrades the
global ingest or peers.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/trading/models.py` | Modified | 3 owned models + unique constraints |
| `web/trading/migrations/0004_*` | New | additive |
| `web/trading/sync.py` | New | persist + fetch, no decrypt |
| `web/worker.py` | Modified | decrypt + private-sync step, per-user isolation |
| `tests/web/test_owned_model_guard.py` | Modified | `OWNED_MODELS` += 3 |
| `tests/web/test_isolation.py` | Modified | A≠B for 3 models |
| `tests/web/test_private_sync.py` | New | sync, idempotency, isolation |
| `tests/web/test_worker_private_sync.py` | New | worker cycle |
| `src/`, `web/credentials.py`, `admin.py` | Unchanged | boundary preserved |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| 30s snapshot series unbounded | Med | document; defer retention follow-up |
| `sync.py` trips owned-model guard later | Low | only `bulk_create`/`count`, never `filter/get/all` |
| Payload shape drift (`account` dict-or-list) | Low | normalize once at boundary |
| Patch coverage 100% strict | Med | one test per branch (persist empty/idempotent/error) |

## Rollback Plan

Revert the branch: delete `sync.py` and its tests, restore `worker.py`,
`models.py`, the migration, `test_isolation.py`, `test_owned_model_guard.py`.
`web/credentials.py`, `admin.py`, and `src/` are untouched, so `main` still
ships a working read-only CLI with R13/R14 intact and the global ingest green.

## Dependencies

- `CREDENTIALS_FERNET_KEY` in env (existing Phase-0 contract); `src.client`
  private read-only methods (exist).

## Open Questions

- Retain `order_id` on `Trade` (CLI has it; #57 omits it)? (recommend omit for 6b.)
- Private cadence: every 30s cycle vs a `PRIVATE_SYNC_SECONDS` knob? (recommend per-cycle now.)
- Private snapshot retention: same change or follow-up? (recommend follow-up.)

## Success Criteria

- [ ] Worker decrypts active credentials and syncs positions/account/trades per user.
- [ ] Re-sync is idempotent (0 new rows); R14 A≠B green for all 3 models.
- [ ] `decrypt` confined to `worker.py`; credential + owned-model scanners green.
- [ ] One failing user does not degrade others or global ingest.
- [ ] `python -m pytest` green (Strict TDD); patch coverage 100%; ruff clean; `makemigrations --check` green.
- [ ] No new runtime dependency; no order surface.

## Review Workload Forecast

- Estimated diff: **~450–600 changed lines** (3 models + migration, `sync.py`,
  `worker.py` step, two new test files, two scanner/isolation updates).
- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: High
