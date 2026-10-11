# positions-journal-ui Specification

## Purpose

Auth-gated, read-only `/positions/` and `/journal/` pages render the LOGGED-IN
user's own persisted rows via the ownership seam (R14), without secrets in the
request path (R13), delegating all business math to pure `src/` functions.

## Requirements

### Requirement: R1 — Auth-gated Position page

`/positions/` MUST be GET-only, login-required (anonymous → 302 login). It MUST
render the LATEST `PositionSnapshot` per symbol via
`PositionSnapshot.for_user(request.user)` (max-`ts` query), plus a header from the
latest `AccountSnapshot.for_user(request.user)` (`available`, `cross_upnl`).
Columns: symbol, side, qty, avg_open, leverage, liq_price, distance, margin
rate/state, upnl. `distance` MUST come from `src.monitor.liq_distance_pct` and
state from `src.monitor.margin_state`; the mark MUST be the symbol's latest global
`TickerSnapshot.last_price` (`None` → "—"). No rows MUST render an empty state.

#### Scenario: Anonymous redirected and latest-per-symbol

- GIVEN anonymous, WHEN GET `/positions/`, THEN 302 to login
- GIVEN two `ts` cycles for one symbol, WHEN GET, THEN only max-`ts` rows render

#### Scenario: Reused distance/margin math and missing mark

- GIVEN a position and a global `TickerSnapshot.last_price`, WHEN rendered, THEN distance = `liq_distance_pct(liq, mark)` and state = `margin_state(margin_rate)`
- GIVEN a symbol with no `TickerSnapshot`, WHEN rendered, THEN distance is "—" with no error
- GIVEN zero position rows, WHEN GET, THEN 200 with a "no data yet" panel

### Requirement: R2 — Auth-gated Journal page

`/journal/` MUST be GET-only, login-required. It MUST render metrics for the user's
`Trade.for_user(request.user)` rows ONLY, from these pure `src/` functions reused
unchanged and never reimplemented in view or JS: `win_rate`/`net_pnl`/`per_symbol`/
`best`/`worst` from `src.journal.metrics`; `expectancy`/`profit_factor`/`equity_curve`
from `src.metrics`. The view MUST pass in the row list and the net sequence
(`realized_pnl - fee`) and compute no metric arithmetic itself.

#### Scenario: Anonymous redirected and empty state

- GIVEN anonymous, WHEN GET `/journal/`, THEN 302 to login
- GIVEN zero trades, WHEN GET, THEN 200 with a "no data yet" panel

#### Scenario: Known fixture yields expected values

- GIVEN the user's trades `realized_pnl/fee` → nets `[10, -5, 5]`, WHEN GET, THEN win_rate `66.67%`, net_pnl `10.0`, expectancy `3.333…`, profit_factor `3.0`, equity_curve `[10, 5, 10]`, and `per_symbol` matches `journal.metrics`

### Requirement: R3 — Request-path invariants: isolation (R14) and no secrets (R13)

Every read MUST route through `for_user(request.user)`; no
`<OwnedModel>.objects.<verb>()` MAY appear in `web/trading/` view code, and user B
MUST NOT see any of A's rows. Views and templates MUST NOT import, call, or
reference `decrypt` (directly or via `getattr`) and MUST NOT contain secrets. Both
the R14.3 and credential scanners MUST stay green.

#### Scenario: A ≠ B and scanners green

- GIVEN A owns rows and B owns none, WHEN B GETs both pages, THEN B sees empty states and none of A's symbols or trade data
- GIVEN the new views, WHEN the R14.3 and credential scanners run on `web/trading/`, THEN neither reports an offender

### Requirement: R4 — Navigation and CSP

`home.html` MUST link to `/positions/` and `/journal/`. Both pages MUST inherit the
existing CSP with NO relaxation (no `unsafe-inline`). Optional HTMX MUST load only
from the already-allowed `https://unpkg.com` and use `hx-*` attributes.

#### Scenario: Home links both pages

- GIVEN an authenticated user on `/`, WHEN rendered, THEN links to `/positions/` and `/journal/` are present

#### Scenario: CSP unchanged

- GIVEN a GET on either page, WHEN the response arrives, THEN its CSP equals the existing allowlist, no `unsafe-inline`

### Requirement: R5 — Boundary, no new dependency, TDD green

`src/` MUST stay framework-free and unchanged (`tests/test_boundary.py` green);
`web/` MAY import `src/`. `requirements.txt` MUST be unchanged; no schema field,
migration, or order surface MAY be added. `python -m pytest` MUST pass with 100%
patch coverage on new lines; ruff MUST be clean.

#### Scenario: Core boundary green

- GIVEN the new views importing `src/` helpers, WHEN the boundary suite runs, THEN it passes unchanged

#### Scenario: No new dependency, migration, or lint

- GIVEN the change, WHEN `requirements.txt`, migrations, and ruff are inspected, THEN no runtime dependency, model field, or migration was added and lint is clean
