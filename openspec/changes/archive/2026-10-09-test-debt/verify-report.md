```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:1c7b89a104d255237b5a31fa50549157ade2d067b41f939fac18bb81de1ad2c8
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 3/3
scenarios: 13/13
test_command: .venv/bin/python -m pytest
test_exit_code: 0
test_output_hash: sha256:4aef21ea735bfc016a3f3d3fa8c1cb555bd10e07c286a1f542ab78ede56d14a6
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check .
build_exit_code: 0
build_output_hash: sha256:bc09ca05fe3036c0d56bbb327f2b382d585258eafdd63d878f82a92869335ea5
```

# Verification Report

**Change**: test-debt (issue #46) — single PR, base `develop`
**Version**: N/A (delta specs)
**Mode**: Strict TDD (`openspec/config.yaml` `strict_tdd: true`, runner `.venv/bin/python -m pytest`)
**Scope**: branch `feat/test-debt` (confirmed `git branch --show-current`), HEAD `2e22dee`; chain diff vs `develop` = 8 files, +708/−0. Commits: `5360d19` (guard), `5349dc8` (E2E), `2e22dee` (doc). All evidence below was reproduced by this verifier from the working tree; apply reports were not trusted.

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total (`tasks.md`: Guard Matrix 8 + WU1 7 + WU2 6 + WU3 2 + Phase 4 2) | 25 |
| Tasks complete (verified in tree) | 25 |
| Tasks incomplete | 0 |

`tasks.md` checkboxes are all still `[ ]` — the apply phase did not mark them (its own note: the orchestrator hard contract "Do NOT edit openspec/** planning artifacts" overrode the skill's marking step). Every task is nonetheless present and verified: WU1 guard (5 tests), WU2 E2E (2 tests), WU3 comment. Treated as a documentation-hygiene WARNING, not an incompleteness.

## Build & Tests Execution

**Build**: ✅ Passed (exit 0)
```text
$ .venv/bin/ruff check .
All checks passed!
$ .venv/bin/ruff format --check .
92 files already formatted
build_exit=0
```

**Tests**: ✅ 315 passed / ❌ 0 failed / ⚠️ 5 deselected (exit 0)
```text
$ .venv/bin/python -m pytest
315 passed, 5 deselected in 86.44s
```

**E2E** (dev-only, real chromium): ✅ 5 passed, 315 deselected (exit 0). The chromium bundle IS available, so the E2E actually ran, including the two new scenarios.
```text
$ .venv/bin/python -m pytest -m e2e
5 passed, 315 deselected in 23.03s
```

**Coverage**: web 97% / threshold 85% → ✅ Above; patch gate exits 0 — but see the vacuous-gate WARNING below.
```text
$ .venv/bin/python -m pytest --cov --cov-report=xml     # exit 0
$ .venv/bin/coverage report --include="web/*" --fail-under=85
TOTAL   710     24    97%                                # exit 0
$ .venv/bin/diff-cover coverage.xml --compare-branch=origin/develop --fail-under=100
No lines with coverage information in this diff.         # exit 0 (vacuous)
```

## L1 — Independent Test Evidence

| Check | Command | Result |
|-------|---------|--------|
| Full suite | `.venv/bin/python -m pytest` | ✅ 315 passed, 5 deselected, exit 0 |
| E2E (real browser) | `.venv/bin/python -m pytest -m e2e` | ✅ 5 passed (chromium present), exit 0 |
| Lint | `.venv/bin/ruff check .` | ✅ All checks passed, exit 0 |
| Format | `.venv/bin/ruff format --check .` | ✅ 92 files formatted, exit 0 |
| Boundary | `.venv/bin/python -m pytest tests/test_boundary.py` | ✅ 4 passed, exit 0 |
| Guard suite | `.venv/bin/python -m pytest tests/test_dependency_guard.py` | ✅ 5 passed, exit 0 |
| Order scanner | `.venv/bin/python -m pytest tests/web/test_no_order_surface.py` | ✅ 36 passed, exit 0 |
| manage boot | `.venv/bin/python -m pytest tests/web/test_manage_boot.py` | ✅ 1 passed, exit 0 |
| No production change | `git diff develop...HEAD -- web src` | ✅ EMPTY (0 lines) |
| Runtime deps unchanged | `git diff develop...HEAD -- requirements.txt` | ✅ EMPTY (0 lines) |

## L2 — Coverage Gates

| Gate | Command | Result |
|------|---------|--------|
| Coverage XML | `pytest --cov --cov-report=xml` | ✅ exit 0, `coverage.xml` written |
| Web gate | `coverage report --include="web/*" --fail-under=85` | ✅ exit 0, TOTAL 97% |
| Patch gate | `diff-cover coverage.xml --compare-branch=origin/develop --fail-under=100` | ⚠️ exit 0, "No lines with coverage information in this diff" |

The patch gate exits 0, satisfying the success criterion, but it measures **nothing**: coverage `source = ["web", "src"]` and every new/changed Python line lives in `tests/`, which is not instrumented. So the "patch coverage 100%" criterion is satisfied only because there are no measurable changed lines, not because new lines were covered. Acceptable for a test/doc-only change (there is no production line to protect), but the gate is not evidence about the new tests. See WARNING 1.

## L3 — Spec Conformance

### Adversarial probes (throwaway copy under `/tmp/opencode`, repo untouched — confirmed `git status` clean after)

| Probe | Question | Result |
|-------|----------|--------|
| `import pandas` injected into real `web/market/quotes.py`, then `pytest tests/test_dependency_guard.py::test_guard_passes_real_tree` | Does the guard FAIL on the real tree? | ✅ FAILED (exit 1); restored, 5 passed again |
| `import os` + `from . import models` + `from .views import x` injected | Not flagged? | ✅ `_offenders == []` |
| Local-root derivation | Does it include flat `web/*.py` stems (`credentials`,`manage`,`scheduler`,`worker`)? | ✅ all present |
| `cryptography` in allowlist | Declared set covered? | ✅ `True` |
| Remove/simulate unmapped dist (`arrow>=1.0` appended) | Does `test_requirements_sync` fail? | ✅ FAILED: `declared dist without import-root mapping: ['arrow']` |
| Missing `requirements.txt` | Silent pass by erroring early? | ✅ raises `FileNotFoundError` — fails loudly, cannot silently pass |
| Scan discovery | Could the guard pass vacuously on 0 files? | ⚠️ Yes — 52 files scanned today, but there is no `assert scanned > 0` (SUGGESTION 2) |
| E2E installs route before `goto`? | Both new tests | ✅ line 171/208 before `goto` line 172/209 |
| E2E parses JSON? | Yes | ✅ `json.loads` (ordering) / `route.send(json.dumps(...))` (bucketing) |
| Ordering assertion a bounded poll? | No — boot uses `_poll`; the tail-pair assert is immediate after the REST-redraw `wait_for_function` | ⚠️ still stable (6/6 runs); see SUGGESTION 1 |
| Can ordering test pass with no frames? | No | ✅ `booted` assert fails first; `ops[-2:]` would be `[]` |
| E2E flake check | 6× ordering + 4× bucketing | ✅ all passed (4.4–5.1s each) |

### Spec Compliance Matrix — market-chart delta (R5 modified, R7 modified, R9 added)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R5 | Forming candle updates in place | `test_market_e2e.py::test_ws_same_bucket_updates_in_place` (e2e) | ✅ COMPLIANT |
| R5 | Switch unsubscribes before subscribing | `test_market_e2e.py::test_ws_switch_unsubscribes_before_subscribing` (e2e) | ✅ COMPLIANT |
| R5 | Reconnect after drop with capped delay | `chart.js:65-68,265-268` inspection (spec-accepted method) | ✅ COMPLIANT (inspection) |
| R5 | E2E DOM smoke | `test_market_e2e.py::test_chart_page_wires_up` (e2e) | ✅ COMPLIANT |
| R7 | No schema change or migration | `git diff develop...HEAD -- web src` empty; no migration files added | ✅ COMPLIANT (inspection) |
| R7 | Auth, CSRF, CSP, WS unchanged | `test_market_ux.py` (CSP present/absent) + diff empty | ✅ COMPLIANT |
| R7 | Core boundary stays green | `tests/test_boundary.py` (4 passed) | ✅ COMPLIANT |
| R7 | Order scanner clean | `tests/web/test_no_order_surface.py` (36 passed) | ✅ COMPLIANT |
| R7 | Guard passes on the current tree | `test_dependency_guard.py::test_guard_passes_real_tree` | ✅ COMPLIANT |
| R7 | Guard fails on unknown import (negative control) | `test_guard_flags_unknown_import`, `::test_guard_reports_each_unknown_root` | ✅ COMPLIANT |
| R7 | Requirements sync enforced | `test_dependency_guard.py::test_requirements_sync` | ✅ COMPLIANT |
| R9 | Documented omission | `pyproject.toml:30-33` comment names `tests/web/test_manage_boot.py` | ✅ COMPLIANT (static) |
| R9 | Boot behavior locked | `tests/web/test_manage_boot.py` (1 passed) | ✅ COMPLIANT |

**Compliance summary**: **3/3 requirements; 13/13 scenarios compliant**. The reconnect scenario's verification method is inspection by its own delta wording (the `window.marketChart` seam was deliberately not extended to avoid a production `chart.js` edit), so it is compliant with the spec as written — but it carries no runtime test (noted as WARNING 2).

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| R5 live candles over browser WS | ✅ Reinforced | Mocked socket (`route_web_socket`) gives deterministic frame-order + bucketing runtime evidence; reconnect remains inspection. |
| R7 no new runtime dependency | ✅ Enforced | AST guard over `web/**`+`src/**` (52 files) + requirements-sync; negative control reproduced against the real tree. |
| R9 manage.py coverage contract | ✅ Documented | `pyproject.toml` omit kept with a comment naming the subprocess test; comment and test both exist. |
| No production behavior change | ✅ Verified | `web`/`src` and `requirements.txt` diffs vs `develop` are empty. |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| W1 mocked `route_web_socket` installed before `goto`, no `connect_to_server` | ✅ Yes | Both tests; boot socket intercepted. |
| Assert parsed `op`/`args[0].ch`, not raw text | ✅ Yes | `json.loads` + tuple compare. |
| Reconnect inspection-only (no prod `chart.js` edit) | ✅ Yes | `chart.js` unchanged; backed by diff. |
| Anti-flake: `wait_for_function` for DOM/series, bounded `_poll` for Python frames | ✅ Mostly | Boot uses `_poll`; the tail-pair assert is immediate (Suggestion 1). |
| W2 guard mirrors `test_boundary.py` AST style | ✅ Yes | Same `ast.walk` + `sys.stdlib_module_names` idiom. |
| Derive local roots; parse requirements; sync test | ✅ Yes | Local roots derived (9), requirements parsed (8 dists). |
| `manage.py` omit kept + documented | ✅ Yes | Comment names the subprocess test. |

## Strict TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | apply-progress `#1395` has a RED→GREEN table for WU1/WU2/WU3. |
| All tasks have tests | ✅ | Guard 5 tests, E2E 2 tests; WU3 is a doc comment (structural, no test expected). |
| RED confirmed (tests exist) | ✅ | Both files exist; negative controls present. |
| GREEN confirmed (tests pass) | ✅ | Full suite 315/315; guard 5/5; e2e 5/5 on independent execution. |
| Triangulation adequate | ✅ | Guard: positive/negative/multi-root/sync (6 cases); E2E: two distinct scenarios. |
| Safety Net for modified files | ✅ | `test_market_e2e.py` had 3/3 pre-existing e2e green; guard file new (N/A). |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit (Python guard) | 5 | 1 | pytest |
| E2E (real chromium) | 2 new (+3 pre-existing) | 1 | pytest-playwright |
| **New total** | **7** | **2** | |
| Full suite | 315 (+5 deselected) | — | pytest, pytest-django, pytest-cov, pytest-playwright |

### Changed-File Coverage

| File | Line % | Uncovered Lines | Rating |
|------|--------|-----------------|--------|
| `tests/test_dependency_guard.py` | n/a (outside `source`) | — | ➖ Not measured (test file) |
| `tests/web/test_market_e2e.py` | n/a (outside `source`) | — | ➖ Not measured (test file) |
| `pyproject.toml` | n/a (config) | — | ➖ |

**Average changed-file coverage**: ➖ Not applicable — no changed file is in coverage `source = ["web","src"]`. This is expected for a test/doc-only change (see WARNING 1).

### Assertion Quality

Scanned the two new/modified test files. No tautologies, no assertions without production-code execution, no ghost loops, no mock-heavy files (0 mocks). The `_offenders(...) == []` empty checks in `test_guard_ignores_...` have companion non-empty tests (`test_guard_flags_unknown_import`, `test_guard_reports_each_unknown_root`). E2E asserts concrete values (`op`/`ch` tuples, exact length, exact `time`). `test_requirements_sync` asserts `declared` is non-empty.

**Assertion quality**: ✅ All assertions verify real behavior.

### Quality Metrics
**Linter**: ✅ No errors (ruff exit 0)
**Type Checker**: ➖ Not configured in this project
**Format**: ✅ 92 files formatted

## Issues Found

### CRITICAL
None.

### WARNING 1 — Patch/coverage gate is vacuous for this change
`diff-cover ... --fail-under=100` exits 0 but reports "No lines with coverage information in this diff", and the new test files are outside coverage `source = ["web","src"]`. The proposal's "patch coverage 100%" success criterion is therefore true only because no measurable line changed — it proves nothing about the new tests. **Fix trigger:** none required for this test-only change; if a future change touches `web/`/`src/`, the gate becomes meaningful and must be re-read, not assumed.

### WARNING 2 — Reconnect scenario has no runtime test
"Reconnect after drop with capped delay" is inspection-verified (`min(1000·2^n,60000)·(0.5+rand)` and `onclose`) exactly as the delta spec permits; no in-browser timing assertion exists. **Fix trigger:** if the spec ever dropped the inspection clause, add a deterministic cap assertion (design notes this is possible only if `backoff` is exposed, which would require a production `chart.js` edit).

### WARNING 3 — `tasks.md` checkboxes not updated
Every task is `[ ]` despite being implemented. **Fix trigger:** mark them `[x]` before archiving, or the archive audit trail misreports progress.

### SUGGESTION 1 — Ordering E2E's final assert is not a bounded poll
`ops[-2:]` is asserted immediately after the REST-redraw `wait_for_function`, not after polling for the pair to appear. `switchTo` emits both frames synchronously on `change`, so the window is tiny — 6/6 repeat runs passed — but a bounded poll for the `unsubscribe`/`subscribe` pair would remove the residual race.

### SUGGESTION 2 — Guard has no "scanned > 0" guard
If `web`/`src` stopped containing `.py` files (rename/move), `_offenders` would return `[]` and the guard would pass vacuously. Add `assert scanned > 0`. Low risk (52 files today).

### SUGGESTION 3 — Superseded prompts/3rd-party dependency in reverse dependency count
None — `cryptography`, `requests`, `rich`, `django`, `psycopg`, `dj_database_url`, `gunicorn`, `redis` are all declared and allowlisted.

## Verdict

**PASS WITH WARNINGS**

Both debts are genuinely closed and independently reproduced. The dependency guard (W2) passes the real 52-file tree, fails on an injected `import pandas` in a real `web/` file (negative control re-run by this verifier), ignores stdlib/declared/local/relative imports, maps `psycopg[binary]→psycopg` and `dj-database-url→dj_database_url`, and its sync test fails when an unmapped dist is added. The E2E (W1) installs `route_web_socket` before `goto`, parses JSON (not raw text), asserts `unsubscribe` strictly before `subscribe`, and asserts same-bucket in-place update (length +1, last `time` unchanged), with a bounded poll for boot frames and no fixed long sleep; it ran 5/5 in real chromium and 10/10 across repeat runs. R9 is documented in `pyproject.toml` with `tests/web/test_manage_boot.py` named and passing. Full suite 315 passed (exit 0), ruff clean, boundary/order-scanner green, and `web`/`src` + `requirements.txt` diffs are empty. The warnings are non-blocking: the patch gate is vacuous (test-only change), reconnect is inspection-per-spec, and the task checkboxes were not ticked. No production behavior change and no new runtime dependency.

## Traceability

| Artifact | Reference |
|----------|-----------|
| Proposal | `openspec/changes/test-debt/proposal.md` |
| Design | `openspec/changes/test-debt/design.md` |
| Tasks | `openspec/changes/test-debt/tasks.md` (25 items, verified in tree) |
| Delta spec | `openspec/changes/test-debt/specs/market-chart/spec.md` (R5/R7 modified, R9 added) |
| Code | `tests/test_dependency_guard.py` (new), `tests/web/test_market_e2e.py` (modified), `pyproject.toml` (comment) |
| Subject-under-test (unchanged) | `web/market/templates/market/chart.js` (`sendSubscribe`, `onPush`, `bucket`, `backoff`, `switchTo`) |
| Apply evidence | Engram `#1395` (`sdd/test-debt/apply-progress`) |
| Probes | executed from `/tmp/opencode` (repo untouched; `git status` clean after) |
| Commits | `5360d19`, `5349dc8`, `2e22dee` |
| Chain diff | `develop...feat/test-debt`, 8 files, +708/−0 |
