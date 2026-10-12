# Signals Screen Specification

## Purpose

Server-rendered `/signals/` screen (Fase D2, issue #77) pairing the global,
single-sourced SMC setups with each user's own `AlertRule` state. Ownership over
market data is per-user; setups are global market data and MUST NOT be recomputed
in the view or the browser. New capability — no prior spec.

## Requirements

### Requirement: S1 — Route and auth

`/signals/` MUST be a GET-only route registered in `market/urls.py` ("signals"
name) and MUST require login (`login_required`); anonymous MUST 302-redirect to
login. Authenticated MUST render a server-rendered HTML page (no JSON endpoint,
no inline script).

#### Scenario: Anonymous redirected

- GIVEN an anonymous session
- WHEN GET `/signals/`
- THEN 302 to login

#### Scenario: Authenticated renders

- GIVEN a logged-in user
- WHEN GET `/signals/`
- THEN 200 HTML extending the base template

### Requirement: S2 — Per-user pair scoping

The screen MUST show exactly the `(symbol, interval)` pairs drawn from the
caller's own `AlertRule.for_user(request.user)` rows, and MUST NOT read another
user's rules. A user with no rules MUST get an empty page (no error).

#### Scenario: Only the caller's pairs

- GIVEN user A owns a rule on `(BTCUSDT, 1h)` and user B on `(ETHUSDT, 4h)`
- WHEN A GETs `/signals/`
- THEN only `(BTCUSDT, 1h)` is shown

#### Scenario: No rules is empty, not an error

- GIVEN a user with no `AlertRule`
- WHEN GET `/signals/`
- THEN 200 with an empty state (no exception)

### Requirement: S3 — Single-sourced setups

For each shown pair the view MUST call the frozen `market.quotes.get_smc_payload`
ONCE and render its `setups[]` (direction, entry, stop, take_profit, rr, score,
`time`). The view MUST NOT recompute SMC; `src/smc/` stays the sole home of setup
math and `get_smc_payload` the only source.

#### Scenario: Setups match the frozen payload

- GIVEN a pair with setups
- WHEN the page renders
- THEN each rendered setup equals the corresponding `get_smc_payload(...)["setups"]` record

#### Scenario: No setups renders empty

- GIVEN `get_smc_payload` returns empty `setups`
- WHEN the page renders
- THEN the pair shows no setup rows without error

### Requirement: S4 — Alert-state rendering

Each pair MUST show an alert state derived from its `AlertRule` rows and
`last_fired_at`: `fired` when `last_fired_at` is set, `armed` when an active rule
exists and has not fired, `inactive` when a matching rule is `is_active=False`,
and `none` when no rule exists (with a link to the config UI). MUST NOT send from
this view.

#### Scenario: Fired vs armed

- GIVEN one rule with `last_fired_at` set and one active rule with it null
- WHEN the page renders
- THEN the first shows `fired` and the second shows `armed`

#### Scenario: Inactive and none

- GIVEN a pair whose only rule is `is_active=False`, and another pair with no rule
- WHEN the page renders
- THEN the first shows `inactive`, the second shows `none` with a config link

#### Scenario: Read-only — no send

- GIVEN any rendered page
- WHEN it completes
- THEN no `send_telegram` call and no `last_fired_at` write occurs

### Requirement: S5 — CSP unchanged, server-rendered

The page MUST contain no inline script/handlers and MUST NOT relax the CSP or add
a runtime dependency. It MUST be a GET snapshot with no pagination in v1, using a
bounded pair set and a fixed setups `limit` (default 200).

#### Scenario: CSP unchanged

- GIVEN the rendered `/signals/` response
- WHEN the header and template are inspected
- THEN `Content-Security-Policy` is unchanged and no inline script exists

#### Scenario: No pagination controls

- GIVEN a user with many pairs
- WHEN the page renders
- THEN all pairs appear on one GET with no pagination controls
