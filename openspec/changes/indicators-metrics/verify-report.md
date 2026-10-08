```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:8ecfa96cace5fede8f9f0992a874049dc88ecf0fbaafe599f6199b645e846097
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 19/20
scenarios: 36/38
test_command: .venv/bin/python -m pytest --cov --cov-report=xml
test_exit_code: 0
test_output_hash: sha256:4622588f269f0e880a5f03a99a19b98a7bc2572c485400a405f09b296f8a0a63
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check .
build_exit_code: 0
build_output_hash: sha256:d5c557c8da9ce05fd31cff5c23d522b45ee452b8ad7f2310f92dbc4ba8474b84
```

# Verification Report

**Change**: indicators-metrics
**Version**: N/A (delta specs)
**Mode**: Strict TDD (openspec `config.yaml` `strict_tdd: true`, runner `.venv/bin/python -m pytest`)
**Scope**: chain tip `feat/coverage-ci` (HEAD `1ec8216`); tracker `feat/indicators-metrics` (merge-base `c6128e9`); chain diff = tracker…HEAD, 8 files, +552/−8.

This verification is independent: every command below was executed in the working tree; the apply report was cross-checked, not trusted. One apply-progress claim (test count) was found stale.

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total (WU1 + WU2 + Phase 4) | 43 |
| Tasks complete | 32 |
| Tasks incomplete | 11 |

WU1 (1.1–2.10, 22 items) + Guard Matrix (9) = 31 checked. WU2 (3.1–3.8) and Phase 4 (4.1–4.3) checkboxes are still `[ ]` in `tasks.md` even though the work is demonstrably present in the tree (this is a checkbox-hygiene gap, not missing implementation). Details under WARNING 2 / SUGGESTION 3.

## Build & Tests Execution

**Build**: ✅ Passed (exit 0)
```text
$ .venv/bin/ruff check .
All checks passed!
$ .venv/bin/ruff format --check .
83 files already formatted
```

**Tests**: ✅ 131 passed / ❌ 0 failed / ⚠️ 0 skipped (exit 0)
```text
$ .venv/bin/python -m pytest --cov --cov-report=xml
........................................................................ [ 54%]
...........................................................              [100%]
Coverage XML written to file coverage.xml
131 passed in 37.06s
```
New suites: `tests/test_indicators.py` 40 tests, `tests/test_metrics.py` 16 tests. `tests/test_boundary.py` 2 tests. The apply-progress artifact reports "128 passed" — **stale by 3**; the 3 extra tests came from `a3144b3` ("cover window>n early returns in ema/rsi/atr"), which the report's own WU1 count of 37 did not include either.

**Coverage** (`src/`): `src/indicators.py` 100% (101/101), `src/metrics.py` 100% (23/23). Web gate: `web/*` 92% (312 stmts, 24 missed) ≥ 85%.

## L1 — Independent Test Evidence

| Check | Command | Result |
|-------|---------|--------|
| Full suite | `.venv/bin/python -m pytest` | ✅ 131 passed, exit 0 |
| Lint | `.venv/bin/ruff check .` | ✅ All checks passed, exit 0 |
| Format | `.venv/bin/ruff format --check .` | ✅ 83 files formatted, exit 0 |
| Boundary | `.venv/bin/python -m pytest tests/test_boundary.py` | ✅ 2 passed, exit 0 |
| Core isolation | imported all 8 `src/*.py` with `django` blocked via `sys.meta_path` hook | ✅ all import clean, `assert "django" not in sys.modules` holds |

Core-isolation note: the CI job installs only `requests rich` (no Django) and imports every `src/*.py`. The local venv **has** Django, so I reproduced the scenario by inserting a meta-path finder that raises `ImportError` for `django`/`django.*`; all of `alerts, client, config, db, indicators, journal, metrics, monitor` imported successfully. `src/indicators.py` and `src/metrics.py` import only `statistics` (AST-verified).

## L2 — Coverage Gates

| Gate | Command | Result |
|------|---------|--------|
| Coverage XML | `.venv/bin/python -m pytest --cov --cov-report=xml` | ✅ exit 0, `coverage.xml` written |
| Web gate (R4) | `.venv/bin/coverage report --include="web/*" --fail-under=85` | ✅ exit 0, TOTAL 92% |
| Patch gate (R1) | `.venv/bin/diff-cover coverage.xml --compare-branch=feat/indicators-metrics --fail-under=100` | ✅ exit 0, 124 lines, 0 missing, 100% |
| Patch gate vs develop | `.venv/bin/diff-cover coverage.xml --compare-branch=origin/develop --fail-under=100` | ✅ exit 0, 124 lines, 0 missing, 100% |
| **Fail path (negative)** | `.venv/bin/python -m pytest tests/test_metrics.py --cov --cov-report=xml` then diff-cover vs tracker | ✅ **exit 1**, `src/indicators.py (0.0%)`, 18% — gate genuinely fails on uncovered changed lines |

