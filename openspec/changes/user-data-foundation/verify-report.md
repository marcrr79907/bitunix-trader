```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:14e86ce7fb4e61fc166758cce007a86de281f2eae128535cfade3abccb917e90
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 14/14
scenarios: 31/32
test_command: .venv/bin/python -m pytest
test_exit_code: 0
test_output_hash: sha256:226373dee6a1f21e0f97395829845fcc2de7d47a652d8c3f7cfc1d474eec60d0
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python web/manage.py makemigrations --check --dry-run
build_exit_code: 0
build_output_hash: sha256:3ac812c575dae4d2c62758ae7fd36422e9445bbf5a0a242a27b762a24c30f396
```

# Verification Report

**Change**: user-data-foundation (Phase 2) — **re-verification**
**Version**: N/A (delta specs)
**Mode**: Strict TDD (openspec `config.yaml` `strict_tdd: true`, runner `.venv/bin/python -m pytest`)
**Scope**: chain tip `feat/user-data-scanners` (HEAD `d14b550`); tracker `feat/user-data-foundation` (`e96a1c7`); chain diff = tracker…HEAD, 10 files, +568/−9. PR1 `5710fd1`, PR2 `c6b38ca`, PR3 `d847f5d`, **WU4 (verify-fix) `d14b550`**.

This is an independent re-verification executed from scratch against the working tree; the fix report (apply-progress Engram `#1329`) was cross-checked, not trusted. **The prior CRITICAL 1 (R14.3 scanner missing) is now closed**: the scanner exists, flags the offenders, passes on the real tree, and an adversarial probe confirms both required scenarios. **WARNING 2 (R14.4 untested) is closed.** The only open spec item is the pre-existing R11 "read-only credential enforced" scenario, which remains untestable from code (operational provisioning control).

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total (Guard Matrix + WU1–WU4 + Phase 4) | 43 |
| Tasks complete | 40 |
| Tasks incomplete | 3 (Phase 4: 4.1–4.3 = this verification) |

WU1 (1.1–1.7), WU2 (2.1–2.6), WU3 (3.1–3.7), **WU4 (4f.1–4f.5)** and the 15 Guard-Matrix rows are all present in the tree and verified here. `tasks.md` checkboxes remain `[ ]` (WARNING 1).

## Build & Tests Execution

**Build**: ✅ Passed (exit 0)
```text
$ .venv/bin/ruff check .
All checks passed!
$ .venv/bin/ruff format --check .
67 files already formatted
$ .venv/bin/python web/manage.py makemigrations --check --dry-run
No changes detected
```

**Tests**: ✅ 191 passed / ❌ 0 failed / ⚠️ 0 skipped (exit 0)
```text
$ .venv/bin/python -m pytest
........................................................................ [ 37%]
........................................................................ [ 75%]
...............................................                          [100%]
191 passed in 51.95s
```
Since the prior verify (179), **12 tests were added** by `d14b550` — all in `tests/web/test_owned_model_guard.py`. New/changed suites: `test_isolation.py` 5, `test_credentials_mechanism.py` 9, `test_no_order_surface.py` 7, **`test_owned_model_guard.py` 7**. `tests/test_boundary.py` 4.

**Coverage**: 93% / threshold 85% → ✅ Above
```text
$ .venv/bin/coverage report --include="web/*" --fail-under=85
TOTAL                               348     24    93%
```
`web/trading/models.py` 100% (30/30), `web/credentials.py` 100%, `web/trading/apps.py` 100%.

## L1 — Independent Test Evidence

| Check | Command | Result |
|-------|---------|--------|
| Full suite | `.venv/bin/python -m pytest` | ✅ 191 passed, exit 0 |
| Guard suite | `.venv/bin/python -m pytest tests/web/test_owned_model_guard.py -v` | ✅ 12 passed, exit 0 |
| Lint | `.venv/bin/ruff check .` | ✅ All checks passed, exit 0 |
| Format | `.venv/bin/ruff format --check .` | ✅ 67 files formatted, exit 0 |
| Migrations | `.venv/bin/python web/manage.py makemigrations --check --dry-run` | ✅ No changes detected, exit 0 |
| Boundary | `.venv/bin/python -m pytest tests/test_boundary.py` | ✅ 4 passed, exit 0 |

