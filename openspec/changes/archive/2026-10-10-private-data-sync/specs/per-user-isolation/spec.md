# Delta for per-user-isolation

Fase 6b adds three owned models (`PositionSnapshot`, `AccountSnapshot`,
`Trade`) and extends the worker trusted-zone exception to credential iteration
plus private persist. R14.1 is unchanged.

## MODIFIED Requirements

### Requirement: R14.2 — Cross-user read denied

Cross-user reads MUST be denied for ALL owned models. Using
`for_user(other).get(pk=<this user's row pk>)` MUST raise `DoesNotExist`; a
lookup that bypasses `for_user` MUST NOT be used by request-serving code.
(Previously: covered only `ExchangeCredential` and `Watchlist`.)

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

### Requirement: R14.3 — Unscoped-query guard

Request-serving code MUST NOT use unscoped queries (`.objects.all()`,
`.objects.get()`, `.objects.filter()`) on owned models. A scanner MUST flag such
usage; `OWNED_MODELS` MUST include `ExchangeCredential`, `Watchlist`,
`PositionSnapshot`, `AccountSnapshot`, and `Trade`. The mechanism holds only
while all access routes through `for_user`.
(Previously: `OWNED_MODELS` held only `ExchangeCredential` and `Watchlist`.)

#### Scenario: Scanner flags an unscoped query

- GIVEN a fixture calling `ExchangeCredential.objects.get(pk=...)` in the request path
- WHEN the guard scans it
- THEN the scanner reports the offender and fails

#### Scenario: Scanner flags the new models

- GIVEN a fixture calling `PositionSnapshot.objects.all()` (or an unscoped query on `AccountSnapshot`/`Trade`)
- WHEN the guard scans it
- THEN the scanner reports the offender

#### Scenario: Scoped query passes the guard

- GIVEN request-serving code calling `for_user(user)` on an owned model
- WHEN the guard scans it
- THEN no offender is reported

#### Scenario: bulk_create and count are sanctioned

- GIVEN `sync.py` persisting owned rows via `bulk_create(ignore_conflicts=True)` and `.count()`
- WHEN the guard scans the trading tree
- THEN no offender is reported

### Requirement: R14.4 — Worker trusted-zone exception

The worker MAY read all users' credentials unscoped and persist private data for
every user. This is a trusted-zone operation and MUST NOT be treated as a
cross-tenant user read. No `for_user` scoping MUST be required for worker-zone
access.
(Previously: exception covered cross-user credential reads only.)

#### Scenario: Worker reads across users legitimately

- GIVEN stored credentials for several users and a worker-zone caller
- WHEN the worker reads them
- THEN all are readable and this does not violate R14

#### Scenario: Worker persists private data for all users

- GIVEN active credentials for several users
- WHEN the worker private-sync step runs
- THEN it writes each user's rows without `for_user` scoping and this is legitimate
