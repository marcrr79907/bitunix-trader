```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:f91263874a6b2c7be4659f2410a54d98858f014ffee01ab4868655ca8b140f65
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 7/7
scenarios: 20/24
test_command: .venv/bin/python -m pytest
test_exit_code: 0
test_output_hash: sha256:9dc34330d352615ab9c0b2fc576381f3ac6790a6e211cf6b051464dabbe9a080
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check . && env -u PYTHONPATH .venv/bin/python web/manage.py check && env -u PYTHONPATH .venv/bin/python web/manage.py makemigrations --check --dry-run
build_exit_code: 0
build_output_hash: sha256:66dc0ae7617066abcfbdff75a0c609ffa6d0a7660b9e27ec8371da04bff7e2a3
```

# Verification Report

**Change**: market-chart (Phase 4) — single PR, base `develop`
**Version**: N/A (delta specs)
**Mode**: Strict TDD (`openspec/config.yaml` `strict_tdd: true`, runner `.venv/bin/python -m pytest`)
**Scope**: branch `feat/market-chart` (confirmed `git branch --show-current`), HEAD `5163125`; chain diff vs `develop` = 26 files, +2022/−4. Commits: `b36a596` (backend), `f990145` (frontend), `1a14562`/`69536fa` (docs), `abb901b` (patch-gate test), `5163125` (manage.py sys.path fix + boot regression test).
**Re-verification**: this report supersedes the prior `fail`. It re-reproduces the CRITICAL the way CI runs it, on the fixed HEAD, plus a `develop` regression check.

Everything below was reproduced from the working tree by this verifier. The prior CRITICAL was re-run from the exact CI commands with `PYTHONPATH` unset, from two different working directories.

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total (Guard Matrix 18 + WU1 9 + WU2 10 + Phase 3 3) | 40 |
| Tasks complete | 40 (`tasks.md` all `[x]`) |
| Tasks incomplete | 0 |

All 18 Guard-Matrix rows, WU1 1.1–1.9, WU2 2.1–2.10 and Phase 3 3.1–3.3 are marked complete and present in the tree. Task 2.9 (WS channel map >30m) remains RESOLVED with live-evidence in the apply artifact.

## Build & Tests Execution

**Build**: ✅ Passed (exit 0) — the prior import regression is closed.
```text
$ .venv/bin/ruff check .
All checks passed!
$ .venv/bin/ruff format --check .
80 files already formatted
$ env -u PYTHONPATH .venv/bin/python web/manage.py check
System check identified no issues (0 silenced).
$ env -u PYTHONPATH .venv/bin/python web/manage.py makemigrations --check --dry-run
No changes detected
build_exit=0
```

**Tests**: ✅ 241 passed / ❌ 0 failed / ⚠️ 1 deselected (exit 0)
```text
$ .venv/bin/python -m pytest
241 passed, 1 deselected in 25.94s
```
**E2E** (dev-only): ✅ 1 passed, 241 deselected — the chromium bundle IS available, so the E2E smoke actually ran and passed.
```text
$ .venv/bin/python -m pytest -m e2e
1 passed, 241 deselected in 4.60s
```

**Coverage**: web 95% / threshold 85% → ✅ Above; patch gate 100% (75 lines, 0 missing) → ✅
```text
$ .venv/bin/python -m pytest --cov --cov-report=xml
241 passed, 1 deselected
$ .venv/bin/coverage report --include="web/*" --fail-under=85
TOTAL                               503     24    95%
$ .venv/bin/diff-cover coverage.xml --compare-branch=origin/develop --fail-under=100
Total:   75 lines  Missing: 0 lines  Coverage: 100%
```

## L1 — Independent Test Evidence