Migration↔model parity: `web/trading/migrations/0001_initial.py` declares exactly the fields in `models.py`; `makemigrations --check` confirms zero drift.

## L2 — Coverage Gates

| Gate | Command | Result |
|------|---------|--------|
| Coverage XML | `.venv/bin/python -m pytest --cov --cov-report=xml` | ✅ exit 0, `coverage.xml` written |
| Web gate (R4) | `.venv/bin/coverage report --include="web/*" --fail-under=85` | ✅ exit 0, TOTAL 93% |
| Patch gate (tracker) | `.venv/bin/diff-cover coverage.xml --compare-branch=feat/user-data-foundation --fail-under=100` | ✅ exit 0, 36 lines, 0 missing, 100% |

## Spec Compliance Matrix

### user-credentials (R13.1–R13.4, 7 scenarios)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R13.1 | Persisted value is ciphertext | `test_set_secrets_stores_ciphertext_at_rest`; raw-column probe | ✅ COMPLIANT |
| R13.1 | Round-trip restores the secret | same test + `test_encrypt_decrypt_round_trip` (`credentials.decrypt(raw)` == plaintext) | ✅ COMPLIANT |
| R13.2 | Boundary encrypts before save | `test_set_secrets_stores_ciphertext_at_rest` | ✅ COMPLIANT |
| R13.2 | Request path does not decrypt | `test_request_path_never_decrypts` (+ trading in `REQUEST_PATH`) | ✅ COMPLIANT |
| R13.3 | Empty secret rejected | `test_set_secrets_rejects_blank_inputs` (4 cases) | ✅ COMPLIANT |
| R13.3 | No plaintext accessor | `test_no_plaintext_accessor_exposed` | ✅ COMPLIANT |
| R13.4 | Worker decrypts a stored credential | `test_set_secrets_stores_ciphertext_at_rest` decrypts the raw column | ✅ COMPLIANT (mechanism-level; no worker code exists yet) |

### per-user-isolation (R14.1–R14.4, 7 scenarios)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R14.1 | for_user returns only the owner's rows | `test_for_user_returns_only_the_owner_rows` | ✅ COMPLIANT |
| R14.1 | Empty owner is not an error | `test_for_user_empty_owner_is_not_an_error` | ✅ COMPLIANT |
| R14.2 | A cannot read B's ExchangeCredential | `test_cross_user_get_denied` | ✅ COMPLIANT |
| R14.2 | A cannot read B's Watchlist row | `test_cross_user_get_denied` | ✅ COMPLIANT |
| R14.3 | Scanner flags an unscoped query | `test_owned_model_guard.py::test_scanner_flags_an_unscoped_owned_query` (+ 7 verb cases, + adversarial probe) | ✅ COMPLIANT **(was UNTESTED)** |
| R14.3 | Scoped query passes the guard | `test_scanner_allows_for_user` (+ `test_request_path_has_no_unscoped_owned_query`) | ✅ COMPLIANT **(was UNTESTED)** |
| R14.4 | Worker reads across users legitimately | `test_worker_zone_reads_across_users` | ✅ COMPLIANT **(was UNTESTED)** |

### market-watchlist (R14.5–R14.7, 5 scenarios)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R14.5 | A user owns their own symbols | `test_for_user_returns_only_the_owner_rows` | ✅ COMPLIANT |
| R14.5 | Cross-user read denied | `test_cross_user_get_denied` | ✅ COMPLIANT |
| R14.6 | Duplicate (user, symbol) raises IntegrityError | `test_duplicate_user_symbol_rejected` | ✅ COMPLIANT |
| R14.6 | Same symbol allowed across users | `test_same_symbol_allowed_across_users` | ✅ COMPLIANT |
| R14.7 | List only the owner's symbols | `test_for_user_returns_only_the_owner_rows` | ✅ COMPLIANT |

