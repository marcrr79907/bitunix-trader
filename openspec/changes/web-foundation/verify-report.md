```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:97773233ba029b52599edaf65498c558b72cd7ad996b85c4478f5b75051d80cc
verdict: pass
blockers: 0
critical_findings: 0
requirements: 3/3
scenarios: 8/8
test_command: .venv/bin/python -m pytest
test_exit_code: 0
test_output_hash: sha256:558523f306d881b9e9a1ba2b39e31315a193cec398984aab8037ed6cfb7a8284
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python web/manage.py check && .venv/bin/python web/manage.py makemigrations --check --dry-run
build_exit_code: 0
build_output_hash: sha256:3d29864cb7d3413f015238e3e5f205dd4a47a5ff7342977b50b3e4627e3e7894
```

# Verification Report

**Change**: web-foundation
**Version**: N/A (delta specs)
**Mode**: Strict TDD (openspec `config.yaml` `strict_tdd: true`, runner `.venv/bin/python -m pytest`)
**Latest scope**: PR2 (commit `f454840`) — branch `feat/web-foundation-user`, base/tracker `feat/web-dashboard`

This document is cumulative. The envelope above reflects the latest independent run (PR2). The PR1 section below is preserved from the prior verification pass and was not re-run as its own scope, but PR1's tests remain green inside the current full-suite execution.

---

# PR2 Verification — commit `f454840`

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total (Phase 2) | 6 |
| Tasks complete | 6 |
| Tasks incomplete | 0 |

Phase 2 items 2.1–2.6 are all checked in `tasks.md` and confirmed against the committed tree.

## Build & Tests Execution

**Build**: ✅ Passed (exit 0)
```text
$ .venv/bin/ruff check .
All checks passed!
$ .venv/bin/ruff format --check .
53 files already formatted
$ .venv/bin/python web/manage.py check
System check identified no issues (0 silenced).
$ .venv/bin/python web/manage.py makemigrations --check --dry-run
No changes detected
```

**Tests**: ✅ 42 passed / ❌ 0 failed / ⚠️ 0 skipped (exit 0, 6.45s)
```text
$ .venv/bin/python -m pytest
tests/test_alerts.py: 4
tests/test_boundary.py: 2
tests/test_db.py: 4
tests/test_journal.py: 4
tests/test_no_secrets.py: 2
tests/test_positions.py: 6
tests/test_settings.py: 6
tests/test_sign.py: 2
tests/web/test_auth.py: 4      <- new in PR2
tests/web/test_health.py: 2
tests/web/test_user.py: 6      <- new in PR2
42 passed in 6.45s
```

Baseline regression: the 20 pre-existing tests + PR1's 12 tests (32) all pass unchanged; PR2 adds exactly 10 tests, matching the apply report.

**Coverage**: ➖ Not available — `pytest-cov` gate is scheduled for PR4 (task 4.7).

## Diff Scope

```
$ git diff --stat feat/web-dashboard...HEAD
 19 files changed, 573 insertions(+), 7 deletions(-)
```

Touched paths: `web/accounts/**` (new), `web/config/settings/base.py`, `web/config/urls.py`, `tests/web/{conftest,test_user,test_auth}.py`, `pyproject.toml`, `.gitignore`, and SDD artifacts (`tasks.md`, `apply-progress.md`).

Scope check `git diff --stat feat/web-dashboard...HEAD -- src/ .github/ Dockerfile docker-compose.yml railway.json` → **empty**. No `src/`, no `.github/`, no Docker/Compose/Railway. No tracked secret file. PR2 boundary respected.

