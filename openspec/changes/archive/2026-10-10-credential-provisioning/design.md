# Design: credential-provisioning

## Technical Approach

Add one module, `web/trading/admin.py`, containing an `ExchangeCredentialAdmin`
(`ModelAdmin`) and a small inline `ExchangeCredentialAdminForm` (`ModelForm`).
The form exposes write-only `api_key`/`api_secret` plaintext fields and funnels
them into the existing `ExchangeCredential.set_secrets` Fernet boundary. The
encrypted columns are never form fields nor rendered values, so the admin never
holds or displays plaintext at rest. No model, migration, dependency, `src/`, or
`credentials.py` change. Maps to CP.1–CP.5 in the delta spec.

## Form + ModelAdmin (exact shape)

```python
class ExchangeCredentialAdminForm(forms.ModelForm):
    api_key = forms.CharField(
        required=False, widget=forms.PasswordInput(render_value=False)
    )
    api_secret = forms.CharField(
        required=False, widget=forms.PasswordInput(render_value=False)
    )

    class Meta:
        model = ExchangeCredential
        fields = ("user", "label", "is_active")  # ciphertext cols excluded

    def clean(self):
        data = super().clean()
        key, secret = data.get("api_key"), data.get("api_secret")
        if bool(key) != bool(secret):
            raise forms.ValidationError(
                "Provide both api_key and api_secret, or leave both blank."
            )
        if not self.instance.pk and not key:
            raise forms.ValidationError("api_key and api_secret are required.")
        return data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get("api_key"):
            instance.set_secrets(self.cleaned_data["api_key"],
                                 self.cleaned_data["api_secret"])
        if commit:
            instance.save()
        return instance


@admin.register(ExchangeCredential)
class ExchangeCredentialAdmin(admin.ModelAdmin):
    form = ExchangeCredentialAdminForm
    list_display = ("label", "user", "is_active", "updated_at")
    readonly_fields = ("created_at", "updated_at")
```

**Create/edit semantics** (CP.3): *create* (`instance.pk is None`) both required
— blank → `ValidationError`, no row. *edit* both blank → validation passes,
`save()` skips `set_secrets`, existing ciphertext untouched. *partial* (exactly
one of the two) → `ValidationError`, row unchanged. `set_secrets` is the only
writer of ciphertext.

## Staff trusted surface (CP.1)

A module-level comment in `admin.py` documents that the changelist lists **all
users' credentials** deliberately — a privileged operator surface (staff auth)
analogous to the worker trusted zone (R14.4). It is *not* the per-user
`for_user` self-service rule; no `get_queryset` override, no `for_user` needed.
The admin never imports `decrypt`, so it cannot leak plaintext even to staff.

## Scanner compatibility (CP.4, CP.5)

- **R13** (`test_credentials_mechanism.py`): `web/trading` is already in
  `REQUEST_PATH`; the new module imports neither `decrypt` nor a `decrypt`
  attribute. Green.
- **R14.3** (`test_owned_model_guard.py`): the scanner flags only literal
  `ExchangeCredential.objects.<verb>()` in `web/{config,accounts,trading}`. The
  admin writes none — Django queries via `_default_manager` inside the
  framework, never in our source. No hand-rolled `get_queryset`. Green.

## Architecture Decisions

| Decision | Option | Tradeoff | Decision |
|---|---|---|---|
| Secrets as form fields | Write-only form fields | Model unchanged; mirrors `InviteForm` pattern | **Write-only form fields** vs plaintext column |
| Ciphertext display | Fully excluded | Zero render surface; readonly adds no value | **Hidden** vs truncated readonly fingerprint |
| Form location | Inline in `admin.py` | One fewer file; no reuse yet | **Inline** vs separate `forms.py` |
| Admin queryset | Default manager | Scanner-safe; staff surface | **Default** vs hand-rolled `get_queryset` |
| Edit-blank rule | `clean()` + conditional `set_secrets` | Keeps model untouched | **Form-level** vs model change |

## Data Flow

    staff POST ──→ ExchangeCredentialAdminForm.clean()
                         │ (valid)              │ (invalid → 200)
                         ▼                      └─ no set_secrets
             form.save() → instance.set_secrets(key, secret)
                         │ → encrypt() [Fernet]
                         ▼
             instance.save() → ciphertext columns

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `web/trading/admin.py` | Create | Admin + inline write-only form |
| `tests/web/test_credential_admin.py` | Create | T1–T8 admin contract |
| `web/trading/models.py`, `web/credentials.py`, `src/`, `accounts/` | Unchanged | Boundary preserved |

## Testing Strategy

Strict TDD; `python -m pytest`; **patch coverage 100%** (diff-cover `--fail-under=100`,
line-based — every added line must execute). Local `fernet_key` fixture
(`monkeypatch.setenv`); staff client via `force_login` on `is_staff=True` user
(existing `test_ux.py`/`test_invite.py` pattern). Raw column probed in the test
with `cred.refresh_from_db()` (tests are outside the scanned request path).

| # | Test | Branch covered |
|---|---|---|
| T1 | staff GET changelist → 200 | CP.1 |
| T2 | non-staff GET → 302 login, no data | CP.1 |
| T3 | add POST both secrets → ciphertext != plaintext; `decrypt` restores | create, `api_key` truthy |
| T4 | change page HTML lacks plaintext **and** ciphertext | CP.2 |
| T5 | add POST blank → error, no row | `not pk and not key` |
| T6 | add POST partial → error, no row | `bool != bool` (create) |
| T7 | edit POST blank → 302, ciphertext unchanged | edit, `api_key` falsy |
| T8 | edit POST partial → error, row unchanged | `bool != bool` (edit) |

Existing scanners (`test_credentials_mechanism.py`, `test_owned_model_guard.py`)
are the CP.4/CP.5 assertions and MUST stay green unchanged.

## Boundary / Migration

No decrypt in the request path; no migration (model unchanged); no new runtime
dependency; no order-execution surface (R11). `set_secrets` and `encrypt`
reused unchanged.

## Task Breakdown Hint

Single PR, ~150–220 changed lines: `admin.py` (~55), test file (~120). No
chaining. `Decision needed before apply: No`; `Chained PRs recommended: No`;
`400-line budget risk: Low`.

## Open Questions

None.