The negative probe proves the gate is not a no-op: omitting the indicators test file drops patch coverage to 18% and `--fail-under=100` exits 1.

## CI Wiring Verification

| Requirement | Evidence | Result |
|-------------|----------|--------|
| R2 `fetch-depth: 0` on test-job checkout | `ci.yml:31-35` | ✅ Present |
| R1 `pytest --cov --cov-report=xml` before gates | `ci.yml:63-64` | ✅ Present, precedes both gates |
| R4 web gate step | `ci.yml:66-67` | ✅ Present, separate step |
| R1 patch gate step | `ci.yml:69-70` | ✅ Present |
| R5 `diff-cover` dev-only | `requirements-dev.txt:7` `diff-cover>=9.0`; **absent** from `requirements.txt` | ✅ |
| R3 `source = ["web","src"]` | `pyproject.toml:21` | ✅ |
| R3 no global `fail_under` | No `[tool.coverage.report]` section at all (`grep fail_under` → none) | ✅ |

### Critical risk probe — does `origin/develop` resolve on a `pull_request` checkout?

**Result: NO RISK. `origin/develop` resolves.** Verified against the pinned action source, not assumption.

`actions/checkout@11bd719...` (v4.2.2) with `fetch-depth: 0` takes the `settings.fetchDepth <= 0` branch (`src/git-source-provider.ts:188-194`), which calls `getRefSpecForAllHistory` → `['+refs/heads/*:refs/remotes/origin/*', tagsRefSpec]` (`src/ref-helper.ts:69-77`). This fetches **all** remote heads, so `origin/develop` is created regardless of the `pull_request` merge-ref checkout. I confirmed the identical source in the v4.2.2 tag clone. The refspec is the same in `main`.

- On `pull_request` → `origin/develop` exists; gate compares chain vs develop. ✅
- Via `workflow_call` from `cd.yml` on `push: develop` → `origin/develop` exists but equals HEAD, so the diff is empty → `No lines with coverage information in this diff` → exit 0 (trivially passes, which is fine: PR CI already gated). Observation only — see SUGGESTION 1.
- No `git fetch origin develop` fallback is needed; the `github.base_ref` variant is not required. The existing `--compare-branch=origin/develop` is correct for the documented PR-to-develop flow.

## Spec Compliance Matrix

### technical-indicators (R1–R8, 15 scenarios)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R1 | Deterministic output | no dedicated repeat-call test; structural purity + independent repeat-call probe | ✅ COMPLIANT |
| R1 | Inputs are not mutated | `test_indicators.py::test_no_mutation_across_all_indicators` (+ per-fn) | ✅ COMPLIANT |
| R2 | Length preserved | `test_sma_length_preserved`, `test_ema_length_preserved`; independent 200-case random probe (all 6 series fns) | ✅ COMPLIANT |
| R2 | Leading warm-up is `None` | `test_sma_known_values` (`[None,None,2.0,3.0]`) | ✅ COMPLIANT |
| R2 | RSI warm-up | `test_rsi_first_valid_index_is_window` | ✅ COMPLIANT |
| R3 | Empty in, empty out | `test_{sma,ema,rsi,atr,vwap,zscore}_empty_returns_empty` (6) | ✅ COMPLIANT |
| R4 | RSI with no losses | `test_rsi_strictly_rising_is_none` (+ `test_rsi_flat` probe) | ✅ COMPLIANT |
| R4 | Z-score on a flat window | `test_zscore_flat_window_is_none` | ✅ COMPLIANT |
| R4 | VWAP with zero volume | `test_vwap_zero_cumulative_volume_is_none` | ✅ COMPLIANT |
| R5 | RSI bounded | `test_rsi_bounded_zero_to_hundred` | ✅ COMPLIANT |
| R5 | ATR non-negative | `test_atr_non_negative` | ✅ COMPLIANT |
| R6 | Typical-price weighting | `test_vwap_single_bar_uses_typical_price` (`h3 l1 c2 v10 → 2.0`) | ✅ COMPLIANT |
| R7 | Full-series special case | `test_zscore_full_series_only_last_position` (`1.224744871`) | ✅ COMPLIANT |
| R8 | Boundary test stays green | `tests/test_boundary.py` | ✅ COMPLIANT |
| R8 | No forbidden import | (none covers `requests`/`rich`/`src.client`/`src.monitor`) | ⚠️ PARTIAL |

