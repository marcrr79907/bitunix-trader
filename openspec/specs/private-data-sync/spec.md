# private-data-sync Specification

## Purpose

First consumer of user credentials (R13) and the private read-only API: the
worker trust zone decrypts ACTIVE credentials and syncs positions, account, and
history trades into three per-user owned models (R14). Persist-only,
request-path-safe fetch module; strictly read-only (R11). New capability.

## Requirements

### Requirement: R1 — Owned private models

Three models MUST inherit `UserOwnedModel` (FK `user` CASCADE, `for_user`) and
be idempotent via a `(user, …)` `UniqueConstraint`:

- `PositionSnapshot` (mirrors `position_row`): `symbol` Char(32); `side`
  Char(8) null; `qty`/`avg_open`/`liq_price`/`upnl`/`margin_rate` Float null;
  `leverage` Integer null (x10/x20…); `ts` DateTime(UTC). Unique
  `(user, symbol, ts)`.
- `AccountSnapshot`: `available`/`cross_upnl` Float null; `ts` DateTime(UTC).
  Unique `(user, ts)`.
- `Trade` (mirrors `trade_row`, no `order_id`): `trade_id` Char(64); `symbol`
  Char(32); `side` Char(8) null; `qty`/`price`/`fee`/`realized_pnl` Float null;
  `ctime` BigInteger null. Unique `(user, trade_id)`.

The migration MUST be additive.

#### Scenario: Three owned models persist with owner

- GIVEN user A and valid position/account/trade payloads
- WHEN each row is saved
- THEN `for_user(A)` returns each row and `for_user(B)` is empty

#### Scenario: Unique keys reject duplicates

- GIVEN a persisted index/account snapshot and a persisted `trade_id`
- WHEN the same `(user, symbol, ts)`, `(user, ts)`, and `(user, trade_id)` recur
- THEN the database rejects each duplicate

#### Scenario: Same trade_id allowed across users

- GIVEN A and B both log exchange trade id `T1`
- WHEN both rows are saved
- THEN both persist (uniqueness is per user)

### Requirement: R2 — Idempotent persistence

`persist_positions/account/trades` MUST write model-ready dicts via
`bulk_create(ignore_conflicts=True)` and report the inserted count from a
row-count delta. Re-persisting an identical payload MUST insert 0 rows.

#### Scenario: Re-sync is a no-op

- GIVEN a payload persisted once
- WHEN the identical payload is persisted again
- THEN the reported count is 0 and row counts are unchanged

#### Scenario: Empty payload persists nothing

- GIVEN an empty position or trade list
- WHEN persistence runs
- THEN it does not raise and returns 0

### Requirement: R3 — Decrypt-free request-path module

`web/trading/sync.py` MUST fetch (`positions()`, `account()`,
`history_trades()` paginated) and persist only. It MUST NOT import or call
`credentials.decrypt`, and MUST touch owned models only via `bulk_create`/`count`.

#### Scenario: sync.py has no decrypt reference

- GIVEN `web/trading/sync.py` in the credential scanner's request path
- WHEN the scanner scans it
- THEN no `decrypt` import, call, bare name, or `getattr` is reported

#### Scenario: Owned-model guard stays green

- GIVEN `sync.py` persisting via `bulk_create`/`count`
- WHEN the R14.3 guard scans the trading tree
- THEN no unscoped-query offender is reported

### Requirement: R4 — Worker trusted-zone private sync

The worker MUST iterate `ExchangeCredential.objects.filter(is_active=True)`
unscoped (R14.4 trusted zone), `decrypt` the encrypted key and secret, build a
`BitunixClient`, and delegate to `sync_user(user, client)`. It MUST run after
the global ingest in the same cycle and MUST preserve the `(funding, ticker)`
return contract.

#### Scenario: Active credentials are synced per user

- GIVEN one active credential and a stub client
- WHEN the worker cycle runs
- THEN that user's positions, account, and trades are persisted

#### Scenario: Inactive credentials are skipped

- GIVEN only inactive credentials
- WHEN the private step runs
- THEN it performs no fetch and is a no-op

### Requirement: R5 — Per-user error isolation

A credential whose client raises MUST NOT prevent other users' sync nor the
global ingest. Each user's step MUST be wrapped so one failure is contained.

#### Scenario: One failing user does not stop peers

- GIVEN user A's client raises and user B's client succeeds
- WHEN the private step runs
- THEN B is still synced and the cycle completes

#### Scenario: Global ingest survives a private failure

- GIVEN a private-sync failure in the cycle
- WHEN `run_once` returns
- THEN the `(funding, ticker)` counts are still produced

### Requirement: R6 — Read-only, no new dependency

The change MUST NOT add any order-execution surface and MUST NOT add a runtime
dependency (`requirements.txt` unchanged). `src/` MUST stay framework-free.

#### Scenario: No order endpoint in new code

- GIVEN the new sync and worker code
- WHEN the order scanner runs
- THEN no order verb or mutating endpoint path is reported

#### Scenario: No runtime dependency added

- GIVEN the change
- WHEN `requirements.txt` is inspected
- THEN no new runtime dependency appears
