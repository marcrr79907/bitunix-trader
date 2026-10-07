# Apply Progress: web-foundation

## Mode

**Strict TDD** (openspec `config.yaml` `strict_tdd: true`, runner `python -m pytest`).

## Scope of this batch

PR1 only — Work Unit 1 of the feature-branch chain: scaffold + env-driven settings +
`/healthz` + framework-free boundary test. Chain strategy: `feature-branch-chain`
(PR1 targets the `feat/web-dashboard` tracker branch; this branch is
`feat/web-foundation-scaffold`).

## Completed Tasks

- [x] 1.1 RED `tests/test_settings.py` — 6 subprocess-boot cases for env parsing,
  prod fail-closed, dev defaults, falsey `DEBUG`.
- [x] 1.2 GREEN `web/config/settings/{__init__,base,dev,prod}.py`.
- [x] 1.3 GREEN `web/manage.py`, `web/config/{urls,wsgi,asgi,health}.py`;
  `pyproject.toml` pythonpath + `DJANGO_SETTINGS_MODULE`; requirements.
- [x] 1.4 RED `tests/web/test_health.py` — anon 200 + no-secret body.
- [x] 1.5 GREEN `/healthz` view + route.
- [x] 1.6 `tests/test_boundary.py` — AST scan of `src/` for `django` root import,
  plus a triangulating scanner test (proves the scanner flags a real violation).
- [x] 1.7 `tests/test_no_secrets.py` — `.env` gitignore + no literal secret markers
  in settings source.