### trade-metrics (R1–R7, 13 scenarios)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R1 | Deterministic output | no dedicated repeat-call test; structural purity + probe | ✅ COMPLIANT |
| R2 | Mean of PnL | `test_expectancy_mean_of_pnl` (`3.333…`) | ✅ COMPLIANT |
| R2 | Empty input | `test_expectancy_empty_is_none` | ✅ COMPLIANT |
| R3 | Normal ratio | `test_profit_factor_normal_ratio` (`6.0`) | ✅ COMPLIANT |
| R3 | No losses | `test_profit_factor_no_losses_is_none` | ✅ COMPLIANT |
| R3 | Empty input | `test_profit_factor_empty_is_none` | ✅ COMPLIANT |
| R4 | Winning trade | `test_r_multiple_winning_trade` (`3.0`) | ✅ COMPLIANT |
| R4 | Zero risk guard | `test_r_multiple_zero_risk_is_none` | ✅ COMPLIANT |
| R5 | Running sum | `test_equity_curve_running_sum` (`[5,3,6]`) | ✅ COMPLIANT |
| R5 | Length preserved | `test_equity_curve_length_preserved` | ✅ COMPLIANT |
| R5 | Empty input | `test_equity_curve_empty_is_empty` | ✅ COMPLIANT |
| R6 | Journal untouched | `git diff tracker…HEAD -- src/journal.py` empty; AST scan: `metrics.py` imports `statistics` only (no `sqlite3`/`src.journal`/`src.db`) | ⚠️ PARTIAL (static only) |
| R7 | Boundary test stays green | `tests/test_boundary.py` | ✅ COMPLIANT |

### patch-coverage-gate (R1–R5, 10 scenarios)

| Requirement | Scenario | Evidence | Result |
|-------------|----------|----------|--------|
| R1 | Uncovered changed line fails CI | negative probe: 18% → exit 1 | ✅ COMPLIANT |
| R1 | Fully covered patch passes | 100% → exit 0 (vs tracker and vs develop) | ✅ COMPLIANT |
| R1 | Compare base is `origin/develop` | `ci.yml:70`; reproduced; resolves per checkout source | ✅ COMPLIANT |
| R2 | Deep clone enables merge-base | `ci.yml:35`; refspec `+refs/heads/*` source-verified | ✅ COMPLIANT |
| R3 | Source includes both trees | `pyproject.toml:21` | ✅ COMPLIANT |
| R3 | No global `fail_under` | `pyproject.toml` (no `[tool.coverage.report]`) | ✅ COMPLIANT |
| R4 | Web gate preserved | `ci.yml:67`; reproduced | ✅ COMPLIANT |
| R4 | Web gate passes unchanged | 92% ≥ 85% | ✅ COMPLIANT |
| R5 | Dev-only dependency | `requirements-dev.txt:7`; absent from `requirements.txt` | ✅ COMPLIANT |
| R5 | No new runtime dependency | `git diff tracker…HEAD -- requirements.txt` empty | ✅ COMPLIANT |

**Compliance summary**: 20 requirements, **19 complete / 1 partial** (technical-indicators R8). 38 scenarios, **36 compliant / 2 partial**.

## Independent Adversarial Probes (executed)

