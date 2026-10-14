# Delta for chart-config

Issue #115 (Fase F2). Adds optional per-indicator `style` to the persisted layout
entry and to the layout API validation. R1/R2/R5 change; R3/R4/R6/R7 stay in
force. The change is additive (JSONField, no migration) and round-trips verbatim.

## MODIFIED Requirements

### Requirement: R1 — Per-user layout persistence

`ChartLayout` MUST inherit `UserOwnedModel` (owner FK `on_delete=CASCADE` +
`for_user`) and persist one layout per `(user, symbol, interval)` via a
`UniqueConstraint`. It MUST carry `indicators` as a `JSONField` (list of
`{token, params, style}`, `params` an object defaulting empty and `style` an
optional object). `style`, when present, MUST be the frozen shape
`{color, lineWidth, precision}` with all three keys optional. No owner-less rows
MAY exist. The migration MUST be additive (no new model field, no migration).
(Previously: `indicators` entries carried only `{token, params}`.)

#### Scenario: Distinct intervals coexist

- GIVEN a layout for A `(BTCUSDT, 1m)`
- WHEN a row for A `(BTCUSDT, 1h)` is saved
- THEN both rows coexist

#### Scenario: Duplicate key rejected

- GIVEN a layout for `(A, BTCUSDT, 1m)`
- WHEN a second `(A, BTCUSDT, 1m)` is inserted
- THEN `IntegrityError` is raised

#### Scenario: JSON round-trip preserves style

- GIVEN `indicators=[{"token":"sma","params":{"sma_len":50},"style":{"color":"#ff0000","lineWidth":2,"precision":4}}]`
- WHEN saved and re-read
- THEN the nested list, params, and style are equal

#### Scenario: Additive migration

- GIVEN the change
- WHEN `makemigrations --check` runs
- THEN it passes (no pending model drift)

### Requirement: R2 — Layout API

`GET /market/api/layout?symbol=&interval=` MUST be login-required (anonymous →
302) and return the caller's layout for that key, or 200 with the DEFAULT set
when none exists (never 404). `PUT /market/api/layout` MUST be login-required and
CSRF-protected, and upsert the caller's layout for the payload's key (one row).
Every read/write MUST route through `ChartLayout.for_user(request.user)`.
Indicator `token`s MUST be validated against `quotes.REGISTRY`; an unknown token
or bad param → 400 before any write. `quotes.parse_layout_indicators` MUST
preserve and validate an optional `style`: unknown style keys, a non-`#rrggbb`
color, or out-of-range ints MUST raise `ValueError` → 400 before any write, and
a valid style MUST be stored verbatim (no defaults injected).
(Previously: the parser rebuilt each entry as `{"token", ["params"]}` and silently dropped any `style`.)

#### Scenario: GET with no layout returns default

- GIVEN A has no layout
- WHEN GET `?symbol=BTCUSDT&interval=1m`
- THEN 200 with the DEFAULT set and `exists:false`

#### Scenario: GET after PUT returns saved set

- GIVEN A PUT a layout with style
- WHEN GET the same symbol and interval
- THEN 200 with the saved set including style and `exists:true`

#### Scenario: PUT upserts one row

- GIVEN A PUTs twice for the same key
- WHEN rows are counted
- THEN exactly one row holds the latest indicators

#### Scenario: Invalid token → 400

- GIVEN PUT `indicators=[{"token":"notreal"}]`
- WHEN handled
- THEN 400 `{"error":"..."}` and no row is written

#### Scenario: Invalid style → 400 before write

- GIVEN PUT `indicators=[{"token":"sma","style":{"lineWidth":9}}]`
- WHEN handled
- THEN 400 `{"error":"..."}` and no row is written

#### Scenario: Unauthenticated → redirect

- GIVEN an anonymous session
- WHEN GET or PUT `/market/api/layout`
- THEN 302 to login

#### Scenario: Parser is the sole drop point

- GIVEN a PUT entry carrying `style`
- WHEN `parse_layout_indicators` runs
- THEN the returned entry retains the validated `style` (not dropped)

### Requirement: R5 — Save on change

Toggling an indicator, editing its parameters, or confirming a style MUST
debounce-save via `PUT`. The payload MUST carry the current `symbol` and
`interval` so a racing symbol switch cannot mis-save, and each entry MUST carry
its `style` when one is set. A failed save MUST be non-fatal to the in-session
chart.
(Previously: only toggles/params triggered the save; no style was emitted.)

#### Scenario: Toggle triggers debounced PUT

- GIVEN an active chart
- WHEN an indicator toggle changes
- THEN one `PUT /market/api/layout` is observed after the debounce

#### Scenario: Payload pins the active chart

- GIVEN a pending debounced save
- WHEN `switchTo` changes the symbol first
- THEN the payload's symbol/interval are those captured at change time

#### Scenario: Style is included in the payload

- GIVEN an active style for `sma`
- WHEN a save fires
- THEN the PUT body's `sma` entry contains its `style`