## Spec Compliance Matrix (PR2 in-scope requirements)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R4 | Custom user model is active | `tests/web/test_user.py::test_auth_user_model_is_custom` | ✅ COMPLIANT |
| R4 | Email is unique and required | `tests/web/test_user.py::test_duplicate_email_rejected` | ✅ COMPLIANT (exact-case) |
| R4 | Role defaults safely | `tests/web/test_user.py::test_role_defaults_to_member` | ✅ COMPLIANT |
| R4 | Authentication uses email | `tests/web/test_user.py::test_authenticate_with_email_succeeds` | ✅ COMPLIANT |
| R3 | Login with email | `tests/web/test_auth.py::test_login_with_email_creates_session` | ✅ COMPLIANT |
| R3 | Logout ends session | `tests/web/test_auth.py::test_logout_invalidates_session` | ✅ COMPLIANT |
| R3 | Password reset round-trip | `tests/web/test_auth.py::test_password_reset_round_trip` | ✅ COMPLIANT |
| R3 | Wrong credentials rejected | `tests/web/test_auth.py::test_wrong_credentials_no_session` | ✅ COMPLIANT |
| R14 | Isolation harness (2 users) | `tests/web/conftest.py::{user_a,user_b}` (exercised by probe) | ✅ HARNESS READY |

**Compliance summary**: 8/8 in-scope scenarios compliant + R14 harness scaffold ready. Cumulative previously-verified (PR1): 13/14, unchanged.

### Not-yet-applicable (belong PR3/PR4 — correctly absent, does not fail this phase)

R1 (invite creation), R2 (token signup) → PR3. R6/R7 (Compose/Railway/worker) → PR4. R11 (no-order surface), R13 (Fernet credentials) → PR4. Their absence is expected.

## Adversarial Probes (independently executed, not from the apply report)

| Probe | Method | Result |
|-------|--------|--------|
| DB-level uniqueness | Inspect `0001_initial.py` + runtime `IntegrityError` test | ✅ `EmailField(max_length=254, unique=True)` → DB constraint present |
| Case-insensitive uniqueness | `create_user("Foo@example.com")` then `create_user("foo@example.com")` | ❌ **Both rows created** — see WARNING 1 |
| `create_superuser` flags | Runtime check | ✅ `is_staff=True`, `is_superuser=True`; `role="member"` (see SUGGESTION 1) |
| Login keys on email | Inspect `AuthenticationForm` + `USERNAME_FIELD` + live POST | ✅ `USERNAME_FIELD="email"`; form field label is "Email"; POST keys session on the user |
| Username leakage in form | Render/inspect login form | ✅ No username field; input widget named `username` but labelled "Email" (cosmetic) |
| Password-reset non-enumeration | POST existing vs. nonexistent email | ✅ Both 302; mail sent only for existing (0 vs 1) — no existence oracle |
| Fixture isolation | Request `user_a`,`user_b` | ✅ pk 1 vs 2, distinct emails/passwords |
| Migration landed + no drift | `makemigrations --check --dry-run` | ✅ "No changes detected" (0001_initial committed) |
| Secrets / out-of-scope files | `git diff` path + secret grep | ✅ No secret, no `src/`, no `.github/`, no Docker |

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| R4 custom User | ✅ Implemented | `web/accounts/models.py` — `AbstractUser`, `username=None`, `email=unique`, `USERNAME_FIELD="email"`, `Role` TextChoices (`member` default, `admin`); `AUTH_USER_MODEL="accounts.User"` set before first migration. |
| R4 manager | ✅ Implemented | `web/accounts/managers.py` — email-based `create_user`/`create_superuser`, `normalize_email` applied. |
| R3 auth views | ✅ Implemented | `web/accounts/urls.py` — native `LoginView`/`LogoutView`/`PasswordReset*`; included from `config/urls.py`. |
| R14 harness | ✅ Scaffolded | `tests/web/conftest.py` — two isolated users; no green assertion by design (Phase 2 adds owned rows). |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| D2 `TextChoices` member/admin, member default | ✅ Yes | `models.py` lines 16–22. |
| D3 `AbstractUser` + `username=None` + custom manager | ✅ Yes | Matches interface contract exactly; no custom backend needed (ModelBackend keys on `USERNAME_FIELD`). |
| D1 `is_staff` decoupled from domain `role` | ✅ Yes | Admin registered with email fieldsets. |
| Login/logout redirect wiring | ✅ Yes | `LOGIN_URL`/`LOGOUT_REDIRECT_URL` set; see SUGGESTION 2 on `LOGIN_REDIRECT_URL="/"`. |
| Template location | ⚠️ Minor note | Design predicted `templates/accounts/*.html`; login shell landed in `templates/registration/` (Django convention). No functional impact; apply report documents it. |

## TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | `apply-progress.md` + Engram `sdd/web-foundation/apply-progress` (#1296). |
| All tasks have tests | ✅ | 2 covering files for 2.1–2.4; 2.5 is the harness itself. |
| RED confirmed (tests exist) | ✅ | All listed test files present and committed. |
| GREEN confirmed (tests pass) | ✅ | 42/42 pass on independent execution. |
| Triangulation adequate | ✅ | `test_user.py` 6 cases (incl. duplicate + explicit `admin`); `test_auth.py` 4 cases (incl. reset round-trip). |
| Safety Net for modified files | ✅ | `base.py`/`urls.py`/`pyproject.toml` modified; PR1's 32 tests green before and after. |

**TDD Compliance**: 6/6 checks passed.

## Issues Found

**CRITICAL**: None.

**WARNING**:
1. **Email uniqueness is case-sensitive → duplicate identities possible.** `web/accounts/models.py:21` uses `unique=True`, and `web/accounts/managers.py:18` calls `normalize_email`, but Django's `normalize_email` only lowercases the **domain** (probe: `Foo@example.com` → `Foo@example.com`). Confirmed at runtime: `Foo@example.com` and `foo@example.com` are **both accepted**, and `authenticate()` succeeds for either spelling. For an email-keyed auth system this is an identity-integrity gap that will surface once PR3's signup or any case-normalizing client is added. **Fix (before PR3):** normalize the full address at the manager boundary (`email = email.strip().lower()`) and/or add a functional unique index, e.g. `UniqueConstraint(Lower("email"), name="uniq_user_email_ci")` in a follow-up migration. Not a violation of the literal R4 scenario (same-string email *is* rejected) — hence WARNING, not CRITICAL.

**SUGGESTION**:
1. `create_superuser` yields `role="member"` (probe-confirmed). Functionally harmless — `is_superuser` bypasses permission checks and D1 gates admin access on `is_staff` — but surprising for an operator reading the admin. Consider defaulting `role=Role.ADMIN` in `create_superuser`.
2. `LOGIN_REDIRECT_URL="/"` (base.py:78) 302s to `/`, which 404s because no root view exists yet (probe: follow-redirect → 404). Expected until a landing route lands in a later PR; harmless for tests.
3. Login input is internally named `username` (Django built-in) with label "Email" — no user-facing leak, purely an HTML `name`/`autocomplete` cosmetic detail.

## Verdict

