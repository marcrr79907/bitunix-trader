# Design: web-foundation

## Technical Approach

A Django 5.1 LTS project in `web/` (project package `config`, app `accounts`) imports the
framework-free `src/` core as an external library. Phase 0 ships env-driven settings, a custom
email-identifier `User`, invitation-gated signup + native auth, `/healthz`, local Compose, a
Railway-shaped deploy (web/worker/scheduler), and a boundary test. No DRF, no Celery, no order
surface. CLI and `src/` stay unchanged.

## Architecture Decisions

| # | Decision | Choice | Alternatives | Rationale |
|---|----------|--------|--------------|-----------|
| D1 | Invite authz (R1) | Require `user.is_staff` on invite creation | `role=="admin"` check; permissions app | Built-in "may use admin" flag: zero machinery, testable. Domain `role` stays a product concept. |
| D2 | Role values (R4) | `TextChoices`: `member` (default), `admin` | `operator`/`viewer`; free text | Specs name exactly two actors; closed enum makes "defaults safely" testable. |
| D3 | User base class | `AbstractUser`, `username=None`, `email=unique`, `USERNAME_FIELD="email"` | `AbstractBaseUser`+`PermissionsMixin` | Provides `is_staff`/permissions/password D1 needs; bare base forces re-adding it. |
| D4 | Duplicate invite (R1) | Form `clean_email`: reject when an unused+unexpired invite exists; DB unique only on `token` | `UniqueConstraint` on `email` | "Active" is clock-dependent; a DB constraint can't express `expires_at > now()`. |
| D5 | `/healthz` | Liveness only: `{"status":"ok"}`, no DB/Redis | Readiness ping | DB-coupled healthcheck turns a DB blip into a restart storm. |
| D6 | Settings | `base` (env parse), `dev` (sqlite, insecure key), `prod` (`os.environ["SECRET_KEY"]`→KeyError) | Single settings; `django-environ` | R5 demands split + fail-closed prod; dict-index gives fail-closed free. |
| D7 | Prod server | `gunicorn` | `runserver`; uvicorn | No async/WS → WSGI. |
| D8 | Worker/scheduler | Bootable stubs (`redis.ping()` then idle) | Defer; RQ now | R7 needs three bootable services in Phase 0; stub proves `REDIS_URL`; RQ deferred to Phase 3. |

**Signup flow**: `GET /signup/<token>/` → token exists? unused? unexpired? → no: 404 (no form);
yes → POST → `create_user(email, pw, role=invite.role)` + `invite.used_at=now()` → `/login/`.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `web/manage.py` | Create | Entry; default `config.settings.dev` |
| `web/config/{settings/{__init__,base,dev,prod}.py, urls.py, wsgi.py, asgi.py, health.py}` | Create | Settings split, root URLs, WSGI/ASGI, liveness view |
| `web/accounts/{__init__,apps,managers,models,forms,views,urls,admin}.py` | Create | User, `Invite`, signup + auth |
| `web/accounts/migrations/0001_initial.py` + `templates/accounts/*.html` | Create | Schema; base/signup/login/password_reset* |
| `web/{worker,scheduler}.py` | Create | Redis-ping + idle stubs (R7) |
| `tests/{test_boundary,test_settings,test_no_secrets}.py`, `tests/web/test_*.py` | Create | Boundary, settings, hygiene, accounts, health |
| `Dockerfile`, `docker-compose.yml`, `railway.json`, `.dockerignore` | Create | Single image / local stack / Railway |
| `.env.example` | Modify | + `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `DEBUG`, `ALLOWED_HOSTS`, `DJANGO_SETTINGS_MODULE` |
| `requirements.txt` | Modify | + `Django>=5.1,<5.2`, `psycopg[binary]>=3.1`, `dj-database-url>=2.1`, `gunicorn>=22`, `redis>=5` |
| `requirements-dev.txt` | Modify | + `pytest-django>=4.8` |
| `pyproject.toml` | Modify | `pythonpath=["web"]`, `DJANGO_SETTINGS_MODULE="config.settings.dev"` |
| `.github/workflows/ci.yml` | Modify | `manage.py check` + pytest-django; `core-isolation` job |

`src/`, existing tests, ruff config, CLI: **unchanged** (R10).

## Interfaces / Contracts

```python
class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)
    USERNAME_FIELD, REQUIRED_FIELDS = "email", []
    objects = UserManager()  # create_user(email, password, **extra)


