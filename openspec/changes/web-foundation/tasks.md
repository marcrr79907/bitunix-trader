# Tasks: web-foundation

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1210 total (additions + deletions) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR2 → PR3 → PR4 (each child targets prior branch) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Base | ~Lines |
|------|------|----|------|--------|
| 1 | Scaffold + settings + `/healthz` + boundary | PR1 | `feat/web-dashboard` | 330 |
| 2 | Custom `User` + native auth + isolation harness | PR2 | PR1 branch | 300 |
| 3 | `Invite` + token signup | PR3 | PR2 branch | 300 |
| 4 | Docker/Compose/Railway + worker stubs + CI/ **CD smoke** | PR4 | PR3 branch | 280 |

All slices ≤ ~330 changed lines (≤ ~60 min review each). PR4 also needs PR1's `healthz`; PR3 **hard-depends on PR2** (User must exist before `Invite.role`/signup FK).

## Requirement → Verification Layer Traceability

Layers: **L1** = pytest/pytest-django (every PR) · **L2** = `docker build` + `docker compose config` (every PR, from PR4) · **L3** = CD deploy then `curl $RAILWAY_URL/healthz` → 200 (fails pipeline otherwise).

| Req | Primary check | Layer(s) | State after Phase 0 |
|-----|---------------|----------|---------------------|
| R1 | `tests/web/test_invite.py` | L1 | green |
| R2 | `tests/web/test_signup.py` | L1 | green |
| R3 | `tests/web/test_auth.py` | L1 | green |
| R4 | `tests/web/test_user.py` | L1 | green |
| R5 | `tests/test_settings.py` | L1 | green |
| R6 | `docker compose config` + compose brings up pg/redis | L2 | green |
| R7 | `docker build` + worker/scheduler boot test + railway.json | L2 | green |
| R8 | `tests/web/test_health.py`; CD `curl /healthz` | L1 + **L3** | green (L1 impl; L3 PR4) |
| R9 | `tests/test_boundary.py` (AST) + `core-isolation` CI job | L1 | green |
| R10 | existing 20 tests | L1 | green (regression) |
| R11 no-order | `tests/web/test_no_order_surface.py` scans `web/` | L1 | green |
| R11-credential | Fernet round-trip + "web path never decrypts" scan | L1 | **mechanism NOW**; real-credential cycle = Phase 2 |
| R12 | `tests/test_no_secrets.py` + `.gitignore` | L1 | green |
| R13 | Fernet mechanism test (`web/credentials.py`) | L1 | **mechanism NOW**; enforcement = Phase 2 |
| R14 | isolation harness (`user_a`, `user_b` fixtures) | L1 | **HARNESS ready**; no owned rows → test goes red→green in Phase 2 |

**Precision notes (honor in sdd-verify):** R11-credential/R13 → the *mechanism* is tested now; only the real-credential lifecycle waits for Phase 2. R14/R13 enforcement → no user-owned rows exist in Phase 0, so no green assertion is possible; the two-user harness is left ready so Phase 2's isolation test flips red→green with no scaffolding. R6/R7 are **fully automated** (L2 build/compose + L3 deploy smoke) — never "manual".

## Phase 1 — PR1: Scaffold + settings + `/healthz` + boundary (L1)

