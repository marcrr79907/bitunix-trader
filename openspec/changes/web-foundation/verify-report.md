```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:2bf1d0f34f19edd6bea69b1ae5b7a73289e8e6abdeeafa730fd42df2a68c609a
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 3/3
scenarios: 12/12
test_command: .venv/bin/python -m pytest
test_exit_code: 0
test_output_hash: sha256:47cf3957ef356c9d1ecf2890d43c95ef2bd4ce87051f8f40dec6296e5f4f4cd6
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python web/manage.py check && .venv/bin/python web/manage.py makemigrations --check --dry-run
build_exit_code: 0
build_output_hash: sha256:b5279678dd650f8577cd632c197640c34eddce0648b064a31314093202ca441d
```

# Verification Report

**Change**: web-foundation
**Version**: N/A (delta specs)
**Mode**: Strict TDD (openspec `config.yaml` `strict_tdd: true`, runner `.venv/bin/python -m pytest`)
**Latest scope**: PR3 (HEAD `330e886`) — branch `feat/web-foundation-invite`, base/tracker `feat/web-dashboard` (PR1+#PR2 merged, tip `357c347`)

This document is cumulative. The envelope above reflects the latest independent run (**PR3**). The PR2 and PR1 sections below are preserved from prior verification passes; their tests remain green inside the current full-suite execution (59 tests). Cumulative previously-verified: PR1 13/14, PR2 8/8 in-scope.

---

# PR3 Verification — commit `330e886`

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total (Phase 3) | 5 |
| Tasks complete | 5 |
| Tasks incomplete | 0 |

Phase 3 items 3.1–3.5 are all checked in `tasks.md` and confirmed against the committed tree. Cumulative 20/20 (Phases 1–3).

## Build & Tests Execution

**Build**: ✅ Passed (exit 0)
```text
$ .venv/bin/ruff check .
All checks passed!
$ .venv/bin/ruff format --check .
58 files already formatted
$ .venv/bin/python web/manage.py check
System check identified no issues (0 silenced).
$ .venv/bin/python web/manage.py makemigrations --check --dry-run
No changes detected
```

**Tests**: ✅ 59 passed / ❌ 0 failed / ⚠️ 0 skipped (exit 0, 10.85s)
```text
$ .venv/bin/python -m pytest
tests/test_alerts.py: 4        tests/web/test_auth.py: 4
tests/test_boundary.py: 2      tests/web/test_health.py: 2
tests/test_db.py: 4            tests/web/test_invite.py: 7   <- new in PR3
tests/test_journal.py: 4       tests/web/test_signup.py: 8   <- new in PR3
tests/test_positions.py: 6     tests/web/test_user.py: 8
tests/test_settings.py: 6
tests/test_no_secrets.py: 2
tests/test_sign.py: 2
59 passed in 10.85s
```

Baseline regression: the 44 pre-PR3 tests (20 original + PR1 12 + PR2 10 + 2 case-insensitivity added on the tracker) all pass unchanged; PR3 adds exactly 15 tests (7 invite + 8 signup), matching the apply report.

**Coverage**: ➖ Not available — `pytest-cov` gate is scheduled for PR4 (task 4.7).

## Diff Scope

```
$ git diff --stat feat/web-dashboard...HEAD
 13 files changed, 582 insertions(+), 8 deletions(-)
```

Touched paths: `web/accounts/{models,forms,views,urls,admin}.py`, `web/accounts/migrations/0002_invite.py`, `web/accounts/templates/accounts/{invite_create,signup}.html`, `tests/web/{test_invite,test_signup}.py`, `pyproject.toml`, and SDD artifacts (`tasks.md`, `apply-progress.md`).

Scope check `git diff --stat feat/web-dashboard...HEAD -- src/ .github/ Dockerfile docker-compose.yml railway.json .dockerignore` → **empty**. No `src/`, no `.github/`, no Docker/Compose/Railway. No tracked secret (`.env` gitignored, confirmed by `test_no_secrets.py`). PR3 boundary respected.

Note: HEAD is a two-commit stack — `3628255` ("(#15)") contains the code, `330e886` adds the SDD docs on top. `origin/feat/web-dashboard` does not yet contain this work (expected mid-chain: PR3 not merged to tracker). One dangling sibling commit exists on `origin/feat/web-foundation-user` (`df84492`, the PR2 case-normalization fix) — its content is already present in this branch's tree.

## Spec Compliance Matrix (PR3 in-scope requirements)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R1 | Create a valid invite | `tests/web/test_invite.py::test_token_is_unique_and_generated` + `test_staff_can_create_invite` | ✅ COMPLIANT |
| R1 | Duplicate active invite rejected | `tests/web/test_invite.py::test_duplicate_active_invite_rejected` | ✅ COMPLIANT (view/form path — see WARNING 2) |
| R1 | Past expiry rejected at creation | `tests/web/test_invite.py::test_past_expiry_rejected_at_creation` | ✅ COMPLIANT (form path — see WARNING 2) |
| R2 | Signup with valid token | `tests/web/test_signup.py::test_valid_token_creates_user_with_invite_role` | ✅ COMPLIANT |
| R2 | Expired token rejected | `tests/web/test_signup.py::test_expired_token_rejected` | ✅ COMPLIANT |
| R2 | Reused token rejected | `tests/web/test_signup.py::test_reused_token_rejected` | ✅ COMPLIANT |
| R2 | Unknown token rejected | `tests/web/test_signup.py::test_unknown_token_rejected` | ✅ COMPLIANT |
| R2 | Open self-registration absent | `tests/web/test_signup.py::test_no_open_self_registration_route` | ✅ COMPLIANT |
| R3 | Login with email | `tests/web/test_auth.py::test_login_with_email_creates_session` | ✅ COMPLIANT (PR2, re-run green) |
| R3 | Logout ends session | `tests/web/test_auth.py::test_logout_invalidates_session` | ✅ COMPLIANT (PR2, re-run green) |
| R3 | Password reset round-trip | `tests/web/test_auth.py::test_password_reset_round_trip` | ✅ COMPLIANT (PR2, re-run green) |
| R3 | Wrong credentials rejected | `tests/web/test_auth.py::test_wrong_credentials_no_session` | ✅ COMPLIANT (PR2, re-run green) |

**Compliance summary**: 12/12 in-scope scenarios compliant. R6/R7/R11/R13 (PR4) and R14 (harness-only) correctly not-applicable.

### Not-yet-applicable (belong PR4 — correctly absent, does not fail)

R6/R7 (Compose/Railway/worker) → PR4. R11 (no-order surface), R13 (Fernet credentials) → PR4. R14 enforcement → no user-owned rows yet (harness ready, PR2).

## Adversarial Probes (independently executed, not from the apply report)

| Probe | Method | Result |
|-------|--------|--------|
| Token entropy/source | Read `models.py:22` `secrets.token_urlsafe(32)`; DB `unique=True` | ✅ CSPRNG, ~256 bits, length ≥ 32, DB unique — PASS |
| Token uniqueness at runtime | Create two invites, compare tokens | ✅ distinct; `TokenField unique=True` in `0002_invite.py` |
| Expiry timezone-awareness | `USE_TZ=True` (base.py:123); `is_valid()` uses `timezone.now()` | ✅ aware comparison — PASS |
| Sequential reuse | `test_token_is_single_use`: 2nd POST → 404, user count stays 1 | ✅ PASS |
| **Concurrent reuse (TOCTOU)** | Two ORM reads both `is_valid()` before any write; no `select_for_update`/transaction | ⚠️ **check-then-set is non-atomic** — see WARNING 3 |
| **Signup for existing email** | Staff invites an email that already has a User (form valid); invitee POSTs password | ❌ **uncaught `IntegrityError` (HTTP 500)**; `used_at` left null — see WARNING 1 |
| **Duplicate active invite via stored case** | Active invite stored `Case@Example.com`; `InviteForm` for `case@example.com` | ❌ **form valid → 2 active invites** — see WARNING 2 |
| **Admin bypass of validation** | `InviteAdmin.form` is Django's default `ModelForm` (probe), not `InviteForm` | ❌ admin path skips `clean_email`/`clean_expires_at` — see WARNING 2 |
| **Password validators on signup** | POST `password1="1"` to signup | ❌ **accepted, user created** — `AUTH_PASSWORD_VALIDATORS` never invoked — see WARNING 4 |
| Info-leak / oracle | expired, reused, unknown tokens → all `Http404`, identical body | ✅ no status/body oracle — PASS |
| Signup email normalisation | Invite `MiXeD@Example.COM` → stored user `mixed@example.com` (`test_signup_normalises_email`) | ✅ matches PR2 lowercase form — PASS |
| No open registration | URLconf has only `/accounts/signup/<token>/`; `/signup/`, `/register/`, `/accounts/signup/` → 404 | ✅ PASS |
| Role escalation | SignupForm exposes only passwords; email+role from server-side invite row | ✅ visitor cannot choose role/email |
| Secrets / out-of-scope files | diff path check + `git ls-files` + `test_no_secrets.py` | ✅ no secret, no `src/`, no `.github/`, no Docker |

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| R1 Invite model | ✅ Implemented | `web/accounts/models.py:49–72` — `email` indexed, `token` unique default `gen_token`, `role` enum, `expires_at` default now+7d, `used_at` nullable; `is_valid()` = unused AND unexpired. |
| R1 staff gate | ✅ Implemented | `views.py:19–23` `@login_required` + `raise PermissionDenied` unless `is_staff`; `member_forbidden` test green. |
| R1 duplicate/expiry validation | ⚠️ Partial | `forms.py:26–40` enforces on the custom view; **admin bypasses it** (WARNING 2). |
| R2 token-gated signup | ✅ Implemented | `views.py:36–54` — lookup → `is_valid()` → 404 otherwise; create user with invite email/role; `used_at` set. |
| R2 single-use | ⚠️ Partial | Sequential reuse blocked; concurrent window not atomic (WARNING 3). |
| R3 auth interplay | ✅ Implemented | PR2 native views unchanged; `redirect("login")` after signup. |
| PR3 rollback | ✅ Verified | Reverting deletes `views.py`/templates/`0002_invite`; `0001_initial` + PR2 auth remain bootable. |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| D1 `is_staff` gate on invite creation | ✅ Yes | `views.py:22`; brute-force test `member_forbidden_from_creating_invite`. |
| D4 form-level duplicate check, DB unique on token only | ⚠️ Yes, with caveat | Implemented exactly as designed, but form-level enforcement does not cover the admin surface (WARNING 2). |
| Signup flow per interface contract | ✅ Yes | GET render / 404; POST create + `used_at`; redirect `/login/`. |
| `gen_token = secrets.token_urlsafe(32)` | ✅ Yes | `models.py:22–24`. |
| Default expiry now + 7d | ✅ Yes | `INVITE_TTL = timedelta(days=7)`; `default_expiry` model-level. |
| `created_by` (design said deferred/YAGNI) | ✅ Implemented | Nullable FK `SET_NULL`, per task brief — sound audit choice. |
| Template location (`templates/accounts/*.html`) | ✅ Yes | invite/signup forms land there as specified; PR2 login shell stays `registration/`. |
| DB unique stays on `token` only | ✅ Yes | `0002_invite.py:31–34`. |

## TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | `apply-progress.md` PR3 section + Engram `sdd/web-foundation/apply-progress`. |
| All tasks have tests | ✅ | 3.1/3.3 RED; 3.2/3.4 GREEN; 3.5 rollback noted. |
| RED confirmed (tests exist) | ✅ | `test_invite.py` (7) + `test_signup.py` (8) present and committed. |
| GREEN confirmed (tests pass) | ✅ | 59/59 pass on independent execution. |
| Triangulation adequate | ✅ | invite: unique/dup/used-then-recreate/past/member/staff; signup: render/valid/expired/reused/unknown/normalise/no-open/single-use. |
| Safety Net for modified files | ✅ | PR1+PR2 44 tests green before and after. |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution (PR3)

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | 0 | 0 | pytest available |
| Integration | 15 | 2 | pytest-django (Django test client + ORM) |
| E2E | 0 | 0 | not installed (deferred) |
| **Total** | **15** | **2** | |

All PR3 tests are integration-style (ORM + form + Django test client) against a real sqlite test DB — the correct layer for token lifecycle.

### Changed File Coverage

Coverage analysis skipped — no coverage tool detected (`pytest-cov` gate scheduled for PR4, task 4.7).

### Assertion Quality (PR3)

Audited `tests/web/test_invite.py` (7) and `tests/web/test_signup.py` (8):

- No tautologies; no type-only-alone assertions.
- No ghost loops (no loops over query results at all).
- No mocks (0 mocks; mock/assertion ratio N/A).
- No smoke-test-only cases — `test_signup_page_renders_for_valid_token` asserts both `200` **and** `b"password" in content` (behavioral).
- Every test calls production code (ORM `create`, `InviteForm.is_valid()`, `client.post/get`) and asserts a value: token inequality, `used_at is None`, `role == "admin"`, `check_password`, `status_code`, `User.objects.count()`, stored `email == "mixed@example.com"`.
- Rejected-path tests correctly assert *both* `404` and that no `User` exists — no assertion-without-side-effect.

**Assertion quality**: ✅ All assertions verify real behavior (0 CRITICAL, 0 WARNING).

### Quality Metrics (PR3)

**Linter**: ✅ No errors (`ruff check .` exit 0) / 0 warnings
**Type Checker**: ➖ Not available (mypy/pyright explicitly out of scope per `tasks.md`)

## Issues Found

**CRITICAL**: None.

**WARNING**:
1. **Signup for an already-existing email crashes with HTTP 500 (unhandled `IntegrityError`).** `web/accounts/forms.py:26–34` (`InviteForm.clean_email`) does not check whether a `User` already holds the email, so staff can create an invite for an existing account (probe: form valid). The invitee then POSTs a password and `views.py:44` `User.objects.create_user(...)` hits `UNIQUE constraint failed: accounts_user.email`; the exception is uncaught → 500, and `used_at` is left null (probe-confirmed). Reachable via the normal staff flow, not only a race. **Fix:** in `clean_email`, reject when `User.objects.filter(email=email).exists()`; and/or catch `IntegrityError` in the signup view and re-render the form.
2. **Duplicate-active and past-expiry rules are not enforced on the admin surface.** `web/accounts/admin.py:32–37` registers `InviteAdmin` without `form = InviteForm`, so Django's default `ModelForm` is used (probe: `InviteAdmin.form` is `ModelForm`) and both `clean_email` and `clean_expires_at` are skipped. Combined with `clean_email` lowercasing only the *submitted* value (`forms.py:27`) while an admin-created row can be stored mixed-case, `case@example.com` passes against a stored `Case@Example.com` → two active invites (probe: invite count 2). The design's own rollout ("seed first invite via admin") makes this a shipped path. **Fix:** set `form = InviteForm` on `InviteAdmin` and normalise email at the model/manager boundary (or a `UniqueConstraint(Lower("email"))`); not a break of the literal R1 scenarios (which exercise the custom view) — hence WARNING.
3. **Single-use is check-then-set, not atomic (TOCTOU).** `views.py:38–50` reads `is_valid()` then writes `used_at` with no `transaction.atomic()` / `select_for_update()`. Two concurrent POSTs with the same token can both pass the check. The `accounts_user.email` unique constraint incidentally caps the damage (the loser gets the same 500 as WARNING 1) rather than creating two accounts. **Fix:** `with transaction.atomic(): invite = Invite.objects.select_for_update().get(token=token)` (or a conditional `UPDATE ... WHERE used_at IS NULL` and check rows-affected).
4. **`AUTH_PASSWORD_VALIDATORS` are configured but never enforced at signup.** `SignupForm` (`forms.py:51–61`) only checks `password1 == password2`; `create_user` calls `set_password` directly. Probe: password `"1"` is accepted and the account is created. The signup route is the **only** account-creation path, so the strength policy is effectively dead. **Fix:** add a `clean_password1` calling `django.contrib.auth.password_validation.validate_password`.

**SUGGESTION**:
1. `require_http_methods(["GET","POST"])` returns 405 on `HEAD`; harmless but a `HEAD` probe to a valid signup link 405s instead of 200 (cosmetic).
2. The invite form's `expires_at` is a free-form `DateTimeField`; consider `forms.DateTimeInput(type="datetime-local")` for usability. The **validation** itself (future-only) is correctly enforced.
3. Commit hygiene: HEAD stacks a docs-only commit (`330e886`) on a squash-titled commit (`3628255 "…(#15)"`) and a dangling sibling (`df84492`) exists on `origin/feat/web-foundation-user`. No functional impact; squash/retarget before opening PR3.

## Verdict

**PASS WITH WARNINGS**
All 5 Phase-3 tasks complete; 59/59 tests pass (PR1+PR2's 44 preserved + 15 new); `ruff check`, `ruff format --check`, `manage.py check`, and `makemigrations --check` all exit 0; diff is strictly PR3 (accounts model/forms/views/urls/admin/templates/migration, tests — no `src/`, `.github/`, or Docker). All 12 in-scope spec scenarios have passing covering tests. Four WARNINGs are security/reliability hardening in the invite/signup slice — none violates a literal spec scenario and none blocks the merge, but WARNINGs 1 and 4 should be fixed before PR4 deploys this to staging.

**Final PR3 merge decision: GO** (carry WARNINGs 1–4 into a follow-up hardening commit before the slice reaches a deployed environment).

---

# PR2 Verification — commit `f454840` (preserved)

Envelope: verdict pass, 42/42 tests, requirements 3/3, scenarios 8/8, ruff+format+manage.py check+makemigrations exit 0, diff strictly PR2 (19 files, +573/-7). Adversarial probes found: DB uniqueness PASS; **case-sensitive email uniqueness GAP** (`Foo@` vs `foo@` both persisted) → WARNING must be addressed before PR3; `create_superuser` yields `role="member"` → SUGGESTION; password-reset non-enumeration PASS; fixtures isolated PASS.

Resolution carried into PR3: the tracker tree now stores emails lowercased (`managers.py` `normalize_email(email).lower()`) and `tests/web/test_user.py` adds `test_duplicate_email_case_insensitive` + `test_authenticate_email_is_case_insensitive` (probe: case-variant user now rejected with `IntegrityError`). **PR2 WARNING 1 is RESOLVED in the PR3 base.**

PR2 section detail (preserved):
- Completeness: 6/6 Phase-2 tasks.
- Spec matrix: R4 (4 scenarios) + R3 (4 scenarios) + R14 harness = 8/8 in-scope.
- Coherence: D2/D3/D1 followed; template location note (`registration/` vs `accounts/`).
- TDD Compliance 6/6.
- Issues: WARNING 1 (case-sensitive uniqueness — now resolved); SUGGESTIONS 1–3 (superuser role, `LOGIN_REDIRECT_URL="/"` 404, internal `username` field name).
- Verdict: PASS WITH WARNINGS; FINAL PR2 MERGE DECISION: GO.

---

# PR1 Verification — commit `98678aa` (preserved)

- Envelope: verdict pass, 32/32 tests, requirements 5/5, scenarios 13/14, ruff+format+manage.py check exit 0, boundary respected (no src/.github/Docker).
- In-scope: R5 (5 scenarios COMPLIANT), R8 (2 COMPLIANT), R9 (2 COMPLIANT + 1 PARTIAL manual no-Django import), R12 (2 COMPLIANT), R10 (2 COMPLIANT).
- WARNINGS: (1) R9 "core imports without Django" has no committed test — real proof is PR4 core-isolation CI job. (2) `redis` package not declared though base.py selects `RedisCache` when `REDIS_URL` set; `redis>=5` deferred to PR4.
- SUGGESTIONS: (1) `test_settings_have_no_hardcoded_secrets` scans settings only; gitleaks PR4. (2) design.md/tasks.md uncommitted mods — RESOLVED as of PR2 verify.
- Verdict: PASS.

Artifacts: openspec/changes/web-foundation/verify-report.md | Engram sdd/web-foundation/verify-report
Session: verify-pr3-bitunix-trader
Project: bitunix-trader
Scope: project
Topic: sdd/web-foundation/verify-report