| Check | Command | Result |
|-------|---------|--------|
| Full suite | `.venv/bin/python -m pytest` | ✅ 241 passed, 1 deselected, exit 0 |
| E2E (real browser) | `.venv/bin/python -m pytest -m e2e` | ✅ 1 passed, 241 deselected, exit 0 (not skipped — bundle present) |
| Lint | `.venv/bin/ruff check .` | ✅ All checks passed, exit 0 |
| Format | `.venv/bin/ruff format --check .` | ✅ 80 files formatted, exit 0 |
| Django system check (no PYTHONPATH) | `env -u PYTHONPATH .venv/bin/python web/manage.py check` | ✅ **exit 0** — "System check identified no issues" |
| Migration drift (no PYTHONPATH) | `env -u PYTHONPATH .venv/bin/python web/manage.py makemigrations --check --dry-run` | ✅ **exit 0** — "No changes detected" |
| Manage boot with minimal env | `env -u PYTHONPATH .venv/bin/python -c ...` (probe) | ✅ `src` resolves to repo-root, `config` to `web/` |
| Boot regression test | `.venv/bin/python -m pytest tests/web/test_manage_boot.py` | ✅ 1 passed, exit 0 |
| Boundary | `.venv/bin/python -m pytest tests/test_boundary.py` | ✅ 4 passed, exit 0 |
| Order-surface scanner | `.venv/bin/python -m pytest tests/web/test_no_order_surface.py` | ✅ 36 passed, exit 0 |
| Credentials scanner (market added) | `.venv/bin/python -m pytest tests/web/test_credentials_mechanism.py` | ✅ 13 passed, exit 0 |
| Runtime deps unchanged | `git diff develop...HEAD -- requirements.txt` | ✅ empty (0 lines) |
| CI workflow unchanged | `git diff develop...HEAD -- .github/workflows/ci.yml` | ✅ empty (0 lines) |

## L2 — Coverage Gates

| Gate | Command | Result |
|------|---------|--------|
| Coverage XML | `.venv/bin/python -m pytest --cov --cov-report=xml` | ✅ exit 0, `coverage.xml` written |
| Web gate | `.venv/bin/coverage report --include="web/*" --fail-under=85` | ✅ exit 0, TOTAL 95% |
| Patch gate | `.venv/bin/diff-cover coverage.xml --compare-branch=origin/develop --fail-under=100` | ✅ exit 0, 75 lines, 0 missing, 100% |

No Python line introduced by this change is uncovered.

## CRITICAL Reproduction — CI-grade, on the fixed HEAD

The prior CRITICAL was `ModuleNotFoundError: No module named 'src'` on bare `python web/manage.py check` / `makemigrations` (CI L1 steps, no `PYTHONPATH`). Re-run exactly:

| Invocation | Dir | Result |
|------------|-----|--------|
| `env -u PYTHONPATH .venv/bin/python web/manage.py check` | repo root | ✅ exit 0 |
| `env -u PYTHONPATH .venv/bin/python web/manage.py makemigrations --check --dry-run` | repo root | ✅ exit 0, "No changes detected" |
| `cd /tmp && env -u PYTHONPATH /.../web/manage.py check` | `/tmp` (foreign cwd) | ✅ exit 0 |
| `cd /tmp && env -u PYTHONPATH /.../web/manage.py makemigrations --check --dry-run` | `/tmp` (foreign cwd) | ✅ exit 0, "No changes detected" |
| `origin/develop` worktree (`5b69260`), same commands | worktree | ✅ exit 0 / exit 0 (no regression in shared code) |

**Root-cause fix, not a CI workaround.** The fix is `web/manage.py::_ensure_project_paths()`, which inserts the repo root and `web/` into `sys.path` unconditionally before Django starts. The CI workflow is unchanged (`git diff develop...HEAD -- .github/workflows/ci.yml` empty), so CI still runs the bare `python web/manage.py check`; it now passes because `manage.py` is self-sufficient, not because the workflow injects a path. `pyproject.toml` (`pythonpath = ["web"]`) and `Dockerfile` (`PYTHONPATH=/app:/app/web`) are untouched.

**Regression test**: `tests/web/test_manage_boot.py` spawns `python web/manage.py check` as a subprocess with a minimal env (`PATH` + `DJANGO_SETTINGS_MODULE`, no `PYTHONPATH`) and asserts `returncode == 0` and no `ModuleNotFoundError`. It passed independently (1 passed, exit 0).

## Independent Adversarial Probes — the fix (`/tmp/opencode`, repo untouched)

