# security-invariants Specification

## Purpose

Invariants the dashboard MUST honor in every phase. This phase states them as binding constraints and proves the ones it can; later phases MUST preserve them. New capability — no prior spec.

## Requirements

### Requirement: R11 — Read-only, no order automation

The system MUST NOT place, modify, or cancel orders, and MUST NOT expose order-execution endpoints. The BitUnix API key MUST be read-only. This prohibition MUST NOT be relaxed by later changes.

#### Scenario: No order execution surface

- GIVEN the web application's routes and code
- WHEN scanned for order-placement capability
- THEN none exists

#### Scenario: Read-only credential enforced

- GIVEN an exchange credential configuration
- WHEN it is provisioned for this system
- THEN it carries read-only permission (no trading scope)

### Requirement: R12 — Secrets out of the repository

No secret (API keys, `SECRET_KEY`, database or Redis credentials) MAY be committed. Secrets MUST come from the environment or platform-managed config; the repo MAY contain only a placeholder `.env.example`.

#### Scenario: Repo contains no real secrets

- GIVEN the repository contents
- WHEN scanned for credentials
- THEN only placeholders/example values appear; no live secret is present

#### Scenario: Runtime secrets come from environment

- GIVEN a deployed service
- WHEN it reads secrets
- THEN values are supplied via environment, not source files

### Requirement: R13 — API keys encrypted (Fernet)

User exchange API keys MUST be stored encrypted with Fernet, and decryption MUST occur only in the worker trust zone, never in request-serving code paths. This phase fixes the constraint; enforcement lands when credentials exist.

#### Scenario: Keys stored encrypted

- GIVEN a stored exchange credential
- WHEN the persisted value is inspected
- THEN it is Fernet ciphertext, not plaintext

#### Scenario: Decryption confined to worker

- GIVEN the web request-serving code paths
- WHEN inspected for plaintext key material
- THEN no decryption of user credentials occurs there

### Requirement: R14 — Per-user isolation

User-owned records MUST be scoped to their owner and MUST NOT be readable across accounts. Cross-user access MUST be tested (A ≠ B).

#### Scenario: No cross-user read

- GIVEN two users A and B with distinct records
- WHEN A attempts to read B's data
- THEN the attempt is denied
