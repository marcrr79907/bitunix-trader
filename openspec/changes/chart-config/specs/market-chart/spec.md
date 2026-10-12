# Delta for market-chart

Issue #71 (Fase A2): the chart gains a per-user persisted layout. A new
requirement R10 covers the `/market/api/layout` GET/PUT contract. Existing
requirements (R1–R9: kline shape, single-source math, CSP, boundary, live stream,
pagination) stay in force and unmodified.

## ADDED Requirements

### Requirement: R10 — Layout endpoint and restore contract

`/market/api/layout` MUST expose the caller's persisted chart layout.
`GET ?symbol=&interval=` MUST be GET-only and login-required (anonymous → 302),
and MUST return the caller's layout for that `(symbol, interval)` or the built-in
DEFAULT set with `exists:false` when none exists (never 404). `PUT` MUST be
login-required and CSRF-protected, upsert the caller's layout for the payload's
`(symbol, interval)` through `ChartLayout.for_user(request.user)`, validate every
indicator `token` against `quotes.REGISTRY` (unknown token or bad param → 400
before any write), and return the saved layout. The `(user, symbol, interval)`
key is unique. The market page MUST NOT introduce inline script/handlers; the
layout fetch/save uses same-origin JS with the page CSRF token (CSP unchanged,
no new dependency).

#### Scenario: GET default when no layout

- GIVEN an authenticated user with no saved layout
- WHEN GET `?symbol=BTCUSDT&interval=1m`
- THEN 200 with the default set and `exists:false` (no 404)

#### Scenario: PUT then GET returns the saved layout

- GIVEN a PUT with a valid indicator set
- WHEN GET the same symbol and interval
- THEN 200 with the saved set and `exists:true`

#### Scenario: Invalid indicator → 400

- GIVEN PUT `indicators=[{"token":"notreal"}]`
- WHEN handled
- THEN 400 `{"error":"..."}` before any write

#### Scenario: Per-user isolation

- GIVEN user A's saved layout
- WHEN user B GETs the same symbol and interval
- THEN B receives the default set, never A's layout

#### Scenario: Market page stays CSP-clean

- GIVEN the rendered `/market/` page
- WHEN the response header and templates are inspected
- THEN `Content-Security-Policy` is unchanged and no inline script/handler exists
