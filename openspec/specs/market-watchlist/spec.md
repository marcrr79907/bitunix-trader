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

> **F11 (#124) delta.** R14.8–R14.10 add the JSON transport the chart needs.
> The entity contract (R14.5–R14.7) is unchanged; no migration was required.

### Requirement: R14.8 — CRUD transport and `for_user` scoping

The system MUST expose `GET`/`POST /market/api/watchlist` and `DELETE
/market/api/watchlist/<symbol>`, all `@login_required` (anonymous → 302), with
POST/DELETE CSRF-protected (`X-CSRFToken`, missing → 403). Every read and write MUST
route through `Watchlist.for_user(request.user)`; no unscoped query on the request
path. The owner MUST NEVER come from the body. POST → 201, GET → 200, DELETE → 204.

#### Scenario: A ≠ B isolation on GET and DELETE

- GIVEN A owns `BTCUSDT` and B owns `ETHUSDT`
- WHEN B GETs the list and then DELETEs `BTCUSDT`
- THEN B sees only `ETHUSDT`, the DELETE returns 204, and A's row is unchanged

#### Scenario: Owner is never taken from the body

- GIVEN a POST by A with `{"symbol": "BTCUSDT", "user": B.pk}`
- WHEN the row is written
- THEN its `user` is A

#### Scenario: Anonymous is redirected

- GIVEN an anonymous session
- WHEN any watchlist route is called
- THEN 302 to login is returned

#### Scenario: CSRF is enforced on writes

- GIVEN an authenticated POST or DELETE without `X-CSRFToken`
- WHEN the request is handled
- THEN 403 is returned and no row changes

### Requirement: R14.9 — Virtual default list

A GET with zero rows for the caller MUST return `config.SYMBOLS` with `"default": true`
and MUST NOT write rows (GET stays a read). A GET with rows MUST return them sorted
with `"default": false`.

#### Scenario: Empty list falls back without seeding

- GIVEN A has no watchlist rows
- WHEN A GETs the list
- THEN `{"symbols": config.SYMBOLS, "default": true}` is returned and the row count stays 0

#### Scenario: Populated list is sorted and explicit

- GIVEN A owns `SOLUSDT` and `BTCUSDT`
- WHEN A GETs the list
- THEN `{"symbols": ["BTCUSDT", "SOLUSDT"], "default": false}` is returned

#### Scenario: Default follows the environment

- GIVEN `BITUNIX_SYMBOLS` changed after a previous GET
- WHEN an empty-list user GETs again
- THEN the new `config.SYMBOLS` is returned (nothing was persisted)

### Requirement: R14.10 — Validation, idempotency and cap

POST MUST validate the symbol against the catalog: warm and absent → 400; malformed
(not `^[A-Z0-9]{2,24}$`) → 400. POST MUST be idempotent via `get_or_create` and MUST
reject with 400 at `MAX_WATCHLIST_SYMBOLS` (50). DELETE MUST be idempotent (204 whether
or not the row existed). Error matrix: missing/malformed → 400; unknown-when-warm →
400; at cap → 400; duplicate → 201 without a second row.

#### Scenario: Add an existing catalog symbol

- GIVEN a warm catalog containing `BTCUSDT` and A below the cap
- WHEN A POSTs `{"symbol": "BTCUSDT"}`
- THEN 201 is returned and one row exists for A

#### Scenario: Unknown-when-warm is 400

- GIVEN a warm catalog without `FAKEUSDT`
- WHEN A POSTs `{"symbol": "FAKEUSDT"}`
- THEN 400 is returned and no row is written

#### Scenario: Malformed symbol is 400

- GIVEN a POST with `{"symbol": "btc/usdt"}`
- WHEN the request is handled
- THEN 400 is returned regardless of cache state

#### Scenario: Duplicate is idempotent

- GIVEN A already owns `BTCUSDT`
- WHEN A POSTs `BTCUSDT` again
- THEN 201 is returned and the row count for `(A, BTCUSDT)` stays 1

#### Scenario: Cap rejects a new symbol

- GIVEN A owns 50 symbols
- WHEN A POSTs a 51st catalog symbol
- THEN 400 is returned and the list stays at 50

#### Scenario: DELETE is idempotent

- GIVEN A owns `BTCUSDT`, and later no longer owns it
- WHEN A DELETEs `BTCUSDT` twice
- THEN both calls return 204 and no error leaks
