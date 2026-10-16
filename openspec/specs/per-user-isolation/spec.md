# per-user-isolation Specification

## Purpose

Ownership contract for user-owned records (R14). A single deep module — abstract `UserOwnedModel` (owner FK + `for_user(user)`) — hides scoping behind one small interface. New capability — no prior spec.

## Requirements

### Requirement: R14.1 — Ownership contract

Every user-owned model MUST inherit an abstract `UserOwnedModel` providing a `user` FK to `AUTH_USER_MODEL` (`on_delete=CASCADE`) and a classmethod `for_user(user)`. `for_user(user)` MUST return a queryset scoped to that user's rows only.

#### Scenario: for_user returns only the owner's rows

- GIVEN user A owns one record and user B owns none
- WHEN `for_user(A)` is evaluated
- THEN A's record is present and `for_user(B)` is empty

#### Scenario: Empty owner is not an error

- GIVEN a user who owns no rows
- WHEN `for_user(user)` is evaluated
- THEN it returns an empty queryset without raising

### Requirement: R14.2 — Cross-user read denied

Cross-user reads MUST be denied for ALL owned models. Using
`for_user(other).get(pk=<this user's row pk>)` MUST raise `DoesNotExist`; a
lookup that bypasses `for_user` MUST NOT be used by request-serving code. The
denial MUST hold when the owned row carries per-indicator `style` data (F2.9),
proven by a committed assertion in `tests/web/test_isolation.py`: A's
`ChartLayout` with a styled indicator yields `for_user(B).count() == 0` and
`for_user(B).get(...)` raises `DoesNotExist`. The denial MUST hold for a `Drawing`
regardless of the symbol it is keyed on (the per-symbol keying drops `interval`;
ownership is unaffected).
(Delivered with: `ExchangeCredential`, `Watchlist`, `PositionSnapshot`,
`AccountSnapshot`, `Trade`, `ChartLayout`, `Drawing`, `AlertRule`,
`ChartPreference`.)
(Previously: the Drawing evidence was keyed `(user, symbol, interval)`.)

#### Scenario: A cannot read B's ExchangeCredential

- GIVEN an `ExchangeCredential` owned by A
- WHEN `for_user(B).get(pk=cred.pk)` is called
- THEN it raises `DoesNotExist`

#### Scenario: A cannot read B's Watchlist row

- GIVEN a `Watchlist` row owned by A
- WHEN `for_user(B).get(pk=row.pk)` is called
- THEN it raises `DoesNotExist`

#### Scenario: A cannot read B's PositionSnapshot

- GIVEN a `PositionSnapshot` owned by A
- WHEN `for_user(B).get(pk=row.pk)` is called
- THEN it raises `DoesNotExist`

#### Scenario: A cannot read B's AccountSnapshot

- GIVEN an `AccountSnapshot` owned by A
- WHEN `for_user(B).get(pk=row.pk)` is called
- THEN it raises `DoesNotExist`

#### Scenario: A cannot read B's Trade

- GIVEN a `Trade` owned by A
- WHEN `for_user(B).get(pk=row.pk)` is called
- THEN it raises `DoesNotExist`

#### Scenario: A cannot read B's ChartLayout

- GIVEN a `ChartLayout` owned by A
- WHEN `for_user(B).get(pk=row.pk)` is called
- THEN it raises `DoesNotExist`

#### Scenario: A cannot read B's styled ChartLayout

- GIVEN a `ChartLayout` owned by A carrying an indicator `style`
- WHEN `tests/web/test_isolation.py` evaluates `for_user(B)`
- THEN `for_user(B).count() == 0` and `for_user(B).get(...)` raises `DoesNotExist` — B never sees the row carrying A's style

#### Scenario: A cannot read B's per-symbol Drawing

- GIVEN a `Drawing` owned by A keyed `(user, symbol)`
- WHEN `for_user(B).get(pk=row.pk)` is called
- THEN it raises `DoesNotExist`

#### Scenario: A cannot read B's AlertRule

- GIVEN an `AlertRule` owned by A
- WHEN `for_user(B).get(pk=rule.pk)` is called
- THEN it raises `DoesNotExist`

#### Scenario: A cannot read B's ChartPreference

- GIVEN a `ChartPreference` owned by A
- WHEN `for_user(B).get(pk=row.pk)` is called
- THEN it raises `DoesNotExist`

### Requirement: R14.3 — Unscoped-query guard

Request-serving code MUST NOT use unscoped queries (`.objects.all()`,
`.objects.get()`, `.objects.filter()`) on owned models. A scanner MUST flag such
usage; `OWNED_MODELS` MUST include `ExchangeCredential`, `Watchlist`,
`PositionSnapshot`, `AccountSnapshot`, `Trade`, `ChartLayout`, `Drawing`,
`AlertRule`, and `ChartPreference`. The mechanism holds only while all access
routes through `for_user`.