| Probe | Question | Result |
|-------|----------|--------|
| Fix sys.path effect | Which paths does it add? | ✅ adds repo root + `web/`; precedence `[web_dir, repo_root, "", ...]` |
| Shadowing | Can repo root shadow stdlib or `web/` modules? | ✅ no. Repo root contains only `src/`, `web/`, `docs/`, `openspec/`, `tests/` — no stdlib-name files/modules. `json`/`sys`/`os`/`pathlib`/`logging` still resolve to stdlib after insertion |
| Module resolution | `config`, `src`, `market`, `accounts`, `trading` | ✅ `config`→`web/config`, `src`→repo-root `src`, `market`/`accounts`/`trading`→`web/*` — correct owners, `web/` listed first so it owns the Django packages |
| Idempotency | Call twice → duplicate rows? | ✅ guarded by `if entry not in sys.path`; web_dir and repo_root each appear exactly once after two calls |
| Double invocation | Imported once by the `__main__` guard | ✅ no re-import risk; module has an `if __name__ == "__main__"` guard |
| `src` vs `web/src`? | Duplicate package? | ✅ `web/` has no `src`; `src` exists only at repo root — no ambiguity |
| Foreign cwd | Relative resolution? | ✅ uses `Path(__file__).resolve()` — absolute, cwd-independent |

No risk introduced. The inserted entries are printed verbatim: `['/home/marc/BeBest/Cripto/bitunix-trader/web', '/home/marc/BeBest/Cripto/bitunix-trader']`.

## Spec Compliance Matrix

### market-chart (R1–R7, 24 scenarios)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R1 | Correct URL and params (unsigned GET) | `test_client_kline.py::test_kline_hits_public_path_unsigned`, `::test_kline_defaults_match_spec` | ✅ COMPLIANT |
| R1 | Mapping ms→s and floats | `test_client_kline.py::test_kline_maps_ms_to_unix_seconds_and_floats` | ✅ COMPLIANT |
| R1 | API error surfaces as BitunixError | `test_client_kline.py::test_kline_api_code_ne_zero_raises`, `::test_kline_http_ne_200_raises` | ✅ COMPLIANT |
| R1 | Empty upstream returns `[]` | `test_client_kline.py::test_kline_empty_data_returns_empty_list`, `::test_kline_null_data_returns_empty_list` | ✅ COMPLIANT |
| R2 | Anonymous → 302 login (page) | `test_market_ux.py::test_market_page_redirects_anonymous_to_login` | ✅ COMPLIANT |
| R2 | Authenticated renders chart page | `test_market_ux.py::test_market_page_renders_chart_container`, `::test_market_page_lists_pairs_and_intervals` | ✅ COMPLIANT |
| R3 | Candles sorted and deduplicated | `test_market_api.py::test_payload_dedupes_and_sorts_ascending_last_wins` | ✅ COMPLIANT |
| R3 | Overlay gaps omitted (no nulls) | `test_market_api.py::test_payload_overlays_are_time_value_pairs_without_nulls` | ✅ COMPLIANT |
| R3 | Invalid interval → 400 | `test_market_api.py::test_endpoint_invalid_interval_is_400` | ✅ COMPLIANT |
| R3 | Invalid symbol → 400 | `test_market_api.py::test_endpoint_upstream_api_reject_is_400`, `::test_endpoint_missing_symbol_is_400` | ✅ COMPLIANT |
| R3 | Empty upstream → 200 empty | `test_market_api.py::test_endpoint_empty_upstream_is_200_empty`, `::test_payload_empty_upstream_is_200_empty_arrays` | ✅ COMPLIANT |
| R3 | Unauthenticated → redirect (API) | `test_market_api.py::test_endpoint_anonymous_redirects_to_login` | ✅ COMPLIANT |
| R4 | SMA point count N−w+1, none null | `test_market_api.py::test_payload_overlays_are_time_value_pairs_without_nulls` | ✅ COMPLIANT |
| R4 | RSI bounded or omitted | `test_market_api.py::test_payload_rsi_bounded_or_omitted` | ✅ COMPLIANT |
| R5 | Forming candle updates in place (bucketing) | (no runtime test; inspection of `chart.js::onPush`/`bucket`) | ❌ UNTESTED |
| R5 | Switch unsubscribes before subscribing | (no runtime test; inspection of `chart.js::sendSubscribe`) | ❌ UNTESTED |
| R5 | Reconnect after drop with capped delay | (no runtime test; inspection of `chart.js::backoff`/`onclose`) | ❌ UNTESTED |
| R5 | E2E DOM smoke | `test_market_e2e.py::test_chart_page_wires_up` | ✅ COMPLIANT |
| R6 | Header present on market page | `test_market_ux.py::test_csp_present_on_market_page` | ✅ COMPLIANT |
| R6 | Admin unaffected | `test_market_ux.py::test_csp_absent_on_admin_login` | ✅ COMPLIANT |
| R6 | `/healthz` unaffected | `test_market_ux.py::test_healthz_still_200` | ✅ COMPLIANT |
| R7 | Core boundary stays green | `tests/test_boundary.py` (4 passed) | ✅ COMPLIANT |
| R7 | Order scanner clean | `tests/web/test_no_order_surface.py` (36 passed) | ✅ COMPLIANT |
| R7 | Runtime dependencies unchanged | (no test; `git diff` empty — inspection) | ❌ UNTESTED |