| Probe | Method | Result |
|-------|--------|--------|
| Anchor values | REPL: all spec exact values (`sma`, `ema`, `vwap`, `zscore`, `expectancy`, `profit_factor`, `r_multiple`, `equity_curve`) | ✅ all match |
| Length preservation | 200 random cases, n∈[0,12], w∈[−2,15], all 6 series fns | ✅ `len(out)==n` always |
| No mutation | all 6 indicators on a shared list; all 4 metrics on a list | ✅ inputs unchanged |
| Determinism | repeat calls on sma/rsi/zscore | ✅ equal |
| zscore `window>n` / flat / `window=n` | `zscore([1,2],3)→[None,None]`; `[5,5,5],2→[None]*3`; `[7,7,7],3→[None]*3`; negatives `[3,2,1],2→[None,-1,-1]` | ✅ `None` everywhere stdev==0 |
| RSI flat / rising | `rsi([5,5,5,5],2)→[None]*4`; rising→all None; bounded `[0,100]` | ✅ avg_loss==0 → `None`, never `inf`/raise |
| ATR non-negative | mixed series | ✅ all `≥0` |
| VWAP sign / zero cum | `[1,1],[1,1],[1,2],[0,4] → [None, 1.333…]` (correct cumulative); negative tp `→ -3.0` | ✅ |
| Metrics edges | `profit_factor([-5,-15])→0.0`; `[0,0]→None`; `expectancy([0.0])→0.0` | ✅ `None` vs `0` distinction correct |
| No network/order surface | grep `requests.|.get(|.post(|Client|...order|socket` in both new modules | ✅ none |
| No forbidden imports in source | string + AST scan of both modules | ✅ `statistics` only |
| **Boundary scanner blind spot** | injected `import requests`, `import rich`, `from src.client import Client` into `src/indicators.py`; ran `tests/test_boundary.py` | ❌ **still passes** — see WARNING 1 |
| diff-cover config-only diff | `--compare-branch=feat/metrics-core` | ✅ exit 0, "No lines with coverage information" |
| `--ignore-errors` flag | `diff-cover --help` | ✅ not a flag in v10.6.0 — correctly not used (task 3.7) |
| Mismatched input lengths | `atr([10,11],[8],[9,10,11],2)`; `vwap` with short highs | ⚠️ both raise `IndexError` (out of contract) — see SUGGESTION 5 |

## TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | `apply-progress` (Engram `sdd/indicators-metrics/apply-progress`, id 1317) documents RED→GREEN per function. |
| All tasks have tests | ✅ | 40 indicator + 16 metric tests; every function and every Guard-Matrix row has a covering test. |
| RED confirmed (tests exist) | ✅ | `tests/test_indicators.py`, `tests/test_metrics.py` exist in the tree. |
| GREEN confirmed (tests pass) | ✅ | 56/56 new tests pass on independent execution inside the 131-test suite. |
| Triangulation adequate | ✅ | sma/ema window-1 identity + general case; rsi Wilder multi-step + rising + flat; metrics negative/zero/all-loss cases. |
| Safety Net for modified files | ✅ | `src/journal.py` untouched (diff empty); existing 75 tests still green. |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | 56 | 2 | pytest |
| Integration / boundary | 2 | 1 | pytest, `ast` |
| **New total** | **58** | **3** | |
| Full suite | 131 | 13 | pytest, pytest-django, pytest-cov |

### Changed-File Coverage

| File | Line % | Uncovered Lines | Rating |
|------|--------|-----------------|--------|
| `src/indicators.py` | 100% | — | ✅ Excellent |
| `src/metrics.py` | 100% | — | ✅ Excellent |

### Assertion Quality

Scanned both new test files: no tautologies, no orphan empty-collection assertions, no type-only assertions, no ghost loops, no mocks (pure unit — correct layer). Every assertion calls production code and checks a concrete value. The `test_*_empty_returns_empty`/`is_none` assertions all have companion non-empty tests in the same file.

**Assertion quality**: ✅ All assertions verify real behavior.

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| R1 pure functions (indicators) | ✅ Implemented | No I/O, no globals; `statistics` only. |
| R2 warm-up alignment | ✅ Implemented | Same-length output, documented leading `None` per function. |
| R3 empty input | ✅ Implemented | Every fn returns `[]` on empty, including nested `atr`/`vwap`. |
| R4 divide-by-zero guards | ✅ Implemented | `avg_loss==0`, `pstdev==0`, `cum_v==0`, `window<1`, `n<=window` all → `None`/all-`None`. |
| R5 ranges | ✅ Implemented | RSI formula bounded; ATR from non-negative TR. |
| R6 VWAP typical price | ✅ Implemented | `tp=(h+l+c)/3`, cumulative. |
| R7 rolling zscore | ✅ Implemented | `pstdev` of trailing window; `window=n` = full series. |
| R8 stdlib boundary | ⚠️ Partial | Code complies; the *test* guard only covers Django (WARNING 1). |
| trade-metrics R1–R7 | ✅ Implemented | Pure, empty→`None`/`[]`, journal untouched. |
| patch-coverage R1–R5 | ✅ Implemented | Steps wired, thresholds verified empirically. |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| A1–A6 formulas | ✅ Yes | sma/ema seed/k, Wilder rsi/atr, vwap tp, zscore pstdev — all match design table. |
| (a) same-length + `None` warm-up | ✅ Yes | No truncation anywhere. |
| (b) `None` vs `inf`/`nan` | ✅ Yes | All undefined positions `None`; no `inf`/`nan` emitted. |
| (c) diff-cover 100% + web 85% scoped | ✅ Yes | Both gates exist and are correctly scoped. |
| (d) `journal.metrics()` untouched | ✅ Yes | `src/journal.py` diff empty. |
| CI wiring (fetch-depth 0, xml, two steps) | ✅ Yes | Matches `design.md` exactly. |
| Coverage config (`source += src`, drop `fail_under`, keep `omit`) | ✅ Yes | `omit` preserved. |
| `diff-cover>=9.0` dev-only | ✅ Yes | Not in runtime requirements. |