class Invite(models.Model):
    email = models.EmailField(db_index=True)
    token = models.CharField(
        max_length=64, unique=True, default=gen_token
    )  # secrets.token_urlsafe(32)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)
    expires_at = models.DateTimeField(default=default_expiry)  # now + 7d
    used_at = models.DateTimeField(null=True, blank=True)

    def is_valid(self):
        return self.used_at is None and self.expires_at > now()


def healthz(request):
    return JsonResponse({"status": "ok"})
```

Boundary test is stdlib-only: `ast.parse` each `src/*.py`, fail on any `django` root import. A
CI `core-isolation` job installs **only** `requirements.txt` (no Django) and imports every `src`
module — the real proof of R9's no-Django scenario.

## Testing Strategy (strict TDD, `python -m pytest`)

| Req | Test | Layer |
|-----|------|-------|
| R1–R4 | `tests/web/test_{invite,signup,auth,user}.py` | Unit/Integration |
| R5, R8, R9 | `test_settings.py`, `test_health.py` (200 anon, no secrets), `test_boundary.py` (AST) + CI | Unit/CI |
| R10 | existing 20 tests | Regression |
| R11 | **Partial**: `test_no_order_surface.py` scans `web/` for order verbs; read-only credential provisioning = **deferred** (deploy-time) | Unit |
| R12 | `test_no_secrets.py`: `.env` gitignored + no literal secret in settings | Unit |
| R13/R14 | **Mechanism NOW** (Fernet round-trip, "web path never decrypts" scan); R14 harness-ready (no owned rows → red→green in Phase 2) | Unit |
| R6/R7 | **Automated**: L2 `docker build` + `docker compose config` + worker/scheduler boot test; L3 deploy `curl /healthz` | L2+L3 |

> Verify MUST NOT under-claim R6/R7 as "manual": they are automated (L2 build + L3 deploy smoke).
> R11-credential/R13: the mechanism is tested now; only the real-credential lifecycle waits Phase 2.
> R14: no user-owned rows exist in Phase 0 → harness left ready to flip red→green in Phase 2.

## Migration / Rollout

1. `makemigrations accounts` → commit `0001_initial.py` first.
2. `migrate` on dev (sqlite) + prod (managed Postgres).
3. `createsuperuser` (email) on deployed `web`; seed first invite via admin; submit `/signup/<token>/`.

**Rollback**: revert `feat/web-dashboard` (delete `web/`, infra, requirement lines); `src/`,
tests, CLI untouched. Tear down Railway services independently.

## PR Slices (feeds sdd-tasks) — Feature Branch Chain

`feat/web-dashboard`; each child targets the prior branch.

| PR | Work unit | ±Lines | Dep |
|----|-----------|--------|-----|
| PR1 | Scaffold + settings + `/healthz` + boundary test | ~330 | base |
| PR2 | Custom `User` + manager + auth + tests | ~300 | PR1 |
| PR3 | `Invite` + signup + migration + tests | ~300 | PR2 |
| PR4 | Docker/compose/railway + stubs + CI **hardening** + CD + `.env.example` | ~330 | PR1, PR3 |

**Branch topology**: `feat/web-dashboard` tracker → `develop` (Railway staging) → `main` (Railway
production); `feat/*` get ephemeral Railway PR environments. Both `develop` and `main` protected.
No separate `staging` branch (develop fills that role).

## Open Questions

None blocking. `Invite.created_by` deferred (YAGNI); readiness probe added with the first real
dependency.
