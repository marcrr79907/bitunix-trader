# user-credentials Specification

## Purpose

Per-user exchange credential storage (R13). Secrets are Fernet ciphertext at rest; encryption happens at the persistence boundary, decryption only in the worker trust zone. New capability — no prior spec.

## Requirements

### Requirement: R13.1 — Ciphertext-at-rest storage

`ExchangeCredential` MUST persist API key and secret only as Fernet ciphertext in `TextField` columns. The model MUST NOT expose a plaintext field. Stored values MUST NOT equal their plaintext originals.

Entity contract:
- `user`: FK to `AUTH_USER_MODEL`, `on_delete=CASCADE`
- `label`: `CharField(max_length=64, blank=True)`
- `api_key_encrypted`, `api_secret_encrypted`: `TextField`
- `is_active`: `BooleanField(default=True)`
- `created_at` (`auto_now_add`), `updated_at` (`auto_now`)

#### Scenario: Persisted value is ciphertext

- GIVEN a credential saved through the boundary
- WHEN the raw database column is read
- THEN it is Fernet ciphertext and does not equal the plaintext input

#### Scenario: Round-trip restores the secret

- GIVEN a credential written via `set_secrets(key, secret)`
- WHEN the raw column is passed to `credentials.decrypt` in the worker zone
- THEN the decrypted value equals the original key/secret

### Requirement: R13.2 — Encrypt-at-boundary, no decrypt in request path

`set_secrets(api_key, api_secret)` MUST encrypt via `credentials.encrypt` before save. Encryption in request-serving code is permitted. Decryption MUST NOT occur in any request-serving code path; only worker-zone code MAY call `credentials.decrypt`.

#### Scenario: Boundary encrypts before save

- GIVEN a caller passing plaintext secrets to `set_secrets`
- WHEN the model is saved and reloaded
- THEN the reloaded encrypted fields are ciphertext, never the plaintext

#### Scenario: Request path does not decrypt

- GIVEN all modules under the request-serving path (including the new data app)
- WHEN scanned for `credentials.decrypt`
- THEN none reaches `decrypt`

### Requirement: R13.3 — set_secrets input guard

`set_secrets` MUST reject empty or whitespace-only inputs and MUST NOT store them. The model MUST NOT expose a plaintext accessor for the secrets.

#### Scenario: Empty secret rejected

- GIVEN an empty or whitespace-only key or secret
- WHEN `set_secrets` is called
- THEN it raises and no row is persisted

#### Scenario: No plaintext accessor

- GIVEN an `ExchangeCredential` instance
- WHEN its public surface is inspected
- THEN no attribute returns the decrypted secret

### Requirement: R13.4 — Worker-zone decryption

Decryption MUST be performed by worker-trust-zone code reading `*_encrypted` columns. The worker MAY read credentials across all users by design (trusted zone, not cross-tenant user access).

#### Scenario: Worker decrypts a stored credential

- GIVEN a stored credential and a worker-zone caller
- WHEN it decrypts the encrypted column
- THEN plaintext is recovered without exposing it in request-serving code
