# Delta for security-invariants

Fase 6b is the first real consumer of `credentials.decrypt`: the worker trust
zone decrypts ACTIVE credentials and the request-path `sync.py` MUST stay
decrypt-free. R11/R12 normative text is unchanged; R13/R14 enforcement now
covers the three new owned models.

## MODIFIED Requirements

### Requirement: R13 — API keys encrypted (Fernet)

User exchange API keys MUST be stored encrypted with Fernet, and decryption MUST
occur only in the worker trust zone, never in request-serving code paths.
Enforcement is now active AND consumed: `web/trading/sync.py` MUST NOT import or
call `decrypt` (the credential scanner's request path includes `trading`), while
`web/worker.py` (outside every scanned request path) owns decryption of ACTIVE
credentials.
(Previously: "decryption is worker-only" was enforced but no production code consumed `decrypt`.)

#### Scenario: Keys stored encrypted

- GIVEN a stored exchange credential
- WHEN the persisted value is inspected
- THEN it is Fernet ciphertext, not plaintext

#### Scenario: Decryption confined to worker

- GIVEN the web request-serving code paths (including `web/trading/sync.py`)
- WHEN inspected for plaintext key material
- THEN no decryption of user credentials occurs there

#### Scenario: sync.py stays decrypt-free

- GIVEN `web/trading/sync.py` and a scanner that flags import, call, bare name, and `getattr("decrypt")`
- WHEN the scanner scans the request path
- THEN `sync.py` is not reported as an offender

#### Scenario: Worker decrypts an active credential

- GIVEN an ACTIVE credential and the worker private-sync step
- WHEN the step runs
- THEN it calls `credentials.decrypt` on the encrypted columns and the scanner remains green

### Requirement: R14 — Per-user isolation

User-owned records MUST be scoped to their owner and MUST NOT be readable across
accounts. Cross-user access MUST be tested (A ≠ B). Enforcement is via the
`for_user(user)` ownership contract plus a scanner that flags unscoped queries
on owned models in request-serving code; `OWNED_MODELS` MUST now include
`PositionSnapshot`, `AccountSnapshot`, and `Trade`. This holds only while access
routes through `for_user` (Django has no row-level security).
(Previously: enforcement covered only `ExchangeCredential` and `Watchlist`.)

#### Scenario: No cross-user read

- GIVEN two users A and B with distinct records
- WHEN A attempts to read B's data
- THEN the attempt is denied

#### Scenario: for_user denies cross-user lookup

- GIVEN an owned record belonging to A
- WHEN `for_user(B).get(pk=record.pk)` is called for any owned model (including the three new ones)
- THEN it raises `DoesNotExist`

#### Scenario: Unscoped query guard

- GIVEN request-serving code using `OwnedModel.objects.get(...)` on an owned model
- WHEN the isolation scanner runs
- THEN it reports the offender

#### Scenario: Worker trusted zone

- GIVEN a worker-zone caller reading all users' credentials
- WHEN it reads them
- THEN the read is permitted and is not a cross-tenant violation
