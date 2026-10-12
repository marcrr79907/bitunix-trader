```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:44cbfa736592bc860e87cb69ca7c937213039e48df848d79ea7de115607d86aa
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 10/10
scenarios: 34/36
test_command: .venv/bin/python -m pytest
test_exit_code: 0
test_output_hash: sha256:6c3a828bd98e33d7f6877d05ea91feccd54a24ae9c6f7b76baa700803dba7b07
test_output_summary: "468 passed, 14 deselected (E2E excluded); E2E -m e2e: 14 passed; web cov 97.86%"
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python web/manage.py makemigrations --check --dry-run
build_exit_code: 0
build_output_hash: sha256:ee0b081a67fbdc096d196f45efb1eaee830a594da48e492c9adc61a10f66aca8
```

# Verification Report

**Change**: chart-config (issue #71, Fase A2) — 3-PR feature-branch chain
**Version**: N/A (delta specs)
**Mode**: Strict TDD (`openspec/config.yaml` `strict_tdd: true`, runner `.venv/bin/python -m pytest`)
**Branch**: `feat/chart-config-boot`, HEAD `8e25b55` (working tree clean).
**Chain**: tracker `feat/chart-config` → PR1 `f9dd867` → PR2 `425eb60` → PR3 `8e25b55`. All three are ancestors of HEAD (`git merge-base --is-ancestor` true ×3). Chain diff vs tracker: 12 files, +887/−32.

This verifier is fresh and adversarial: every claim below was reproduced from the current branch, not trusted from the apply report. Independent probes ran from `/tmp/opencode/probe_layout.py` (repo untouched; no probe file left in the tree).

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total (WU1 4 + WU2 5 + WU3 4) | 13 |
| Tasks complete | 13 |
| Tasks incomplete | 0 |

`tasks.md` shows WU3 3.1–3.4 marked `[x]` (4/28 checkbox lines); WU1/WU2 lines are still `[ ]` although their deliverables are in the branch tip (commits `f9dd867`, `425eb60`) — cosmetic, see SUGGESTION.

## Build & Tests Execution

**Build**: ✅ Passed (exit 0)
```text
$ .venv/bin/ruff check .            → All checks passed!
$ .venv/bin/ruff format --check .   → 105 files already formatted
$ .venv/bin/python web/manage.py makemigrations --check --dry-run → No changes detected
build_exit=0
```

**Tests**: ✅ 468 passed / ❌ 0 failed / ⚠️ 14 deselected (exit 0); E2E ✅ 14 passed
```text
$ .venv/bin/python -m pytest
468 passed, 14 deselected in 73.21s
$ .venv/bin/python -m pytest -m e2e
14 passed, 468 deselected in 31.34s
$ node --test "tests/js/**/*.test.js"
tests 9 / pass 9 / fail 0
```

**Coverage**: web gate 97.86% (floor 85%) → ✅ Above; patch gate 100% → ✅
```text
$ .venv/bin/python -m pytest --cov --cov-report=xml   → 468 passed, coverage.xml written
$ .venv/bin/diff-cover coverage.xml --compare-branch=feat/chart-config --fail-under=100
web/market/quotes.py (100%), web/market/views.py (100%), web/trading/models.py (100%)
Total: 77 lines  Missing: 0  Coverage: 100%
$ .venv/bin/python -m pytest --cov=web --cov-fail-under=85 → 97.86% (482 passed, E2E incl.)
```

## L1 — Independent Test Evidence

| Check | Command | Result |
|-------|---------|--------|
| Full suite | `.venv/bin/python -m pytest` | ✅ 468 passed, 14 deselected, exit 0 |
| E2E (real chromium) | `.venv/bin/python -m pytest -m e2e` | ✅ 14 passed, exit 0 |
| Guard + boundary + order-scan | `pytest tests/web/test_owned_model_guard.py tests/test_boundary.py tests/web/test_no_order_surface.py` | ✅ 61 passed |
| Lint / format | `ruff check .` / `ruff format --check .` | ✅ exit 0 |
| Migration drift | `manage.py makemigrations --check --dry-run` | ✅ "No changes detected" |
| Runtime deps unchanged | `git diff develop...HEAD -- requirements.txt` | ✅ empty |
| CSP / settings unchanged | `git diff develop...HEAD -- web/config/` | ✅ empty |
| `chart-core.js` unchanged | `git diff develop...HEAD -- .../chart-core.js` | ✅ empty |
| Migration additive | `0005_chartlayout.py` = `CreateModel` only, no Remove/Alter/Delete | ✅ additive |
| Migration deps | `("trading","0004_private_snapshots")` + swappable user | ✅ |

## L2 — Coverage Gates

| Gate | Command | Result |
|------|---------|--------|
| Coverage XML | `pytest --cov --cov-report=xml` | ✅ exit 0 |
| Patch gate | `diff-cover coverage.xml --compare-branch=feat/chart-config --fail-under=100` | ✅ 77 lines, 0 missing, 100% |
| Web gate | `pytest --cov=web --cov-fail-under=85` | ✅ 97.86% |

## L3 — Spec Conformance

### chart-config (R1–R7 — 21 scenarios)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R1 | Distinct intervals coexist | `test_isolation.py > test_chart_layout_distinct_intervals_coexist` | ✅ COMPLIANT |
| R1 | Duplicate key rejected | `test_isolation.py > test_chart_layout_duplicate_key_rejected` | ✅ COMPLIANT |
| R1 | JSON round-trip | `test_isolation.py > test_chart_layout_json_round_trip` | ✅ COMPLIANT |
| R2 | GET no layout → default | `test_market_api.py > test_layout_get_without_row_returns_default_not_404` | ✅ COMPLIANT |
| R2 | GET after PUT → saved | `test_market_api.py > test_layout_put_then_get_returns_saved_set` | ✅ COMPLIANT |
| R2 | PUT upserts one row | `test_market_api.py > test_layout_put_upserts_one_row_for_the_same_key` | ✅ COMPLIANT |
| R2 | Invalid token → 400 | `test_market_api.py > test_layout_put_invalid_token_is_400_and_writes_nothing` | ✅ COMPLIANT |
| R2 | Unauthenticated → redirect | `test_layout_anonymous_get/put_redirects_to_login` | ✅ COMPLIANT |
| R3 | B cannot read A's layout | `test_isolation.py > test_chart_layout_cross_user_get_denied` | ✅ COMPLIANT |
| R3 | B's GET never leaks A's | `test_market_api.py > test_layout_isolation_b_get_never_sees_a` | ✅ COMPLIANT |
| R3 | B's PUT doesn't touch A | `test_market_api.py > test_layout_isolation_b_put_does_not_touch_a_row` | ✅ COMPLIANT |
| R3 | Guard covers the new model | `test_owned_model_guard.py > test_scanner_flags_the_private_models[ChartLayout.objects.all()]` | ✅ COMPLIANT |
| R4 | Reload restores toggles | `test_market_e2e.py > test_boot_restores_saved_layout` | ✅ COMPLIANT |
| R4 | Fetch failure falls back | `test_market_e2e.py > test_fetch_failure_falls_back_to_dom_defaults` | ✅ COMPLIANT |
| R4 | Switch loads target layout | `test_market_e2e.py > test_switch_loads_target_layout` | ✅ COMPLIANT |
| R5 | Toggle → debounced PUT | `test_market_e2e.py > test_toggle_fires_one_debounced_put` | ✅ COMPLIANT |
| R5 | Payload pins the active chart | (none races a switch mid-debounce) | ⚠️ PARTIAL |
| R6 | Length edit takes effect | `test_saved_sma_ema_length_uses_server_token` (request carries `sma_len=50`) + `test_endpoint_param_overrides_reach_the_builder` | ✅ COMPLIANT |
| R6 | Default matches prior rendering | (no suite regression test; probe confirms equality) | ⚠️ PARTIAL |
| R7 | CSP unchanged | `test_market_ux.py > test_csp_present_on_market_page` + empty `web/config` diff | ✅ COMPLIANT |
| R7 | No inline handler / new dep | `test_shell.py > test_no_inline_event_handler_in_templates` / `test_no_inline_script_tag` + empty `requirements.txt` diff | ✅ COMPLIANT |

### per-user-isolation (R14.2, R14.3 — 10 scenarios)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R14.2 | A cannot read B's ExchangeCredential | `test_isolation.py > test_cross_user_get_denied` | ✅ COMPLIANT |
| R14.2 | A cannot read B's Watchlist | `test_isolation.py > test_cross_user_get_denied` | ✅ COMPLIANT |
| R14.2 | A cannot read B's PositionSnapshot | `test_cross_user_get_denied_for_private_models` | ✅ COMPLIANT |
| R14.2 | A cannot read B's AccountSnapshot | `test_cross_user_get_denied_for_private_models` | ✅ COMPLIANT |
| R14.2 | A cannot read B's Trade | `test_cross_user_get_denied_for_private_models` | ✅ COMPLIANT |
| R14.2 | A cannot read B's ChartLayout | `test_chart_layout_cross_user_get_denied` | ✅ COMPLIANT |
| R14.3 | Scanner flags an unscoped query | `test_owned_model_guard.py > test_scanner_flags_an_unscoped_owned_query` | ✅ COMPLIANT |
| R14.3 | Scanner flags the new models | `test_scanner_flags_the_private_models[ChartLayout…]` | ✅ COMPLIANT |
| R14.3 | Scoped query passes | `test_scanner_allows_for_user[_on_the_private_models]` | ✅ COMPLIANT |
| R14.3 | bulk_create and count sanctioned | `test_request_path_has_no_unscoped_owned_query` (scans `web/trading/sync.py`; `bulk_create`/`count` are not scanner verbs) | ✅ COMPLIANT |

### market-chart (R10 — 5 scenarios)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R10 | GET default when no layout | `test_market_api.py > test_layout_get_without_row_returns_default_not_404` | ✅ COMPLIANT |
| R10 | PUT then GET returns saved | `test_market_api.py > test_layout_put_then_get_returns_saved_set` | ✅ COMPLIANT |
| R10 | Invalid indicator → 400 | `test_market_api.py > test_layout_put_invalid_token_is_400_and_writes_nothing` | ✅ COMPLIANT |
| R10 | Per-user isolation | `test_market_api.py > test_layout_isolation_b_get_never_sees_a` | ✅ COMPLIANT |
| R10 | Market page stays CSP-clean | `test_market_ux.py > test_csp_present_on_market_page` + `test_shell.py` inline scans | ✅ COMPLIANT |

**Compliance summary**: **34/36 scenarios compliant**, 2 PARTIAL (W1, W2), 0 UNTESTED, 0 FAILING. Requirements: **10/10** with covering tests.

## Adversarial Probes (throwaway, `/tmp/opencode/probe_layout.py`)

| Probe | Input | Result |
|-------|-------|--------|
| Model: intervals coexist | `(A,BTCUSDT,1m)` + `(A,BTCUSDT,1h)` | ✅ 2 rows |
| Model: dup key | second `(A,BTCUSDT,1m)` | ✅ `IntegrityError` |
| Model: A≠B | `for_user(B).get(pk=A.pk)` | ✅ `DoesNotExist` |
| Endpoint: GET default | no row | ✅ 200, `exists:false`, `[sma,ema,rsi]` |
| Endpoint: PUT→GET | `sma len 50` | ✅ 200, round-trips verbatim |
| Endpoint: invalid token | `[{"token":"zzz"}]` | ✅ 400 |
| Endpoint: A≠B PUT | B writes same key | ✅ A row unchanged, B gets own row |
| Endpoint: anonymous | GET + PUT | ✅ 302 both |
| Adapter: no indicator MATH in JS | grep for reduce/sum/avg/rolling | ✅ none (only `Math.pow` for WS backoff) |
| Adapter: live stream uses `update` | `chart.js` write sites | ✅ `candleSeries.update(bar)` (L337) is the only live write; `setData` only in history/pagination/toggle |
| Adapter: async boot + fallback | `boot()`/`loadLayout` | ✅ `loadLayout().then(build→connect→fetch)`; `.catch` → `readIndicators()`/`readParams()`; never blank |
| Adapter: CSRF meta | `chart.html` head | ✅ `<meta name="csrf-token" content="{{ csrf_token }}">` |
| Adapter: rebuild carries captured key | `saveLayout` | ✅ `symbol`/`interval` captured before `setTimeout` |
| R6: default equivalence | `_b_sma(p)` vs `_b_sma20(p)`, `_b_ema` vs `_b_ema20` | ✅ `sma==sma20` True, `ema==ema20` True; `sma_len=50` differs True |
| Guard negative control | unscoped `ChartLayout.objects.get` in tmp file | ✅ flagged; `for_user(...).get` not flagged |
| Registry drift | server `REGISTRY` vs JS `REGISTRY` keys | ✅ identical (excluding legacy `sma20`/`ema20`/`rsi14`) |

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| R1 model | ✅ Implemented | `ChartLayout(UserOwnedModel)` — FK CASCADE via base, `for_user`, JSON `indicators` default list, `updated_at` auto_now, `UniqueConstraint(user,symbol,interval)` |
| R2/R10 API | ✅ Implemented | `api_layout` GET/PUT `@login_required`; GET miss → 200 default; PUT validates before write; `for_user(...).update_or_create(user=request.user, …)` |
| R3/R14 isolation | ✅ Implemented | Every access through `for_user`; `ChartLayout` in `OWNED_MODELS`; real-tree scan clean |
| R4 restore | ✅ Implemented | Async `boot()`; `loadLayout` before build; `.catch` → DOM defaults; `switchTo` loads target layout first |
| R5 save | ✅ Implemented | Debounced 500 ms PUT with captured `symbol`/`interval`; `.catch` silent |
| R6 tokens/params | ✅ Implemented | JS + HTML moved to `sma`/`ema`; server builders param-driven; default 20 == prior rendering |
| R7 CSP/deps | ✅ Implemented | No inline script/handler; CSRF meta; `requirements.txt` + `web/config` diffs empty |
| Single write path (#68) | ✅ Implemented | WS `update()` only; `setData` confined to history/pagination/toggle |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| Unique key `(user,symbol,interval)` | ✅ Yes | migration + constraint |
| JSON `indicators` vs granular columns | ✅ Yes | `JSONField(default=list)` |
| Boot async with DOM-default fallback | ✅ Yes | `loadLayout().catch → readIndicators` |
| Endpoint home `market/views.py` | ✅ Yes | `market → trading.models` direction kept |
| CSRF meta (no inline) | ✅ Yes | `<meta name="csrf-token">` |
| `update_or_create(user=…)` explicit | ✅ Yes | Deviation documented in apply-progress (`for_user` filter dropped on CREATE); still scoped on read |
| `gen` generation counter (not in design) | ✅ Yes | Closes boot/switch race; small additive guard; verified by inspection |
| `marketChart.ready` test seam | ✅ Yes | Read-only DOM seam, not a behavior change |

## Issues Found

### CRITICAL

None.

### BLOCKER

None.

### WARNING 1 — R5 "Payload pins the active chart" is not race-tested (⚠️ PARTIAL).

`test_toggle_fires_one_debounced_put` asserts the payload carries the active `symbol`/`interval` in the ordinary case, but no test schedules a debounce, then performs `switchTo`, and asserts the pending PUT still carries the *captured* key. The capture-at-change-time logic is correct by inspection (`chart.js` L442–451 snapshots `state.symbol`/`state.interval` before `setTimeout`), and the `gen` counter guards the reverse race (a stale layout load clobbering a newer chart). Non-blocking: the guarantee holds in code, only the racing ordering lacks a regression test.

### WARNING 2 — R6 "Default matches prior rendering" has no suite regression test (⚠️ PARTIAL).

No test asserts `sma`/`ema` at default length 20 equals the former `sma20`/`ema20` output. The independent probe confirms exact equality (`_b_sma(ctx,p)['sma'] == _b_sma20(ctx,p)['sma20']` True; `_b_ema` likewise True), and `sma_len=50` provably differs. The equivalence is real but unguarded; a future default change would regress silently.

### WARNING 3 — Cross-token param accepted by `parse_layout_indicators`.

`parse_layout_indicators([{"token":"ema","params":{"sma_len":9}}])` is accepted (probe: prints the entry verbatim). `_validate_layout_params` validates each key against the global `_INT_PARAMS`/`_FLOAT_PARAMS` sets, not against the *token's* relevant params, so a valid-but-mismatched key (`sma_len` on the `ema` token) is stored. The `ema` builder reads `ema_len` (default 20) and ignores `sma_len`, so rendering is unaffected — the stored JSON merely carries a meaningless key. Low impact; no UI path emits it.

### WARNING 4 — API accepts legacy tokens the JS adapter cannot render.

`parse_layout_indicators([{"token":"sma20"}])` is accepted (probe) because `sma20`/`ema20`/`rsi14` remain in the server `REGISTRY` for kline back-compat. The adapter's `REGISTRY` (and the toggles) only know `sma`/`ema`/`rsi`, so a layout storing a legacy token returns 200 on GET but `applyLayout` unchecks every toggle and `buildChart` renders no indicator series (candles still render — degraded, not fully blank). No current UI path stores legacy tokens (toggles emit `sma`/`ema`), so this is only reachable via a hand-crafted PUT. Consider restricting layout tokens to the adapter's vocabulary, or mapping legacy tokens on read.

### SUGGESTION 1 — `tasks.md` checkboxes for WU1/WU2 remain unmarked.

Only WU3 3.1–3.4 are `[x]`; WU1/WU2 lines are `[ ]` although their commits (`f9dd867`, `425eb60`) are in the chain. Cosmetic; matches the known pattern from the `chart-indicators` report.

### SUGGESTION 2 — No node test for the `chart.js` adapter.

`tests/js/chart-core.test.js` (9 tests) covers the pure core only. The adapter logic added here (debounced PUT, key capture, `loadLayout` apply/fallback, `switchTo` ordering, token migration) is exercised solely by E2E. Acceptable given the E2E layer, but a pure extraction of the debounce/capture logic would allow a unit test.

## TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | apply-progress `#1444` RED→GREEN table present |
| All tasks have tests | ✅ | WU1 (isolation/guard/model), WU2 (endpoint/validator), WU3 (E2E) all present |
| RED confirmed (tests exist) | ✅ | test files exist and reference the new model/endpoint/adapter seams |
| GREEN confirmed (tests pass) | ✅ | 468/468 + E2E 14/14 on independent execution |
| Triangulation adequate | ✅ | model 6 cases; endpoint 23 cases; E2E 6 layout cases incl. parametrized `sma`/`ema` |
| Safety Net for modified files | ✅ | baseline green before each slice; new tests only added |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit (validator/parser) | ~10 | `test_market_api.py` (`parse_layout_indicators`) | pytest |
| Integration (endpoint/model/guard) | ~35 | `test_market_api.py`, `test_isolation.py`, `test_owned_model_guard.py` | pytest + Django client |
| E2E | 14 | `test_market_e2e.py` | Playwright (chromium, available) |
| JS core (node) | 9 | `tests/js/chart-core.test.js` | node --test |
| **Layout-specific total** | **~26** | 4 files | |

### Changed File Coverage

| File | Line % | Uncovered Lines | Rating |
|------|--------|-----------------|--------|
| `web/trading/models.py` | 100% (patch) | — | ✅ Excellent |
| `web/market/quotes.py` | 100% (patch) | — | ✅ Excellent |
| `web/market/views.py` | 100% (patch) | — | ✅ Excellent |
| `web/market/templates/market/chart.js` | E2E-covered (no Python line) | — | ✅ (DOM/E2E layer) |
| `web/market/templates/market/chart.html` | E2E-covered | — | ✅ |
| `tests/web/*` | n/a (test code) | — | — |

**Average changed Python file coverage**: 100% (patch gate, 77 lines). PR3's adapter has no Python lines → diff-cover reports "no lines with coverage information"; E2E is its verification layer (per apply hard contract).

### Assertion Quality

Scanned all changed tests. Behavioral assertions dominate: status-code + body-shape + row-count + isolation-proof (`A row unchanged`) + DOM/toggle state + request-URL capture. Three `… is not None` assertions exist (`test_market_api.py` L404–405, L646) but each is **combined** with a value/length/shape assertion in the same test (`sma20[0]["time"] == times[20]`, `macd[0]["time"] == …`), so they are not type-only. No tautologies, no assertion-without-production-call, no ghost loops.

**Assertion quality**: ✅ All assertions verify real behavior.

### Quality Metrics

**Linter**: ✅ No errors (`ruff check .`)
**Type Checker**: ➖ Not applicable (no type checker configured)
**Formatter**: ✅ 105 files already formatted

## Verdict

**PASS WITH WARNINGS**

The full chain is present (`f9dd867` → `425eb60` → `8e25b55`, all ancestors of HEAD) and every L1/L2 gate is green: 468 passed + 14 E2E, ruff + format clean, `makemigrations --check` clean, patch gate 100% on 77 lines, web coverage 97.86%, `requirements.txt`/CSP/`chart-core.js` unchanged. 10/10 requirements and 34/36 scenarios are compliant; the model, endpoint, isolation/guard, adapter boot, and CSP contracts were all independently reproduced, including a negative-control guard probe and JS inspection confirming no indicator math, an `update()`-only live stream, and an async boot with a DOM-default fallback.

The 2 non-compliant scenarios are PARTIAL (WARNING 1: the racing-switch payload-pinning ordering is untested but correct by inspection; WARNING 2: the `sma`/`ema` = `sma20`/`ema20` default equivalence is probe-verified but has no suite regression test). Two additional non-blocking API holes are documented (WARNING 3: cross-token params accepted; WARNING 4: legacy tokens storable but not renderable by the adapter). No CRITICAL, no BLOCKER, no FAILING test → **pass_with_warnings**.

## Traceability

| Artifact | Reference |
|----------|-----------|
| Proposal | `openspec/changes/chart-config/proposal.md` |
| Design | `openspec/changes/chart-config/design.md` |
| Tasks | `openspec/changes/chart-config/tasks.md` (13 WU tasks; 13 complete) |
| Delta specs | `specs/chart-config/spec.md`, `specs/per-user-isolation/spec.md`, `specs/market-chart/spec.md` |
| Code | `web/trading/models.py`, `web/trading/migrations/0005_chartlayout.py`, `web/market/{views,urls,quotes}.py`, `web/market/templates/market/{chart.js,chart.html}` |
| Tests | `tests/web/test_isolation.py`, `tests/web/test_owned_model_guard.py`, `tests/web/test_market_api.py`, `tests/web/test_market_e2e.py` |
| Apply evidence | Engram `#1444` (`sdd/chart-config/apply-progress`) |
| Commits | PR1 `f9dd867`, PR2 `425eb60`, PR3 `8e25b55` |
| Chain diff | `git diff feat/chart-config...HEAD` — 12 files, +887/−32 |
| Probes | `/tmp/opencode/probe_layout.py` (11 passed; repo untouched) |
