# Delta for per-user-isolation

## MODIFIED Requirements

### Requirement: R14.2 — Cross-user read denied

Cross-user reads MUST be denied for ALL owned models. Using
`for_user(other).get(pk=<this user's row pk>)` MUST raise `DoesNotExist`; a
lookup that bypasses `for_user` MUST NOT be used by request-serving code.
(Delivered with: `ExchangeCredential`, `Watchlist`, `PositionSnapshot`,
`AccountSnapshot`, `Trade`, `ChartLayout`, `Drawing`.)
(Previously: the delivered set ended at `ChartLayout`.)

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

#### Scenario: A cannot read B's Drawing

- GIVEN a `Drawing` owned by A
- WHEN `for_user(B).get(pk=row.pk)` is called
- THEN it raises `DoesNotExist`

### Requirement: R14.3 — Unscoped-query guard

Request-serving code MUST NOT use unscoped queries (`.objects.all()`,
`.objects.get()`, `.objects.filter()`) on owned models. A scanner MUST flag such
usage; `OWNED_MODELS` MUST include `ExchangeCredential`, `Watchlist`,
`PositionSnapshot`, `AccountSnapshot`, `Trade`, `ChartLayout`, and `Drawing`. The
mechanism holds only while all access routes through `for_user`.
(Previously: the `OWNED_MODELS` list ended at `ChartLayout`.)

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

#### Scenario: Scoped query passes the guard

- GIVEN request-serving code calling `for_user(user)` on an owned model
- WHEN the guard scans it
- THEN no offender is reported

#### Scenario: bulk_create and count are sanctioned

- GIVEN `sync.py` persisting owned rows via `bulk_create(ignore_conflicts=True)` and `.count()`
- WHEN the guard scans the trading tree
- THEN no offender is reported