**Compliance summary**: 7/7 requirements implemented; **20/24 scenarios compliant, 4 UNTESTED**. The four untested scenarios are the same as the prior verify: three JS runtime behaviors verified by static inspection only (R5), plus one dependency invariant verified by `git diff` (R7). No scenario is FAILING.

## Independent Adversarial Probes (from `/tmp`)

### Payload seam — `get_kline_payload` with a stub client

| Probe | Scenario | Result |
|-------|----------|--------|
| a | Duplicate times → last-wins dedupe | ✅ `[0,60]`, close `99.0` (last row won) |
| b | Unsorted input → ascending | ✅ `[0,60,120]` |
| c | Short series (N=5 < 20) → sma20/ema20/rsi14 all `[]`, no crash | ✅ |
| d | Flat window → rsi14 `[]`; every emitted value non-null | ✅ no nulls |
| e | Mixed series (N=40) → no overlay value is `None` | ✅ |
| f | SMA count on N=40 → exactly 21 | ✅ |
| g | RSI values bounded `[0,100]` | ✅ |
| h | Empty upstream → exact `{"candles":[],"overlays":{"sma20":[],"ema20":[],"rsi14":[]}}` | ✅ |
| i | `1M` in INTERVALS; `2s` rejected | ✅ |

### Endpoint matrix (real Django test client)

| Probe | Expected | Result |
|-------|----------|--------|
| `symbol=BTCUSDT&interval=1m` (stub) | 200 | ✅ |
| `interval=2s` | 400 | ✅ |
| missing `symbol` | 400 | ✅ |
| `limit=0` / `201` / `abc` | 400 / 400 / 400 | ✅ |
| upstream API reject (`BitunixError`) | 400 | ✅ |
| network failure (`requests.ConnectionError`) | 502 `{"error":"upstream"}` | ✅ |
| empty upstream | 200 empty arrays | ✅ |
| anonymous page + API | 302 to `/login/` | ✅ |
| POST page + API | 405 | ✅ |
| `interval=1M` (uppercase) | 200 | ✅ |
| CSP on `/market/` | present, wss + CDN + self | ✅ |
| CSP `script-src` contains `'unsafe-inline'` | **must be absent** | ✅ absent |
| CSP on `/admin/login/` | absent | ✅ |
| `/healthz` | 200, CSP absent (short-circuited first) | ✅ |

**Exact header emitted on `/market/`:**
```
default-src 'self'; script-src 'self' https://unpkg.com; style-src 'self' 'unsafe-inline' https://unpkg.com; connect-src 'self' wss://fapi.bitunix.com; img-src 'self' data:
```

### JS / static inspection

