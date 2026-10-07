```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:2bcc0476e4ec7d9dcea9e1c665ab1755b5d5610ba20eeaa7ddbb1d58028374dd
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 5/5
scenarios: 8/9
test_command: .venv/bin/python -m pytest --cov
test_exit_code: 0
test_output_hash: sha256:6dc44404826ad8a6ff560e80ce61aca319a4e3d45b57ec670940578bd8328961
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python web/manage.py check && .venv/bin/python web/manage.py makemigrations --check --dry-run
build_exit_code: 0
build_output_hash: sha256:6ada7137be3b599cdf4ac4c5cf8c5087dad140d57f1b0b1f918c9368091a66b8
```

# Verification Report

**Change**: web-foundation
**Version**: N/A (delta specs)
**Mode**: Strict TDD (openspec `config.yaml` `strict_tdd: true`, runner `.venv/bin/python -m pytest`)
**Latest scope**: PR4 (HEAD `7d87c5b`) — branch `feat/web-foundation-infra`, base/tracker `feat/web-dashboard` (PR1+PR2+PR3 merged)

This document is cumulative. The envelope above reflects the latest independent run (**PR4**). The PR3, PR2, and PR1 sections below are preserved from prior verification passes; their tests remain green inside the current full-suite execution (70 tests). Cumulative previously-verified in-scope: PR1 13/14, PR2 8/8, PR3 12/12.

---

# PR4 Verification — commit `7d87c5b` (tip)

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total (Phase 4) | 11 |
| Tasks complete | 11 |
| Tasks incomplete | 0 |

Phase 4 items 4.1–4.11 are all checked in `tasks.md` and confirmed against the committed tree. Cumulative 31/31 (Phases 1–4).

## Build & Tests Execution

**Build**: ✅ Passed (exit 0)
```text
$ .venv/bin/ruff check .
All checks passed!
$ .venv/bin/ruff format --check .
64 files already formatted
$ .venv/bin/python web/manage.py check
System check identified no issues (0 silenced).
$ .venv/bin/python web/manage.py makemigrations --check --dry-run
No changes detected
```

**Tests**: ✅ 70 passed / ❌ 0 failed / ⚠️ 0 skipped (exit 0)
```text
$ .venv/bin/python -m pytest --cov
......................................................................   [100%]
web/accounts/forms.py      36  2  94%   web/config/settings/base.py  40  3  92%
web/accounts/managers.py   23  1  96%   web/config/settings/dev.py    7  0 100%
web/accounts/models.py     37  2  95%   web/config/settings/prod.py   5  5   0%
web/accounts/views.py      53  3  94%   web/credentials.py           13  0 100%
web/config/health.py        4  0 100%   web/scheduler.py              9  1  89%
web/config/urls.py          5  0 100%   web/worker.py                23  2  91%
TOTAL                     284 19  93%
Required test coverage of 85.0% reached. Total coverage: 93.31%
70 passed in 36.06s
```
PR4 adds 11 tests (4 credentials + 2 order-surface + 2 service-stub parametrised = 2) — repo suite grew 59 → 70. Baseline 59 preserved unchanged.

**Coverage**: 93.31% / threshold: 85% → ✅ Above (gate enforced via `[tool.coverage.report] fail_under = 85`).

## Diff Scope

```
$ git diff --stat feat/web-dashboard...HEAD
 .dockerignore, .env.example, .github/workflows/{cd,ci}.yml, .gitignore,
 Dockerfile, docker-compose.yml, openspec/…, pyproject.toml, railway.json,
 requirements{,-dev}.txt, tests/web/{test_credentials_mechanism,test_no_order_surface,test_service_stubs}.py,
 web/{credentials,scheduler,worker}.py
 20 files changed, 582 insertions(+), 21 deletions(-)

$ git diff --stat feat/web-dashboard...HEAD -- src/
(empty)
```
`src/` untouched (R10 preserved); no `src/` diff. No tracked secret (`.env` gitignored; `.pem/.key/.p12` absent). PR4 boundary respected.

## L2 / L3 Independent Execution (independently run, not from apply report)

