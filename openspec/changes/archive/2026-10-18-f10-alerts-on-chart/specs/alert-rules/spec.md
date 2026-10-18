# Delta for alert-rules

Issue #123 (F10) adds a **JSON transport** over the frozen model and engine so the
ESM chart can create/edit rules in place. The only alert CRUD today is Django HTML
forms (`web/trading/urls.py:13-17` → `views.py:205-258`), unusable from the chart.
This ADDS R10 (JSON CRUD contract) and R11 (API `for_user` scope). R1–R9 are
UNCHANGED: the model (`web/trading/models.py:288-304`), `parse_condition`
(`src/alert_rules.py:108-119`), the `matches` semantics (`:159-165`), the edge/
dedup behavior and the worker are untouched; the HTML transport stays as-is.

## ADDED Requirements

### Requirement: R10 — JSON CRUD transport

The system MUST expose `/market/api/alerts` (GET list, POST create) and
`/market/api/alerts/<id>` (PUT partial, DELETE), `@login_required`. GET MUST key on
`symbol` AND `interval` (a rule is interval-scoped, `models.py:292`); a missing or
empty `symbol`, an unknown `interval`, or an `interval` outside `CANDLE_INTERVALS`
(`web/trading/candles.py:30`) MUST return 400 mirroring `views.py:425-427`. Rows
MUST be `{id, symbol, interval, condition, is_active, last_fired_at,
telegram_chat_id}` with `last_fired_at` as epoch seconds or null (chart time
convention, `models.py:68`). POST MUST validate `symbol ∈ SYMBOLS`,
`interval ∈ CANDLE_INTERVALS`, `is_active` as a real bool, then normalize
`condition` via `parse_condition`, mapping `ValueError` → 400 with no write.
PUT MUST be partial: `condition` re-validated via `parse_condition`, `is_active`
a real bool, `symbol`/`interval` immutable (a differing value → 400, mirroring
`views.py:526-527`), a miss → 404. DELETE MUST return 204. POST/PUT MUST require
the `X-CSRFToken` header (a missing header → 403 via `CsrfViewMiddleware`).

#### Scenario: List is pair-scoped

- GIVEN A's rules on `(BTCUSDT,1h)` and `(BTCUSDT,5m)`
- WHEN A GETs `?symbol=BTCUSDT&interval=1h`
- THEN only the `1h` rows are returned with `last_fired_at` as epoch seconds

#### Scenario: Missing pair key is 400

- GIVEN a GET without `symbol`
- WHEN the request is handled
- THEN it returns 400 and no query result leaks

#### Scenario: Create normalizes the condition

- GIVEN a POST with `{type:"price",op:"above",level:"100"}`
- WHEN the request is handled
- THEN 201 is returned and the stored `condition` equals `parse_condition`'s output (`level` is a float)

#### Scenario: Invalid condition is 400

- GIVEN a POST with `condition={"type":"magic"}`
- WHEN the request is handled
- THEN 400 is returned and no rule is created

#### Scenario: Non-evaluable interval is 400

- GIVEN a POST with `interval="1m"` or a symbol outside `SYMBOLS`
- WHEN the request is handled
- THEN 400 is returned and nothing is written

#### Scenario: Partial PUT keeps absent fields

- GIVEN A's rule with `condition` and `telegram_chat_id`
- WHEN A PUTs only `{"is_active": false}`
- THEN `is_active` flips, `condition` is unchanged, and one row exists

#### Scenario: Symbol is immutable on PUT

- GIVEN A's rule on `BTCUSDT`
- WHEN A PUTs `{"symbol": "ETHUSDT"}`
- THEN 400 is returned and the row is unchanged

#### Scenario: Unknown id is 404

- GIVEN an id that does not exist
- WHEN PUT or DELETE is called
- THEN 404 is returned

#### Scenario: CSRF is enforced

- GIVEN an authenticated POST without `X-CSRFToken`
- WHEN the request is handled
- THEN 403 is returned and no rule is created

#### Scenario: Delete returns 204

- GIVEN A's rule
- WHEN A DELETEs it
- THEN 204 is returned and the row is gone

### Requirement: R11 — API is for_user scoped

Every read and write in the JSON transport MUST route through
`AlertRule.for_user(request.user)`; the owner MUST be set explicitly on create
(`for_user` filters, it does not inject — `views.py:472`). A pk owned by another
user MUST yield 404 and MUST NOT leak existence, condition, or `last_fired_at`.

#### Scenario: A ≠ B on list

- GIVEN rules owned by A and by B on the same pair
- WHEN B GETs the pair
- THEN only B's rows are returned

#### Scenario: A ≠ B on PUT and DELETE

- GIVEN A's rule
- WHEN B PUTs or DELETEs that pk
- THEN 404 is returned and A's row is unchanged

#### Scenario: Owner set on create

- GIVEN a valid POST by A
- WHEN the rule is written
- THEN its `user` is A

#### Scenario: Anonymous is redirected

- GIVEN an anonymous session
- WHEN any alert API route is called
- THEN 302 to login is returned