- **No indicator math in `chart.js`**: only a read of `payload.overlays.rsi14`; no computation. ✅ R4 single-source holds.
- **`chart.js` size**: 192 lines (unchanged from prior verify; design forecast ~140). ✅ SUGGESTION on doc drift only.
- **Template injection**: symbols come from `src.config.SYMBOLS` (server-controlled), not user input; `|safe` JSON risk is not user-reachable. ✅
- **No secret/WS-URL leak**: no API key, token, or secret in `chart.html`/`chart.js`; WS URL is the public endpoint. ✅
- **`api_kline` is GET-only + login-gated**: anonymous → 302, POST → 405. ✅

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| R1 kline client | ✅ Implemented | Public unsigned GET; ms→s int, floats; empty/null → `[]`; errors → `BitunixError`. `src/client.py:126-138`. |
| R2 auth-gated page | ✅ Implemented | `market_page` `@login_required` + GET-only; chart-first layout. `web/market/views.py:25-28`. |
| R3 kline JSON | ✅ Implemented | sort/dedupe last-wins; uniform `{time,value}` overlays; 400/400/400/502/200 contract; never 500. |
| R4 indicators single-source | ✅ Implemented | Overlays computed only via `src/indicators.py`; `_zip` drops `None`; no JS math. |
| R5 live WS | ✅ Implemented (JS) | subscribe-on-open, unsubscribe-before-subscribe, bucketed `series.update`, capped+jittered backoff, ping. |
| R6 CSP | ✅ Implemented | Path-conditional middleware, last in `MIDDLEWARE`; `script-src` strict; healthz bypass. |
| R7 boundary/read-only/no-dep | ✅ Implemented | `src/` framework-free; `/market/kline` clean; `requirements.txt` diff empty. |
| **Startup import-safety (fix)** | ✅ Implemented | `web/manage.py::_ensure_project_paths()` makes `src` importable without `PYTHONPATH`. |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| (a) Lightweight Charts v5.2.0 CDN-pinned | ✅ Yes | `chart.html:37` pins `@5.2.0`; v5 `addSeries`. |
| (b) Browser-direct public WS (A1) | ✅ Yes | `WS_URL = wss://fapi.bitunix.com/public/`; no Channels. |
| (c) Ephemeral candles, no model/migration | ✅ Yes | No model; `makemigrations` reports no changes (now green under CI env). |
| (d) Path-conditional custom CSP middleware, last | ✅ Yes | `middleware.py:45-53`; last in `base.py:95`. |
| (e) Indicator math server-side only | ✅ Yes | `quotes.py` imports `src.indicators`; JS has no math. |
| (f) Page JS served same-origin via `chart_js` view | ✅ Yes | `views.py:61-67`. |
| (g) Overlay set v1 (sma20 + ema20 lines, rsi14 list) | ✅ Yes | Uniform `{time,value}` lists; RSI in side panel. |
| Error contract 502-vs-500 | ✅ Yes | BitunixError→400, RequestException→502, never 500. |
| **Import-safety of `src` at URLconf load** | ✅ **Yes (resolved)** | The prior ❌ is closed by `_ensure_project_paths()`; verified under CI's exact no-`PYTHONPATH` invocation and a foreign cwd. |
| `chart.js` ~120–140 lines | ⚠️ Deviation | Shipped 192 lines. Modest, no math. SUGGESTION. |

## TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | apply-progress `#1353` has a full RED→GREEN table for WU1/WU2/2.2. |
| All tasks have tests | ✅ | 28 new tests now (27 prior + boot regression); all 18 Guard-Matrix rows carry a covering test, except the 3 JS-runtime scenarios (static-only). |
| RED confirmed (tests exist) | ✅ | `test_client_kline.py` (7), `test_market_api.py` (11), `test_market_ux.py` (8), `test_market_e2e.py` (1), `test_manage_boot.py` (1) all exist. |
| GREEN confirmed (tests pass) | ✅ | All new tests pass on independent execution; full suite 241/241 (exit 0). |
| Triangulation adequate | ✅ | Dedupe/sort/empty; valid/invalid interval/limit/symbol; 400/502/200 matrix; flat/mixed/short series; CSP present/absent; boot with/without `PYTHONPATH`. |
| Safety Net for modified files | ✅ | Baseline 212 → 241; full suite green. |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit (client mapping) | 7 | 1 | pytest |
| Integration (`quotes` seam + Django views) | 19 | 2 | pytest, pytest-django |
| Integration (manage.py boot subprocess) | 1 | 1 | pytest, subprocess |
| E2E (real chromium) | 1 | 1 | pytest-playwright |
| **New total** | **28** | **5** | |
| Full suite | 241 (+1 deselected) | — | pytest, pytest-django, pytest-cov, pytest-playwright |