#### Scenario: Scanner flags an unscoped query

- GIVEN a fixture calling `ExchangeCredential.objects.get(pk=...)` in the request path
- WHEN the guard scans it
- THEN the scanner reports the offender and fails

#### Scenario: Scanner flags the new models

- GIVEN a fixture calling `PositionSnapshot.objects.all()` (or an unscoped query on `AccountSnapshot`/`Trade`/`ChartLayout`/`Drawing`)
- WHEN the guard scans it
- THEN the scanner reports the offender

#### Scenario: Scanner flags an unscoped Drawing query

- GIVEN a fixture calling `Drawing.objects.all()` in the request path
- WHEN the guard scans it
- THEN the scanner reports the offender (proves `Drawing` is in `OWNED_MODELS`)

#### Scenario: Scanner flags an unscoped AlertRule query

- GIVEN a fixture calling `AlertRule.objects.all()` in the request path
- WHEN the guard scans it
- THEN the scanner reports the offender (proves `AlertRule` is in `OWNED_MODELS`)

#### Scenario: Scanner flags an unscoped ChartPreference query

- GIVEN a fixture calling `ChartPreference.objects.all()` in the request path
- WHEN the guard scans it
- THEN the scanner reports the offender (proves `ChartPreference` is in `OWNED_MODELS`)

#### Scenario: Scoped query passes the guard

- GIVEN request-serving code calling `for_user(user)` on an owned model
- WHEN the guard scans it
- THEN no offender is reported

#### Scenario: bulk_create and count are sanctioned

- GIVEN `sync.py` persisting owned rows via `bulk_create(ignore_conflicts=True)` and `.count()`
- WHEN the guard scans the trading tree
- THEN no offender is reported

### Requirement: R14.4 — Worker trusted-zone exception

The worker MAY read all users' credentials and alert rules unscoped and persist
private data for every user. This is a trusted-zone operation and MUST NOT be
treated as a cross-tenant user read. No `for_user` scoping MUST be required for
worker-zone access; the R14.3 scanner MUST NOT apply to `web/worker.py`.

#### Scenario: Worker reads across users legitimately

- GIVEN stored credentials for several users and a worker-zone caller
- WHEN the worker reads them
- THEN all are readable and this does not violate R14

#### Scenario: Worker persists private data for all users

- GIVEN active credentials for several users
- WHEN the worker private-sync step runs
- THEN it writes each user's rows without `for_user` scoping and this is legitimate

#### Scenario: Worker reads all users' rules unscoped

- GIVEN active `AlertRule`s owned by several users
- WHEN `run_alert_rules` reads `AlertRule.objects.filter(is_active=True)` in `web/worker.py`
- THEN all rules are readable and the owned-model guard reports no offender

### Requirement: R14.5 — Analytics view is scoped

The `/analytics/` view MUST read trades ONLY through `Trade.for_user(request.user)`
and MUST NOT use unscoped `<OwnedModel>.objects.<verb>()` queries on any owned
model, including `Trade`. Global market data (`Candle`, `TickerSnapshot`) MAY be
read unscoped, but user trades MUST be scoped before any join; the R14.3 scanner
MUST stay green on `web/trading/`.

#### Scenario: Analytics reads only the caller's trades

- GIVEN user A owns trades and user B owns none
- WHEN B GETs `/analytics/`
- THEN no owned-model query outside `for_user` occurs and B sees no trade data

#### Scenario: Unscoped analytics fixture is flagged

- GIVEN a fixture under the request path calling `Trade.objects.all()` in an analytics-style view
- WHEN the R14.3 guard scans it
- THEN the scanner reports the offender

### Requirement: R14.6 — Cross-user update denied (PUT)

The `PUT /market/api/drawings/<id>` path MUST resolve the row through
`Drawing.for_user(request.user)` and MUST NOT use an id-only lookup. A PUT that
targets another user's `id` MUST resolve to nothing (404) with no existence leak
and MUST NOT modify the row. The denial MUST be proven by a committed assertion
in `tests/web/test_market_api.py` (A≠B PUT → 404, A's row unchanged).

#### Scenario: B's PUT of an A id is 404

- GIVEN A's drawing `d`
- WHEN B PUTs `/market/api/drawings/<d.id>` with a valid body
- THEN 404 and A's `points`/`style` are unchanged

#### Scenario: for_user scopes the update target

- GIVEN a `Drawing` owned by A
- WHEN the PUT path calls `Drawing.for_user(B).get(pk=d.pk)` (or `.filter(...).first()`)
- THEN it resolves to nothing for B

#### Scenario: Owner's own PUT succeeds

- GIVEN A's drawing `d`
- WHEN A PUTs `/market/api/drawings/<d.id>`
- THEN 200 with the updated row scoped to A