### security-invariants (delta: R11, R13, R14, 13 scenarios)

| Requirement | Scenario | Test / Evidence | Result |
|-------------|----------|-----------------|--------|
| R11 | No order execution surface | `test_no_order_surface_in_web_and_src` (real tree: 0 offenders) | ✅ COMPLIANT |
| R11 | Read-only credential enforced | (no test — operational property, pre-existing) | ❌ UNTESTED |
| R11 | Extended mutating verbs caught | `test_scanner_flags_extended_verbs` (12 verbs) | ✅ COMPLIANT |
| R11 | getattr-hidden verb caught | `test_scanner_flags_a_getattr_hidden_verb` | ✅ COMPLIANT |
| R11 | Forbidden endpoint path caught | `test_scanner_flags_forbidden_endpoint_paths` (16 paths) | ✅ COMPLIANT |
| R11 | Read endpoints do not match | `test_scanner_ignores_read_only_endpoints` (4 literals) | ✅ COMPLIANT |
| R13 | Keys stored encrypted | `test_set_secrets_stores_ciphertext_at_rest` | ✅ COMPLIANT |
| R13 | Decryption confined to worker | `test_request_path_never_decrypts` | ✅ COMPLIANT |
| R13 | New app is scanned for decrypt | `test_scanner_covers_the_trading_app` + `test_scanner_flags_a_decrypt_call` | ✅ COMPLIANT |
| R14 | No cross-user read | `test_cross_user_get_denied` | ✅ COMPLIANT |
| R14 | for_user denies cross-user lookup | `test_cross_user_get_denied` | ✅ COMPLIANT |
| R14 | Unscoped query guard | `test_scanner_flags_an_unscoped_owned_query` + `test_request_path_has_no_unscoped_owned_query` | ✅ COMPLIANT **(was UNTESTED)** |
| R14 | Worker trusted zone | `test_worker_zone_reads_across_users` | ✅ COMPLIANT **(was UNTESTED)** |

**Compliance summary**: 14 requirements, **14 complete**. 32 scenarios, **31 compliant / 1 untested** (R11 "Read-only credential enforced" — pre-existing, no regression).

## Independent Adversarial Probes (executed)

All probes ran outside the repo (`/tmp`), against the real tree.

| Probe | Method | Result |
|-------|--------|--------|
| Ciphertext-at-rest | RAW `SELECT` of `api_key_encrypted` after `set_secrets` | ✅ raw ≠ plaintext; `credentials.decrypt(raw)` == plaintext |
| Blank/None guard | `set_secrets("   " / "" / None, ...)` | ✅ all raise `ValueError`, no row persisted |
| Plaintext accessor | `hasattr(row,"api_key"/"api_secret")`; public `dir()` scan | ✅ none |
| Cross-user read (both models) | `for_user(B).get(pk=A_row)` | ✅ `DoesNotExist` |
| **R14.3 scanner — synthetic (a)(b)(c)** | `/tmp` tree: `ExchangeCredential.objects.get`, `Watchlist.objects.filter`, `Watchlist.for_user` | ✅ (a)+(b) flagged, (c) NOT, exactly 2 offenders |
| **R14.3 scanner — real tree** | scan `web/` + `src/` | ✅ 0 offenders (`web/config`, `web/accounts`, `web/trading` all clean) |
| **R14.3 scanner — self/pycache** | synthetic `__pycache__` + scanner file | ✅ skipped |
| **R14.3 scanner — verb coverage** | `.all/.get/.filter/.exclude/.first/.last/.create/.get_or_create` | ✅ all 8 flagged (test parametrization) |
| **R14.3 scanner — bypass (getattr manager)** | `getattr(ExchangeCredential.objects, "get")(pk=1)` | ⚠️ NOT flagged — see SUGGESTION 1 |
| **R14.3 scanner — bypass (manager alias)** | `q = ExchangeCredential.objects; q.get(pk=1)` | ⚠️ NOT flagged — see SUGGESTION 1 |
| **R14.3 scanner — bypass (import alias)** | `from trading.models import ExchangeCredential as EC; EC.objects.get(pk=1)` | ⚠️ NOT flagged — see SUGGESTION 1 |
| **R14.3 scanner — bypass (qualified/attr chain)** | `trading.models.ExchangeCredential.objects.get(pk=1)` | ⚠️ NOT flagged — see SUGGESTION 1 |
| Order scanner — synthetic | mutating verbs + getattr + paths vs read literals | ✅ mutating flagged, reads NOT |
| Order scanner — real tree | scan `web/` + `src/` | ✅ 0 false positives |
| Credential scanner — trading scope | `REQUEST_PATH` + fixture `decrypt` | ✅ offenders found; real request path clean |

## TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | `apply-progress` (`#1329`) has a full RED→GREEN table incl. WU4 4f.1–4f.5. |
| All tasks have tests | ✅ | Every WU and Guard-Matrix row now carries a covering test, incl. R14.3 + R14.4. |
| RED confirmed (tests exist) | ✅ | `test_owned_model_guard.py` exists; 7 test functions (12 cases after parametrize). |
| GREEN confirmed (tests pass) | ✅ | 191/191 pass on independent execution. |
| Triangulation adequate | ✅ | 6 verb cases, 2 owned models, for_user negative, pycache, real-tree, worker-zone. |
| Safety Net for modified files | ✅ | Baseline documented 133→138→145→179→191; existing suites green. |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit (AST scanner + Django ORM) | 61 | 4 | pytest, pytest-django, `ast` |
| Integration / boundary | 4 | 1 | pytest, `ast` |
| **New/changed total** | **65** | **5** | |
| Full suite | 191 | 15 | pytest, pytest-django, pytest-cov |

### Changed-File Coverage

| File | Line % | Uncovered Lines | Rating |
|------|--------|-----------------|--------|
| `web/trading/models.py` | 100% | — | ✅ Excellent |
| `web/trading/apps.py` | 100% | — | ✅ Excellent |
| `web/config/settings/base.py` | 93% | (pre-existing) | ✅ Excellent |
| `web/trading/migrations/0001_initial.py` | omitted | — | ✅ (migrations) |
| `tests/web/test_owned_model_guard.py` | n/a | — | ✅ (test file) |

### Assertion Quality

Scanned `test_owned_model_guard.py` in full (Step 5f). No tautologies, no assertion without a production/scanner call, no ghost loops (the only loop is over `REQUEST_PATH` roots and asserts a concrete empty list), no mocks. The new suite is well-triangulated: positive controls assert a **specific offender path** for each verb/model, and the negative controls (`for_user`, real tree, pycache) assert `== []` each with a paired positive. `test_worker_zone_reads_across_users` asserts set equality against both created rows (`readable == {mine, theirs}`) — a real value assertion, not a smoke test.

