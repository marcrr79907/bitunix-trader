# Proposal: web-foundation

## Intent

Move from "run CLI commands" to always-on market context. Phase 0 ships the hosting, auth and data foundation: a deployed, invitation-only Django skeleton. CLI unchanged; **strictly read-only, no order endpoints ever.**

## Scope

### In Scope
- Branch `feat/web-dashboard`.
- Django scaffold `web/` (`manage.py`, settings split base/dev/prod).
- Custom `User`, email as identifier.
- `accounts` app: `Invite` (email, token, role, expires_at, used_at) + token-gated signup; login/logout/password-reset via Django built-ins.
- Env-driven settings: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `DEBUG` (no hardcoded localhost).
- Railway: Postgres + Redis, services `web`/`worker`/`scheduler` (stubs), skeleton deployed.
- Docker Compose (pg + redis) for local dev.
- CI runs `pytest-django` alongside the existing suite.
- Add Django, psycopg, pytest-django, dj-database-url to requirements.

### Out of Scope
- Indicators/metrics, market persistence, real worker sync, JSON API, non-auth UI, alerts, historic data.
- Order automation (HARD invariant).

## Capabilities

### New Capabilities
- `invite-access`: invitation-gated signup, login/logout/password-reset, invite roles.
- `deployment-foundation`: env-driven settings, Railway services, Compose, deployed skeleton.
- `core-domain-boundary`: Django depends on `src/`; `src/` never imports Django.

### Modified Capabilities
- None.

## Approach

`web/` imports `src/` as an external library; core never imports Django. Settings read `DATABASE_URL`/`REDIS_URL` via `dj-database-url`, so Railway→VPS is code-free. Custom `User` from day 1 avoids a painful later migration. `worker`/`scheduler` ship as bootable stubs so infra is real, logic deferred.

**Reuse vs New**: REUSED UNCHANGED — `src/*.py` (7 modules), 20 tests, ruff config. NEW — `web/` tree, `Dockerfile`, `docker-compose.yml`, Railway config, `.env.example`, added requirements.

**Boundary**: core modules stay dependency-free; a test asserts no Django import leaks into `src/`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/` | New | Django project + `accounts` app |
| `requirements*.txt` | Modified | Django, psycopg, pytest-django, dj-database-url |
| `pyproject.toml` | Modified | settings module, pytest-django |
| `.github/workflows/ci.yml` | Modified | Django checks + app tests |
| `Dockerfile`, `docker-compose.yml`, `.env.example` | New | Local + deploy infra |
| `src/` | Unchanged | Framework-free core reused as-is |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Custom User introduced too late | Low | In Phase 0, before data |
| `src/` imports Django | Med | Boundary test + review gate |
| Railway env drift from local | Med | Single URL contract |
| CI duration grows | Low | Split jobs, cache pip |

## Rollback Plan

Revert `feat/web-dashboard`: delete `web/`, infra files, requirements lines. `src/`, tests and CLI stay untouched, so `main` still ships a working CLI. Tear down Railway services/plugins independently.

## Open Questions

- Django 5.0 vs 5.1 for Phase 0?
- Health endpoint now, or rely on Railway's port probe?
- `worker`/`scheduler` as separate services now, or split later?

## Success Criteria

- [ ] `python -m pytest` green (20 existing + new).
- [ ] `ruff check . && ruff format --check .` green.
- [ ] Skeleton deployed on Railway; `web` responds against managed Postgres.
- [ ] Invite → signup → login works end-to-end.
- [ ] `src/` has zero Django imports (boundary test).
- [ ] `docker compose up` brings pg + redis locally.

## Review Workload Forecast

- Estimated diff: **> 400 changed lines** (scaffold + infra + tests).
- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: High