**PASS WITH WARNINGS**
All 6 Phase-2 tasks complete; 42/42 tests pass (PR1's 32 preserved + 10 new); `ruff check`, `ruff format --check`, `manage.py check`, and `makemigrations --check` all exit 0; diff is strictly PR2 (accounts app, auth wiring, tests, settings — no `src/`, `.github/`, or Docker). One WARNING (case-sensitive email uniqueness) must be addressed **before PR3** but does not block merging PR2, whose scope is the identity foundation.

**Final PR2 merge decision: GO** (with the uniqueness hardening carried into PR3).

---

# PR1 Verification — commit `98678aa` (preserved)

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total (Phase 1) | 9 |
| Tasks complete | 9 |
| Tasks incomplete | 0 |

## Build & Tests Execution

**Build**: ✅ Passed — `ruff check .` all checks passed; `ruff format --check .` 41 files formatted; `manage.py check` no issues.

**Tests**: ✅ 32 passed / ❌ 0 failed / ⚠️ 0 skipped. Baseline 20 tests + 12 new all green.

## Spec Compliance Matrix (in-scope requirements)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R5 | Database from DATABASE_URL | `test_settings.py::test_database_url_is_parsed_not_hardcoded` | ✅ COMPLIANT |
| R5 | Redis from REDIS_URL | `test_settings.py::test_redis_url_is_used_for_cache` | ✅ COMPLIANT |
| R5 | Missing SECRET_KEY in prod fails closed | `test_settings.py::test_prod_without_secret_key_fails_closed` | ✅ COMPLIANT |
| R5 | Dev defaults are local-only | `test_settings.py::test_dev_defaults_are_local_only` | ✅ COMPLIANT |
| R5 | DEBUG is environment-controlled | `test_settings.py::test_debug_falsey_disables_regardless_of_module` | ✅ COMPLIANT |
| R8 | Healthcheck succeeds (anonymous) | `tests/web/test_health.py::test_healthz_returns_200_anonymously` | ✅ COMPLIANT |
| R8 | Health does not leak secrets | `tests/web/test_health.py::test_healthz_body_has_no_secrets` | ✅ COMPLIANT |
| R9 | No Django import in core | `tests/test_boundary.py::test_no_django_import_in_core` | ✅ COMPLIANT |
| R9 | Boundary test fails on violation | `tests/test_boundary.py::test_scanner_flags_a_django_violation` | ✅ COMPLIANT |
| R9 | Core imports without Django | (none committed) — verified manually | ⚠️ PARTIAL |
| R9 | Web may depend on core | (none) — no `web→src` usage yet | ➖ N/A for PR1 |
| R12 | Repo contains no real secrets | `test_no_secrets.py::test_dotenv_is_gitignored` | ✅ COMPLIANT |
| R12 | Runtime secrets come from environment | `test_no_secrets.py::test_settings_have_no_hardcoded_secrets` | ✅ COMPLIANT |
| R10 | Existing suite stays green | 20 baseline tests in full run | ✅ COMPLIANT |
| R10 | CLI behavior preserved | `src/` untouched; baseline tests pass | ✅ COMPLIANT |

**Compliance summary**: 13/14 in-scope scenarios compliant (1 PARTIAL, 1 N/A).

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| D5 liveness-only `/healthz` | ✅ Yes | No DB/Redis in the view. |
| D6 settings split + fail-closed prod | ✅ Yes | `base`/`dev`/`prod`; dict-index prod secret. |
| D7 WSGI prod server | ➖ Deferred | `wsgi.py`/`asgi.py` created; gunicorn is PR4. |
| D8 worker/scheduler stubs | ➖ Deferred | PR4 scope. |
| Boundary test stdlib-only | ✅ Yes | No Django import in `tests/test_boundary.py`. |

## Issues Found

**CRITICAL**: None.

**WARNING**:
1. **R9 "Core imports without Django" has no committed covering test.** Real proof is the `core-isolation` CI job scheduled for PR4; manually verified this session (6/6 `src` modules import with Django blocked).
2. **`redis` package not declared** yet `base.py` selects `RedisCache` when `REDIS_URL` is set. No PR1 path exercises the cache; `redis>=5` is deferred to PR4. Flag so PR4 does not forget.

**SUGGESTION**:
1. `test_settings_have_no_hardcoded_secrets` scans only `web/config/settings/*.py`; broader gitleaks scan is PR4.
2. ~~`design.md` and `tasks.md` have uncommitted working-tree modifications.~~ **Resolved** — working tree is clean as of PR2 verification.

## Verdict

**PASS** — 9/9 Phase-1 tasks; 32/32 tests pass; `ruff check`, `ruff format --check`, and `manage.py check` exit 0; diff respected the PR1 boundary.
