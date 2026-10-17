# Delta for chart-drawings

Issue #120 (F7): the drawing surface gains a **duplicate** operation. It reuses
the existing CRUD (R2) — a clone is created through the same `POST` with cloned
`points` (and a small offset), minting a new id, triggered by a thin
`bus.emit("drawing:duplicate")` handled in `controllers/drawings.js`. This
MODIFIES R2 (CRUD reused; duplicate defined as create-with-cloned-points). R8
(read-only boundary) stays in force and unchanged. R1, R3–R7, R9–R15 stay in force
and unmodified.

## MODIFIED Requirements

### Requirement: R2 — Drawings CRUD API

`GET /market/api/drawings?symbol=` MUST be login-required (anonymous → 302) and
return the caller's drawings for that `(user, symbol)` as
`{"drawings":[{id,kind,points,style,visible,locked}]}`, or an empty list when none
exist (never 404). It MUST NOT filter by `interval`. `POST /market/api/drawings`
MUST be login-required and CSRF-protected, validate the payload before any write,
accept optional `visible`/`locked` booleans (defaulting to True/False), store the
row for `(user, symbol)` via `Drawing.for_user(request.user)`, and return the
created row including its `id` and both flags; an `interval` key in the body MUST
be accepted and ignored (never 400). A non-boolean `visible`/`locked` MUST yield
400 before any write. `PUT /market/api/drawings/<id>` MUST be login-required and
CSRF-protected, resolve through `Drawing.for_user(request.user)` (miss → 404, A≠B
→ 404 with no existence leak), accept a PARTIAL `{points?, style?, visible?,
locked?}` body, treat `kind` as immutable, validate via `parse_drawing`, and
return the updated row `{id,kind,points,style,visible,locked}` (200). A
non-boolean flag MUST yield 400 before any write. `DELETE /market/api/drawings/<id>`
MUST be login-required and CSRF-protected, delete through
`Drawing.for_user(request.user)`, and be idempotent (a miss → 404 with no error
leak). Every read/write MUST route through `for_user`. A **duplicate** MUST be a
plain create: the client MUST reuse `POST /market/api/drawings` with the source
row's `kind`, cloned `points` (optionally offset by a small delta), and its `style`
— minting a NEW id — and MUST NOT introduce a server endpoint or bus event beyond
the existing set.
(Previously: no duplicate operation was defined; POST/list/PUT/DELETE unchanged.)

#### Scenario: Duplicate clones via the existing POST

- GIVEN A's committed `trendline` `d`
- WHEN duplicate runs
- THEN a `POST /market/api/drawings` with `kind`/`points`/`style` cloned from `d` is captured and the response carries a NEW `id` (distinct from `d.id`)

#### Scenario: Duplicate uses no new endpoint

- GIVEN a duplicate in flight
- WHEN the network is inspected
- THEN only the pre-existing drawings endpoint is hit (no duplicate-specific route)

#### Scenario: GET with no drawings returns empty list

- GIVEN A has no drawings
- WHEN GET `?symbol=BTCUSDT`
- THEN 200 `{"drawings":[]}` (no 404)

#### Scenario: POST creates a row with id and flags

- GIVEN a valid `{symbol,kind,points,style,visible:false,locked:true}` body
- WHEN POST
- THEN 201 and the returned row carries the new `id`, `visible:false`, `locked:true`, persisted for A

#### Scenario: PUT updates points, style, and flags

- GIVEN A's `trendline` `d`
- WHEN PUT `/market/api/drawings/<d.id>` with `{points,style,visible,locked}`
- THEN 200 with the updated row and the persisted values match

#### Scenario: PUT kind is immutable

- GIVEN A's drawing `d`
- WHEN PUT includes a `kind` differing from the stored kind
- THEN 400 and no row is modified

#### Scenario: DELETE by id removes the row

- GIVEN A's drawing `d`
- WHEN DELETE `/market/api/drawings/<d.id>`
- THEN the row is gone and a subsequent GET omits it

#### Scenario: Unauthenticated → redirect

- GIVEN an anonymous session
- WHEN GET, POST, PUT, or DELETE `/market/api/drawings*`
- THEN 302 to login

#### Scenario: CSRF enforced on write

- GIVEN an authenticated POST, PUT, or DELETE without a valid CSRF token
- WHEN handled
- THEN 403 and no write occurs
