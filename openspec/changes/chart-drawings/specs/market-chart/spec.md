# Delta for market-chart

Issue #72 (Fase A3): the chart gains a per-user drawing collection. A new
requirement R11 covers the `/market/api/drawings` GET/POST/DELETE contract plus
the v5 primitive render/restore behavior. Existing requirements (R1–R10: kline
shape, single-source math, CSP, boundary, live stream, pagination, layout) stay
in force and unmodified.

## ADDED Requirements

### Requirement: R11 — Drawings endpoint and render/restore contract

`/market/api/drawings` MUST expose the caller's persisted drawings for a chart.
`GET ?symbol=&interval=` MUST be GET-only and login-required (anonymous → 302)
and MUST return the caller's drawings for that `(symbol, interval)` as
`{"drawings":[...]}`, or an empty list when none exist (never 404). `POST` MUST be
login-required and CSRF-protected, validate `kind`/`interval`/`symbol`/`points`/
`style` before any write (unknown `kind`, bad shape, or invalid `interval` → 400),
create through `Drawing.for_user(request.user)`, and return the created row with
its `id`. `DELETE /market/api/drawings/<id>` MUST be login-required and
CSRF-protected, delete through `Drawing.for_user(request.user)` (miss → 404), and
never touch another user's row. The market page MUST render saved drawings via the
already-loaded Lightweight Charts v5.2.0 series primitive (no new dependency, no
DOM access — CSP unchanged), restore them after `buildChart` and on
`switchTo(symbol, interval)` (clearing the previous key's primitives), and MUST
NOT introduce inline script/handlers or relax the read-only boundary.

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

#### Scenario: DELETE by id is idempotent-by-id

- GIVEN the caller's drawing `d`
- WHEN DELETE `/market/api/drawings/<d.id>`
- THEN 200 and the row is removed; a second DELETE of the same id yields 404

#### Scenario: Per-user isolation

- GIVEN user A's drawing `d`
- WHEN user B GETs the same key or DELETEs `<d.id>`
- THEN B sees no drawing and B's DELETE returns 404; A's row is unchanged

#### Scenario: Drawings render and restore

- GIVEN saved drawings for the active key
- WHEN the page loads or `switchTo` changes symbol/interval
- THEN primitives attach for the new key, previous primitives are cleared, and `window.marketChart.drawings` lists the loaded shapes

#### Scenario: Market page stays CSP-clean

- GIVEN the rendered `/market/` page
- WHEN the response header and templates are inspected
- THEN `Content-Security-Policy` is unchanged and no inline script/handler exists
