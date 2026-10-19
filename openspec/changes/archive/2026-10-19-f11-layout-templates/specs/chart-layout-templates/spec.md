# chart-layout-templates Specification

## Purpose

Named, per-user indicator setups that can be applied to any chart (issue #248,
F11-B). Today the configuration is persisted per `(user, symbol, interval)`
island (`ChartLayout`, `web/trading/models.py:210-230`); this capability adds a
reusable, user-global template built from the same validated payload.

New capability — no prior spec. A template is a **setup**, not a pane layout, and
not a shared/public artifact: every row is owned and scoped by `for_user`.

## Requirements

### Requirement: T1 — `ChartTemplate` entity

`ChartTemplate` MUST inherit `UserOwnedModel` (owner FK `on_delete=CASCADE` +
`for_user`) and MUST NOT reuse or overload `ChartLayout`. It MUST carry:

| Field | Contract |
|---|---|
| `name` | `CharField(max_length=40)`, non-empty after trimming |
| `indicators` | `JSONField(default=list)`, the same list shape `ChartLayout` stores |
| `created_at` | `DateTimeField(auto_now_add=True)` |

A `UniqueConstraint(user, name)` MUST exist so a name is unique per user. The
migration MUST be additive: it creates only the new table, alters no existing
column or constraint, and `makemigrations --check` MUST stay green.

#### Scenario: One row per (user, name)

- GIVEN A saved a template named `Scalping`
- WHEN a second `(A, Scalping)` row is inserted
- THEN `IntegrityError` is raised

#### Scenario: Distinct users share a name

- GIVEN A owns a template named `Scalping`
- WHEN B saves a template named `Scalping`
- THEN both rows coexist

#### Scenario: Indicators round-trip

- GIVEN `indicators=[{"token":"sma","params":{"sma_len":50},"style":{"color":"#ff0000"}}]`
- WHEN saved and re-read
- THEN the nested list is equal

#### Scenario: Additive migration

- GIVEN the change
- WHEN `makemigrations --check` runs
- THEN it passes and `0017` creates only the `charttemplate` table

### Requirement: T2 — Per-user isolation (R14)

Every read and write MUST route through `ChartTemplate.for_user(request.user)`;
request-path code MUST NOT use an unscoped query. `ChartTemplate` MUST be present
in the owned-model guard's `OWNED_MODELS` set. The owner MUST NEVER be taken from
the request body.

#### Scenario: B cannot read A's templates

- GIVEN A owns a template
- WHEN `for_user(B)` lists templates
- THEN the list is empty

#### Scenario: Cross-user delete is 404

- GIVEN A owns a template with id `T`
- WHEN B sends `DELETE /market/api/templates/T`
- THEN 404 is returned and A's row still exists

#### Scenario: Owner is never taken from the body

- GIVEN a POST by A with `{"name":"x","indicators":[...],"user":<B.pk>}`
- WHEN the row is written
- THEN its `user` is A

#### Scenario: Guard covers the new model

- GIVEN a fixture calling `ChartTemplate.objects.all()`
- WHEN the guard scans it
- THEN `ChartTemplate` is in `OWNED_MODELS` and the offender is reported

### Requirement: T3 — Template API

`GET /market/api/templates` MUST be login-required (anonymous → 302) and return
`{"templates": [{"id", "name", "indicators"}, ...]}` for the caller only, ordered
by `name`. A caller with no templates MUST receive `{"templates": []}` (never
404).

`POST /market/api/templates` MUST be login-required and CSRF-protected, accept
`{name, indicators}`, and validate **before any write**:

1. `name` MUST be a string, trimmed, length 1..40 → otherwise 400.
2. `indicators` MUST pass `quotes.parse_layout_indicators` (unknown token, bad
   param, bad style, or non-bool `visible` → 400) with no row written.

A name already owned by the caller MUST be a 400 (`InvalidName`/duplicate), not a
silent overwrite. Success MUST be 201 with the created row.

`DELETE /market/api/templates/<id>` MUST be login-required, CSRF-protected,
resolve through `for_user` (a foreign or absent id → 404 with no leak), and return
204.

