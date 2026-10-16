# Delta for chart-drawings

Drawings become **per symbol** (issue #124, Ola 3): the key drops `interval` so a
drawing is visible across every interval of a pair (TradingView-style) and is
cleared only on a **symbol** change. First destructive migration in the tree.
Kind schemas (R5), render contract (R6), isolation (R3), and boundary (R8)
are unchanged and stay in force.

## MODIFIED Requirements

### Requirement: R1 — Drawing model, ownership, and index

`Drawing` MUST inherit `UserOwnedModel` (owner FK `on_delete=CASCADE` +
`for_user`) and carry `symbol` (max 32), `kind` (`CharField`, one of
`DRAWING_KINDS`), `points` (`JSONField`), `style` (`JSONField`), and `created_at`
(`auto_now_add`). It MUST be indexed on `(user, symbol)` and MUST NOT carry a
unique constraint on that tuple. No owner-less rows MAY exist. Migration `0012`
MUST remove the old `(user, symbol, interval)` index BEFORE dropping `interval`,
then add the `(user, symbol)` index (SQLite-safe order). It MUST keep ALL rows and
MUST NOT dedupe (no unique constraint means nothing collides; dedupe would destroy
user data). Its reverse MUST be lossy — it re-adds `interval` defaulted to `"1m"`;
the original per-interval split is NOT recoverable (documented rollback contract).
(Previously: keyed `(user, symbol, interval)`, indexed on that tuple, additive `0006`.)

#### Scenario: Many drawings coexist on one chart

- GIVEN A has a `hline` on `BTCUSDT`
- WHEN A creates a second `trendline` on the same symbol
- THEN both rows persist (no `IntegrityError`, distinct `id`)

#### Scenario: Interval drop keeps every row

- GIVEN A has a drawing on `(BTCUSDT, 1m)` and one on `(BTCUSDT, 1h)`
- WHEN `0012` runs
- THEN both rows survive as distinct drawings under `BTCUSDT` (no dedupe, no error)

#### Scenario: JSON round-trip

- GIVEN `points=[{"time":1700000000,"price":50000.0}]` and `style={"color":"#f00","width":1}`
- WHEN saved and re-read
- THEN the nested list and object are equal

#### Scenario: Destructive migration order

- GIVEN the change applied
- WHEN migrations are inspected
- THEN `0012` removes the `interval` index, then the column, then adds `(user, symbol)` (`makemigrations --check` green)

#### Scenario: Reverse is lossy

- GIVEN drawings with `interval` dropped
- WHEN `0012` is reversed
- THEN every row gets `interval="1m"` and the prior per-interval split is gone

### Requirement: R2 — Drawings CRUD API

`GET /market/api/drawings?symbol=` MUST be login-required (anonymous → 302) and
return the caller's drawings for that `(user, symbol)` as
`{"drawings":[{id,kind,points,style}]}`, or an empty list when none exist (never
404). It MUST NOT filter by `interval`. `POST /market/api/drawings` MUST be
login-required and CSRF-protected, validate the payload before any write, store
the row for `(user, symbol)` via `Drawing.for_user(request.user)`, and return the
created row including its `id`; an `interval` key in the body MUST be accepted and
ignored (never 400). `DELETE /market/api/drawings/<id>` MUST be login-required and
CSRF-protected, delete through `Drawing.for_user(request.user)`, and be idempotent
(a miss → 404 with no error leak). Every read/write MUST route through `for_user`.
(Previously: keyed and fetched by `(symbol, interval)`; `interval` required in the body.)

#### Scenario: GET with no drawings returns empty list

- GIVEN A has no drawings
- WHEN GET `?symbol=BTCUSDT`
- THEN 200 `{"drawings":[]}` (no 404)

#### Scenario: GET lists only the caller's symbol

- GIVEN A saved two drawings on `BTCUSDT` and one on `ETHUSDT`
- WHEN GET `?symbol=BTCUSDT` (any `interval` query ignored)
- THEN exactly the two BTCUSDT rows are returned

#### Scenario: POST creates a row with id

- GIVEN a valid `{symbol,kind,points,style}` body
- WHEN POST
- THEN 201 and the returned row carries the new `id`, persisted for A

#### Scenario: Stale interval accepted and ignored

- GIVEN POST `{symbol,interval:"1m",kind,points,style}`
- WHEN handled
- THEN 201 with a row (the `interval` key is ignored, not rejected)

#### Scenario: DELETE by id removes the row

- GIVEN A's drawing `d`
- WHEN DELETE `/market/api/drawings/<d.id>`
- THEN the row is gone and a subsequent GET omits it

#### Scenario: DELETE miss is 404

- GIVEN an `id` that does not exist for A
- WHEN DELETE
- THEN 404 and no row is affected

#### Scenario: Unauthenticated → redirect

- GIVEN an anonymous session
- WHEN GET, POST, or DELETE `/market/api/drawings*`
- THEN 302 to login

#### Scenario: CSRF enforced on write

- GIVEN an authenticated POST or DELETE without a valid CSRF token
- WHEN handled
- THEN 403 and no write occurs

### Requirement: R4 — Validation before write (kind / points / style)

The server MUST validate the payload BEFORE any write; an unknown `kind`, a
`kind` outside `DRAWING_KINDS`, an empty `symbol`, or `points`/`style` not matching
the kind's schema MUST yield 400 `{"error":"..."}` and MUST NOT create a row.
`interval` is NO LONGER part of the drawing contract: its presence or value MUST
NOT yield 400 (accept-and-ignore). Validation MUST live in a pure
`parse_drawing(kind, points, style)` (raise `ValueError`) in `quotes.py`; the view
maps it to 400.
(Previously: an `interval` outside `INTERVALS` yielded 400.)

#### Scenario: Unknown kind → 400 before write

- GIVEN POST `kind="notreal"`
- WHEN handled
- THEN 400 and no row is written

#### Scenario: Interval in body never 400

- GIVEN POST with `interval="7m"` (or any value)
- WHEN handled
- THEN no 400 is raised for the `interval` key

#### Scenario: Bad shape for kind → 400

- GIVEN POST `kind="trendline"` with a single point
- WHEN handled
- THEN 400 and no row is written

### Requirement: R7 — Load and restore on boot and switch

The chart MUST load drawings when it opens: after `buildChart`, fetch the caller's
drawings for the active `symbol` and attach their primitives; a failed fetch MUST
be non-fatal (the chart still renders). `switchTo(symbol, interval)` MUST
detach/clear the previous chart's primitives and reload ONLY when the `symbol`
changed; on an interval-only change drawings MUST stay attached with no refetch.
The `window.marketChart.drawings` seam MUST expose the loaded shapes for tests and
`window.marketChart` MUST keep exactly its 8 frozen keys (no new key).
(Previously: fetched per `(symbol, interval)` and cleared on every switch.)

#### Scenario: Reload restores saved drawings

- GIVEN saved drawings for the active symbol
- WHEN the page reloads
- THEN the chart attaches those primitives and `window.marketChart.drawings` lists them

#### Scenario: Symbol switch clears then loads

- GIVEN drawings on `BTCUSDT` and different ones on `ETHUSDT`
- WHEN `switchTo("ETHUSDT", "1m")` runs
- THEN BTCUSDT primitives are cleared and only ETHUSDT drawings are attached

#### Scenario: Interval-only switch keeps drawings

- GIVEN drawings rendered on `BTCUSDT 1m`
- WHEN `switchTo("BTCUSDT", "1h")` runs
- THEN the drawings stay attached and no drawings refetch is issued

#### Scenario: Failed fetch is non-fatal

- GIVEN the drawings fetch fails
- WHEN the chart boots
- THEN the chart renders with no drawings and no error surfaces

#### Scenario: Seam stays 8 keys

- GIVEN a booted chart
- WHEN `window.marketChart` is read
- THEN exactly `{chart, candleSeries, panes, ready, drawings, smc, smcCounts, smcToggles}` exist (no new key)
