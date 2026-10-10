# Archive Report: credential-provisioning

**Archived**: 2026-10-10
**Verdict**: PASS WITH WARNINGS (0 blockers, 0 criticals) — 5/5 requirements, 10/10 scenarios, 327/327 tests
**Delivery**: single PR — PR #60 (`feat/credential-admin`) → `develop`
**Merged commit range**: `0c073b9`…`c1dc04d` on `develop` (PR #60 merge `c1dc04d`; branch commits `7128a8d` planning, `b09249b` admin, `9f7bfe5` CP.1 fail-closed alignment + verify report)

## What Shipped

Issue #56 (Fase 6a) closes the provisioning gap: `ExchangeCredential` existed as
Fernet ciphertext but could not be created — `web/trading/admin.py` did not exist
and the app registered no admin. This change adds a staff-only admin that
provisions credentials through the existing `set_secrets` encryption boundary,
write-only plaintext entry, ciphertext never rendered back. Strictly read-only
(R11): credentials carry no trading scope, ever. Prerequisite for Fase 6b (#57,
worker sync).

| Area | Delivered |
|------|-----------|
| Admin | `web/trading/admin.py` (new, 67 lines) — `ExchangeCredentialAdmin` (`@admin.register`) + inline `ExchangeCredentialAdminForm`; `list_display=("label","user","is_active","updated_at")`, `readonly_fields=("created_at","updated_at")`; `search_fields=("label","user__email")`, `list_filter=("is_active",)`; module-level staff trusted-surface comment; no `get_queryset` override |
| Form | Write-only `api_key`/`api_secret` (`PasswordInput(render_value=False)`); `Meta.fields=("user","label","is_active")` (encrypted columns excluded); `clean()` enforce both-or-none + required-on-create; `save()` calls `set_secrets` only when `api_key` truthy |
| Tests | `tests/web/test_credential_admin.py` (new, 253 lines, 11 tests) — T1–T8 admin contract + T9/T10 AST/regex scanner assertions |
| Spec | `openspec/specs/credential-provisioning/spec.md` — new capability CP.1–CP.5 |
| Reused as-is | `ExchangeCredential.set_secrets`, `credentials.encrypt`, existing R13/R14.3 scanners, `user_a`/`user_b`/`fernet_key` fixtures |
| Untouched | `web/trading/models.py`, `web/credentials.py`, `src/`, `accounts/`, `requirements.txt` (diff empty), no migration (`makemigrations --check` clean) |

## Requirement Outcomes

| Req | Domain | Outcome | Notes |
|-----|--------|---------|-------|
| CP.1 | credential-provisioning | ✅ Green (post-alignment) | Staff admin reachable; non-staff → 302 login, no data; documented staff trusted surface. WARNING 1 resolved by amending CP.1 to the fail-closed `is_staff AND model permissions (or superuser)` wording in `9f7bfe5` |
| CP.2 | credential-provisioning | ✅ Green | Write-only `PasswordInput(render_value=False)`; saved column is Fernet ciphertext (`!=` plaintext, `decrypt` round-trip); plaintext **and** ciphertext absent from change-page HTML |
| CP.3 | credential-provisioning | ✅ Green | Create blank → validation error, no row; blank edit preserves byte-identical ciphertext; partial edit rejected, row unchanged; `set_secrets` is the only ciphertext writer |
| CP.4 | credential-provisioning | ✅ Green | No `decrypt` import/attr reach in `admin.py` (AST); credential scanner green; no migration; no new runtime dependency |
| CP.5 | credential-provisioning | ✅ Green | No `<OwnedModel>.objects.<verb>()` call, no `get_queryset` override; `test_owned_model_guard.py` + `test_credentials_mechanism.py` green unchanged |

**Legend**: ✅ green · ⚠️ partial (invariant holds; test-coverage gap).

## Verify Findings (non-blocking)

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| S1 | Suggestion | `search_fields`/`list_filter` added beyond the design's "exact shape" | Accepted — neither touches secret columns (probe confirmed), standard admin ergonomics, patch coverage stays 100% |
| S2 | Suggestion | Whitespace-only secrets rely on `set_secrets` to fail closed (re-rendered 200, no row, no field-level error) | Accepted — fail-closed, not a spec requirement (CP.3 covers blank/partial, not whitespace); add `.strip()` checks in `clean()` only if clearer UX is wanted |
| W1 | Warning | CP.1 "Staff can reach" proven only for the superuser superset; bare `is_staff=True` → 403 PermissionDenied (Django admin per-model permission check) | ✅ **Resolved in `9f7bfe5`** — CP.1 amended to the fail-closed wording: access requires `is_staff` **AND** model permissions (or superuser); the gate is intentionally more restrictive, never less; no security hole |
| W2 | Warning | `tasks.md` checkboxes were not ticked during apply (23/23 `[ ]`) | ✅ **Closed at archive** — archived copy is 23/23 `[x]` (0 unchecked), verified here |

## Carry-Forward Items

1. **CP.1 documents the admin as a staff trusted surface** (all-users changelist) — a
   deliberate operator scope analogous to the worker trusted zone (R14.4),
   deliberately distinct from the per-user `for_user` self-service rule. The admin
   uses Django's standard per-model permission gate. If a self-service (non-staff)
   credential UI is ever wanted, that is a future change (Fase 6c) — do not loosen
   the trusted-zone gate to serve it.
2. **Fase 6b (#57, worker sync/decrypt) is the next consumer** of this provisioning
   surface; the admin intentionally never decrypts, so worker-zone decryption stays
   the only plaintext-recovery path.
3. **S2 whitespace UX** — optional `.strip()` validation in `clean()` if clearer
   form feedback is wanted; behavior is already fail-closed.

## SDD Cycle Complete

Planned (`7128a8d`) → implemented (`b09249b`) → verified (`pass_with_warnings`, 0
blockers, 0 criticals) → CP.1 warning resolved (`9f7bfe5`) → merged (PR #60 →
`develop`, `c1dc04d`) → archived.

Delta spec merged into the main spec store (source of truth) — **new capability**,
so the delta is copied verbatim as the canonical full spec:

- `openspec/specs/credential-provisioning/spec.md` — CP.1–CP.5 **created** (5
  requirements, 10 scenarios). No existing capability modified; `user-credentials`
  (R13) and `per-user-isolation` (R14) requirements unchanged (this change adds a
  *consumer* of both, compliance proven by the existing scanners plus the new
  admin tests).

Archive audit trail: `openspec/changes/archive/2026-10-10-credential-provisioning/`
(explore, proposal, specs, design, tasks, verify-report, archive-report).

## Traceability — Engram Observation IDs

| Artifact | Observation ID |
|----------|----------------|
| `sdd/credential-provisioning/explore` | (openspec file store; see archive folder) |
| `sdd/credential-provisioning/proposal` | (openspec file store) |
| `sdd/credential-provisioning/spec` | (openspec file store) |
| `sdd/credential-provisioning/design` | (openspec file store) |
| `sdd/credential-provisioning/tasks` | (openspec file store) |
| `sdd/credential-provisioning/apply-progress` | Engram `#1404` |
| `sdd/credential-provisioning/verify-report` | (openspec file store) |
| `sdd/credential-provisioning/archive-report` | Engram `sdd/credential-provisioning/archive-report` |

Merged specs have no standalone Engram observations — they live in the OpenSpec
file store (`openspec/specs/credential-provisioning/spec.md`).
