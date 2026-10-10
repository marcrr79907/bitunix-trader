# Exploration: private-data-sync (Fase 6b, issue #57)

**Change**: `private-data-sync`
**Issue**: #57 (Fase 6b). Context: #56 (6a, done), #58 (6c, UI, depends on this).
**Date**: 2026-10-10
**Mode**: investigation only. No code written.

## Executive Summary

The worker (trusted zone) must **decrypt active credentials and sync read-only private data** (positions, account, history trades) into three new per-user models. This is the **first real use of `credentials.decrypt` and the private API**. The crux is a clean seam split forced by two live scanners: `web/trading/` is inside the credential scanner's `REQUEST_PATH` (no `decrypt` allowed there), so the new `web/trading/sync.py` must be persistence-and-fetch only, while `web/worker.py` (outside all scanned request paths) owns decryption and credential iteration. Read-only (R11) is absolute; no order surface is touched.

Two scan-critical facts verified:

1. **Decrypt confinement**: `test_credentials_mechanism.py:20` sets `REQUEST_PATH = (config, accounts, trading, market)`. `sync.py` must NOT import/call `credentials.decrypt`; `web/worker.py` is NOT in `REQUEST_PATH` → it may decrypt. Scanners stay green by construction.
2. **Owned-model guard**: `test_owned_model_guard.py:17` sets `REQUEST_PATH = (config, accounts, trading)` (worker excluded). `UNSCOPED_VERBS` (lines 21-34) does **NOT** contain `bulk_create` or `count`. So `sync.py` in `trading/` can persist owned rows via `bulk_create(ignore_conflicts=True)` + `.count()` deltas (the existing `ingest.py` pattern) **without tripping the guard**. The new models, however, MUST be added to `OWNED_MODELS` (line 20) so the guard covers them.

## Current State (read, not guessed)

| Area | Fact | Source |
|---|---|---|
| Owned base | `UserOwnedModel` abstract: `user` FK CASCADE + `for_user(user)` | `web/trading/models.py:90-104` |
| Credentials | `ExchangeCredential(UserOwnedModel)`, ciphertext only, `is_active`, `set_secrets`; no decrypt accessor | `web/trading/models.py:107-127` |
| Decrypt seam | `credentials.decrypt` fail-closed (Fernet key from env); docstring says worker-only | `web/credentials.py:18-32` |
| Credential scanner | `REQUEST_PATH += trading, market`; flags import/attr/bare/getattr `decrypt` | `tests/web/test_credentials_mechanism.py:20,31-62` |
| Owned guard | flags literal `<OwnedModel>.objects.<verb>()`; `UNSCOPED_VERBS` = all/get/filter/exclude/first/last/create/update/get_or_create/update_or_create; **no `bulk_create`, no `count`** | `tests/web/test_owned_model_guard.py:20-64` |
| Worker zone | `run_once(client, symbols) -> (funding, ticker)`; candle cycle isolated try/except; return contract fixed; `INGEST_POLL_SECONDS=30` | `web/worker.py:40-86` |
| Persist style | `bulk_create(ignore_conflicts=True)` + count delta; `UniqueConstraint`; idempotent | `web/trading/ingest.py:65-83`, `candles.py:77-87` |
| Positions payload | `client.positions()` → list; fields `symbol, side (BUY/SELL→LONG/SHORT), qty, avgOpenPrice, leverage, liqPrice, unrealizedPNL, marginRate` | `src/client.py:154-158`, `src/monitor.py:161-179` |
| Account payload | `client.account()` → dict-or-list; fields `available, crossUnrealizedPNL` | `src/client.py:160-165`, `src/monitor.py:238-239` |
| Trades payload | `client.history_trades()` → `{tradeList:[...]}`; fields `tradeId, orderId, symbol, side, qty, price, fee, realizedPNL, ctime` (ms) | `src/client.py:167-173`, `src/journal.py:29-40` |
| Trade upsert (CLI) | SQLite `trades.trade_id TEXT PRIMARY KEY`, `INSERT OR IGNORE` | `src/db.py:33-45,78-88` |
| Isolation harness | `user_a`/`user_b` fixtures; A≠B asserts for both existing owned models | `tests/web/conftest.py`, `test_isolation.py` |
| Retention | `prune_snapshots` prunes `FundingSnapshot`/`TickerSnapshot` only, never `Candle` | `openspec/changes/cron-jobs/` |

## 1. Model field sets (proposed, mirroring the CLI)

