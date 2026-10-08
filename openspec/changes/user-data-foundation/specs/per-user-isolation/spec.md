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

Cross-user reads MUST be denied for BOTH owned models. Using `for_user(other).get(pk=<this user's row pk>)` MUST raise `DoesNotExist`; a lookup that bypasses `for_user` MUST NOT be used by request-serving code.

#### Scenario: A cannot read B's ExchangeCredential

- GIVEN an `ExchangeCredential` owned by A
- WHEN `for_user(B).get(pk=cred.pk)` is called
- THEN it raises `DoesNotExist`

#### Scenario: A cannot read B's Watchlist row

- GIVEN a `Watchlist` row owned by A
- WHEN `for_user(B).get(pk=row.pk)` is called
- THEN it raises `DoesNotExist`

### Requirement: R14.3 — Unscoped-query guard

Request-serving code MUST NOT use unscoped queries (`.objects.all()`, `.objects.get()`, `.objects.filter()`) on owned models. A scanner MUST flag such usage. The mechanism holds only while all access routes through `for_user`.

#### Scenario: Scanner flags an unscoped query

- GIVEN a fixture calling `ExchangeCredential.objects.get(pk=...)` in the request path
- WHEN the guard scans it
- THEN the scanner reports the offender and fails

#### Scenario: Scoped query passes the guard

- GIVEN request-serving code calling `for_user(user)` on an owned model
- WHEN the guard scans it
- THEN no offender is reported

### Requirement: R14.4 — Worker trusted-zone exception

The worker MAY read all users' credentials. This is a trusted-zone operation and MUST NOT be treated as a cross-tenant user read. No `for_user` scoping MUST be required for worker-zone access.

#### Scenario: Worker reads across users legitimately

- GIVEN stored credentials for several users and a worker-zone caller
- WHEN the worker reads them
- THEN all are readable and this does not violate R14
