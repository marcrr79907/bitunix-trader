# Delta for security-invariants

Phase 2 flips R13/R14 from stated/mechanism-only to enforced, and hardens the R11 order-surface scanner. R11/R12 normative text is unchanged; only enforcement coverage is strengthened.

## MODIFIED Requirements

### Requirement: R11 — Read-only, no order automation

The system MUST NOT place, modify, or cancel orders, and MUST NOT expose order-execution endpoints. The BitUnix API key MUST be read-only. This prohibition MUST NOT be relaxed by later changes. Enforcement MUST scan `web/` AND `src/` for order-execution verbs, `getattr`-hidden verb calls, and forbidden mutating endpoint-path strings.
(Previously: scanner covered only 11 verbs via `ast.Attribute`/`ast.Name` and only scanned `web/`.)

#### Scenario: No order execution surface

- GIVEN the web application's routes and code
- WHEN scanned for order-placement capability
- THEN none exists

#### Scenario: Read-only credential enforced

- GIVEN an exchange credential configuration
- WHEN it is provisioned for this system
- THEN it carries read-only permission (no trading scope)

#### Scenario: Extended mutating verbs caught

- GIVEN a fixture using `place_tpsl_order`, `change_leverage`, or `adjust_position_margin`
- WHEN the order scanner runs
- THEN each fixture file is reported as an offender

#### Scenario: getattr-hidden verb caught

- GIVEN a fixture line `getattr(client, "place_order")(...)`
- WHEN the order scanner runs
- THEN the fixture is reported as an offender

#### Scenario: Forbidden endpoint path caught

- GIVEN a fixture containing `/trade/place_order` (and other mutating paths such as `/tpsl/...`, `/account/change_*`)
- WHEN the order scanner runs
- THEN the fixture is reported as an offender

#### Scenario: Read endpoints do not match

- GIVEN code referencing `/trade/get_history_orders` or `/position/get_*`
- WHEN the order scanner runs
- THEN no offender is reported

### Requirement: R13 — API keys encrypted (Fernet)

User exchange API keys MUST be stored encrypted with Fernet, and decryption MUST occur only in the worker trust zone, never in request-serving code paths. Enforcement is now active: the credential scanner's request path MUST include the new data app, so decrypt-in-request-path is caught.
(Previously: "enforcement lands when credentials exist"; scanner request path covered only `web/config` and `web/accounts`.)

#### Scenario: Keys stored encrypted

- GIVEN a stored exchange credential
- WHEN the persisted value is inspected
- THEN it is Fernet ciphertext, not plaintext

#### Scenario: Decryption confined to worker

- GIVEN the web request-serving code paths
- WHEN inspected for plaintext key material
- THEN no decryption of user credentials occurs there

#### Scenario: New app is scanned for decrypt

- GIVEN the new data app added to the credential scanner's request path
- WHEN a fixture there calls `credentials.decrypt`
- THEN the scanner reports it as an offender

### Requirement: R14 — Per-user isolation

User-owned records MUST be scoped to their owner and MUST NOT be readable across accounts. Cross-user access MUST be tested (A ≠ B). Enforcement is via the `for_user(user)` ownership contract plus a scanner that flags unscoped queries on owned models in request-serving code. This holds only while access routes through `for_user` (Django has no row-level security).
(Previously: mechanism-only; no owned rows or enforcement test existed.)

#### Scenario: No cross-user read

- GIVEN two users A and B with distinct records
- WHEN A attempts to read B's data
- THEN the attempt is denied

#### Scenario: for_user denies cross-user lookup

- GIVEN an owned record belonging to A
- WHEN `for_user(B).get(pk=record.pk)` is called for either owned model
- THEN it raises `DoesNotExist`

#### Scenario: Unscoped query guard

- GIVEN request-serving code using `OwnedModel.objects.get(...)` on an owned model
- WHEN the isolation scanner runs
- THEN it reports the offender

#### Scenario: Worker trusted zone

- GIVEN a worker-zone caller reading all users' credentials
- WHEN it reads them
- THEN the read is permitted and is not a cross-tenant violation