**Assertion quality**: ✅ All assertions verify real behavior.

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| R13.1 ciphertext-at-rest | ✅ Implemented | `TextField` columns only; raw column verified non-plaintext, valid Fernet. |
| R13.2 encrypt-at-boundary | ✅ Implemented | `set_secrets` calls `credentials.encrypt`; credential scanner covers `web/config`, `web/accounts`, `web/trading`. |
| R13.3 input guard / no accessor | ✅ Implemented | `not value or not value.strip()` → `ValueError`; no `decrypt_*`, no `api_key`/`api_secret`. |
| R13.4 worker-zone decryption | ✅ Implemented | Model stays key-unaware; worker calls `credentials.decrypt` on `*_encrypted`. |
| R14.1 ownership contract | ✅ Implemented | `UserOwnedModel.for_user` filters by owner. |
| R14.2 cross-user denial | ✅ Implemented | `for_user(other)` scopes out the row → `DoesNotExist`. |
| R14.3 unscoped-query guard | ✅ **Implemented (was missing)** | `tests/web/test_owned_model_guard.py` AST scanner flags `<OwnedModel>.objects.<verb>()` in request paths; real tree clean. |
| R14.4 worker trusted zone | ✅ Implemented + tested | `test_worker_zone_reads_across_users` proves cross-user read is permitted. |
| R14.5–R14.7 watchlist | ✅ Implemented | FK `related_name="watchlist"`, `UniqueConstraint(user, symbol)`, `for_user`. |
| R11/R12/R13 scanner hardening | ✅ Implemented | Order scanner extended to 23 verbs + getattr + 16 paths over `web/`+`src/`. |
| No new runtime dependency | ✅ Verified | `d14b550` adds only a test file; chain diff touches no `requirements*.txt`. |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| D1 app = `trading` | ✅ Yes | `INSTALLED_APPS += "trading"`; `REQUEST_PATH` includes it. |
| D2 `for_user` + scanner guard | ✅ **Yes** | `for_user` implemented; the promised unscoped-query scanner now exists and is proven (CRITICAL closed). |
| D3 `Watchlist` kept | ✅ Yes | Second owned model present and proven. |
| D4 model-level proof only | ✅ Yes | No admin/UI exposed. |
| Order scanner (verbs/getattr/paths, `web/`+`src/`) | ✅ Yes | Matches design.md:76-91. |
| Credential scanner `REQUEST_PATH` | ✅ Yes | `(config, accounts, trading)`. |
| Worker trusted-zone exemption | ✅ Yes | design.md:113-118; now proven by `test_worker_zone_reads_across_users`. |
| `src/`/`accounts` untouched | ✅ Yes | Chain diff excludes them; boundary green. |

## Issues Found

**CRITICAL**: None — prior CRITICAL 1 (R14.3 scanner missing) is **closed and independently reproduced**.

**WARNING 1 (LOW) — `tasks.md` checkboxes are all `[ ]` despite completed work.**
`openspec/changes/user-data-foundation/tasks.md` shows `[ ]` for every Guard-Matrix row and WU1–WU4 task, though all are present and verified. The apply phase intentionally left the tracker-branch artifact untouched to avoid a merge conflict on child branches. **Fix:** flip `[x]` for WU1 1.1–1.7, WU2 2.1–2.6, WU3 3.1–3.7, **WU4 4f.1–4f.5**, and the completed Guard-Matrix rows. *(Promoted to a SUGGESTION in the re-check below — planning-artifact hygiene on the tracker branch.)*

**WARNING 2 (LOW) — R11 "Read-only credential enforced" has no covering test.**
Pre-existing (present in `openspec/specs/security-invariants/spec.md`, re-listed in the delta). This is an operational property of the provisioned API key, not introspectable from code; no test or config assertion checks it. Not a regression introduced by this change. **Fix trigger:** document it as an out-of-band provisioning control, or add a config check if the key scope ever becomes representable.

**SUGGESTION 1 — R14.3 scanner matches only a direct `<Name>.objects.<verb>()` call; four bypass shapes evade it.**
The scanner's `_is_unscoped_owned_call` requires `model` to be a bare `ast.Name` in `OWNED_MODELS`. Independently probed and confirmed unhandled: (a) `getattr(ExchangeCredential.objects, "get")(pk=1)`, (b) manager alias `q = ExchangeCredential.objects; q.get(pk=1)`, (c) import alias `ExchangeCredential as EC; EC.objects.get(...)`, (d) qualified/attribute chain `trading.models.ExchangeCredential.objects.get(...)`. This is the **same class of documented static-analysis limitation** as the order scanner's SUGGESTION 2 (`getattr` with a non-constant verb) and the credential scanner — Django offers no row-level security, so any static scanner is a guardrail, not a proof. No current offender exists. **Optional hardening:** also resolve simple `Name → Attribute` bindings via a light scope pass, or accept it as a documented ceiling. **Not a blocker.**

**SUGGESTION 2 — order scanner `getattr` detection only matches a constant verb.** (unchanged from prior verify)
`getattr(client, "place_" + "order")` or `getattr(client, var)` evades the order scanner. Known limitation of static detection — no change required.

