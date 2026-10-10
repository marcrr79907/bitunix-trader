# Tasks: credential-provisioning

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

## Guard/Edge Matrix (every row = a test/assertion in WU1)

- [x] 1.1 create both → ciphertext at rest (`raw != plaintext`, `decrypt` restores) (CP.2)
- [x] 1.2 create blank → validation error, no row (CP.3)
- [x] 1.3 edit both-blank → ciphertext unchanged (CP.3)
- [x] 1.4 edit partial (one secret) → error, ciphertext unchanged (CP.3)
- [x] 1.5 admin renders no plaintext + ciphertext cols absent from form (CP.2)
- [x] 1.6 ciphertext columns not form fields/rendered values (CP.2)
- [x] 1.7 staff gate: non-staff → 302 login, no data (CP.1)
- [x] 1.8 no `decrypt` import/attr in `admin.py` request path (CP.4)
- [x] 1.9 R14.3 owned-model guard green; no `.objects.<verb>()` in source (CP.5)
- [x] 1.10 R13 credentials mechanism green unchanged (CP.4)
- [x] 1.11 no migration; no new dependency
- [x] 1.12 patch coverage 100% (diff-cover `--fail-under=100`), ruff clean

## WU1 — admin + form + tests (single PR)

Base `main`. Depends: none. Strict TDD (`python -m pytest`). ~150–220 lines.
Rollback: delete `web/trading/admin.py` + `tests/web/test_credential_admin.py`; no model/migration/dep change.

- [x] 1.1 **RED** `tests/web/test_credential_admin.py`: local `fernet_key` fixture (`monkeypatch.setenv`, mirror `test_credentials_mechanism.py`); staff client via `force_login(is_staff=True)` (mirror `test_ux.py`); changelist URL `/admin/trading/exchangecredential/`.
- [x] 1.2 **RED** T1 staff GET changelist → 200; T2 non-staff GET → 302 `/admin/login/`, no credential data.
- [x] 1.3 **RED** T3 add POST both secrets → `refresh_from_db()`, raw ciphertext `!= plaintext`, `decrypt` restores; T4 change-page HTML lacks plaintext **and** ciphertext.
- [x] 1.4 **RED** T5 add blank → form error, `count()==0`; T6 add partial → error, no row.
- [x] 1.5 **RED** T7 edit both-blank → 302, ciphertext unchanged; T8 edit partial → error, row unchanged.
- [x] 1.6 **RED** T9/T10: `admin.py` AST has no `decrypt` reach (CP.4); no literal `ExchangeCredential.objects.<verb>()` (CP.5).
- [x] 1.7 **GREEN** create `web/trading/admin.py`: `ExchangeCredentialAdminForm` (`api_key`/`api_secret` `required=False`, `PasswordInput(render_value=False)`; `Meta.fields=("user","label","is_active")`); `clean()` (partial → error; create-blank → error; edit-both-blank ok); `save()` → `set_secrets` when `api_key` truthy, else `super().save()`.
- [x] 1.8 **GREEN** `@admin.register(ExchangeCredential)` `ExchangeCredentialAdmin`: `form`, `list_display=("label","user","is_active","updated_at")`, `readonly_fields=("created_at","updated_at")`; module-level staff trusted-surface comment. No `get_queryset`, no `.objects.<verb>()`.
- [x] 1.9 **GREEN** full suite green: `test_owned_model_guard.py`, `test_credentials_mechanism.py`, `test_no_order_surface.py` unchanged.
- [x] 1.10 `python -m pytest` green; `ruff check . && ruff format --check .` green; diff-cover 100% on new lines.
- [x] 1.11 **Rollback**: revert branch (delete both files). Read-only CLI + R13/R14 mechanisms intact.

## Review Workload Forecast

- Estimated changed lines: `admin.py` ~55 + tests ~120 → **~150–220 total** (add+del).
- Suggested split: single PR — WU1 only. No chaining.
- Delivery strategy: ask-on-risk (no decision required; Low risk, under 400).

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low
