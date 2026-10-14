# Delta for chart-config

Issue #121 (Fase F8). Adds two user-global, additive `ChartPreference` fields
(`scale_mode`, `chart_type`) and extends the preference API to partial-body PUTs
with per-field 400 validation. R8/R9 change; R10 (boot restore) and R11
(isolation/CSP) stay in force, extended only by the two new fields. Migration
`0010` is additive (two `CharField`s with defaults).

## MODIFIED Requirements

### Requirement: R8 — User-global interval preference model

`ChartPreference` MUST inherit `UserOwnedModel` (owner FK `on_delete=CASCADE` +
`for_user`), with a `OneToOneField` to the user (exactly one row per user), a
`last_interval` `CharField(max_length=8)` validated against `quotes.INTERVALS`, a
`scale_mode` `CharField(max_length=16, default="linear")` validated against
`SCALE_MODES`, and a `chart_type` `CharField(max_length=16, default="candles")`
validated against `CHART_TYPES`. It MUST NOT reuse or overload `ChartLayout` (a
preference is user-global, not per-chart). The migration `0010` MUST be additive
(`makemigrations --check` green).
(Previously: the model carried only `last_interval`, migration `0009`.)

#### Scenario: One row per user

- GIVEN A saved a preference
- WHEN A saves again
- THEN exactly one row holds the latest values

#### Scenario: Additive migration 0010

- GIVEN the change
- WHEN `makemigrations --check` runs
- THEN it passes and `0010` adds only the two columns with defaults

#### Scenario: Field round-trip

- GIVEN `last_interval="4h"`, `scale_mode="log"`, `chart_type="area"`
- WHEN saved and re-read
- THEN each value equals its saved value and no owner-less row exists

### Requirement: R9 — Preference API

`GET /market/api/preference` MUST be login-required (anonymous → 302) and return
the caller's preference as `{interval, scale_mode, chart_type, exists}`, or
`{interval:"1m", scale_mode:"linear", chart_type:"candles", exists:false}` when
none exists (never 404). `PUT /market/api/preference` MUST be login-required and
CSRF-protected and MUST accept a PARTIAL body: only the keys present are applied.
Each present field MUST be validated before any write — `interval` against
`quotes.INTERVALS`, `scale_mode` against `SCALE_MODES`, `chart_type` against
`CHART_TYPES` (invalid → 400 with no row touched, one 400 per bad field). The PUT
MUST upsert through `ChartPreference.for_user(request.user)`, apply only the
supplied fields, and return the saved preference. The route MUST stay registered
in `market/urls.py` without altering existing routes.
(Previously: the body required `interval` and wrote only `last_interval`.)

#### Scenario: GET default when no preference

- GIVEN A has no preference
- WHEN GET `/market/api/preference`
- THEN 200 `{interval:"1m", scale_mode:"linear", chart_type:"candles", exists:false}` (no 404)

#### Scenario: Partial PUT applies only present keys

- GIVEN A has `{interval:"1h", scale_mode:"log", chart_type:"area"}`
- WHEN PUT `{chart_type:"line"}`
- THEN 200 and the row is `{interval:"1h", scale_mode:"log", chart_type:"line"}`

#### Scenario: Invalid scale_mode → 400

- GIVEN PUT `{scale_mode:"bogus"}`
- WHEN handled
- THEN 400 `{"error":"..."}` and no row is written

#### Scenario: Invalid chart_type → 400

- GIVEN PUT `{chart_type:"notreal"}`
- WHEN handled
- THEN 400 `{"error":"..."}` and no row is written

#### Scenario: Invalid interval → 400

- GIVEN PUT `{interval:"7m"}`
- WHEN handled
- THEN 400 `{"error":"..."}` and no row is written

#### Scenario: Unauthenticated → redirect

- GIVEN an anonymous session
- WHEN GET or PUT `/market/api/preference`
- THEN 302 to login

## ADDED Requirements

### Requirement: R12 — Preference isolation and CSP for the new fields

Both new fields MUST route through `ChartPreference.for_user(request.user)`
(A ≠ B isolation); request path code MUST NOT use unscoped queries. No inline
`<script>`/handler MAY be added; the market CSP and `requirements.txt` MUST be
unchanged.

#### Scenario: B never sees A's scale/type

- GIVEN A saved `scale_mode="percentage"` and `chart_type="heikin-ashi"`
- WHEN B GETs the preference
- THEN B receives `linear`/`candles` with `exists:false`

#### Scenario: B's PUT does not touch A's row

- GIVEN A's preference
- WHEN B PUTs `{scale_mode:"log"}`
- THEN B gets its own row and A's row is unchanged

#### Scenario: CSP unchanged

- GIVEN the rendered market page
- WHEN the header is inspected
- THEN the CSP equals the prior value and no inline script exists