- [x] 1.8 `.env.example` — 6 new placeholders (no secrets).
- [x] 1.9 PR1 rollback boundary — no `src/`/CLI/ruff-config changes; revert = delete
  `web/`, revert the 3 config files + `pyproject.toml`/requirements/`.env.example`.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/test_settings.py` | Unit (subprocess boot) | ✅ 20/20 | ✅ Written (6 failed, no `web/`) | ✅ 6 passed | ✅ 6 cases (db/redis/prod/dev/debug×2) | ✅ Clean |
| 1.3 | `tests/test_settings.py` (boots modules) | Integration | ✅ 20/20 | ✅ via 1.1 | ✅ 6 passed | ➖ structural config | ✅ `ruff format` |
| 1.4 | `tests/web/test_health.py` | Integration (Django test client) | N/A (new) | ✅ Written → 404 (route removed, demonstrated) | ✅ 2 passed | ✅ 2 cases (status+json, no-leak) | ✅ Clean |
| 1.6 | `tests/test_boundary.py` | Unit (stdlib AST) | N/A (new) | ✅ guard passes green | ✅ 2 passed | ✅ scanner-violation case | ✅ Clean |
| 1.7 | `tests/test_no_secrets.py` | Unit (subprocess git) | N/A (new) | ✅ Written | ✅ 2 passed | ✅ 2 cases (gitignore + scans) | ✅ Clean |

Notes:
- Health route RED was demonstrated by removing the URL line → `test_healthz_returns_200_anonymously`
  failed 404, then restored → green. `health.py` was scaffolded with the settings split;
  the RED gate was replayed against the URL wiring to honor the ordering.
- `test_healthz_body_has_no_secrets` was strengthened to assert `200` first so it cannot
  pass trivially on a 404 error body.
- `test_boundary.py` passes immediately by design (1.6 = guard). Triangulation added a
  synthetic `leaky.py` so the scanner is proven to actually catch a Django import.

## Test Summary

- Total tests written: 12 (6 settings + 2 health + 2 boundary + 2 no_secrets)
- Total tests passing: 32 / 32 (full suite; baseline 20 preserved)
- Layers used: Unit (10), Integration (2)
- Approval tests: None — no refactoring of existing modules
- Pure functions created: 3 (`env_bool`, `env_list`, `_imported_roots`/`_django_offenders`)

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `web/manage.py` | Created | Entry point, default `config.settings.dev` |
| `web/config/__init__.py` | Created | Package marker |
| `web/config/settings/__init__.py` | Created | Package marker |
| `web/config/settings/base.py` | Created | Env-driven shared settings (DATABASE_URL/REDIS_URL/DEBUG/ALLOWED_HOSTS) |
| `web/config/settings/dev.py` | Created | Local defaults, DEBUG true, insecure key fallback |
| `web/config/settings/prod.py` | Created | `os.environ["SECRET_KEY"]` fail-closed, DEBUG False |
| `web/config/urls.py` | Created | `/healthz` + admin |
| `web/config/health.py` | Created | Liveness-only JSON view (no DB) |
| `web/config/wsgi.py` | Created | WSGI entry (prod default) |
| `web/config/asgi.py` | Created | ASGI entry |
| `tests/test_settings.py` | Created | R5 settings contract (subprocess boot) |
| `tests/web/__init__.py` | Created | Package marker |
| `tests/web/test_health.py` | Created | R8 `/healthz` contract |
| `tests/test_boundary.py` | Created | R9 stdlib AST boundary guard |
| `tests/test_no_secrets.py` | Created | R12 secrets hygiene |
| `pyproject.toml` | Modified | `pythonpath=["web"]`, `DJANGO_SETTINGS_MODULE` |
| `requirements.txt` | Modified | Django==5.1.*, psycopg[binary], dj-database-url |
| `requirements-dev.txt` | Modified | pytest-django |
| `.env.example` | Modified | SECRET_KEY, DATABASE_URL, REDIS_URL, DEBUG, ALLOWED_HOSTS, DJANGO_SETTINGS_MODULE |

## Deviations from Design

None. Settings split, dict-index fail-closed prod, liveness-only `/healthz`, and the
stdlib-only AST boundary test all match design D5/D6/D7 and the interfaces section.

One implementation note: `base.py` gains a small `env_bool`/`env_list` helper pair
instead of inline parsing. This keeps falsey handling consistent across modules and is
what the 1.1 spec scenarios (`DEBUG` falsey, list hosts) require.

## Issues Found

None.

## Remaining Tasks

Phase 2 (PR2): custom `User` + manager + native auth + isolation harness. Phase 3 (PR3):
`Invite` + token signup. Phase 4 (PR4): Docker/Compose/Railway + stubs + CI/CD.

## Workload / PR Boundary

- Mode: chained PR slice (feature-branch-chain), PR1.
- Current work unit: PR1 scaffold + settings + `/healthz` + boundary.
- Boundary: starts from clean `feat/web-foundation-scaffold` (base `feat/web-dashboard`);
  ends after all Phase 1 tasks + local commit. Does not touch `src/`, PR2–PR4 artifacts,
  Docker, Railway, or `.github/workflows`.
- Budget impact: ~330 changed lines, within the per-slice ~330 target.

## Status

9/9 Phase-1 tasks complete. Ready for verify (PR1) then PR2.

---

# Apply Progress: web-foundation — PR2 (batch 2)

## Mode

**Strict TDD** (openspec `config.yaml` `strict_tdd: true`, runner `python -m pytest`).

## Scope of this batch

PR2 only — Work Unit 2 of the feature-branch chain: custom email-identifier `User`,
native Django auth, and the R14 isolation harness. Branch `feat/web-foundation-user`
(base `feat/web-dashboard` containing PR1). Chain strategy: `feature-branch-chain`.

## Completed Tasks

- [x] 2.1 RED `tests/web/test_user.py` — 6 cases (AUTH_USER_MODEL, duplicate email,
  role default, explicit admin role, email auth, create_superuser).
- [x] 2.2 GREEN `web/accounts/{__init__,apps,managers,models,admin}.py` +
  `AUTH_USER_MODEL="accounts.User"`; migration `0001_initial.py`.
- [x] 2.3 RED `tests/web/test_auth.py` — 4 cases (email login, wrong creds,
  logout, password-reset round-trip).
- [x] 2.4 GREEN auth views in `accounts/urls.py`, included from `config/urls.py`.
- [x] 2.5 `tests/web/conftest.py` — `user_a`/`user_b` R14 harness (no assertion yet).
- [x] 2.6 PR2 rollback — revert deletes `accounts/`+download; PR1 scaffold boots.

## Base class decision (justification)

Chose **`AbstractUser` with `username=None` + custom `UserManager`** over
`AbstractBaseUser`+`PermissionsMixin` (design D3). Rationale: design D1 gates
invite creation on `is_staff` and needs permissions; `AbstractUser` ships
`is_staff`/`is_superuser`/`PermissionsMixin`/`date_joined`, so the bare base
would force re-adding all of it. Setting `username=None` removes the field from
the model without a data migration, and `USERNAME_FIELD="email"` makes
`ModelBackend` authenticate by email with no custom backend (verified in
`django/contrib/auth/backends.py`).

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 2.1 | `tests/web/test_user.py` | Unit/Integration (ORM + auth) | ✅ 32/32 | ✅ Written → 9 failed (`auth.User`, `create_user()` needs username) | ✅ 6 passed | ✅ 6 cases incl. duplicate-email + explicit `admin` | ✅ `ruff format` |
| 2.2 | `tests/web/test_user.py` (migration) | Integration | ✅ 32/32 | ✅ via 2.1 | ✅ passed | ✅ `makemigrations --check` clean | ✅ clean |
| 2.3 | `tests/web/test_auth.py` | Integration (Django test client) | ✅ 32/32 | ✅ Written → failed (no routes/templates) | ✅ 4 passed | ✅ 4 cases incl. reset token round-trip | ✅ clean |
| 2.4 | `tests/web/test_auth.py` | Integration | ✅ 32/32 | ✅ via 2.3 | ✅ passed | ✅ reset-confirm redirect + set-password | ✅ clean |
| 2.5 | `tests/web/conftest.py` | Fixture harness | N/A (new) | ✅ (fixtures reference custom manager that did not exist) | ✅ exercised by 2.1/2.3 suites | ➖ harness only by design | ✅ clean |

Notes:
- RED for 2.1/2.3 was executed before the app existed → 9 failures captured
  (`AUTH_USER_MODEL` was `auth.User`; Django's default manager rejected the
  email-only `create_user` signature). GREEN flipped exactly on adding `accounts`.
- 2.4 initially needed `registration/login.html`: the wrong-creds scenario renders
  the form and returns 200, so with no template it raised `TemplateDoesNotExist`.
  Added a minimal `login.html` + `base.html`; the remaining reset templates are
  Django's own (admin app) and need no files. This is the in-cycle GREEN fix, not
  a test edit.
- `role` triangulated from the member default to an explicit `admin` value so the
  `TextChoices` enum cannot pass by hardcoding `member`.

## Test Summary

- Total tests written this batch: 10 (6 user + 4 auth) + 2 fixtures
- Total tests passing: 42 / 42 (full suite; baseline 32 preserved)
- Layers used: Unit (1), Integration (9)
- Approval tests: None — no refactoring of existing modules
- Pure functions created: 0 (model/manager + view wiring; no pure logic to extract)

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `web/accounts/__init__.py` | Created | Package marker |
| `web/accounts/apps.py` | Created | `AccountsConfig` |
| `web/accounts/managers.py` | Created | `UserManager` (email-based `create_user`/`create_superuser`) |
| `web/accounts/models.py` | Created | `User(AbstractUser)`, `Role` TextChoices, email unique |
| `web/accounts/admin.py` | Created | `UserAdmin` with email fieldsets |
| `web/accounts/urls.py` | Created | Native login/logout/password-reset routes |
| `web/accounts/migrations/__init__.py` | Created | Package marker |
| `web/accounts/migrations/0001_initial.py` | Created | Generated `User` schema |
| `web/accounts/templates/registration/{base,login}.html` | Created | Minimal login form shell |
| `web/config/settings/base.py` | Modified | `accounts` app, `AUTH_USER_MODEL`, login/logout redirects |
| `web/config/urls.py` | Modified | include `accounts.urls` |
| `tests/web/test_user.py` | Created | R4 contract |
| `tests/web/test_auth.py` | Created | R3 contract |
| `tests/web/conftest.py` | Created | R14 `user_a`/`user_b` harness |
| `pyproject.toml` | Modified | ruff per-file-ignore `E501` for `**/migrations/*.py` |

## Deviations from Design

None material. Two implementation notes:
- Added a minimal `registration/login.html` + `base.html`. The design file table
  anticipated `templates/accounts/*.html`; Django's convention (and reusable
  password-reset confirmation template) uses `registration/`, so the login shell
  landed there. Password-reset templates are Django's shipped admin templates —
  no files added.
- `role` column uses `max_length=16` exactly as the design interface specifies.

## Verification (PR2)

- `.venv/bin/python -m pytest` → **42 passed**
- `.venv/bin/python web/manage.py makemigrations --check --dry-run` → **No changes detected**
- `.venv/bin/python web/manage.py check` → **System check identified no issues (0 silenced)**
- `.venv/bin/ruff check .` → **All checks passed!**
- `.venv/bin/ruff format --check .` → **53 files already formatted**

## Status

6/6 Phase-2 tasks complete. 15/15 total tasks complete (Phases 1–2). Ready for
verify (PR2), then PR3 (Invite + token signup).
