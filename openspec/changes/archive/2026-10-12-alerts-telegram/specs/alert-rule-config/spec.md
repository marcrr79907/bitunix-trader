# Alert Rule Config Specification

## Purpose

Per-user `AlertRule` configuration UI (Fase D2, issue #77): server-rendered
create / edit / toggle / delete, each scoped to the caller, with `condition`
validated through the engine's own `parse_condition`. New capability — no prior
spec. The config UI reads/writes configuration only — it never evaluates, sends,
or orders.

## Requirements

### Requirement: C1 — Server-rendered form view

`AlertRule` CRUD MUST be server-rendered Django form views (`AlertRuleForm`)
requiring login; anonymous MUST 302. The form MUST be CSRF-protected and MUST NOT
introduce inline script/handlers or relax the CSP.

#### Scenario: Anonymous redirected

- GIVEN an anonymous session
- WHEN GET the rules list or create route
- THEN 302 to login

#### Scenario: Valid create persists

- GIVEN a logged-in user and a valid form payload
- WHEN POST create
- THEN the rule is persisted with `user=request.user` and the list shows it

### Requirement: C2 — Per-user scoping (for_user)

Every read and write MUST route through `AlertRule.for_user(request.user)` (list,
edit, toggle, delete). A pk that is not the caller's MUST yield 404 and MUST NOT
leak existence. `owner` MUST be set explicitly on create (`for_user` filters, it
does not inject the owner).

#### Scenario: A ≠ B on edit

- GIVEN a rule owned by A
- WHEN B requests edit or delete of that pk
- THEN 404 and A's rule is unchanged

#### Scenario: List is caller-scoped

- GIVEN rules owned by A and by B
- WHEN A opens the rules list
- THEN only A's rules appear

#### Scenario: Owner set on create

- GIVEN a valid create by A
- WHEN the rule is written
- THEN its `user` is A

### Requirement: C3 — Condition validated via parse_condition

The form MUST build the `condition` dict from structured fields and MUST validate
it with `src.alert_rules.parse_condition` in `clean()`, mapping `ValueError` to a
form error and persisting only the normalized dict. `interval` MUST be constrained
to `CANDLE_INTERVALS` and `symbol` to `config.SYMBOLS`. The three valid types are
`price`, `indicator`, `smc_setup`.

#### Scenario: Invalid condition rejected

- GIVEN a payload whose `condition` breaches `parse_condition` (unknown type/op)
- WHEN POST
- THEN a form error is returned and no rule is persisted

#### Scenario: Valid condition normalized

- GIVEN a valid `smc_setup` payload
- WHEN POST
- THEN the persisted `condition` equals `parse_condition`'s normalized output

#### Scenario: Out-of-range symbol or interval rejected

- GIVEN `interval="1m"` (not in `CANDLE_INTERVALS`) or a symbol outside `SYMBOLS`
- WHEN POST
- THEN a form error is returned and nothing is written

### Requirement: C4 — Activate / toggle and edit

The UI MUST allow editing an existing rule and toggling `is_active` (activate /
deactivate), both through `for_user`. Toggling MUST NOT evaluate or send.

#### Scenario: Toggle flips state

- GIVEN A's active rule
- WHEN A toggles it
- THEN `is_active` flips and no send occurs

#### Scenario: Edit updates fields

- GIVEN A's rule
- WHEN A edits `symbol`/`interval`/`condition` validly
- THEN the row is updated under A's ownership
