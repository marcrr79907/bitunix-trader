# Delta for market-chart

D2 registers the `/signals/` screen route in the market app. R1–R12 are
unchanged; this delta only adds the route to the market URL set and reaffirms the
existing CSP/read-only invariants for the new page.

## ADDED Requirements

### Requirement: R13 — `/signals/` route is registered in the market app

`market/urls.py` MUST register a GET-only `signals` route serving the
`signals-screen` capability at `/signals/`, without altering any existing market
route. The new page MUST carry the SAME `Content-Security-Policy` header as the
market page (R6) — no relaxation — and MUST NOT introduce inline script/handlers
or a runtime dependency (R7). The route MUST match no order-scanner forbidden
fragment.

#### Scenario: Route registered and namespaced

- GIVEN the market URL configuration
- WHEN it is resolved
- THEN `/signals/` maps to the signals view and every existing market route is unchanged

#### Scenario: CSP and boundary unchanged

- GIVEN a rendered `/signals/` response
- WHEN the header and manifest are inspected
- THEN the CSP is unchanged (no relaxation), no inline script exists, no runtime dependency was added, and the order scanner is clean