## Issues Found

**CRITICAL**: None.

**WARNING 1 (MEDIUM) — The R8 "No forbidden import" guard only scans Django.**
`tests/test_boundary.py:26-44` checks `"django" in _imported_roots` and nothing else. R8 (`technical-indicators/spec.md:118-129`) *names* `requests`, `rich`, `src.client`, `src.monitor` and gives the scenario "GIVEN a change adding `import requests` … THEN the check fails." I injected `import requests`, `import rich`, and `from src.client import Client` into `src/indicators.py` and `tests/test_boundary.py` **stayed green (2 passed)**. The *invariant* holds today — an independent AST scan confirms both new modules import only `statistics`, with no network/order calls — so this is a test-coverage gap, not a live violation. It is the same class as the web-foundation verify-report's WARNING 1/2 (scanner blind spots), which were classified WARNING. **Fix:** generalize `_django_offenders` to a banned-roots set `{"django","requests","rich","src"}` and assert the self-test flags each, or add a dedicated test that scans the two new modules' import roots.

**WARNING 2 (LOW) — WU2/Phase-4 task checkboxes are unchecked despite completed work.**
`tasks.md:57-70` still shows `[ ]` for 3.1–3.8 and 4.1–4.3, though every artifact is present in the tree and verified here. The chain diff hash used for `evidence_revision` is unaffected, but task-tracking is stale relative to reality. **Fix:** flip `[x]` for 3.1–3.8 and 4.1–4.3.

**SUGGESTION 1 — Patch gate compares against a hardcoded `origin/develop`, ignoring `github.base_ref`.**
`ci.yml:70` uses `--compare-branch=origin/develop`. Intentional per `design.md`, and correct for the documented PR→develop flow (verified `origin/develop` resolves). For chained PRs targeting intermediate branches it compares the whole chain vs develop (stricter, not weaker). On CD (`push: develop`) the diff is empty → the step passes trivially — acceptable since PR CI already gated the code. No change required; optionally use `origin/${{ github.base_ref }}` if the chain later targets a release branch.

**SUGGESTION 2 — No dedicated repeat-call determinism test.**
Both specs have a "called twice → equal" scenario; no committed test asserts it. Purity is structurally guaranteed and I confirmed determinism in a probe, but an explicit test would lock the contract.

**SUGGESTION 3 — `apply-progress` test count is stale (128 vs actual 131).**
The artifact predates the 3 `window>n` tests added in `a3144b3`. Update the report so downstream phases read a correct number.

**SUGGESTION 4 — No committed test asserts `journal.metrics()` is unchanged (R6).**
The requirement is proven statically (`src/journal.py` diff empty; `metrics.py` imports no `sqlite3`/`src.journal`/`src.db`), but no runtime test covers the "signature and results unchanged" scenario. A one-line import-signature test would close it.

**SUGGESTION 5 — `atr`/`vwap` index input series by `len(closes)`.**
`atr([10,11],[8],[9,10,11],2)` and a `vwap` with a short `highs` list raise `IndexError`. This is outside the documented contract (equal-length OHLCV), but a defensive length check or a docstring note would avoid a silent footgun for future callers.

## Verdict

**PASS WITH WARNINGS**

Reproduced independently: **131/131 tests pass** (exit 0), `ruff check`/`ruff format --check` exit 0, boundary green, core imports clean without Django, web gate 92% (≥85), patch gate 100% (vs tracker and vs develop), and the patch gate's **fail path verified** (18% → exit 1). All 4 runtime deps and both CI gates are wired exactly as designed. The headline CI risk — `origin/develop` unresolvable on a `pull_request` checkout — is **not real**: `fetch-depth: 0` fetches `+refs/heads/*:refs/remotes/origin/*` (source-verified in the pinned v4.2.2 action), so the base always resolves. Two WARNINGs are test/tracking hygiene (the R8 banned-import guard only covers Django; WU2/Phase-4 checkboxes stale); neither breaks a spec requirement nor the pipeline. **Merge decision: GO.**
