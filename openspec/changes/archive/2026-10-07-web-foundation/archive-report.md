# Archive Report: web-foundation

**Archived**: 2026-10-07
**Verdict**: PASS WITH WARNINGS (0 blockers, 0 critical) — 70/70 tests, 93.31% coverage (≥85% gate)
**Delivery**: 4 chained PR slices → tracker `feat/web-dashboard` → promoted to `develop` (PR #17)
**Merged commit**: `c9f89df`

## What Shipped

An always-on, invitation-only Django web dashboard foundation — Phase 0. Strictly read-only: no order endpoints exist. The CLI and the framework-free `src/` core are untouched.

| Area | Delivered |
|------|-----------|
| Django project | `web/` (`config` project, `accounts` app), settings split base/dev/prod |
| Identity | Custom email-identifier `User` (`AUTH_USER_MODEL`), role defaulting to `member` |
| Access | `Invite` (token, role, expiry, `used_at`) + staff-gated creation + token-gated signup; native login/logout/password-reset |
| Config | Env-driven `DATABASE_URL` / `REDIS_URL` / `SECRET_KEY` / `DEBUG`; prod fails closed on missing secret |
| Infra | `Dockerfile`, `docker-compose.yml` (pg16 + redis7), `railway.json`, worker/scheduler bootable stubs |
| CI/CD | L1 pytest/pytest-django + ruff + `manage.py check` + `makemigrations --check` + pip-audit + gitleaks + core-isolation; L2 docker build/compose; L3 `/healthz` deploy smoke |
| Crypto | `web/credentials.py` Fernet mechanism, fail-closed, confined to worker zone |

## Requirement Outcomes

| Req | Domain | Outcome | Notes |
|-----|--------|---------|-------|
| R1 | invite-access | ✅ Green | Invite creation, duplicate/expiry validation |
| R2 | invite-access | ✅ Green | Token-gated signup; reused/expired/unknown rejected; no open registration |
| R3 | invite-access | ✅ Green | Email login, logout, password-reset round-trip |
| R4 | user-identity | ✅ Green | Custom `User`, unique email, safe role default, email auth |
| R5 | deployment-foundation | ✅ Green | Env-driven settings, prod fail-closed, dev defaults |
| R6 | deployment-foundation | ✅ Green | Compose brings pg + redis healthy (L2) |
| R7 | deployment-foundation | ⚠️ Partial | `web`/`worker`/`scheduler` boot green locally (L2); **managed-service split + secrets still pending** |
| R8 | deployment-foundation | ✅ Green | `/healthz` 200 anonymous, no secret leak; L3 smoke wired |
| R9 | core-domain-boundary | ✅ Green | One-way dependency; AST boundary test + core-isolation CI job |
| R10 | core-domain-boundary | ✅ Green | `src/` diff empty; existing 20 tests green |
| R11 | security-invariants | ✅ Green (invariant) / ⚠️ mechanism | No order surface exists (`git grep` clean); read-only credential provisioning deferred to Phase 2 |
| R12 | security-invariants | ✅ Green | No committed secret; `.env.example` placeholders only; gitleaks |
| R13 | security-invariants | 🔶 Mechanism-only | Fernet round-trip + fail-closed + confinement scan green; real-credential enforcement = Phase 2 |
| R14 | security-invariants | 🔶 Harness-only | `user_a`/`user_b` fixtures ready; no user-owned rows exist in Phase 0 → enforcement flips red→green in Phase 2 |

**Legend**: ✅ green · 🔶 mechanism/harness now, enforcement later · ⚠️ partial/deferred.

## Carry-Forward Items

1. **Railway provisioning + secrets** — project/services creation and `STAGING_URL` / `PROD_URL` repo secrets still pending. CD (L3) skips gracefully until set.
2. **R7 three-service split** — must be created per-service in the Railway dashboard; `railway.json` only sets the `web` default (`services` block is inert — see WARNING 4).
3. **R14 isolation enforcement** — harness ready; the isolation test flips red→green in Phase 2 once user-owned rows exist.
4. **`src/` coverage** — legacy CLI coverage is incremental; the 85% gate currently measures `web/` only.
5. **Django bumped 5.1 → 5.2 LTS** — CVEs found in 5.1; 5.2 LTS adopted.

## Verify Findings (non-blocking, fix before the noted trigger)

| # | Severity | Finding | Fix trigger |
|---|----------|---------|-------------|
| 1 | Medium | Order-surface scanner blind spot — `ORDER_VERBS` misses real BitUnix verbs (`create_order`, `submit_order`, `cancel_*`) and `getattr` string args. Invariant holds today. | Before Phase 2 order/credential code |
| 2 | Low-Med | Fernet confinement scan misses `getattr(x, "decrypt")` and wildcard-import bare calls. | Before Phase 2 credential code |
| 3 | Medium | `.dockerignore` patterns are root-only → image ships `web/db.sqlite3` + `__pycache__`. Use `**/` recursive patterns. | Before first real Railway deploy |
| 4 | Low-Med | `railway.json` `services` key is not in the Railway schema (inert). Drop it or use `environments`; configure services in dashboard. | Before first real Railway deploy |
| S1–S3 | Suggestion | Worker/scheduler INFO logs invisible (no `basicConfig`); image runs as root; `prod.py` 0% attributed coverage. | Opportunistic |

## SDD Cycle Complete

Planned → implemented → verified → archived. Delta specs merged into the main spec store:

- `openspec/specs/invite-access/spec.md`
- `openspec/specs/deployment-foundation/spec.md`
- `openspec/specs/core-domain-boundary/spec.md`
- `openspec/specs/security-invariants/spec.md`
- `openspec/specs/user-identity/spec.md`

Archive audit trail: `openspec/changes/archive/2026-10-07-web-foundation/` (proposal, specs, design, tasks, apply-progress, verify-report).

## Traceability — Engram Observation IDs

| Artifact | Observation ID |
|----------|----------------|
| `sdd/web-foundation/proposal` | 1292 |
| `sdd/web-foundation/design` | 1293 |
| `sdd/web-foundation/tasks` | 1294 |
| `sdd/web-foundation/apply-progress` | 1296 |
| `sdd/web-foundation/verify-report` | 1298 |
| `sdd/web-foundation/pr4-findings` | 1303 |

Specs have no standalone Engram observations — they live in the OpenSpec file store (both delta and merged main spec).
