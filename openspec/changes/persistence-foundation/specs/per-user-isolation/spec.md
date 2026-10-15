# Delta for per-user-isolation

The ownership shape is unchanged (issue #124, Ola 3): `Drawing` still inherits
`UserOwnedModel` and CRUD still routes through `for_user`. Only the Drawing
scenario's keying evidence moves from `(user, symbol, interval)` to
`(user, symbol)`. R14.1, R14.3–R14.5 are unchanged.

## MODIFIED Requirements

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
