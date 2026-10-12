```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:45a9b89ee00c29098a21733b38ef2dd2b90ace4059bf0351459fb16993085b43
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 6/6
scenarios: 41/44
test_command: .venv/bin/python -m pytest
test_exit_code: 0
test_output_hash: sha256:8e9c5b36d324fcb610ab5214af2470b6eab46c76c679a1ca3c4eb30eda8d091d
test_output_summary: "434 passed, 8 deselected (E2E excluded); E2E -m e2e: 8 passed"
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check . && env -u PYTHONPATH .venv/bin/python web/manage.py makemigrations --check --dry-run
build_exit_code: 0
build_output_hash: sha256:78e327c52752653727035efa552c0d9370171e6b6695a606d936a8fee7bc6354
```

# Verification Report (Re-verification)

**Change**: chart-indicators (issue #70, Fase A1) — 3-PR feature-branch chain
**Version**: N/A (delta specs)
**Mode**: Strict TDD (`openspec/config.yaml` runner `.venv/bin/python -m pytest`)
**Branch**: `feat/chart-indicators-panes`, HEAD `d79833c` (working tree clean except this untracked report).

## Re-verification scope

This pass re-checks the two items the prior report left open:

1. **PR3 restored.** The prior report found the fix rebase had silently dropped PR3 (`1ef769e` dangling, branch tip byte-identical to the payload tip). PR3 has since been recovered by cherry-pick. HEAD is now `d79833c` — `feat(market): adapter panes, indicator toggles and pane E2E` — with the full chain `65b8e5f → 248a39c → 1df274d → 043858f → d79833c`.
2. **MACD CRITICAL stays closed.** Re-probed independently at both the function and the endpoint.

**Prior BLOCKER (PR3 dropped): CLOSED.** `git merge-base --is-ancestor d79833c HEAD` → true; `chart.js` contains the pane registry (`grep -c` = 10 for `paneIndex|PANE_ORDER|REGISTRY`); the chain diff returns to **9 files, +1224/−80** (Python + `chart.js` +254 + `chart.html` +12 + `theme.css` +4 + the 2 pane/toggle E2E tests).

**Prior CRITICAL (MACD reversed ordering → HTTP 500): remains CLOSED.** Function is no-raise for `fast > slow` / `fast == slow`; endpoint returns 400 for `fast >= slow` and 200 for `fast < slow`; default/`fast <= slow` output byte-identical.

No new defect found. Verdict moves `fail` → **`pass_with_warnings`**.

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total (Guard 15 + WU1 3 + WU2 4 + WU3 4 + Phase 4 4) | 30 |
| Tasks complete | 30 (WU3 3.1–3.4 restored with PR3) |
| Tasks incomplete | 0 |

WU3 3.1–3.4 are present again: `chart.js` `REGISTRY`/`PANE_ORDER`/pane-index rendering + rebuild-on-toggle, `chart.html` toggle fieldset, and the 2 pane/toggle E2E tests. The `tasks.md` checkboxes remain unmarked (SUGGESTION 2), but the deliverable is in the branch tip and the tests pass.

## Build & Tests Execution

**Build**: ✅ Passed (exit 0)
```text
$ .venv/bin/ruff check .            → All checks passed!
$ .venv/bin/ruff format --check .   → 104 files already formatted
$ env -u PYTHONPATH .venv/bin/python web/manage.py makemigrations --check --dry-run
                                    → No changes detected
build_exit=0
```

**Tests**: ✅ 434 passed / ❌ 0 failed / ⚠️ 8 deselected (exit 0); E2E ✅ 8 passed
```text
$ .venv/bin/python -m pytest
434 passed, 8 deselected in 55.04s
$ .venv/bin/python -m pytest -m e2e
8 passed, 434 deselected in 16.76s
$ node --test "tests/js/**/*.test.js"
tests 9 / pass 9 / fail 0
```
Note: E2E is 8/8 (prior fail-state report: 6/6) — the 2 pane/toggle tests returned with PR3. Deselected is 8 (not 6), and total collected is 442 (434 + 8).

**Coverage**: patch gate 100% (166 lines, 0 missing) → ✅
```text
$ .venv/bin/python -m pytest --cov --cov-report=xml     → 434 passed, coverage.xml written
$ .venv/bin/diff-cover coverage.xml --compare-branch=feat/chart-indicators --fail-under=100
src/indicators.py (100%), web/market/quotes.py (100%), web/market/views.py (100%)
Total: 166 lines  Missing: 0 lines  Coverage: 100%
```

## L1 — Independent Test Evidence

| Check | Command | Result |
|-------|---------|--------|
| Full suite | `.venv/bin/python -m pytest` | ✅ 434 passed, 8 deselected, exit 0 |
| E2E (real chromium) | `.venv/bin/python -m pytest -m e2e` | ✅ 8 passed, exit 0 |
| Lint | `.venv/bin/ruff check .` | ✅ All checks passed, exit 0 |
| Format | `.venv/bin/ruff format --check .` | ✅ 104 files formatted, exit 0 |
| Migration drift | `.venv/bin/python web/manage.py makemigrations --check --dry-run` | ✅ exit 0, "No changes detected" |
| JS core | `node --test "tests/js/**/*.test.js"` | ✅ 9 passed, exit 0 |
| Runtime deps unchanged | `git diff feat/chart-indicators...HEAD -- requirements.txt` | ✅ empty |
| CSP / settings unchanged | `git diff ... -- web/config/middleware.py web/config/settings/base.py` | ✅ empty |
| `chart-core.js` unchanged | `git diff ... -- web/market/templates/market/chart-core.js` | ✅ empty |
| Phase 4.4 (Playwright overlays+panes render, toggle refetch) | `test_selected_indicator_renders_a_pane`, `test_toggle_adds_and_removes_panes` | ✅ passed |

## L2 — Coverage Gates

| Gate | Command | Result |
|------|---------|--------|
| Coverage XML | `.venv/bin/python -m pytest --cov --cov-report=xml` | ✅ exit 0 |
| Patch gate | `.venv/bin/diff-cover coverage.xml --compare-branch=feat/chart-indicators --fail-under=100` | ✅ exit 0, 166 lines, 0 missing, 100% |

## CRITICAL Re-probe — the fixed defect

| Probe | Input | Result |
|-------|-------|--------|
| Direct function | `macd(range(1,40), fast=30, slow=5, signal=9)` | ✅ no raise; lens 39/39/39; line non-`None` ×10, signal non-`None` ×2 |
| Direct function | `macd(..., fast=26, slow=26, signal=9)` | ✅ no raise; `line[25] == 0.0` |
| Defaults unchanged | `macd([1,2,3,4,5], 2, 3, 2)` | ✅ `([None,None,.5,.5,.5], [None,None,None,.5,.5], [None,None,None,0,0])` — exact |
| Default warm-up | `macd(range(40))` | ✅ line warm-up 24 `None` / 25 first; signal 32 `None` / 33 first |
| **Endpoint** (raise_request_exception=False) | `...&indicators=macd&macd_fast=30&macd_slow=5` | ✅ **400** (was 500) |
| Endpoint | `...&indicators=macd&macd_fast=5&macd_slow=5` | ✅ **400** |
| Endpoint | `...&indicators=macd&macd_fast=5&macd_slow=10` | ✅ **200** |
| Endpoint | `...&indicators=macd` (defaults) | ✅ **200** |
| Endpoint | `...&indicators=macd&macd_fast=12&macd_slow=26` (explicit defaults) | ✅ **200** |

**Root cause fix intact.** `quotes.py::_parse_params` raises `ValueError` when `macd_fast >= macd_slow` (line 241); `views.py` maps it to 400. The function-level fix (`signal` EMA over the first non-`None` index of `macd_line`) keeps `fast <= slow` output unchanged. The endpoint matrix was re-run as a temporary pytest probe (5/5) and the probe file was removed.

## L3 — Spec Conformance

### technical-indicators (R1, R2, R4 — 17 scenarios)

R1 contract prose satisfied for all orderings (crash-free; `signal_line` EMA over the valid suffix). R2 warm-up table (25/33, 19, 13/15) and R4 guards verified unchanged. R1 "Deterministic output" remains **UNTESTED** (called twice, no explicit test) — WARNING 1. All other R1/R2/R4 scenarios ✅ COMPLIANT.

### market-chart (R3, R4 — 23 scenarios)

All 23 ✅ COMPLIANT. `_parse_params` ordering check strengthens "Invalid values → 400"; `test_endpoint_macd_fast_gte_slow_is_400` covers the new rejection. Backend unchanged otherwise.

### chart-live-stream (R6 — 4 scenarios)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R6 | Every active series advances on close (incl. panes) | pane render (`test_selected_indicator_renders_a_pane`) + `test_ws_same_bucket_updates_in_place`; no single test asserts every series' last point advances | ⚠️ PARTIAL |
| R6 | No mid-stream `setData` | `test_ws_stream_never_calls_setdata` | ✅ COMPLIANT |
| R6 | Toggle uses the history path | `test_toggle_adds_and_removes_panes` (asserts refetch with `indicators=…macd…`) | ✅ COMPLIANT |
| R6 | No series deforms on refresh | `upsertCandle` monotonic (node) + inspection | ⚠️ PARTIAL |

**Compliance summary**: **41/44 scenarios compliant**, 2 PARTIAL (W1), 1 UNTESTED (W1), 0 FAILING-by-test. Restoring PR3 recovered the "Toggle uses the history path" scenario from UNTESTED → COMPLIANT (was 40 → now 41). The remaining 3 non-compliant are the pre-existing WARNING 1 items only.

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| R1 pure functions | ✅ Implemented | `macd` crash-free for any ordering; `fast <= slow` output unchanged |
| R2 warm-up alignment | ✅ Implemented | 25/33, 19, 13/15 verified unchanged |
| R4 divide-by-zero | ✅ Implemented | guards intact |
| R3 kline endpoint | ✅ Implemented | validation → 400 incl. ordering check; `{candles,overlays,panes}` |
| R4 derived warm-up | ✅ Implemented | `max(20, max first_valid)` |
| R6 active series on close | ✅ Implemented | generalized `updateLastPoint` for every active series; rebuild-on-toggle via history path |
| Single-source math / boundary / no-dep | ✅ Implemented | `git diff` empty for `requirements.txt`, CSP, `chart-core.js` |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| (a) Server-selected set vs client selection | ✅ Yes | server selects + client registry renders the active set |
| (b) Derived warm-up `max(20, …)` | ✅ Yes | |
| (c) Pane rebuild vs incremental surgery | ✅ Yes | `chart.js` `REGISTRY`/`PANE_ORDER`/pane indices + `chart.remove()` rebuild-on-toggle |
| (d) Exact-5-key candles via `panes` bucket | ✅ Yes | |
| Volume = `quote_vol` | ✅ Yes | |
| MACD ordering validated server-side | ✅ Yes | `_parse_params` rejects `fast >= slow` |

## Issues Found

### CRITICAL — none open.

MACD `fast >= slow` no longer 500s: `macd(..., 30, 5, 9)` does not raise; the endpoint returns 400 for `fast >= slow` and 200 for `fast < slow`; default output unchanged (exact fixtures re-verified). Remains closed.

### BLOCKER — none open.

PR3 is present in the branch tip: `d79833c` is an ancestor of HEAD; `chart.js` has the pane registry (`grep -c` = 10); chain diff = 9 files, +1224/−80; E2E 8/8. Prior blocker closed.

### WARNING 1 (remains) — R6 "Every active series advances" and "No series deforms" are verified by inspection / partial tests only, and R1 "Deterministic output" has no call-twice test.

`test_ws_stream_never_calls_setdata` proves the single-write-path (`update()` only) but does not assert that *every active series'* last point advances at close; `upsertCandle` (node) covers candle monotonicity, not indicator-series alignment. R1 "Deterministic output" (spec: call a function twice, results equal) has no explicit test.

### WARNING 2 (resolved) — server registry vs JS adapter.

Prior warning (server exposes tokens the JS adapter cannot render) is moot: the `REGISTRY` maps `sma20`/`ema20`/`bollinger`/`vwap` overlays and `rsi`/`macd`/`stochastic`/`atr`/`volume` panes, and the pane/toggle E2E render + rebuild them.

### WARNING 3 (remains) — MACD default-parameter fixture is monotonic.

`test_macd_default_warmup_is_25_line_33_signal` uses `[float(i) for i in range(40)]`, so `line` is constant and `histogram` is 0. No test asserts a non-trivial default-parameter MACD curve. Unchanged by the fixes.

### SUGGESTION 1 — `_parse_params` rejects the MACD invariant even when `macd` is not selected.

`indicators=sma&macd_fast=30&macd_slow=5` → 400 although MACD is not requested (`macd_fast`/`macd_slow` carry defaults that trigger the check globally). Over-rejection is safe but stricter than the spec's per-indicator contract. Consider gating the check on `"macd" in names`. Low impact (no UI path emits these).

### SUGGESTION 2 — `tasks.md` checkboxes unmarked (unchanged).

## TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | apply-progress `#1433` RED→GREEN table |
| All tasks have tests | ✅ | WU1/WU2 unit/integration + WU3 pane/toggle E2E all present |
| RED confirmed (tests exist) | ✅ | PR1/PR2 regression tests + PR3 E2E tests exist |
| GREEN confirmed (tests pass) | ✅ | 434/434 + E2E 8/8 on independent execution |
| Triangulation adequate | ✅ | MACD triangulated for `fast > slow`, `fast == slow`; panes render/toggle triangulated |
| Safety Net for modified files | ✅ | baseline green; new tests only added |

**TDD Compliance**: 6/6 checks passed.

### Assertion Quality

Scanned new/changed tests. `test_macd_fast_greater_than_slow_does_not_raise` asserts length equality + `any(v is not None)` (behavioral, exercises the crash path). `test_endpoint_macd_fast_gte_slow_is_400` asserts status 400 + `error` in body (behavioral). `test_toggle_adds_and_removes_panes` asserts DOM pane count change + a refetch URL containing the toggled token (behavioral). `test_selected_indicator_renders_a_pane` asserts the exposed series has data. No tautologies, no assertion-without-production-call, no ghost loops. **Assertion quality**: ✅ All assertions verify real behavior.

## Verdict

**PASS WITH WARNINGS**

Both prior findings are closed. The MACD CRITICAL is genuinely fixed (`macd` crash-free for reversed/equal ordering; endpoint 400 for `macd_fast >= macd_slow`, 200 for `fast < slow`; default output byte-identical). The PR3 blocker is resolved — the branch tip `d79833c` contains the adapter pane registry, the toggle fieldset, and the 2 pane/toggle E2E tests. All L1/L2 gates are green: 434 passed, E2E 8 passed, ruff clean, migrations clean, patch gate 100% on 166 lines, no new dep, CSP/`chart-core.js` unchanged.

41/44 scenarios are compliant; the 3 remaining are pre-existing inspection/partial coverage items (WARNING 1: R6 "Every active series advances", R6 "No series deforms", R1 "Deterministic output") plus the unchanged WARNING 3 fixture monotonicity. None block the change. Warning-level issues only → `pass_with_warnings`.

## Traceability

| Artifact | Reference |
|----------|-----------|
| Proposal | `openspec/changes/chart-indicators/proposal.md` |
| Design | `openspec/changes/chart-indicators/design.md` |
| Tasks | `openspec/changes/chart-indicators/tasks.md` (30 tasks; all present in branch) |
| Delta specs | `specs/technical-indicators/spec.md`, `specs/market-chart/spec.md`, `specs/chart-live-stream/spec.md` |
| Code | `src/indicators.py`, `web/market/quotes.py`, `web/market/views.py`, `web/market/templates/market/chart.js`, `chart.html`, `web/accounts/templates/registration/theme.css` |
| Tests | `tests/test_indicators.py`, `tests/web/test_market_api.py`, `tests/web/test_market_e2e.py`, `tests/js/chart-core.test.js` |
| Apply evidence | Engram `#1433` (`sdd/chart-indicators/apply-progress`) |
| Commits | PR1 `248a39c`, PR2 `043858f`, PR3 `d79833c` (recovered via cherry-pick of `1ef769e`) |
| Chain diff | `git diff feat/chart-indicators...HEAD` — 9 files, +1224/−80 |
| Probes | `/tmp/opencode/probe_rv2.py`, `/tmp/opencode/rv2_*.txt` (repo untouched; temp pytest probe removed) |
