# Delta for chart-config

`ChartPreference` (user-global, OneToOne) gains a persisted `smc` JSONField
(issue #124, Ola 3) and the partial-PUT preference API carries it end-to-end. All
other requirements are unchanged.

## MODIFIED Requirements

### Requirement: R8 — User-global interval preference model

`ChartPreference` MUST inherit `UserOwnedModel` (owner FK `on_delete=CASCADE` +
`for_user`), with a `OneToOneField` to the user (exactly one row per user), a
`last_interval` `CharField(max_length=8)` validated against `quotes.INTERVALS`, a
`scale_mode` `CharField(max_length=16, default="linear")` validated against
`SCALE_MODES`, a `chart_type` `CharField(max_length=16, default="candles")`
validated against `CHART_TYPES`, a `theme` `CharField(max_length=16,
default="system")` validated against `THEMES`, and an `smc` `JSONField`
(`default=dict`, the SMC family toggles; an empty object means "all families ON").
It MUST NOT reuse or overload `ChartLayout` (a preference is user-global, not
per-chart). The migration `0013` MUST be additive (`makemigrations --check` green).
(Previously: the model carried `last_interval`, `scale_mode`, `chart_type`, `theme`; migration `0011`.)

#### Scenario: One row per user

- GIVEN A saved a preference
- WHEN A saves again
- THEN exactly one row holds the latest values

#### Scenario: Additive migration 0013

- GIVEN the change
- WHEN `makemigrations --check` runs
- THEN it passes and `0013` adds only the `smc` JSONField with a default

#### Scenario: Field round-trip

- GIVEN `last_interval="4h"`, `scale_mode="log"`, `chart_type="area"`, `theme="dark"`, `smc={"range":false}`
- WHEN saved and re-read
- THEN each value equals its saved value,
- AND the `smc` object round-trips as JSON,
- AND no owner-less row exists

### Requirement: R9 — Preference API

`GET /market/api/preference` MUST be login-required (anonymous → 302) and return
the caller's preference as `{interval, scale_mode, chart_type, theme, smc,
exists}`, or `{interval:"1m", scale_mode:"linear", chart_type:"candles",
theme:"system", smc:{}, exists:false}` when none exists (never 404). `PUT
/market/api/preference` MUST be login-required and CSRF-protected and MUST accept
a PARTIAL body: only the keys present are applied. Each present field MUST be
validated before any write — `interval` against `quotes.INTERVALS`, `scale_mode`
against `SCALE_MODES`, `chart_type` against `CHART_TYPES`, `theme` against
`quotes.THEMES`, `smc` as a JSON object (invalid → 400 with no row touched, one
400 per bad field). The PUT MUST upsert through
`ChartPreference.for_user(request.user)`, apply only the supplied fields, and
return the saved preference. The route MUST stay registered in `market/urls.py`
without altering existing routes.
(Previously: the body carried `interval`, `scale_mode`, `chart_type`, `theme`; no `smc`.)

#### Scenario: GET default when no preference

- GIVEN A has no preference
- WHEN GET `/market/api/preference`
- THEN 200 `{interval:"1m", scale_mode:"linear", chart_type:"candles", theme:"system", smc:{}, exists:false}` (no 404)

#### Scenario: Partial PUT applies only present keys

- GIVEN A has `{interval:"1h", scale_mode:"log", chart_type:"area", theme:"dark"}`
- WHEN PUT `{theme:"light"}`
- THEN 200 and the row is `{interval:"1h", scale_mode:"log", chart_type:"area", theme:"light"}`

#### Scenario: smc round-trips through the API

- GIVEN A has no saved `smc`
- WHEN PUT `{smc:{"range":false,"fvg":true}}`
- THEN 200 and a subsequent GET returns `smc:{"range":false,"fvg":true}`

#### Scenario: Invalid theme → 400

- GIVEN PUT `{theme:"bogus"}`
- WHEN handled
- THEN 400 `{"error":"..."}` and no row is written

#### Scenario: Invalid smc → 400

- GIVEN PUT `{smc:"notanobject"}`
- WHEN handled
- THEN 400 `{"error":"..."}` and no row is written

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