- [ ] 1.1 **RED** `tests/test_settings.py`: `DATABASE_URL` parsed (no hardcoded host), `REDIS_URL` used, prod missing `SECRET_KEY` raises, dev local defaults + `DEBUG` true, falsey `DEBUG` disables. [L1]
- [ ] 1.2 **GREEN** `web/config/settings/{__init__,base,dev,prod}.py`: split via `dj-database-url`; prod `os.environ["SECRET_KEY"]` fail-closed. [L1]
- [ ] 1.3 **GREEN** `web/manage.py`, `web/config/{urls,wsgi,asgi}.py`; `pyproject.toml` `pythonpath=["web"]` + `DJANGO_SETTINGS_MODULE`; requirements (+Django 5.1, psycopg, dj-database-url, pytest-django). [L1]
- [ ] 1.4 **RED** `tests/web/test_health.py`: anonymous `GET /healthz` → 200; body has no secret/connection string. [L1]
- [ ] 1.5 **GREEN** `web/config/health.py` + route in `config/urls.py`. [L1]
- [ ] 1.6 `tests/test_boundary.py`: `ast.parse` every `src/*.py`, fail on `django` root import (passes immediately — guard test). [L1]
- [ ] 1.7 `tests/test_no_secrets.py`: `.env` gitignored; no literal secret in settings. [L1]
- [ ] 1.8 `.env.example`: add `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `DEBUG`, `ALLOWED_HOSTS`, `DJANGO_SETTINGS_MODULE` placeholders. [L1]
- [ ] 1.9 **PR1 rollback**: revert branch → delete `web/`, revert `pyproject.toml`/requirements/`.env.example`; `src/`+CLI untouched.

## Phase 2 — PR2: Custom `User` + native auth (L1) — *before PR3*

- [ ] 2.1 **RED** `tests/web/test_user.py`: `AUTH_USER_MODEL == accounts.User`; duplicate email rejected; `role` defaults `member`; `authenticate(email, pw)` succeeds. [L1]
- [ ] 2.2 **GREEN** `web/accounts/{apps,managers,models,admin}.py` + `AUTH_USER_MODEL`; `makemigrations` → `0001_initial.py`. [L1]
- [ ] 2.3 **RED** `tests/web/test_auth.py`: login with email; wrong creds → no session; logout invalidates session; password-reset round-trip. [L1]
- [ ] 2.4 **GREEN** wire Django auth views in `accounts/urls.py` + `config/urls.py`. [L1]
- [ ] 2.5 `tests/web/conftest.py`: R14 isolation **harness** — `user_a`, `user_b` fixtures only (no green assertion yet). [L1]
- [ ] 2.6 **PR2 rollback**: revert → delete `accounts/`+migration; PR1 scaffold remains bootable.

## Phase 3 — PR3: `Invite` + token signup (L1) — *requires PR2*

- [ ] 3.1 **RED** `tests/web/test_invite.py`: valid invite (unique token, `used_at` null, future expiry); duplicate active rejected; past expiry rejected; creation gated by `is_staff` (D1). [L1]
- [ ] 3.2 **GREEN** `Invite` in `accounts/models.py` + `forms.py` `clean_email`; `makemigrations` → `0002_invite`; register in `admin.py`. [L1]
- [ ] 3.3 **RED** `tests/web/test_signup.py`: valid token creates user with invite role + sets `used_at`; expired/reused/unknown rejected; no open registration route. [L1]
- [ ] 3.4 **GREEN** view `signup/<token>/` + templates `accounts/*.html`. [L1]
- [ ] 3.5 **PR3 rollback**: revert → delete signup view/templates + `0002_invite`; PR2 auth still green.

## Phase 4 — PR4: Docker/Compose/Railway + stubs + CI/CD (L1 + L2 + L3)

- [ ] 4.1 **GREEN** `web/credentials.py`: Fernet `encrypt`/`decrypt` (key from env), confined to worker zone; add `cryptography`. [L1]
- [ ] 4.2 **RED→GREEN** `tests/web/test_credentials_mechanism.py`: Fernet round-trip **now** + AST scan asserts no `web/config`/`web/accounts` module decrypts (R11-cred, R13). [L1]
- [ ] 4.3 `tests/web/test_no_order_surface.py`: scan `web/` for order-placement verbs (R11). [L1]
- [ ] 4.4 **RED→GREEN** `tests/web/test_service_stubs.py` (mock `redis.Redis.ping`) → `web/worker.py`, `web/scheduler.py` bootable Redis-ping+idle stubs (D8/R7). [L1]
- [ ] 4.5 `Dockerfile`, `.dockerignore`, `docker-compose.yml` (pg+redis), `railway.json` (web/worker/scheduler). [L2]
- [ ] 4.6 `.env.example`: finalize `REDIS_URL`, crypto key placeholder. [L1]
- [ ] 4.7 `.github/workflows/ci.yml`: add `core-isolation` job (install `requirements.txt` only, import all `src/`); add **L2** job (`docker build` + `docker compose config`); add **L3** CD job — deploy then `curl $RAILWAY_URL/healthz`, fail on non-200. [L2 + L3]
- [ ] 4.8 **PR4 rollback**: revert → delete infra files + CI/CD jobs, remove worker/scheduler stubs; app still runnable via dev settings.
