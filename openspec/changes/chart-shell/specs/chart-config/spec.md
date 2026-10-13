# Delta for chart-config

Issue #116 (Fase F3). Adds a **user-global last-interval preference** — distinct
from the existing per-`(user, symbol, interval)` layout (`ChartLayout`). NEW
behavior; existing R1–R7 are unchanged and still in force.

## ADDED Requirements

### Requirement: R8 — User-global interval preference model

`ChartPreference` MUST inherit `UserOwnedModel` (owner FK `on_delete=CASCADE` +
`for_user`), with a `OneToOneField` to the user (exactly one row per user) and a
`last_interval` `CharField(max_length=8)` validated against `quotes.INTERVALS`.
It MUST NOT reuse or overload `ChartLayout` (a preference is user-global, not
per-chart). The migration MUST be additive (`makemigrations --check` green).

#### Scenario: One row per user

- GIVEN A saved a preference
- WHEN A saves again
- THEN exactly one row holds the latest `last_interval`

#### Scenario: Additive migration

- GIVEN the change
- WHEN `makemigrations --check` runs
- THEN it passes (no pending model drift)

#### Scenario: JSON/field round-trip

- GIVEN `last_interval="4h"`
- WHEN saved and re-read
- THEN the value equals `"4h"` and no owner-less row exists

### Requirement: R9 — Preference API

`GET /market/api/preference` MUST be login-required (anonymous → 302) and return
the caller's preference, or `{interval:"1m", exists:false}` when none exists
(never 404). `PUT /market/api/preference` MUST be login-required and
CSRF-protected, validate `interval` against `quotes.INTERVALS` (invalid → 400
before any write), upsert through `ChartPreference.for_user(request.user)`, and
return the saved preference. The route MUST be registered in `market/urls.py`
without altering existing routes.

#### Scenario: GET default when no preference

- GIVEN A has no preference
- WHEN GET `/market/api/preference`
- THEN 200 `{interval:"1m", exists:false}` (no 404)

#### Scenario: PUT then GET returns the saved interval

- GIVEN A PUT `{interval:"1h"}`
- WHEN GET the preference
- THEN 200 `{interval:"1h", exists:true}`

#### Scenario: Invalid interval → 400

- GIVEN PUT `{interval:"7m"}`
- WHEN handled
- THEN 400 `{"error":"..."}` and no row is written

#### Scenario: Unauthenticated → redirect

- GIVEN an anonymous session
- WHEN GET or PUT `/market/api/preference`
- THEN 302 to login

### Requirement: R10 — Boot restore and save on change

Boot MUST asynchronously fetch the preference BEFORE `start()` and apply the
saved interval as the initial chart interval; a failed or empty fetch MUST fall
back to `"1m"` and MUST NOT block boot (the `gen` guard stays intact). An
interval change (chip or select) MUST debounce-PUT the preference, mirroring
`saveLayout`; a failed save MUST be non-fatal to the in-session chart.

#### Scenario: Persisted interval restores on reload

- GIVEN A previously saved `last_interval="1h"`
- WHEN the page reloads on `/market/`
- THEN the initial chart interval is `1h` and the active chip reflects it

#### Scenario: Fetch failure defaults to 1m

- GIVEN the preference fetch fails at boot
- WHEN the page boots
- THEN the chart renders with interval `1m` (never blank) and boot is not blocked

#### Scenario: Change persists

- GIVEN an active chart on `1m`
- WHEN the interval changes to `5m`
- THEN one debounced `PUT /market/api/preference` with `{interval:"5m"}` is observed

### Requirement: R11 — Per-user isolation (R14) and CSP

Both GET and PUT MUST route through `ChartPreference.for_user(request.user)`
(A ≠ B isolation); request path code MUST NOT use unscoped queries. No inline
`<script>`/handler MAY be added; the market CSP and `requirements.txt` MUST be
unchanged.

#### Scenario: B never sees A's preference

- GIVEN A saved `last_interval="4h"`
- WHEN B GETs the preference
- THEN B receives `{interval:"1m", exists:false}`

#### Scenario: B's PUT does not touch A's row

- GIVEN A's preference
- WHEN B PUTs a preference
- THEN B gets its own row and A's row is unchanged

#### Scenario: CSP unchanged

- GIVEN the rendered market page
- WHEN the header is inspected
- THEN the CSP equals the prior value and no inline script exists
