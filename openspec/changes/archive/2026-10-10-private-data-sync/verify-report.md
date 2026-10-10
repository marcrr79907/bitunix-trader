```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:9765df4d93651adfb6af4ab27620933d36ca9f02ea6488996fb09cddcc944a3e
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 12/12
scenarios: 34/35
test_command: .venv/bin/python -m pytest
test_exit_code: 0
test_output_hash: sha256:461018366a5d1428e9f1637c5ec42810eb0ec4dc347da4495591b1b62bc56a02
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check . && env -u PYTHONPATH .venv/bin/python web/manage.py makemigrations --check --dry-run
build_exit_code: 0
build_output_hash: sha256:0d5065391432555c7520ea34039b2f0e632bd39513c1e2602b9512ce0075b3a2
```

# Verification Report

**Change**: private-data-sync (issue #57, Fase 6b) — 3-PR feature-branch-chain (`feat/private-sync` → `feat/private-sync-tier` `a298308` → `feat/private-sync-worker` `39d9fb7` → `feat/private-sync-guards` `a8b10d2`)
**Version**: N/A (delta specs)
**Mode**: Strict TDD (`openspec/config.yaml` `strict_tdd: true`, runner `.venv/bin/python -m pytest`)
**Scope**: branch `feat/private-sync-guards` (confirmed `git branch --show-current`), HEAD `a8b10d2`. Patch-gate diff vs tracker = 18 files (`openspec/**` + 4 code + 5 test). This is a FRESH adversarial verify; nothing below trusts the apply report.

All commands were reproduced from the working tree by this verifier. Adversarial probes ran as a throwaway script in `/tmp/opencode/probe_private_sync.py` against a real in-process Django test DB; the repo is unmodified apart from regenerated `coverage.xml`.

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 33 (Guard Matrix 12 + WU1 9 + WU2 7 + WU3 5) |
| Tasks complete | 0 marked in `tasks.md` (WARNING 3); all 3 WUs implemented per tree + apply-progress |
| Tasks incomplete | 0 (WU1/WU2/WU3 all present and passing) |

`tasks.md` has **zero** `[x]` marks (0 checked, 33 unchecked). Apply-progress `#1412` states the marks were intentionally not written because "a hard contract forbids editing `openspec/**`". Completion was judged from the tree, tests, and Engram artifact `#1412`.

## Build & Tests Execution

**Build**: ✅ Passed (exit 0)
```text
$ .venv/bin/ruff check .
All checks passed!
$ .venv/bin/ruff format --check .
99 files already formatted
$ env -u PYTHONPATH .venv/bin/python web/manage.py makemigrations --check --dry-run
No changes detected
build_exit=0
```

**Tests**: ✅ 370 passed / ❌ 0 failed / ⚠️ 5 deselected (exit 0)
```text
$ .venv/bin/python -m pytest
370 passed, 5 deselected in 53.68s
```

**Coverage**: web 97% / threshold 85% → ✅ Above; **patch gate 99% (target 100%) → ❌ below** (WARNING 1)
```text
$ .venv/bin/python -m pytest --cov --cov-report=xml    # 370 passed
$ .venv/bin/coverage report --include="web/*" --fail-under=85
TOTAL   850   24   97%
$ .venv/bin/diff-cover coverage.xml --compare-branch=feat/private-sync --fail-under=100
web/trading/models.py (100%)
web/trading/sync.py (98.3%): Missing lines 124
web/worker.py (100%)
Total:   108 lines  Missing: 1 line  Coverage: 99%
diff-cover exit = 1
```

## L1 — Independent Test Evidence

| Check | Command | Result |
|-------|---------|--------|
| Full suite | `.venv/bin/python -m pytest` | ✅ 370 passed, 5 deselected, exit 0 |
| Lint | `.venv/bin/ruff check .` | ✅ All checks passed, exit 0 |
| Format | `.venv/bin/ruff format --check .` | ✅ 99 files formatted, exit 0 |
| Migration drift | `env -u PYTHONPATH .venv/bin/python web/manage.py makemigrations --check --dry-run` | ✅ exit 0, "No changes detected" |
| Boundary + guard + credential + order scanners | `.venv/bin/python -m pytest tests/test_boundary.py tests/web/test_owned_model_guard.py tests/web/test_credentials_mechanism.py tests/web/test_no_order_surface.py` | ✅ 73 passed, exit 0 |
| Runtime deps unchanged | `git diff develop...HEAD -- requirements.txt` | ✅ empty (0 bytes) |
| Chain file list | `git diff --name-only develop...HEAD` | ✅ only `openspec/**` + `web/trading/{models,sync}.py`, `web/worker.py`, `web/trading/migrations/0004_*` + 5 test files — no `src/` |

## L2 — Coverage Gates

| Gate | Command | Result |
|------|---------|--------|
| Coverage XML | `.venv/bin/python -m pytest --cov --cov-report=xml` | ✅ exit 0, `coverage.xml` written |
| Web gate | `.venv/bin/coverage report --include="web/*" --fail-under=85` | ✅ exit 0, TOTAL 97% |
| Patch gate | `.venv/bin/diff-cover coverage.xml --compare-branch=feat/private-sync --fail-under=100` | ❌ exit 1, **108 lines, 1 missing, 99%** |

`web/trading/sync.py` line 124 (`break` when the **first** trades page is empty — `_fetch_trades` while-loop) is never exercised by the committed suite. The scenario "empty payload persists nothing" is covered via `persist_trades(user, [])`, but the empty-*first-page* fetch path is not. The declared 100% patch gate is not met.

## Spec Compliance Matrix

### private-data-sync delta (R1–R6 — 13 scenarios)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R1 | Three owned models persist with owner | `test_private_models.py::test_*_for_user_scopes_to_owner` (3) | ✅ COMPLIANT |
| R1 | Unique keys reject duplicates | `test_private_models.py::test_duplicate_{position,account,trade_id}_rejected` | ✅ COMPLIANT |
| R1 | Same trade_id allowed across users | `test_private_models.py::test_trade_id_allowed_across_users` | ✅ COMPLIANT |
| R2 | Re-sync is a no-op | `test_private_sync.py::test_persist_*_twice_is_idempotent` (3) | ✅ COMPLIANT |
| R2 | Empty payload persists nothing | `test_private_sync.py::test_empty_inputs_persist_nothing` | ✅ COMPLIANT |
| R3 | sync.py has no decrypt reference | `test_private_sync.py::test_sync_module_has_no_decrypt_reference` | ✅ COMPLIANT |
| R3 | Owned-model guard stays green | `test_owned_model_guard.py::test_request_path_has_no_unscoped_owned_query`, `::test_scanner_allows_for_user_on_the_private_models` | ✅ COMPLIANT |
| R4 | Active credentials synced per user | `test_worker_private_sync.py::test_active_credential_is_decrypted_and_persisted` | ✅ COMPLIANT |
| R4 | Inactive credentials skipped | `test_worker_private_sync.py::test_inactive_credential_is_skipped_without_fetch`, `::test_no_credentials_is_a_noop` | ✅ COMPLIANT |
| R5 | One failing user does not stop peers | `test_worker_private_sync.py::test_one_failing_user_does_not_stop_peers` | ✅ COMPLIANT |
| R5 | Global ingest survives a private failure | `test_worker_private_sync.py::test_run_once_survives_private_sync_failure` | ✅ COMPLIANT |
| R6 | No order endpoint in new code | `test_no_order_surface.py` (73-suite green) | ✅ COMPLIANT |
| R6 | No runtime dependency added | (no test; empty `git diff` — inspection) | ❌ UNTESTED |

### per-user-isolation delta (R14.2–R14.4 — 11 scenarios)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R14.2 | A cannot read B's ExchangeCredential | `test_isolation.py::test_cross_user_get_denied` | ✅ COMPLIANT |
| R14.2 | A cannot read B's Watchlist row | `test_isolation.py::test_cross_user_get_denied` | ✅ COMPLIANT |
| R14.2 | A cannot read B's PositionSnapshot | `test_isolation.py::test_cross_user_get_denied_for_private_models` | ✅ COMPLIANT |
| R14.2 | A cannot read B's AccountSnapshot | `test_isolation.py::test_cross_user_get_denied_for_private_models` | ✅ COMPLIANT |
| R14.2 | A cannot read B's Trade | `test_isolation.py::test_cross_user_get_denied_for_private_models` | ✅ COMPLIANT |
| R14.3 | Scanner flags an unscoped query | `test_owned_model_guard.py::test_scanner_flags_an_unscoped_owned_query` | ✅ COMPLIANT |
| R14.3 | Scanner flags the new models | `test_owned_model_guard.py::test_scanner_flags_the_private_models` (6 params) | ✅ COMPLIANT |
| R14.3 | Scoped query passes the guard | `test_owned_model_guard.py::test_scanner_allows_for_user_on_the_private_models` | ✅ COMPLIANT |
| R14.3 | bulk_create and count are sanctioned | `test_owned_model_guard.py::test_request_path_has_no_unscoped_owned_query` | ✅ COMPLIANT |
| R14.4 | Worker reads across users legitimately | `test_owned_model_guard.py::test_worker_zone_reads_across_users` | ✅ COMPLIANT |
| R14.4 | Worker persists private data for all users | `test_worker_private_sync.py::test_active_credential_is_decrypted_and_persisted` | ✅ COMPLIANT |

### security-invariants delta (R13, R14 — 8 scenarios)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R13 | Keys stored encrypted | `test_credentials_mechanism.py::test_encrypt_decrypt_round_trip` | ✅ COMPLIANT |
| R13 | Decryption confined to worker | `test_credentials_mechanism.py::test_request_path_never_decrypts` | ✅ COMPLIANT |
| R13 | sync.py stays decrypt-free | `test_worker_private_sync.py::test_sync_is_decrypt_free_while_worker_owns_it`, `test_private_sync.py::test_sync_module_has_no_decrypt_reference` | ✅ COMPLIANT |
| R13 | Worker decrypts an active credential | `test_worker_private_sync.py::test_active_credential_is_decrypted_and_persisted` (asserts recovered plaintext on both columns) | ✅ COMPLIANT |
| R14 | No cross-user read | `test_isolation.py::test_cross_user_get_denied_for_private_models` | ✅ COMPLIANT |
| R14 | for_user denies cross-user lookup | `test_isolation.py::test_cross_user_get_denied_for_private_models` | ✅ COMPLIANT |
| R14 | Unscoped query guard | `test_owned_model_guard.py::test_scanner_flags_unscoped_verbs`, `::test_scanner_flags_the_private_models` | ✅ COMPLIANT |
| R14 | Worker trusted zone | `test_owned_model_guard.py::test_worker_zone_reads_across_users` | ✅ COMPLIANT |

### market-ingestion delta (R4b — 3 scenarios)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R4b | Cycle still ingests beside the private step | `test_worker_private_sync.py::test_active_credential_is_decrypted_and_persisted` + `test_run_once_survives_private_sync_failure` | ✅ COMPLIANT |
| R4b | Private failure is isolated | `test_worker_private_sync.py::test_run_once_survives_private_sync_failure` | ✅ COMPLIANT |
| R4b | No active credentials is a no-op | `test_worker_private_sync.py::test_no_credentials_is_a_noop` | ✅ COMPLIANT |

**Compliance summary**: 12/12 requirements implemented; **34/35 scenarios compliant, 1 UNTESTED, 0 FAILING**. The single untested scenario is R6 "no runtime dependency added", verified only by the empty `git diff develop...HEAD -- requirements.txt` (inspection, no committed guard test) — mirrors the archived candle-pagination SUGGESTION 1.

## Independent Adversarial Probes — throwaway (`/tmp/opencode`, repo untouched)

22/23 probes passed; the one `FAIL` was a probe-harness artifact (shared in-process test DB retained earlier active credentials, so the inactive-skip branch was legitimately reached with prior creds present — the committed `test_inactive_credential_is_skipped_without_fetch` runs in a clean DB and passes).

| Probe | Question | Result |
|-------|----------|--------|
| P1 idempotency | `persist_positions`/`account` twice at same `ts` → 1 then 0 | ✅ `1,0` / `1,0` |
| P1 A≠B | same `(user,symbol,ts)` for A and B → separate rows, `for_user(A).count()==1 == B` | ✅ |
| P1 trade reuse | same `trade_id` T-1 for A and B → distinct pks | ✅ |
| P1 unparseable | `"x"`/`"??"` floats → `None`, no raise | ✅ |
| P2 isolation | A's client raises `BitunixError`, B persists → `run_private_sync == 1`, A count 0 | ✅ |
| P2 inactive | inactive cred → factory not called, synced 0 | ✅ (committed test, clean DB) |
| P3 contract | `run_once` returns `(1,1)` while private step raises | ✅ |
| P3 ingest | funding/ticker rows persist despite private failure | ✅ |
| P4 return type | `run_once` returns exactly `tuple[int,int]` | ✅ |
| P5 fail-closed | `decrypt` with `CREDENTIALS_FERNET_KEY` unset → `RuntimeError`, never plaintext | ✅ |
| P6 owner FK | position/account/trade without `user` → `IntegrityError` (no orphan rows) | ✅ |
| P7 confinement | `web/trading/*.py` has no `decrypt` call/attr/bare; `worker.py` imports AND calls | ✅ |
| P8 guard path | `REQUEST_PATH` = `config, accounts, trading, market` — excludes `worker` | ✅ |
| P8 trading+market | `trading` and `market` in `REQUEST_PATH` | ✅ |
| P9 false positive | `web/market/**` references no owned model → adding it to `REQUEST_PATH` is safe | ✅ |
| P10 unscoped read | `worker.py` really does `ExchangeCredential.objects.filter(is_active=True)` | ✅ |
| P11 empty first page | `_fetch_trades` with empty `tradeList` → `[]`; `None` data → `[]` | ✅ |
| P11 pagination | 150 trades → calls `[0, 100]`, returns 150 | ✅ |

### Holes examined
- **Decrypt fail-closed**: `credentials._fernet()` raises `RuntimeError` when the key is missing — never falls back to plaintext. ✅ (P5)
- **Private data without owner FK**: impossible — `user` is non-null CASCADE on all 3 models; `IntegrityError` otherwise. ✅ (P6)
- **`run_once` return contract**: exactly `(funding, ticker)` `tuple[int,int]`, even when the private step raises. ✅ (P3/P4)
- **`web/market` false positive**: `market/` uses no owned model, so extending the guard's `REQUEST_PATH` cannot create a false offender. ✅ (P9)
- **`bulk_create(ignore_conflicts=True)` idempotency on the unique constraints**: holds for `(user,symbol,ts)`, `(user,ts)`, `(user,trade_id)` — re-run inserts 0. ✅ (P1)

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| R1 owned models | ⚠️ Implemented w/ deviation | Three models on `UserOwnedModel`, FK CASCADE, `for_user`, correct `(user,…)` `UniqueConstraint`s. **`PositionSnapshot.leverage` is `IntegerField`, spec/design declare `Float null`** (WARNING 2). |
| R2 idempotent persist | ✅ Implemented | `bulk_create(ignore_conflicts=True)` + count delta; empty guards return 0. |
| R3 decrypt-free module | ✅ Implemented | `sync.py` imports only `trading.models`, `django`; AST clean; owned models touched only via `bulk_create`/`count`. |
| R4 worker trusted zone | ✅ Implemented | `run_private_sync` iterates `filter(is_active=True)` unscoped, `decrypt`s both columns, builds client, delegates to `sync_user`; step runs after ticks+candles inside its own `try/except`. |
| R5 per-user isolation | ✅ Implemented | Per-credential `try/except Exception → logger.warning`; one failure never aborts peers. |
| R6 read-only / no dep | ✅ Implemented | No order surface (scanner 73 green); `requirements.txt` diff empty; `src/` has no Django import. |
| R13/R14 enforcement | ✅ Implemented | `sync.py` scanner-clean; `worker.py` owns decrypt; `OWNED_MODELS` now 5; A≠B proven for all 3. |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| Decrypt seam: worker.py owns decrypt | ✅ Yes | Confirmed by AST (P7) and scan-path inspection. |
| Persist API: `bulk_create(ignore_conflicts=True)` + count delta | ✅ Yes | Matches design; verbs absent from `UNSCOPED_VERBS`. |
| Clock: explicit `ts` param on position/account persist | ✅ Yes | `sync_user` stamps once; re-sync no-op verified. |
| Cadence: every cycle, no `PRIVATE_SYNC_SECONDS` knob | ✅ Yes | No knob in code (YAGNI as designed). |
| Models: 3 owned models | ✅ Yes | Fields map to `position_row`/`trade_row`. |
| `_f` only helper | ⚠️ Extended | Added `_i` int helper (int coercion for `leverage`/`ctime`) — documented deviation in `#1412`. |
| `persist_account` normalizes dict-or-list | ✅ Yes | Design said normalize once at boundary; implemented. |

## TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | Full table in apply-progress `#1412` (WU1/WU2/WU3). |
| All tasks have tests | ✅ | All WU tasks map to committed test files. |
| RED confirmed (tests exist) | ✅ | `test_private_models.py`, `test_private_sync.py`, `test_worker_private_sync.py`, guard/isolation additions all exist. |
| GREEN confirmed (tests pass) | ✅ | 370/370 on independent execution (exit 0). |
| Triangulation adequate | ✅ | Multiple cases per behavior (12 model cases, 6 guard params, idempotent+empty+paginate, A-fails/B-syncs). |
| Safety Net for modified files | ✅ | Baselines recorded (353→359→370); full suite green. |
| Independent RED for WU3 isolation | ⚠️ | Isolation additions are pure coverage over already-shipped WU1 behavior; their RED is subsumed by the guard's parametrized RED (honestly disclosed in `#1412`). |

**TDD Compliance**: 6/7 checks fully passed; WU3 isolation RED subsumed (WARNING 4).

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | ~26 | `test_private_models.py`, `test_private_sync.py` | pytest |
| Integration (DB) | ~13 | `test_worker_private_sync.py`, `test_isolation.py` | pytest, pytest-django |
| AST scanner | ~4 | `test_owned_model_guard.py`, decrypt-confinement | pytest, `ast` |
| **New/changed total** | **43** | **5** | |
| Full suite | 370 (+5 deselected) | — | pytest, pytest-django, pytest-cov |

### Changed-File Coverage

| File | Line % | Uncovered | Rating |
|------|--------|-----------|--------|
| `web/trading/models.py` | 100% | — | ✅ Excellent |
| `web/worker.py` | 100% | — | ✅ Excellent |
| `web/trading/sync.py` | 98.3% | L124 | ⚠️ Low (1 line) — WARNING 1 |

**Average changed-file coverage**: 99.4% (108 patch lines, 1 missing).

### Assertion Quality

All tests call production code and assert concrete values (recovered plaintext, row counts, coerced floats, raised exception types, exact payload dicts, offender lists). No tautologies, no assertion-without-call, no ghost loops. Guard tests carry paired positive/negative controls (`test_scanner_flags_*` alongside `test_scanner_allows_for_user*`); the decrypt-confinement test explicitly includes a positive control on `worker.py` so the scanner is not vacuously green.

**Assertion quality**: ✅ All assertions verify real behavior.

### Quality Metrics
**Linter**: ✅ No errors (ruff exit 0)
**Type Checker**: ➖ Not configured
**Format**: ✅ 99 files formatted

## Issues Found

### WARNING 1 — Patch-coverage gate is 99%, not the required 100%.

`.venv/bin/diff-cover coverage.xml --compare-branch=feat/private-sync --fail-under=100` exits **1** on 108 lines with 1 missing: `web/trading/sync.py` line 124 (the `break` when the first trades page is empty). The committed suite paginates 150 trades (short-page break is covered) but never drives an empty *first* page through `_fetch_trades`. **Fix trigger:** add one test — `sync_user(user, StubClient(trades=[]))` (or `_fetch_trades` with a client returning `{"tradeList": []}`) — which covers the branch and lifts the gate to 100%. Coverage gaps are non-blocking per Strict-TDD verify rules, but this gate was an explicit acceptance criterion.

### WARNING 2 — `PositionSnapshot.leverage` deviates from the spec/design field type.

Spec R1 states position fields `qty`/`avg_open`/`leverage`/`liq_price`/`upnl`/`margin_rate` are **`Float null`**; design repeats this. The model (and migration `0004`) use `models.IntegerField(null=True)` for `leverage`, with a new `_i` int-coercion helper. Functionally sound (leverage is integral), and no scenario asserts the Python type. **Fix trigger:** either amend spec R1 to `IntegerField` for `leverage`, or switch the field to `FloatField` — reconcile text and code before archive.

### WARNING 3 — `tasks.md` is 0/33 checked; completion is not readable from the artifact.

Same gap the archived candle-pagination change carried (its WARNING 1). Apply-progress `#1412` deliberately did not write `[x]` because a hard contract forbids editing `openspec/**`. The work is present and verified, but archive-time traceability cannot read completion from `tasks.md`. **Fix trigger:** let `sdd-apply` mark `[x]`, or add an explicit "completion lives in `#1412`" note to `tasks.md`.

### WARNING 4 — WU3 isolation tests have no independent RED.

`test_isolation.py`'s three new tests assert already-shipped WU1 behavior; their RED is subsumed by the guard test's RED. This is disclosed honestly in `#1412` and is a pipeline-evidence nuance, not a code defect.

### SUGGESTION 1 — R6 "runtime dependencies unchanged" has no covering test.

Verified only by an empty `git diff develop...HEAD -- requirements.txt`. **Fix trigger:** add a guard test asserting no new runtime import in `web/`/`src/` outside the declared set.

## Verdict

**PASS WITH WARNINGS**

All executable gates are green and independently reproduced on `a8b10d2`: **370 tests pass** (exit 0), `ruff check`/`ruff format --check` exit 0, `makemigrations --check --dry-run` reports no changes, the boundary + guard + credential + order suites are green (73 passed), `requirements.txt` is byte-identical to develop, and web coverage is 97% (≥85). 22 of 23 adversarial probes pass — agent-side idempotency, A≠B scoping for all three models, cross-user `trade_id` reuse, per-user error isolation, the `(funding, ticker)` return contract held under a raising private step, decrypt fail-closed on a missing key, the owner-FK invariant, decrypt confinement, the guard's path exclusion of `worker.py`, and a clean `web/market` scan. The change is not blocked.

It carries four warnings. The material one is **WARNING 1**: the declared 100% patch gate is **99%** — `web/trading/sync.py` line 124 (empty-first-page break) is uncovered. WARNING 2 is a spec/design field-type mismatch (`leverage` int vs declared float). WARNINGS 3–4 are traceability/evidence nuances (`tasks.md` unmarked; WU3 RED subsumed). None is a functional defect.

## Traceability

| Artifact | Reference |
|----------|-----------|
| Proposal | `openspec/changes/private-data-sync/proposal.md` |
| Design | `openspec/changes/private-data-sync/design.md` |
| Tasks | `openspec/changes/private-data-sync/tasks.md` (0/33 marked — WARNING 3) |
| Delta specs | `openspec/changes/private-data-sync/specs/{private-data-sync,per-user-isolation,security-invariants,market-ingestion}/spec.md` (35 scenarios) |
| Code | `web/trading/models.py`, `web/trading/sync.py`, `web/worker.py`, `web/trading/migrations/0004_private_snapshots.py`, `web/credentials.py` |
| Tests | `tests/web/test_private_models.py`, `tests/web/test_private_sync.py`, `tests/web/test_worker_private_sync.py`, `tests/web/test_owned_model_guard.py`, `tests/web/test_isolation.py` |
| Apply evidence | Engram `#1412` (`sdd/private-data-sync/apply-progress`) |
| Probes | `/tmp/opencode/probe_private_sync.py` (repo untouched) |
| Commits | `a298308` (WU1), `39d9fb7` (WU2), `a8b10d2` (WU3) |
| Chain diff | `feat/private-sync...feat/private-sync-guards`, 18 files (9 openspec + 4 code + 5 test) |