### Changed-File Coverage

| File | Line % | Uncovered Lines | Rating |
|------|--------|-----------------|--------|
| `src/client.py` | 100% | — | ✅ Excellent |
| `web/config/middleware.py` | 100% | — | ✅ Excellent |
| `web/market/apps.py` | 100% | — | ✅ Excellent |
| `web/market/quotes.py` | 100% | — | ✅ Excellent |
| `web/market/urls.py` | 100% | — | ✅ Excellent |
| `web/market/views.py` | 100% | — | ✅ Excellent |
| `web/manage.py` | n/a (excluded) | — | note below |

**Average changed-file coverage**: 100% for measured files. `web/manage.py` is listed in `pyproject.toml` `[tool.coverage.run].omit` (together with `wsgi.py`/`asgi.py`), so its 19 new lines do **not** appear in `coverage.xml` and the diff-cover patch gate does not measure them — it reports the same 75 lines as before the fix. The fix is covered by the `test_manage_boot.py` subprocess test and by the direct CI-grade reproductions above, not by coverage instrumentation. (`chart.js`/`chart.html` are templates; E2E is their layer.)

### Assertion Quality

Scanned the new/modified test files (Step 5f). `test_manage_boot.py` asserts `returncode == 0` after actually executing `web/manage.py` in a real subprocess and also asserts the absence of `ModuleNotFoundError` — behavioral, not tautological (it passes only if Django boots). No tautologies, no assertion without production-code execution, no ghost loops. `test_endpoint_empty_upstream_is_200_empty` has paired non-empty companions. E2E asserts a concrete global type, canvas count, and empty script-error list.

**Assertion quality**: ✅ All assertions verify real behavior.

### Quality Metrics
**Linter**: ✅ No errors (ruff exit 0)
**Type Checker**: ➖ Not configured in this project
**Format**: ✅ 80 files formatted

## Issues Found

### CRITICAL — `python web/manage.py check` / `makemigrations` fail on the branch; CI is RED. → ✅ RESOLVED

The prior blocker (`ModuleNotFoundError: No module named 'src'` when the new `market` URLconf transitively imports `src` at Django startup with no `PYTHONPATH`) is closed by `web/manage.py::_ensure_project_paths()` (`5163125`). Verified by this verifier:
- `env -u PYTHONPATH .venv/bin/python web/manage.py check` → exit 0 (repo root **and** `/tmp`).
- `env -u PYTHONPATH .venv/bin/python web/manage.py makemigrations --check --dry-run` → exit 0, "No changes detected" (repo root **and** `/tmp`).
- `origin/develop` worktree still exits 0 → no regression into shared code.
- The fix is in `manage.py`, not the CI workflow: `git diff develop...HEAD -- .github/workflows/ci.yml` is empty; CI still runs the bare command.
- Adversarial probes found no shadowing, no duplicate path rows, no ambiguous packages.

### WARNING 1 (LOW) — 3 R5 JS-runtime scenarios have no runtime test.

"Forming candle updates in place", "switch unsubscribes before subscribing", and "reconnect after drop with capped delay" are verified by static inspection of `chart.js` only (all three ARE correctly implemented). The E2E is DOM-only (`test_market_e2e.py:62-68`) and does not exercise switch/reconnect/bucketing. **Fix trigger:** add a JS unit test (e.g. `node --test` on an extracted pure module) or an E2E that drives an interval switch and asserts the unsubscribe-then-subscribe frame order; otherwise mark these scenarios as inspection-verified in the spec.