No new dependency, no inline script, and `src/` MUST stay framework-free.

#### Scenario: GET lists only the caller's templates, ordered

- GIVEN A owns `Zeta` and `Alpha`
- WHEN A GETs the list
- THEN the response is `["Alpha", "Zeta"]` in that order

#### Scenario: GET empty is an empty list

- GIVEN A owns no template
- WHEN A GETs the list
- THEN 200 `{"templates": []}` (no 404)

#### Scenario: POST creates a template

- GIVEN a valid name and indicator payload
- WHEN A POSTs
- THEN 201 is returned and exactly one row exists for A

#### Scenario: Invalid indicators write nothing

- GIVEN `indicators=[{"token":"notreal"}]`
- WHEN A POSTs
- THEN 400 is returned and the row count is unchanged

#### Scenario: Duplicate name is 400

- GIVEN A already owns `Scalping`
- WHEN A POSTs another `Scalping`
- THEN 400 is returned and only one row exists

#### Scenario: Blank or overlong name is 400

- GIVEN `name="   "` or a 41-character name
- WHEN A POSTs
- THEN 400 is returned and no row is written

#### Scenario: Anonymous is redirected

- GIVEN an anonymous session
- WHEN any template route is called
- THEN 302 to login is returned

#### Scenario: CSRF is enforced on writes

- GIVEN an authenticated POST or DELETE without `X-CSRFToken`
- WHEN the request is handled
- THEN 403 is returned and no row changes

### Requirement: T4 — Apply a template to the active chart

Applying a template MUST write the template's entries into the four store keys the
render path already consumes — `indicators`, `params`, `styles`,
`indicatorVisible` — and MUST reuse the existing rebuild command. It MUST NOT
introduce a new bus event, a new store key, a second write path, or a
server-side apply endpoint.

The template's entry list MUST be saved with the same pure helper the layout save
uses (`buildIndicators`), so a template and a layout can never disagree about
shape.

#### Scenario: Apply changes the active chart

- GIVEN an active chart with the default set and a template containing only `rsi`
- WHEN the template is applied
- THEN the store's `indicators` is `["rsi"]` and the chart rebuilds with that series

#### Scenario: Apply persists the layout

- GIVEN a template applied to `(BTCUSDT, 1h)`
- WHEN the apply completes
- THEN one `PUT /market/api/layout` for `(BTCUSDT, 1h)` carries the template's indicators

#### Scenario: No new bus event or store key

- GIVEN the change
- WHEN `chart-bus.js` and `chart-store.js` are inspected
- THEN the event vocabulary and the 11 `STORE_KEYS` are unchanged

### Requirement: T5 — UI, CSP and the module ceiling

The templates affordance MUST be static markup: a `<select>`, a **Save as…**
button opening a native `<dialog>` with a name input, and Apply/Delete buttons. No
inline `<script>` or inline event handler MAY be added; the market CSP MUST be
unchanged.

The controller MUST be a new leaf module `controllers/templates.js` that never
imports `main`. It MUST be added to `views.CONTROLLER_ALLOWLIST` and documented in
`docs/architecture/chart-modules.md`. No module MAY exceed the ~300-line ceiling;
`main.js` MUST stay at or below 297 lines after the wiring.

Styles MUST use existing design-system tokens only (no literal colors).

#### Scenario: Markup is CSP-clean

- GIVEN the rendered market page
- WHEN the response header and template are inspected
- THEN the CSP equals the prior value and no inline handler exists

#### Scenario: The controller is served and allowlisted

- GIVEN `GET /market/controllers/templates.js`
- WHEN fetched
- THEN 200 `text/javascript` and `templates` is in `CONTROLLER_ALLOWLIST`

#### Scenario: Module ceiling holds

- GIVEN every module under `web/market/templates/market/`
- WHEN `test_module_size_guard.py` runs
- THEN no module exceeds 300 lines and the allowlist stays empty

#### Scenario: Frozen seams hold

- GIVEN the browser build
- WHEN `window.marketChart` and the store vocabulary are inspected
- THEN they carry exactly 8 and 11 keys respectively
