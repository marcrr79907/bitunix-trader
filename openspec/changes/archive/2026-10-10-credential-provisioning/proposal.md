# Proposal: credential-provisioning

## Intent

`ExchangeCredential` exists as Fernet ciphertext but **cannot be created**:
`web/trading/admin.py` does not exist and the app registers no admin. Fase 6a
closes that gap with a staff-only admin that provisions credentials through the
existing `set_secrets` encryption boundary, unblocking Fase 6b (#57, worker sync).
Strictly read-only (R11): credentials carry no trading scope, ever.

## Scope

### In Scope
- `web/trading/admin.py`: register `ExchangeCredential` (`@admin.register`).
- Write-only form: `api_key`/`api_secret` plaintext fields (not model fields) whose
  `save()` calls `set_secrets`; encrypted columns excluded from the form.
- `list_display` without secrets; `readonly_fields` = timestamps only.
- Staff gating via Django admin (`is_staff`), no new auth path.
- Tests: ciphertext-at-rest on admin save; no plaintext rendered; blank-on-edit
  keeps existing; partial-edit rejected; non-staff denied; scanners stay green.

### Out of Scope
- Self-service non-staff provisioning (future).
- Fase 6b worker sync/decrypt (#57); Fase 6c UI.
- Model/migration changes; credential rotation (`MultiFernet`).
- **Any order execution — HARD invariant (R11).**

## Capabilities

### New Capabilities
- `credential-provisioning`: staff-admin encrypted provisioning surface — write-only
  plaintext entry funnelled to `set_secrets`, ciphertext never rendered back.

### Modified Capabilities
- None. `user-credentials` (R13) and `per-user-isolation` (R14) requirements are
  unchanged; this change adds a *consumer* of both, whose compliance is proven by
  the existing scanners plus new admin tests.

## Approach

One `ModelAdmin` + one small `ModelForm` (inline in `admin.py` unless it grows),
reusing `set_secrets` unchanged. Plaintext lives only in the form/request and is
encrypted at the boundary; the admin never imports `decrypt`, so R13's worker-only
rule holds. The default admin queryset is used — the R14.3 scanner flags only
literal `<OwnedModel>.objects.<verb>()` in source, which we do not write, so it
stays green. The admin is a **staff trusted surface** (like the worker, R14.4),
not a per-user view; it may list all users' credentials and this is documented as
deliberate, not an accidental unscoped read.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/trading/admin.py` | New | `ExchangeCredentialAdmin` + write-only form |
| `tests/web/test_credential_admin.py` | New | T1–T5 admin contract |
| `web/trading/models.py`, `web/credentials.py`, `src/`, `accounts/` | Unchanged | boundary preserved |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Patch coverage 100% is strict | Med | Minimal form branches; one test per branch |
| Accidental plaintext render | Low | Encrypted columns excluded; T2 asserts absence |
| Hand-rolled `get_queryset` trips R14.3 | Low | Use default manager; no `.objects.verb()` in source |
| Staff surface misread as R14 violation | Low | Document trusted-zone rationale in spec/design |

## Rollback Plan

Revert the branch: delete `web/trading/admin.py` and `test_credential_admin.py`.
No model, migration, settings, `src/`, or `credentials.py` change to undo, so
`main` still ships a working read-only CLI with R13/R14 mechanisms intact.

## Dependencies

- `CREDENTIALS_FERNET_KEY` present in env (existing Phase-0 contract).

## Success Criteria

- [ ] Credential creatable from admin; persisted value is Fernet ciphertext.
- [ ] Admin never renders plaintext; encrypted columns not exposed.
- [ ] Blank-on-edit keeps existing; partial edit rejected.
- [ ] Non-staff cannot reach the admin (302 to login).
- [ ] R13/R14.3 scanners green; `python -m pytest` green; patch coverage 100%; ruff clean.
- [ ] No new runtime dependency; no migration.

## Review Workload Forecast

- Estimated diff: **~150–220 changed lines** (admin + form + admin tests).
- Decision needed before apply: No
- Chained PRs recommended: No
- 400-line budget risk: Low