### WARNING 2 (LOW) — R7 "runtime dependencies unchanged" has no covering test.

Verified by empty `git diff develop...HEAD -- requirements.txt` (0 lines). **Fix trigger:** add a guard test asserting no new runtime import appears in `web/`/`src/` outside the declared set, mirroring the archived market-ingestion WARNING 4.

### SUGGESTION 1 — `chart.js` is 192 lines vs the ~120–140 forecast.

Still modest and free of business logic; extra is the channel map, ping keepalive, and interval helper. Update the design's line estimate when archiving.

### SUGGESTION 2 — E2E assertion tolerates any `net::`/`WebSocket` console error.

`test_market_e2e.py:67` filters all `net::`/`WebSocket` errors, which could mask a broken CDN script or misrouted fetch. The chart-global assertion still catches a dead CDN; consider narrowing the filter to the known WS/fetch noise.

### SUGGESTION 3 (new) — `web/manage.py` is omitted from coverage, so the patch gate does not measure the fix.

`pyproject.toml` `[tool.coverage.run].omit` excludes `web/manage.py`, so the change that closed the blocker is invisible to `diff-cover` and the web gate. Not a defect (the file is a thin bootstrap; its behavior is locked by `test_manage_boot.py`), but worth noting: future edits to `manage.py` get no coverage safety net. If desired, drop it from `omit` and let `test_manage_boot.py` count toward the patch or rely on the subprocess test as the contract.

## Verdict

**PASS WITH WARNINGS**

The prior CI-breaking CRITICAL is genuinely closed and independently reproduced. On HEAD `5163125`, `env -u PYTHONPATH .venv/bin/python web/manage.py check` and `... makemigrations --check --dry-run` both exit 0 from the repo root and from a foreign cwd, and `origin/develop` still passes. The fix is a root-cause change in `web/manage.py` (self-sufficient `sys.path`), while the CI workflow is untouched, and it is locked by `tests/web/test_manage_boot.py`. Adversarial probes found no shadowing, idempotency, or package-ambiguity risk.

Functional evidence remains strong: **241/241 tests pass** (exit 0), the dev-only E2E ran in a real chromium (1/1), `ruff check` and `ruff format --check` exit 0, web coverage is 95% (≥85), the patch gate is 100% on 75 lines with no missing lines, boundary/order-scanner suites are green, and `requirements.txt` is unchanged. The remaining items are non-blocking: 3 inspection-verified JS-runtime scenarios, 1 inspection-verified dependency invariant, a JS line-count drift, a broad E2E error filter, and the coverage-omit note on `manage.py`. **Archive is no longer blocked.**

## Traceability

| Artifact | Reference |
|----------|-----------|
| Proposal | `openspec/changes/market-chart/proposal.md` |
| Design | `openspec/changes/market-chart/design.md` (a–g, error contract, JS/CSP design) |
| Tasks | `openspec/changes/market-chart/tasks.md` (all `[x]`) |
| Delta spec | `openspec/changes/market-chart/specs/market-chart/spec.md` (R1–R7) |
| Code | `src/client.py`, `web/market/{__init__,apps,quotes,urls,views}.py`, `web/market/templates/market/{chart.html,chart.js}`, `web/config/{middleware,urls,settings/base}.py`, `web/accounts/templates/accounts/home.html`, `web/manage.py` |
| Tests | `tests/test_client_kline.py`, `tests/web/test_market_api.py`, `tests/web/test_market_ux.py`, `tests/web/test_market_e2e.py`, `tests/web/test_manage_boot.py`, `tests/web/test_credentials_mechanism.py`, `tests/test_boundary.py`, `tests/web/test_no_order_surface.py` |
| Reused core | `src/indicators.py`, `src/config.py::SYMBOLS`, `src/client.py::_unwrap` |
| Apply evidence | Engram `#1353` (`sdd/market-chart/apply-progress`) |
| Probes | executed from `/tmp/opencode` (repo untouched) |
| Commits | `b36a596`, `f990145`, `1a14562`, `69536fa`, `abb901b`, `5163125` |
| Chain diff | `develop...feat/market-chart`, 26 files, +2022/−4 |
