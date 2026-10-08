# market-watchlist Specification

## Purpose

Per-user symbol watchlist — the second owned model that proves the ownership seam generalises beyond the secret table (R14). New capability — no prior spec.

## Requirements

### Requirement: R14.5 — Per-user symbol list

`Watchlist` MUST store a per-user list of exchange symbols and MUST inherit the ownership contract (`UserOwnedModel` + `for_user`).

Entity contract:
- `user`: FK to `AUTH_USER_MODEL`, `on_delete=CASCADE`, `related_name="watchlist"`
- `symbol`: `CharField(max_length=32)`
- `created_at`: `auto_now_add`
- `UniqueConstraint(user, symbol)`

#### Scenario: A user owns their own symbols

- GIVEN user A adds `BTCUSDT`
- WHEN `for_user(A)` is evaluated
- THEN it contains that symbol

#### Scenario: Cross-user read denied

- GIVEN A owns a `Watchlist` row
- WHEN `for_user(B).get(pk=row.pk)` is called
- THEN it raises `DoesNotExist`

### Requirement: R14.6 — Duplicate symbol rejected

Adding the same symbol twice for the same user MUST be rejected by the database uniqueness constraint.

#### Scenario: Duplicate (user, symbol) raises IntegrityError

- GIVEN user A already has `BTCUSDT`
- WHEN another `Watchlist(user=A, symbol="BTCUSDT")` is saved
- THEN the database raises `IntegrityError`

#### Scenario: Same symbol allowed across users

- GIVEN A and B both track `BTCUSDT`
- WHEN both rows are saved
- THEN both persist (uniqueness is per user)

### Requirement: R14.7 — Owned-scoped reads

All reads of a watchlist MUST route through `for_user(user)`. Watchlist data MUST NOT be read cross-user.

#### Scenario: List only the owner's symbols

- GIVEN A owns two symbols and B owns one
- WHEN `for_user(A)` is evaluated
- THEN exactly A's two symbols are returned
