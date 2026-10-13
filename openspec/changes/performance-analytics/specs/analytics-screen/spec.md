# analytics-screen Specification

## Purpose

Server-rendered, read-only `/analytics/` screen in the `trading` app, showing the
caller's own performance breakdowns (by SMC-setup kind / UTC hour / symbol) and
the SMC-vs-trades calibration, plus inline-SVG charts. Charts are pure Python
inline SVG — no JS, no new dependency, CSP unchanged. `/journal/` stays frozen.
New capability — no prior spec.

## Requirements

### Requirement: AS1 — Route and auth

`trading/urls.py` MUST register a GET-only `analytics` route at `/analytics/`
without altering any existing route (`/journal/` included). It MUST require login
(`login_required`); anonymous MUST 302-redirect to login. Authenticated MUST render
server-rendered HTML extending the base shell (no JSON endpoint, no inline script).
A nav link MAY be added in `base.html`.

#### Scenario: Anonymous redirected
- GIVEN an anonymous session
- WHEN GET `/analytics/`
- THEN 302 to login

#### Scenario: Authenticated renders
- GIVEN a logged-in user
- WHEN GET `/analytics/`
- THEN 200 HTML extending the base template and `/journal/` behavior is unchanged

### Requirement: AS2 — Per-user scoping

Every trade read MUST route through `Trade.for_user(request.user)`; the view MUST
NOT read another user's trades and MUST NOT use `<OwnedModel>.objects.<verb>()` in
request-serving code. User B MUST NOT see any of A's analytics. A user with no
trades MUST get a 200 empty state (no error). Historical SMC signals are global
market data (computed from `Candle`), but trades are joined in Python **after**
scoping to the caller.

#### Scenario: A ≠ B
- GIVEN A owns trades and B owns none
- WHEN B GETs `/analytics/`
- THEN B sees empty states and none of A's symbols or trade data

#### Scenario: No trades is empty, not an error
- GIVEN a user with no `Trade`
- WHEN GET `/analytics/`
- THEN 200 with an empty state (no exception)

### Requirement: AS3 — Breakdowns and calibration content

The screen MUST render the grouped metrics from `src/analytics.py` for the
dimensions `setup`, `hour`, and `symbol` (`group_metrics`), each bucket showing
net PnL, win rate, expectancy, profit factor and max drawdown, and MUST render the
calibration block from `calibrate(signals, trades, window_seconds=...)` with
`matched`/`unmatched` summaries and a `by_setup` table (`r_by_setup` shown as `—`
when `None`). All metric arithmetic MUST come from `src/analytics.py` /
`src/metrics.py` — the view and template MUST NOT reimplement math. The hour
dimension MUST be the caller-supplied UTC hour (`(ctime_ms // 3_600_000) % 24`).

#### Scenario: Grouped tables rendered
- GIVEN a user with trades spanning setups, hours, and symbols
- WHEN GET `/analytics/`
- THEN each dimension renders its `group_metrics` buckets with the metric columns

#### Scenario: Calibration block rendered
- GIVEN signals exist within the window
- WHEN GET `/analytics/`
- THEN `matched`, `unmatched`, and the `by_setup` table render; a `None` R shows `—`

#### Scenario: View does not recompute math
- GIVEN the rendered page
- WHEN the view/template are inspected
- THEN no metric formula is duplicated outside `src/`

### Requirement: AS4 — Inline SVG charts, no JS, no new dependency

Charts MUST be server-rendered inline **SVG** produced by a pure Python builder
exposing at minimum `svg_polyline(points: list[tuple[float, float]], **opts) -> str`
returning an SVG markup string, deterministic for identical input, with no I/O and
no external dependency. The page MUST contain no inline `<script>` and no inline
event handler, MUST NOT relax the `Content-Security-Policy` header, and MUST NOT
add a runtime dependency or load a second chart library. The SVG MUST carry
accessible labels (`role="img"` + `aria-label`, or a `<title>`). SVG is HTML
markup, not script — it MUST NOT require a CSP change.

#### Scenario: Equity chart is inline SVG
- GIVEN a user with an equity curve
- WHEN GET `/analytics/`
- THEN the response contains an inline `<svg>` and no `<script>` and no `on*=` handler

#### Scenario: SVG builder is deterministic and pure
- GIVEN identical points and options
- WHEN `svg_polyline` runs twice
- THEN both strings are byte-identical and no exception is raised on empty points

#### Scenario: CSP and dependency unchanged
- GIVEN a rendered `/analytics/` response
- WHEN the header and manifest are inspected
- THEN `Content-Security-Policy` equals the prior value and `requirements.txt` is unchanged

### Requirement: AS5 — Historical signal seam

Historical SMC signals for calibration MUST be extracted via `market.quotes`
with the frozen chain (`src/smc/` stays the sole SMC math home). `get_smc_payload`
MUST accept a keyword-only `before=None` (UNIX seconds, exclusive upper bound) so
the chain can run over candles ending at a trade's bar; when omitted, behavior MUST
be identical to today. The view/helper MUST NOT recompute SMC math.

#### Scenario: before bounds the window
- GIVEN `get_smc_payload(client, symbol, interval, limit, before=T)`
- WHEN it runs
- THEN the SMC chain computes over candles older than `T`, via the shared DB-first seam

#### Scenario: before omitted is backward compatible
- GIVEN a call without `before`
- WHEN it runs
- THEN the payload equals the pre-change newest-window payload

#### Scenario: SMC math not duplicated
- GIVEN the analytics seam
- WHEN inspected
- THEN setup math still lives only in `src/smc/`

### Requirement: AS6 — Read-only boundary

The `/analytics/` screen and the signal seam MUST NOT place, modify, or cancel
orders; MUST NOT add an execution path, an exchange-client import, or a new
runtime dependency; and MUST NOT add a schema field or migration. The R11 order
scanner MUST stay clean and `/journal/` MUST remain frozen.

#### Scenario: Order scanner clean
- GIVEN the new view, seam, and template
- WHEN the R11 order-surface scanner runs
- THEN no order-execution surface is reported

#### Scenario: No schema change
- GIVEN the change
- WHEN migrations are inspected
- THEN no new migration or model field exists
