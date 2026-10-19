# Delta for market-watchlist

Issue #124 (F11): the `Watchlist` entity exists (`web/trading/models.py:130-144`, unique
`(user, symbol)`) but has no transport. This ADDS R14.8 (JSON CRUD, CSRF, `for_user`
scoping), R14.9 (virtual default) and R14.10 (validation, idempotency, 50-symbol cap).
R14.5, R14.6 and R14.7 stay in force and unmodified. No migration.

## ADDED Requirements

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
