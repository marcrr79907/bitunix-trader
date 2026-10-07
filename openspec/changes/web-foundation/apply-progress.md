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