**SUGGESTION 3 — order scanner flags any `ast.Attribute`/`ast.Name` with a verb id, including a variable named `place_order`.** (unchanged from prior verify)
No false positives in the current tree; acceptable given the fail-safe direction.

**SUGGESTION 4 — `for_user(unsaved_user)` raises `ValueError`, not an empty queryset.** (unchanged from prior verify)
`for_user(user)` with an unsaved instance raises `ValueError`; with a saved-other user it returns `[]`, with `None` it returns `[]`. The spec's "empty owner is not an error" scenario covers only a *persisted* empty owner, so this is compliant, but a future caller passing an unsaved user gets an exception rather than an empty queryset. Optional: short-circuit `if user is None or getattr(user, "pk", None) is None: return cls.objects.none()`.

## Re-check of Prior Findings

| Prior finding | Status after `d14b550` | Evidence |
|---------------|------------------------|----------|
| CRITICAL 1 — R14.3 scanner missing | ✅ **CLOSED** | `test_owned_model_guard.py` 12 cases pass; probe (a)/(b)/(c) correct; real tree 0 offenders. |
| WARNING 1 — tasks.md checkboxes stale | ⚠️ **Still stale** → demoted to SUGGESTION | All `[ ]` still; planning artifact on tracker branch, not a blocker. |
| WARNING 2 — R14.4 worker read untested | ✅ **CLOSED** | `test_worker_zone_reads_across_users` asserts both users' credentials readable. |
| WARNING 3 — R11 read-only untested (pre-existing) | ⚠️ **Still open, pre-existing** | No test/config assertion; not introspectable from code. Remains a WARNING (not introduced by this change). |

## Verdict

**PASS WITH WARNINGS**

Reproduced independently from scratch: **191/191 tests pass** (exit 0; +12 vs the prior 179), `ruff check`/`ruff format --check` exit 0 (67 files), `makemigrations --check` clean, boundary green, web gate 93% (≥85), patch gate 100% (0 missing). **The prior CRITICAL is genuinely closed**: the R14.3 unscoped-query scanner exists, is exercised by 12 passing cases, flags `ExchangeCredential.objects.get` and `Watchlist.objects.filter` while clearing `for_user`, and yields **zero offenders on the real `web/`+`src/` tree** under an adversarial probe run from `/tmp`. **WARNING 2 is closed** by `test_worker_zone_reads_across_users`. All 14 requirements now have implementation + passing covering tests (31/32 scenarios compliant). The single open scenario is the pre-existing R11 "read-only credential enforced", an operational provisioning property with no code-level representation; it is not a regression. Remaining items are hygiene and documented scanner ceilings (SUGGESTION 1 four bypass shapes, SUGGESTIONs 2–4 unchanged). **Archive decision: READY** — R14.3/R14.4 no longer block; the only non-blocking follow-up is the R11 read-only control plus `tasks.md` checkbox cleanup on the tracker branch.

## Traceability

| Artifact | Reference |
|----------|-----------|
| Proposal | `openspec/changes/user-data-foundation/proposal.md` |
| Design | `openspec/changes/user-data-foundation/design.md` (D2, Scanner Hardening) |
| Tasks | `openspec/changes/user-data-foundation/tasks.md` |
| Delta specs | `specs/{user-credentials,per-user-isolation,market-watchlist,security-invariants}/spec.md` |
| Code | `web/trading/models.py`, `web/trading/migrations/0001_initial.py`, `web/config/settings/base.py` |
| Tests | `tests/web/test_isolation.py`, `tests/web/test_credentials_mechanism.py`, `tests/web/test_no_order_surface.py`, **`tests/web/test_owned_model_guard.py`** |
| Apply evidence | Engram `#1329` (`sdd/user-data-foundation/apply-progress`) |
| Commits | `5710fd1` (PR1), `c6b38ca` (PR2), `d847f5d` (PR3), **`d14b550` (WU4 verify-fix)** |
| Chain diff | `feat/user-data-foundation...feat/user-data-scanners`, 10 files, +568/−9, sha256 `14e86ce7…` |
