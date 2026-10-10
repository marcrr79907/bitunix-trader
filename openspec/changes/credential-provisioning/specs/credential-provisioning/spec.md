# credential-provisioning Specification

## Purpose

Staff-only admin surface that provisions `ExchangeCredential` rows through the
existing `set_secrets` Fernet boundary. Plaintext is write-only; persisted
columns stay ciphertext; the admin never decrypts. New capability — no prior spec.

## Requirements

### Requirement: CP.1 — Staff-gated admin surface

`ExchangeCredential` MUST be manageable via the Django admin. Access MUST require
`is_staff` (delegated to Django admin auth; no new auth path). The admin MAY list
all users' credentials as a **staff trusted surface** — a deliberate operator
scope analogous to the worker trusted zone (R14.4). This is NOT the per-user
`for_user` self-service rule; it MUST be documented as a trusted-zone decision.

#### Scenario: Staff can reach the credential admin

- GIVEN a staff user
- WHEN the credential admin changelist is requested
- THEN it responds successfully

#### Scenario: Non-staff is denied

- GIVEN an authenticated non-staff user
- WHEN the credential admin URL is requested
- THEN the response redirects to login (302) and exposes no credential data

### Requirement: CP.2 — Write-only plaintext, ciphertext at rest

The admin form MUST accept `api_key`/`api_secret` ONLY as write-only inputs
(e.g. `PasswordInput(render_value=False)`); neither MUST be rendered back. The
persisted `api_key_encrypted`/`api_secret_encrypted` columns MUST remain Fernet
ciphertext produced by `set_secrets`. The admin MUST NOT expose a plaintext
accessor; encrypted columns MUST NOT appear as form fields or rendered values.

#### Scenario: Save stores ciphertext, not plaintext

- GIVEN a staff POST of the add form with plaintext secrets
- WHEN the raw database column is read
- THEN it is Fernet ciphertext and does not equal the submitted plaintext

#### Scenario: Plaintext never rendered back

- GIVEN a saved credential
- WHEN the admin change page HTML is fetched
- THEN the plaintext secret string is absent from the response

### Requirement: CP.3 — Create and edit semantics

The form MUST require both secrets on create (blank → validation error). On edit,
both blank MUST keep the existing ciphertext unchanged; exactly one provided MUST
fail validation. `set_secrets` MUST be the only path writing ciphertext.

#### Scenario: Create with blank secrets fails

- GIVEN a staff add submission with blank `api_key` or `api_secret`
- WHEN the form is validated
- THEN validation fails and no ciphertext row is created

#### Scenario: Blank edit preserves ciphertext

- GIVEN an existing credential
- WHEN the change form is submitted with both secrets blank
- THEN validation passes and the stored ciphertext is unchanged

#### Scenario: Partial edit is rejected

- GIVEN an existing credential
- WHEN the change form submits only one of the two secrets
- THEN validation fails and the stored ciphertext is unchanged

### Requirement: CP.4 — No decrypt in the admin/request path

Admin and request-serving code MUST NOT import or call `credentials.decrypt`; the
credential scanner MUST stay green. The change MUST introduce no migration and no
new runtime dependency.

#### Scenario: Credential scanner stays green

- GIVEN the admin module under the scanner's request path
- WHEN the credential scanner runs
- THEN no decrypt offender is reported

### Requirement: CP.5 — Scanner compatibility (unscoped-query guard)

Registering the admin MUST NOT trip the R14.3 unscoped-query guard. `web/trading/admin.py`
MUST NOT contain a hand-written `<OwnedModel>.objects.<verb>()` call.

#### Scenario: Owned-model guard stays green

- GIVEN the new admin source
- WHEN `test_owned_model_guard.py` runs
- THEN no unscoped-query offender is reported

#### Scenario: Credentials mechanism stays green

- GIVEN the new admin source
- WHEN `test_credentials_mechanism.py` runs
- THEN the suite passes unchanged