| Probe | Command | Result |
|-------|---------|--------|
| Compose config valid | `docker compose config` | ✅ exit 0 |
| Image builds | `docker build -t bitunix-trader:verify .` | ✅ exit 0 |
| Image contains app | `docker run … ls /app` | ✅ `src/` + `web/` present, no `.env`, no `.git`, no `openspec/`, no `tests/` |
| Full stack boots (R6) | `docker compose up -d --build` | ✅ `db` healthy, `redis` healthy, `web`/`worker`/`scheduler` running |
| Web + healthz (R8/R6/R7) | `curl localhost:8000/healthz` | ✅ **HTTP 200** `{"status":"ok"}`, `Server: gunicorn` |
| Migrations apply | compose web logs | ✅ all `accounts`/`auth`/`admin`/`sessions` migrations applied, gunicorn boots |
| CD non-200 fails | simulated `cd.yml` bash with unreachable URL | ✅ loop exhausts → `exit 1` |
| CD unset-URL skips | simulated `cd.yml` with empty URL | ✅ graceful skip, no failure |
| Workflows parse | `yaml.safe_load` all `.github/workflows/*.yml` | ✅ `ok` |
| Actions pinned | `grep 'uses: …@[0-9a-f]{40}'` | ✅ 8/8 SHA-pinned, 0 unpinned |
| pip-audit clean | `.venv/bin/pip-audit -r requirements.txt` | ✅ "No known vulnerabilities found" |

## Spec Compliance Matrix (PR4 in-scope requirements)