All three live in `web/trading/models.py`, inherit `UserOwnedModel` (`user` FK CASCADE, `for_user`), and are idempotent via a `(user, …)` `UniqueConstraint`.

**`PositionSnapshot`** (mirrors `position_row`, one row per position per poll):

| field | type | null | notes |
|---|---|---|---|
| `user` | FK CASCADE | no | from `UserOwnedModel` |
| `symbol` | CharField(32) | no | |
| `side` | CharField(8) | yes | normalized `LONG`/`SHORT` |
| `qty` | FloatField | yes | raw can be `""` → None |
| `avg_open` | FloatField | yes | `avgOpenPrice` |
| `leverage` | FloatField | yes | raw may be str |
| `liq_price` | FloatField | yes | |
| `upnl` | FloatField | yes | `unrealizedPNL` |
| `margin_rate` | FloatField | yes | |
| `ts` | DateTimeField (UTC) | no | poll instant |

`UniqueConstraint(user, symbol, ts)` — re-poll of the same instant is a no-op.

**`AccountSnapshot`** (mirrors the balance dict, one row per poll):

| field | type | null | notes |
|---|---|---|---|
| `user` | FK CASCADE | no | |
| `available` | FloatField | yes | |
| `cross_upnl` | FloatField | yes | `crossUnrealizedPNL` |
| `ts` | DateTimeField (UTC) | no | |

`UniqueConstraint(user, ts)`.

**`Trade`** (mirrors `trade_row`, one row per exchange trade — **not** a snapshot series):

| field | type | null | notes |
|---|---|---|---|
| `user` | FK CASCADE | no | |
| `trade_id` | CharField(64) | no | exchange id (string key) |
| `symbol` | CharField(32) | no | |
| `side` | CharField(8) | yes | uppercased |
| `qty` | FloatField | yes | |
| `price` | FloatField | yes | |
| `fee` | FloatField | yes | |
| `realized_pnl` | FloatField | yes | `realizedPNL` |
| `ctime` | BigIntegerField | yes | raw epoch ms |

