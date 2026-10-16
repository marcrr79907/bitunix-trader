# Delta for market-chart

Issue #117 (Fase F4, Ola 4): the chart gains drawing selection, drag, keyboard
delete/deselect, and a properties dialog, plus a `PUT` persistence path. This
MODIFIES R11 (the drawings endpoint/render contract) to add `PUT
/market/api/drawings/<id>` and the interaction/render seam. Existing requirements
(R1–R10, R12+) stay in force and unmodified.

## MODIFIED Requirements

### Requirement: R11 — Drawings endpoint and render/restore contract

`/market/api/drawings` MUST expose the caller's persisted drawings for a chart.
`GET ?symbol=&interval=` MUST be GET-only and login-required (anonymous → 302)
and MUST return the caller's drawings for that `(symbol, interval)` as
`{"drawings":[...]}`, or an empty list when none exist (never 404). `POST` MUST be
login-required and CSRF-protected, validate `kind`/`interval`/`symbol`/`points`/
`style` before any write (unknown `kind`, bad shape, or invalid `interval` → 400),
create through `Drawing.for_user(request.user)`, and return the created row with
its `id`. `PUT /market/api/drawings/<id>` MUST be login-required and
CSRF-protected, resolve through `Drawing.for_user(request.user)` (miss → 404 and
another user's `id` → 404 with no leak), accept a PARTIAL `{points?, style?}`
body, keep `kind` immutable, validate via `parse_drawing` (→ 400 before write),
and return the updated row `{id,kind,points,style}` (200). `DELETE
/market/api/drawings/<id>` MUST be login-required and CSRF-protected, delete
through `Drawing.for_user(request.user)` (miss → 404), and never touch another
user's row. The market page MUST render saved drawings via the already-loaded
Lightweight Charts v5.2.0 series primitive (no new dependency, no DOM access —
CSP unchanged), restore them after `buildChart` and on `switchTo(symbol,
interval)` (clearing the previous key's primitives), and MUST support selecting,
dragging, keyboard deleting/deselecting, and restyling a drawing, persisting a
drag via ONE `PUT` on `pointerup` through `requestUpdate` only (never
`setData`/`update`; #68). It MUST NOT introduce inline script/handlers or relax
the read-only boundary.
(Previously: only GET/POST/DELETE, no `PUT`; no interaction/render seam.)

#### Scenario: GET empty when no drawings

- GIVEN an authenticated user with no drawings
- WHEN GET `?symbol=BTCUSDT&interval=1m`
- THEN 200 `{"drawings":[]}` (no 404)

#### Scenario: POST then GET returns the drawing

- GIVEN a valid drawing payload
- WHEN POST then GET the same key
- THEN 201 with an `id`, and GET lists that drawing

#### Scenario: Invalid kind → 400 before write

- GIVEN POST `kind="notreal"`
- WHEN handled
- THEN 400 `{"error":"..."}` before any write

#### Scenario: PUT updates a drawing in place

- GIVEN the caller's drawing `d`
- WHEN PUT `/market/api/drawings/<d.id>` with a partial `{points, style}`
- THEN 200 with the updated row; a following GET lists the new coordinates

#### Scenario: PUT miss or cross-user is 404

- GIVEN an unknown `id`, or an `id` owned by another user
- WHEN PUT
- THEN 404 and no row is modified

#### Scenario: PUT kind immutable → 400

- GIVEN the caller's drawing `d`
- WHEN PUT carries a differing `kind`
- THEN 400 before any write

#### Scenario: DELETE by id is idempotent-by-id

- GIVEN the caller's drawing `d`
- WHEN DELETE `/market/api/drawings/<d.id>`
- THEN 200 and the row is removed; a second DELETE of the same id yields 404

#### Scenario: Per-user isolation

- GIVEN user A's drawing `d`
- WHEN user B GETs the same key or PUTs/DELETEs `<d.id>`
- THEN B sees no drawing and B's PUT/DELETE returns 404; A's row is unchanged

#### Scenario: Select, drag, and persist round-trips

- GIVEN a rendered drawing
- WHEN it is selected and dragged, then the drag ends
- THEN exactly one `PUT /market/api/drawings/<id>` is issued and the seam shows the new points

#### Scenario: Drawings render and restore

- GIVEN saved drawings for the active key
- WHEN the page loads or `switchTo` changes symbol/interval
- THEN primitives attach for the new key, previous primitives are cleared, and `window.marketChart.drawings` lists the loaded shapes

#### Scenario: Market page stays CSP-clean

- GIVEN the rendered `/market/` page
- WHEN the response header and templates are inspected
- THEN `Content-Security-Policy` is unchanged and no inline script/handler exists