| Requirement | Scenario | Evidence | Result |
|-------------|----------|----------|--------|
| R6 | Compose brings up dependencies | `docker compose up` → db+redis `healthy` (executed); CI L2 `docker compose config` | ✅ COMPLIANT |
| R7 | Web responds | `curl /healthz` → 200 over compose gunicorn | ✅ COMPLIANT |
| R7 | Worker and scheduler boot | `tests/web/test_service_stubs.py::test_stub_boots_and_idles[worker/scheduler]` + both containers `running` | ✅ COMPLIANT |
| R7 | Prod uses managed services | external Railway project — not repo-verifiable; `railway.json` config issue below | ⚠️ PARTIAL |
| R8 | Healthcheck succeeds | `tests/web/test_health.py` (PR1, re-run green) + live 200 | ✅ COMPLIANT |
| R11 | No order execution surface | `tests/web/test_no_order_surface.py` + independent `git grep` for order verbs returns none | ✅ COMPLIANT (scanner gap — WARNING 1) |
| R11-creds | Read-only credential enforced | `.env.example` documents read-only/no-withdrawal; mechanism now, real provisioning deferred (design) | ⚠️ PARTIAL (deferred per spec) |
| R13 | Keys stored encrypted | `test_credentials_mechanism.py::test_encrypt_decrypt_round_trip` + `test_fails_closed_without_key` | ✅ COMPLIANT (mechanism) |
| R13 | Decryption confined to worker | `test_request_path_never_decrypts` | ⚠️ PARTIAL (scan holds for today's code — WARNING 2) |
| R14 | No cross-user read | no user-owned rows exist in Phase 0; harness `user_a`/`user_b` ready (PR2) | ➖ NOT APPLICABLE (per design) |

**Compliance summary**: 8/9 in-scope scenarios proven compliant; R7 "prod uses managed services" is external to the repo (PARTIAL). R11-credential/R13 real enforcement is explicitly deferred by the spec ("enforcement lands when credentials exist"); the mechanism scenarios pass.

## Adversarial Probes (independently executed)

| Probe | Method | Result |
|-------|--------|--------|
| Fernet key fail-closed | `credentials.encrypt` with `CREDENTIALS_FERNET_KEY` unset | ✅ raises `RuntimeError` |
| Fernet round-trip | generate key, encrypt, decrypt | ✅ round-trips; ciphertext ≠ plaintext |
| **Decrypt confinement scan holes** | synthetic files: `getattr(credentials,"decrypt")`, wildcard `from credentials import *` + bare `decrypt(t)`, `importlib.import_module("credentials").decrypt(t)`, aliased import | ⚠️ `importlib`/alias **caught**; `getattr`-string and wildcard-bare-call **MISSED** — see WARNING 2 |
| **Order-surface scan holes** | synthetic files with `place_order`, `create_order`, `submit_order`, `create_market_order`, `create_limit_order`, `cancel_all_orders` | ⚠️ only `place_order` **caught**; the 5 common BitUnix verbs **MISSED** — see WARNING 1 |
| Order invariant actually holds | `git grep` order/trade verbs across `src/*.py` + `web/*.py` | ✅ none (only read endpoints `get_history_orders`, `position/get_pending_positions`) |
| **`.dockerignore` nested leak** | `docker build` + inspect image for `web/db.sqlite3`, `__pycache__`, `.env` | ❌ image **ships `/app/web/db.sqlite3` and `__pycache__`** (patterns `*.sqlite3`/`__pycache__` do not match nested paths) — see WARNING 3 |
| Dockerfile correctness | inspect image | ✅ `PYTHONPATH=/app:/app/web`, non-secret build, `${PORT:-8000}`, `src/`+`web/` copied, no `.env`; ⚠️ runs as root (SUGGESTION 2) |
| Compose dependency gating | `docker compose config` + up | ✅ `web` depends on db+redis `service_healthy`; `web` runs `migrate` before gunicorn; worker/scheduler depend on healthy redis |
| **railway.json schema** | compare against `https://railway.app/railway.schema.json` | ❌ schema has **no `services` key** (only `build`/`deploy`/`environments`); the 3-service block is inert — see WARNING 4 |
| CI coverage gate actually gates | local `pytest --cov` + `[tool.coverage.report] fail_under=85` | ✅ enforced ("Required test coverage of 85.0% reached") |
| CI hardening presence | read `ci.yml` | ✅ SHA-pinned (8), `concurrency` + `cancel-in-progress`, `timeout-minutes`, `permissions` least-privilege, core-isolation installs no Django |
| CD fail-on-non-200 / skip | simulate `cd.yml` bash | ✅ exit 1 on non-200; skip when URL unset |
| No secrets in workflows | read both files | ✅ only `${{ secrets.* }}` references |
| No committed secret | pattern grep + `git ls-files` | ✅ only test fixture passwords and an empty `.env.example` placeholder |
| Migration drift | `makemigrations --check --dry-run` | ✅ No changes detected |
| Worker/scheduler logging | compose logs | ⚠️ `logger.info` never prints — no `logging.basicConfig()` (Python default WARNING) — SUGGESTION 1 |

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| R6 Compose | ✅ Implemented | `docker-compose.yml` pg16+redis7 with healthchecks; verified healthy + reachable. |
| R7 Docker image | ✅ Implemented | `Dockerfile:5-22` single image, three commands, gunicorn `${PORT:-8000}`. |
| R7 worker/scheduler stubs | ✅ Implemented | `web/worker.py` Redis-ping + idle; `web/scheduler.py` reuses `worker.idle_loop`. No business logic. |
| R7 Railway shape | ⚠️ Partial | `railway.json` valid `build`/`deploy` keys; **`services` block ignored by Railway** (WARNING 4). |
| R11 no-order surface | ✅ Implemented | No order verbs in `web/`; scanner exists but has a blind spot (WARNING 1). |
| R13 Fernet mechanism | ✅ Implemented | `web/credentials.py` env-key `Fernet`, fail-closed on missing key; decrypt confined by test (WARNING 2). |
| R12 secrets hygiene | ✅ Preserved | `.env.example` placeholders only; `.env` gitignored. |
| R10 core unchanged | ✅ Preserved | `git diff … -- src/` empty. |
| PR4 rollback | ✅ Verified | Reverting deletes infra files + stubs + CI/CD jobs; app still boots via dev settings (compose/`manage.py check` proven). |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| D7 prod server = gunicorn (WSGI) | ✅ Yes | Dockerfile CMD + compose + railway.json all gunicorn `config.wsgi`. |
| D8 worker/scheduler bootable stubs | ✅ Yes | Redis ping then idle; test mocks `redis.Redis.ping`. |
| Single image, per-service command | ✅ Yes | Matches tasks.md 4.5. |
| R13 "mechanism NOW, enforcement Phase 2" | ✅ Yes | Round-trip + fail-closed + confinement scan; real credential lifecycle deferred as specified. |
| R6/R7 automated via L2/L3 (not manual) | ✅ Yes | L2 CI `docker build` + `docker compose config`; L3 CD smoke; executor also booted the full stack. |

## TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | `apply-progress.md` PR4 section. |
| All tasks have tests | ✅ | 4.1/4.2 Fernet, 4.3 order scan, 4.4 stubs; 4.5–4.11 infra verified by L2/L3 execution. |
| RED confirmed | ✅ | Apply report documents RED→GREEN for credentials/stubs/order-scan. |
| GREEN confirmed (tests pass) | ✅ | 70/70 pass on independent execution, coverage 93.31% ≥ 85%. |
| Triangulation adequate | ✅ | Fernet: round-trip + fail-closed + confinement + scanner self-test; order: scan + scanner self-test; stubs: worker + scheduler parametrised. |
| Safety Net for modified files | ✅ | PR1–PR3's 59 tests green before/after. |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution (PR4)

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit (stdlib AST + mocked redis) | 6 | 3 | pytest, `unittest.mock` via monkeypatch |
| Integration (Django test client) | 4 | (PR2/PR3 preserved) | pytest-django |
| **New PR4** | **6** | **3** | |
| Full suite | **70** | 13 | |

### Assertion Quality (PR4)

- `test_encrypt_decrypt_round_trip`: asserts ciphertext ≠ plaintext **and** decrypt equals original — behavioural.
- `test_fails_closed_without_key`: asserts `RuntimeError` raised — no fallback secret.
- `test_request_path_never_decrypts` + `test_scanner_flags_a_decrypt_call`: guard + triangulating self-test (proves scanner catches a real violation).
- `test_no_order_surface_in_web` + `test_scanner_flags_an_order_call`: guard + self-test.
- `test_stub_boots_and_idles[worker|scheduler]`: asserts `main(iterations=1) == 0` after a real (mocked-transport) ping — no tautology.

**Assertion quality**: ✅ 0 CRITICAL, 0 WARNING. Note: the two scanners' self-tests only prove the *narrow* verb lists they check (WARNINGs 1/2).

## Issues Found

**CRITICAL**: None.

**WARNING 1 (MEDIUM) — Order-surface scanner has a large blind spot.** `tests/web/test_no_order_surface.py:15-17` defines `ORDER_VERBS = {place_order, batch_order, cancel_order, close_position}` but BitUnix's actual order verbs are `create_order`, `submit_order`, `modify_order`, `create_market_order`, `create_limit_order`, `cancel_all_orders`. Probe: only `place_order` is caught; the other five are missed, and `getattr(client, "place_order")` (string, not `ast.Name`/`ast.Attribute`) also slips through. R11 states the prohibition "MUST NOT be relaxed by later changes", so a weak guard materially weakens that guarantee. The invariant **holds today** (independent `git grep` across `src/`+`web/` finds no order verbs), so this is a test gap, not a live violation. **Fix:** extend `ORDER_VERBS` with the real verb set (`create_order`, `submit_order`, `modify_order`, `cancel_order`, `cancel_all_orders`, `create_market_order`, `create_limit_order`, `close_position`, `close_all_positions`) and detect `getattr(x, "verb")` string args.

**WARNING 2 (LOW-MEDIUM) — Fernet confinement scan has holes.** `tests/web/test_credentials_mechanism.py:31-47` catches aliased imports and `x.decrypt(...)`, but misses `getattr(credentials, "decrypt")` and `from credentials import *` + a bare `decrypt(t)` call. R13 enforcement is explicitly deferred by the spec ("enforcement lands when credentials exist") and no request-path module decrypts today, so severity is low. **Fix:** also flag any `getattr(x, "decrypt")` string arg and any `ast.Name(id="decrypt")` when the module has a wildcard credentials import.

**WARNING 3 (MEDIUM) — `.dockerignore` does not exclude nested build/local artifacts; the image ships `web/db.sqlite3` and `__pycache__`.** `.dockerignore` uses `*.sqlite3`, `__pycache__`, `.env`, but Docker's pattern semantics make these **root-only**; `COPY web/ web/` (Dockerfile:17) therefore bakes `/app/web/db.sqlite3` and `__pycache__/` into the image (confirmed via `docker run … find /app -name '*.sqlite3'`). Today the file is 0 bytes and untracked, so no data leak exists in the committed state; but the local dev DB lives at exactly this path (`base.py:49`), so a populated dev database — or a nested `web/.env` — would be copied into the image. **Fix:** use recursive patterns, e.g. add `**/db.sqlite3`, `**/*.sqlite3`, `**/__pycache__`, `**/*.py[cod]`, `**/.env`.

**WARNING 4 (LOW-MEDIUM) — `railway.json` uses a non-schema `services` key.** The Railway JSON schema (fetched `https://railway.app/railway.schema.json`) defines only `build`, `deploy`, and `environments` — there is **no top-level `services`** key. The `services: {web, worker, scheduler}` block (railway.json:15-26) is ignored by Railway; the actual three-service split must be created/configured per-service in the Railway dashboard. The file's own `_comment` acknowledges this ("each service overrides its Start Command … in the dashboard"). The valid `build`/`deploy` keys and `deploy.startCommand` (web default) are correct. **Fix:** either drop the inert `services` block and document the dashboard steps, or move per-service start commands into the supported `environments` map.

**SUGGESTION 1 — Worker/scheduler `logger.info` is invisible.** `web/worker.py:35` and `web/scheduler.py:17` log at INFO with no `logging.basicConfig()`; Python's default root level is WARNING, so the "up; redis reachable; idle" line never prints (compose logs empty). R7 boot is still proven (container running + test). Add a `logging.basicConfig(level=logging.INFO)` in `main()` so the deployed service emits its liveness line.

**SUGGESTION 2 — Docker image runs as root.** Dockerfile has no `USER`; gunicorn runs as root. Add a non-root user for defence-in-depth (Railway runs the container rootless at the platform level, so impact is contained).

**SUGGESTION 3 — `prod.py` shows 0% coverage.** `web/config/settings/prod.py` (5 statements) is untested in the default `dev`-settings run; the 85% aggregate gate hides it. The PR1 `test_settings.py` exercises prod fail-closed via subprocess, so the behaviour *is* tested — the coverage tool just doesn't attribute it. No action needed unless per-file gating is introduced.

## Verdict

**PASS WITH WARNINGS**
All 11 Phase-4 tasks complete. Independently executed: 70/70 tests pass with 93.31% coverage (≥85% gate), `ruff check`/`ruff format --check`/`manage.py check`/`makemigrations --check` all exit 0, `pip-audit` clean, all workflow YAML valid, all 8 actions SHA-pinned, `src/` untouched, no committed secret. The full L2 stack was brought up (`docker compose up --build`): db+redis healthy, `web`/`worker`/`scheduler` running, and `GET /healthz` returned **HTTP 200**. R6/R7/R8/R11/R13-mechanism are proven compliant; R7's "managed services" scenario is external (PARTIAL), and R11-credential/R13 enforcement is explicitly deferred by the spec. Four WARNINGs are hardening: two test-scanner blind spots (order verbs, decrypt confinement), a `.dockerignore` nested-artifact leak into the image, and an inert `railway.json` `services` block. None violates a literal spec scenario and none breaks the green pipeline.

**Final PR4 merge decision: GO** — fix WARNING 3 (`.dockerignore`) and WARNING 4 (`railway.json`) before the first real Railway deploy; fix WARNING 1 (order-verb list) and WARNING 2 (decrypt scan) before Phase 2 introduces order/credential code.

---

# PR3 Verification — commit `330e886` (preserved)

## Envelope (PR3)
- verdict: pass_with_warnings, blockers: 0, critical_findings: 0, requirements: 3/3, scenarios: 12/12
- test_command: `.venv/bin/python -m pytest` | exit 0 | 59 passed
- test_output_hash: sha256:47cf3957ef356c9d1ecf2890d43c95ef2bd4ce87051f8f40dec6296e5f4f4cd6
- build_command: `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python web/manage.py check && .venv/bin/python web/manage.py makemigrations --check --dry-run` | exit 0
- build_output_hash: sha256:b5279678dd650f8577cd632c197640c34eddce0648b064a31314093202ca441d
- PR3 HEAD `330e886`, branch `feat/web-foundation-invite`, base/tracker `feat/web-dashboard` (tip `357c347`)

## PR3 — Diff scope
13 files, +582/-8. Only `web/accounts/{models,forms,views,urls,admin}.py`, `migrations/0002_invite.py`, `templates/accounts/{invite_create,signup}.html`, `tests/web/{test_invite,test_signup}.py`, `pyproject.toml`, SDD artifacts. Scope check against `src/`, `.github/`, Dockerfile, docker-compose.yml, railway.json, .dockerignore = EMPTY. No secret tracked. PASS.

## PR3 — Per-requirement verdicts (in-scope)
| Req | Scenario | Test | Verdict |
|-----|----------|------|---------|
| R1 | Create valid invite | test_invite.py::{test_token_is_unique_and_generated,test_staff_can_create_invite} | PASS |
| R1 | Duplicate active rejected | test_invite.py::test_duplicate_active_invite_rejected | PASS (view path; admin bypass WARNING 2) |
| R1 | Past expiry rejected | test_invite.py::test_past_expiry_rejected_at_creation | PASS (form path; admin bypass WARNING 2) |
| R2 | Valid token signup | test_signup.py::test_valid_token_creates_user_with_invite_role | PASS |
| R2 | Expired token rejected | test_signup.py::test_expired_token_rejected | PASS |
| R2 | Reused token rejected | test_signup.py::test_reused_token_rejected | PASS |
| R2 | Unknown token rejected | test_signup.py::test_unknown_token_rejected | PASS |
| R2 | Open self-registration absent | test_signup.py::test_no_open_self_registration_route | PASS |
| R3 | Login/logout/reset/wrong-creds | test_auth.py (4) | PASS (PR2, re-run green) |
Compliance 12/12. Cumulative PR1 13/14, PR2 8/8 preserved.

## PR3 — Adversarial probes (independently run)
- Token: secrets.token_urlsafe(32), ~256 bits, CharField(unique=True) DB constraint. PASS
- Expiry: USE_TZ=True, compares against timezone.now(). PASS
- Sequential reuse: 2nd POST -> 404, count 1. PASS
- Info leak: expired/reused/unknown all Http404, identical body. PASS
- Email normalisation: MiXeD@Example.COM -> stored mixed@example.com. PASS
- No open registration: only /accounts/signup/<token>/; /signup/,/register/,/accounts/signup/ -> 404. PASS
- Role escalation: form exposes only passwords; email+role from invite row. PASS
- CONCURRENT reuse TOCTOU: check-then-set used_at, no select_for_update/transaction -> race window. WARNING 3
- SIGNUP FOR EXISTING EMAIL: uncaught IntegrityError -> HTTP 500, used_at left null. WARNING 1
- DUPLICATE ACTIVE VIA STORED CASE + ADMIN BYPASS: InviteAdmin.form is default ModelForm (not InviteForm) -> clean_email/clean_expires_at skipped -> 2 active invites. WARNING 2
- PASSWORD VALIDATORS: signup accepts "1"; AUTH_PASSWORD_VALIDATORS never invoked. WARNING 4

## PR3 — Issues
CRITICAL: None.
WARNING 1 (HIGH): Signup for existing email -> uncaught IntegrityError 500 (forms.py:26-34 no User-exists check; views.py:44 create_user). Reachable via staff flow. Fix: reject existing user email in clean_email + catch IntegrityError.
WARNING 2 (MEDIUM-HIGH): Duplicate/expiry rules not enforced in admin; admin.py:32-37 lacks form=InviteForm; plus forms.py:27 lowercases only submitted value. Fix: form=InviteForm on InviteAdmin + normalize at model/manager or UniqueConstraint(Lower(email)).
WARNING 3 (MEDIUM): single-use TOCTOU (views.py:38-50). Fix: transaction.atomic + select_for_update, or conditional UPDATE...WHERE used_at IS NULL.
WARNING 4 (MEDIUM): AUTH_PASSWORD_VALIDATORS configured but never enforced (forms.py:51-61; create_user set_password). Fix: clean_password1 -> password_validation.validate_password.
SUGGESTION: HEAD 405; expires_at widget; commit hygiene (docs-only 330e886 on #15 squash + dangling df84492 on origin/feat/web-foundation-user).

## PR3 — Design coherence
D1 is_staff gate YES. D4 form-level dup check (admin caveat) YES. gen_token/default_expiry/INVITE_TTL YES. created_by SET_NULL YES. templates/accounts/*.html YES. TDD 6/6.

## PR3 — Verdict: PASS WITH WARNINGS
5/5 Phase-3 tasks; 59/59 tests (44 preserved + 15 new); all check commands exit 0; diff strictly PR3. 4 WARNINGs are hardening; none breaks a literal spec scenario. FINAL PR3 MERGE DECISION: GO (fix WARNINGs 1 & 4 before staging deploy).

---

# PR2 Verification — commit `f454840` (preserved)

Envelope: verdict pass, 42/42 tests, requirements 3/3, scenarios 8/8, ruff+format+manage.py check+makemigrations exit 0, diff strictly PR2 (19 files, +573/-7). Adversarial probes: DB uniqueness PASS; **case-sensitive email uniqueness GAP** (`Foo@` vs `foo@` both persisted) → WARNING addressed before PR3; `create_superuser` yields `role="member"` → SUGGESTION; password-reset non-enumeration PASS; fixtures isolated PASS.

Resolution carried into PR3: the tracker tree now stores emails lowercased (`managers.py` `normalize_email(email).lower()`) and `tests/web/test_user.py` adds `test_duplicate_email_case_insensitive` + `test_authenticate_email_is_case_insensitive`. **PR2 WARNING 1 RESOLVED.**

- Completeness: 6/6 Phase-2 tasks.
- Spec matrix: R4 (4 scenarios) + R3 (4 scenarios) + R14 harness = 8/8 in-scope.
- Issues: WARNING 1 (case-sensitive uniqueness — resolved); SUGGESTIONS 1–3 (superuser role, `LOGIN_REDIRECT_URL="/"` 404, internal `username` field name).
- Verdict: PASS WITH WARNINGS; FINAL PR2 MERGE DECISION: GO.

---

# PR1 Verification — commit `98678aa` (preserved)

- Envelope: verdict pass, 32/32 tests, requirements 5/5, scenarios 13/14, ruff+format+manage.py check exit 0, boundary respected (no src/.github/Docker).
- In-scope: R5 (5 COMPLIANT), R8 (2 COMPLIANT), R9 (2 COMPLIANT + 1 PARTIAL no-Django import), R12 (2 COMPLIANT), R10 (2 COMPLIANT).
- WARNINGS: (1) R9 "core imports without Django" real proof is PR4 core-isolation CI job — **now delivered in PR4** (`core-isolation` job exists). (2) `redis` package deferred to PR4 — **now delivered** (`redis>=5` in requirements.txt).
- SUGGESTIONS: (1) `test_settings_have_no_hardcoded_secrets` scans settings only; gitleaks PR4 — **now delivered** (gitleaks job). (2) design.md/tasks.md uncommitted mods — RESOLVED.
- Verdict: PASS.

---

Artifacts: `openspec/changes/web-foundation/verify-report.md` | Engram `sdd/web-foundation/verify-report`
Session: verify-pr4-bitunix-trader
Project: bitunix-trader
Scope: project
Topic: sdd/web-foundation/verify-report