`UniqueConstraint(user, trade_id)`. Idempotency is `(user, trade_id)` — same trade id across users must NOT collide (differs from the CLI's global `trade_id` PK). `order_id` is present in the CLI but omitted here: **open question** (issue #57 lists fields without it).

Migration: one additive `0004_private_snapshots.py`, `makemigrations --check` green.

## 2. The decrypt split (the core seam)

- **`web/trading/sync.py` (NEW, request-path-safe, NO decrypt):**
  - `persist_positions(user, rows) -> int`, `persist_account(user, row) -> int`, `persist_trades(user, rows) -> int` — each maps raw DictCU payload → model dicts (reusing `src.monitor.position_row`/`src.journal.trade_row` where practical), then `bulk_create(ignore_conflicts=True)` + count delta.
  - `sync_user(user, client) -> dict` — orchestration: `client.positions()`, `client.account()`, `client.history_trades()` (with `skip` pagination mirroring `journal.sync`), delegates to the `persist_*` helpers.
  - Imports: `trading.models`, `src.monitor`, `src.journal`. **No `credentials` import** → credential scanner green.
  - Uses only `bulk_create`/`count` on owned models (never `filter/get/all`) → owned-model guard green.

- **`web/worker.py` (MODIFIED, trusted zone, owns decrypt):**
  - `run_private_sync(client_factory=BitunixClient)` — `for cred in ExchangeCredential.objects.filter(is_active=True)` (**allowed**: worker.py is outside `REQUEST_PATH`), `secret = decrypt(cred.api_secret_encrypted)` / key likewise, build `client_factory(key, secret)`, then `try: sync_user(cred.user, client) except Exception: log`. One user's failure is isolated.
  - Called from `run_once` after the candle cycle, in its own isolated `try/except` (same pattern as candles), so the `(funding, ticker)` return contract is **unchanged** and no active creds → no-op (existing worker tests unaffected).
  - Lazy imports inside the function (Django not set up at import time), matching the existing `_bootstrap()` ordering.

## 3. OWNED_MODELS update

`tests/web/test_owned_model_guard.py:20` MUST gain the three new names:
`OWNED_MODELS = frozenset({"ExchangeCredential", "Watchlist", "PositionSnapshot", "AccountSnapshot", "Trade"})`.
Does `bulk_create` trip the guard? **No** — it is absent from `UNSCOPED_VERBS`. `count()` is also absent. The worker's `ExchangeCredential.objects.filter(...)` uses a flagged verb but lives in `worker.py`, which is **not** in the guard's `REQUEST_PATH` (R14.4 trusted zone). Both scanners stay green. No resolution hack needed.

## 4. Worker integration & cadence

- Private sync runs **inside the existing cycle** (every 30s), as an independently isolated step after ticks+candles. Simplest correct option; the `(funding, ticker)` contract is preserved and the global ingest can never be degraded by a private failure (per-user AND per-step isolation).
- **Growth risk**: a 30s position/account snapshot series grows ~2,880 rows/user/symbol/day. `prune_snapshots` does **not** cover these tables today. **Open question for design**: private cadence (`PRIVATE_SYNC_SECONDS`) and/or retention. Recommend keeping every-cycle for 6b and flagging retention as a follow-up (do not silently extend prune in this change).
- Optionally a `PRIVATE_SYNC_SECONDS` env guard, defaulting to the ingest poll, if reviewers want a knob. Ladder says skip until needed; note as open question.

## 5. Idempotency

- Positions/account: `(user, symbol, ts)` / `(user, ts)` + `ignore_conflicts` → re-sync of the same instant inserts 0.
- Trades: `(user, trade_id)` + `ignore_conflicts` → re-sync of a page inserts 0. Pagination stops when `len(batch) < limit` (mirrors `journal.sync`).

## 6. Tests required (Strict TDD, `python -m pytest`, patch gate 100%)

1. Model constraints: unique `(user,symbol,ts)`, `(user,ts)`, `(user,trade_id)`; nullability; same `trade_id` allowed across users.
2. R14 A≠B for the 3 new models (extend `test_isolation.py`).
3. Decrypt confinement: credential scanner green (no new code); assert `sync.py` has no `decrypt`.
4. Idempotent re-sync: `persist_*` twice → 0 new rows.
5. Per-user isolation: a stub user-client that raises does not stop the next user.
6. Worker cycle persists private data with a stub client + stub credential factory.
7. `OWNED_MODELS` guard covers the 3 new models (fixture test).

## 7. Scope boundaries

**In**: 3 owned models + migration; `sync.py` (fetch+persist, no decrypt); `worker.py` private-sync step (decrypt, per-user isolation); `OWNED_MODELS` guard update; tests; 100% patch coverage; ruff clean; no new dependency.

**Out**: UI/views/templates (6c); alerts (Fase 7); retention/decimation of private snapshots (follow-up); credential rotation; self-service provisioning; **any order execution — hard invariant (R11)**.

## 8. Risks & open questions

- **Snapshot growth** (Med): 30s series with no retention. Mitigation: document + defer retention to a follow-up; consider a cadence knob.
- **`sync.py` in the request path** (Low): any future `filter/get/all` on owned models trips the guard. Keep strictly to `bulk_create`/`count`.
- **Payload shape drift** (Low): `account()` may return dict or list (CLI normalizes); `positions()` may return symbols outside `config.SYMBOLS` — no mark-price dependency here, so fine.
- **`order_id`** omitted vs CLI (Low): confirm whether Trade needs it.
- **Cadence** (Med): every-cycle vs own interval — decide in design.
- **Decimal precision**: CLI uses `float`; SQLite/Postgres FloatField matches the existing global-snapshot choice. Consistent, accepted.

## Affected Areas

- `web/trading/models.py` — add 3 owned models (Modified).
- `web/trading/migrations/0004_*` — additive (New).
- `web/trading/sync.py` — fetch+persist seam, no decrypt (New).
- `web/worker.py` — private-sync step + decrypt (Modified).
- `tests/web/test_owned_model_guard.py` — `OWNED_MODELS` += 3 (Modified).
- `tests/web/test_isolation.py` — A≠B for 3 models (Modified).
- `tests/web/test_private_sync.py` — sync + idempotency + isolation (New).
- `tests/web/test_worker_private_sync.py` — worker cycle (New).

## Recommendation

Adopt the split exactly as the scanners force it: **`sync.py` = fetch+persist, no decrypt; `worker.py` = decrypt + credential iteration + per-user isolation**. Persist via `bulk_create(ignore_conflicts=True)` + count delta, matching `ingest.py`/`candles.py`. Add the 3 models to `OWNED_MODELS`. Run private sync per cycle with per-user isolation and preserve the `(funding, ticker)` return contract. Defer retention to a follow-up and surface it as an explicit open question.

## Ready for Proposal

Yes — scope, field sets, seam split, scanner impact, idempotency keys, test matrix, and risks are all grounded in read code.
