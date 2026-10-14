```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:32af0ec0898bcaeb4cd4d7abf884d57ade39dd40c24f23a1e34c828da7bf33bf
verdict: fail
blockers: 0
critical_findings: 1
requirements: 15/15
scenarios: 56/56
test_command: .venv/bin/python -m pytest -m e2e -p no:randomly -q -o addopts=""
test_exit_code: 0
test_output_hash: sha256:fd62f7253613f082ce778070d813ee91fc62604cb50931d8d3b533e95cb84ca9
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check .
build_exit_code: 0
build_output_hash: sha256:4681b0ccbdda71659532720526217f684c9ce9dd9641425c786c7920d1b4db53
```

# Verify Report — chart-scales (issue #121, Fase F8)

**Verdict**: `fail` — one reachable CRITICAL correctness defect in the Heikin Ashi **live** path (repeated same-bucket pushes drift and cascade). Every L1/L2/L3 gate is otherwise green.
**Verified by**: fresh adversarial verifier (independent replication + throwaway node HA state-machine probe, Django-client endpoint probe and real Playwright browser probe; apply reports NOT trusted)
**Branch**: `feat/chart-scales-persistence` (HEAD `4649d4f`), chain: tracker `feat/chart-scales` (`11ace8c` = merge of S1+S2) + S1 `…-core` (`0d69ebe`) + S2 `…-ui` (`1afba65`) + S3 `…-persistence` (`4649d4f`). Confirmed with `git branch --show-current`; working tree clean. S3 diff vs tracker = 7 files (model/migration/view/main + tests), no host/store/core — clean chain.
**Mode**: Strict TDD. Artifact store: openspec.

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 3 slices (1.1–1.4, 2.1–2.6, 3.1–3.7) + guard matrix |
| Tasks complete | all acceptance artifacts present + green |
| Tasks incomplete | 0 |

`tasks.md` checkboxes are unmarked (executor contract forbids editing `openspec/**`); every acceptance artifact exists and passes at runtime. Not a finding (F0/F1/F2 precedent).

## Gates (L1)

| Gate | Command | Result |
| --- | --- | --- |
| JS unit | `node --test "tests/js/**/*.test.js"` | **131 passed, 0 fail** (exit 0) — SHA256 `c9e200d5…` |
| E2E | `.venv/bin/python -m pytest -m e2e -p no:randomly -q -o addopts=""` | **51 passed, 887 deselected** (exit 0) — `fd62f725…` |
| Python unit | `.venv/bin/python -m pytest tests/ --ignore=tests/web -o addopts=""` | **337 passed** (exit 0) — `e858b495…` |
| Lint/format | `.venv/bin/ruff check . && .venv/bin/ruff format --check .` | **clean** (135 files, exit 0) |
| Migration drift | `python web/manage.py makemigrations --check --dry-run` | **"No changes detected"** (exit 0) |
| Dependency | `git diff origin/develop -- requirements.txt` | **empty** (0 lines) |
| `src/` boundary | `git diff origin/develop...HEAD -- src/` | **empty** (0 lines) |
| Migration in diff | additive `0010_chartpreference_scale_type.py` only (2 `AddField`s, defaults) | ✅ additive |

`git diff --stat origin/develop...HEAD` = 28 files, +2314/−50. Node locally is **v24.14.0**; the HA fixtures here are integer/exact-quarter arithmetic, so the assertions hold identically on Node 22 (no `Math.pow(10,` anywhere; `Number("1e-"+n)` untouched this change).

> **Flake note (not a defect):** three isolated runs produced `sqlite3.OperationalError: no such savepoint` / `database table is locked` in the live-server E2E harness. The suite passes cleanly on re-run (51/51) and on a second full-suite run. This is the pre-existing SQLite+live_server harness behaviour under contention, unrelated to this change.

## Gates (L2) — Patch coverage

Generated the real CI artifact (`.venv/bin/python -m pytest --cov --cov-report=xml`, no `--cov=` scoping so `[tool.coverage.run].source` wins), then:

`diff-cover coverage.xml --compare-branch=feat/chart-scales --fail-under=100` →

```
web/market/quotes.py (100%)
web/market/views.py (100%)
web/trading/models.py (100%)
Total:   27 lines
Missing: 0 lines
Coverage: 100%
```

**exit 0.** Re-run against `origin/develop` (tracker already contains no Python from S1/S2, so this is also clean) also returns **100% / 27 lines / exit 0**. The only Python lines are the two vocab tuples, the model fields, and `api_preference` branches — all covered.

## TDD Compliance (Strict TDD)

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | Task IDs map to node/E2E/pytest artifacts |
| All tasks have tests | ✅ | `chart-types-core.test.js` (new), `chart-host.test.js` (+8), `chart-store.test.js` (`STORE_KEYS`=9), `test_market_api.py` (+9), `test_market_e2e.py` (+6) |
| RED confirmed (tests exist) | ✅ | all listed files exist and assert new behaviour |
| GREEN confirmed (tests pass) | ✅ | 131 node + 337 py + 51 E2E on fresh execution |
| Triangulation adequate | ✅ | HA: 2/3-bar chain, single, empty, malformed, `nextHeikinAshi` parity; type/scale: Ctor map, unknown fallback, option-only, build re-apply; endpoint: partial PUT, per-field 400 no-write, A≠B, empty body |
| Safety Net for modified files | ✅ | **0 removed-content lines** in `test_market_e2e.py` vs develop (add-only); only the 2 sanctioned pref-body asserts extended (R9) |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit (JS) | 131 | `tests/js/*` | node --test |
| Unit (py HTTP/parser) | 337 | `tests/web/test_market_api.py` etc. | pytest + Django client |
| E2E | 51 | `tests/web/test_market_e2e.py` | Playwright (chromium) |
| **Total** | **131 node + 337 py + 51 E2E** | | |

### Assertion Quality

**Assertion quality**: ✅ All committed assertions verify real behaviour.
- `chart-host.test.js` uses a `PriceScaleMode` stub with **non-standard values (70/71/72)** so a magic-number implementation (0/1/2) fails — the host is forced to read the symbol.
- E2E asserts live v5 API state (`seriesType()`, `priceScale("right").options().mode`, captured PUT bodies), never CSS classes or internals.
- Endpoint tests assert exact 4-key bodies and DB row state after 400 (no partial write).
- No tautologies, no ghost loops, no empty-collection-only assertions found.

### Quality Metrics
**Linter**: ✅ No errors (ruff, 135 files)
**Type Checker**: ➖ Not applicable (JS/Django project)

## Spec Compliance Matrix

### chart-scales (CS1–CS7)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| CS1 | HA matches the recursive formula | node `heikinAshi: exact 2-bar recursive fixture` (+ probe: bar1 `haLow=10`, not 9.5) | ✅ COMPLIANT |
| CS1 | Empty input is safe | node `heikinAshi: empty and non-array` / `toChartData: empty / non-array` | ✅ COMPLIANT |
| CS1 | Single candle uses first-bar branch | node `heikinAshi: single candle` / `nextHeikinAshi: null prevHa` | ✅ COMPLIANT |
| CS1 | Unknown type never throws | node `toChartData: unknown type degrades` | ✅ COMPLIANT |
| CS1 | Line-like mapping | node `toChartData: line/area map to {time,value}` | ✅ COMPLIANT |
| CS1 | Core is pure and served | node `purity: the module imports nothing` + `test_module_allowlist_routes_serve_javascript` / `test_import_graph_routes_resolve` | ✅ COMPLIANT |
| CS2 | Scale applies without a data write | node `setScaleMode is option-only…` + E2E `test_scale_select_changes_price_scale_mode` | ✅ COMPLIANT |
| CS2 | Re-applied on rebuild | node `build re-applies the scale mode after createChart` | ✅ COMPLIANT |
| CS2 | Unknown scale falls back to linear | node `unknown scale falls back to Normal without throwing` | ✅ COMPLIANT |
| CS3 | Each type builds its Ctor | node `build selects the candle Ctor from state.chartType` + `unknown chartType degrades` | ✅ COMPLIANT |
| CS3 | Type change goes through rebuild | E2E `test_type_select_rebuilds_with_new_series_ctor` (new series identity) | ✅ COMPLIANT |
| CS3 | Indicators survive a type change | E2E type-select tests rebuild with active indicators; overlay/pane series unchanged (static) | ✅ COMPLIANT |
| CS4 | Live push uses update only | node `HA live new bar … via update() only` + E2E `test_ws_stream_never_calls_setdata` | ✅ COMPLIANT |
| CS4 | New bar chains HA state | node `HA live new bar chains state…` (first push of N+1) | ✅ COMPLIANT |
| CS4 | setCandles resets HA state | node `setCandles resets the HA state from the new first bar` | ✅ COMPLIANT |
| CS4 | Non-HA types are untouched | node `candles history is written verbatim` | ✅ COMPLIANT |
| **CS4** | **(unscored) repeated same-bucket pushes** | **no committed test; probe proves it is wrong once ≥2 ticks share a bucket** | ❌ **FAILING (C1)** |
| CS5 | Selects are present and labelled | E2E `test_scale_and_type_selects_present_and_labelled` (aria-label, options, no `on*`) | ✅ COMPLIANT |
| CS5 | Scale select emits the light event | E2E `test_scale_select_changes_price_scale_mode` (no kline refetch) | ✅ COMPLIANT |
| CS5 | Type select triggers rebuild | E2E `test_type_select_rebuilds_with_new_series_ctor` | ✅ COMPLIANT |
| CS5 | Controls restore the preference | E2E `test_boot_restores_saved_scale_and_type` | ✅ COMPLIANT |
| CS6 | Round-trip persists the pair | E2E `test_scale_and_type_round_trip_persists_across_reload` (+ probe) | ✅ COMPLIANT |
| CS6 | Fetch failure falls back | `loadPreference().catch` → linear/candles (static; boot never blank) | ✅ COMPLIANT |
| CS6 | Only the changed field is sent | E2E `test_scale_change_debounce_persists_only_scale` / `…_only_type` | ✅ COMPLIANT |
| CS7 | Seam stays 8 keys | E2E `Object.keys(window.marketChart).length === 8` (multiple) + probe | ✅ COMPLIANT |
| CS7 | No dependency or CSP change | empty `requirements.txt`/`src/` diff; CSP untouched | ✅ COMPLIANT |

### chart-config (R8/R9/R12)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R8 | One row per user | pre-existing upsert tests + `test_preference_put_upserts_one_row_for_the_user` | ✅ COMPLIANT |
| R8 | Additive migration 0010 | `makemigrations --check` clean; migration = 2 `AddField` w/ defaults | ✅ COMPLIANT |
| R8 | Field round-trip | `test_preference_put_scale_then_get_round_trip` / `…_chart_type…` | ✅ COMPLIANT |
| R9 | GET default when no preference | `test_preference_get_default_when_absent` (4 keys) | ✅ COMPLIANT |
| R9 | Partial PUT applies only present keys | `test_preference_partial_put_updates_only_present_key` (+ probe) | ✅ COMPLIANT |
| R9 | Invalid scale_mode → 400 | `test_preference_put_invalid_scale_mode_is_400_and_writes_nothing` | ✅ COMPLIANT |
| R9 | Invalid chart_type → 400 | `test_preference_put_invalid_chart_type_is_400_and_writes_nothing` | ✅ COMPLIANT |
| R9 | Invalid interval → 400 | `test_preference_put_invalid_interval_is_400_and_writes_nothing` | ✅ COMPLIANT |
| R9 | Unauthenticated → redirect | pre-existing anon tests (+ probe: GET/PUT 302) | ✅ COMPLIANT |
| R12 | B never sees A's scale/type | `test_preference_isolation_b_never_sees_a_scale_or_type` | ✅ COMPLIANT |
| R12 | B's PUT does not touch A's row | `test_preference_isolation_b_put_does_not_touch_a_row` | ✅ COMPLIANT |
| R12 | CSP unchanged | CSP untouched; `test_market_page_has_no_inline_script_or_handler` | ✅ COMPLIANT |

### chart-shell (R25/R26)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R25 | Focus and names | `select:focus-visible` global rule; both selects have `aria-label` | ✅ COMPLIANT |
| R25 | CSP and manifest unchanged | E2E no-`on*` assertion + empty dep diff | ✅ COMPLIANT |
| R26 | Two native selects exist | E2E `test_scale_and_type_selects_present_and_labelled` | ✅ COMPLIANT |
| R26 | Scale change emits the light event | E2E `test_scale_select_changes_price_scale_mode` | ✅ COMPLIANT |
| R26 | Type change triggers rebuild | E2E `test_type_select_rebuilds_with_new_series_ctor` | ✅ COMPLIANT |
| R26 | Controls restore the preference | E2E `test_boot_restores_saved_scale_and_type` | ✅ COMPLIANT |
| R26 | No new controller | `toolbar.js` owns the selects; `CONTROLLER_ALLOWLIST` still 7 (test asserts `== 7`) | ✅ COMPLIANT |

### market-chart (R14/R20/R21)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R14 | Inventory and no-cycle | `test_import_graph_routes_resolve`, `test_module_allowlist_routes_serve_javascript`; core imports nothing (node regex) | ✅ COMPLIANT |
| R14 | Store never holds candles | `test set never admits candle data`; keys = 9 | ✅ COMPLIANT |
| R14 | Size ceiling | all ≤ 300 **except `chart-host.js` = 322** (see W1) | ⚠️ PARTIAL (W1) |
| R14 | New core is served | allowlist route test (iterates `MODULE_ALLOWLIST`, now includes `chart-types-core`) | ✅ COMPLIANT |
| R20 | Seam stays 8 keys | E2E + probe | ✅ COMPLIANT |
| R20 | Only one new bus event | `EVENTS.scaleChanged`; type reuses `indicator:changed` | ✅ COMPLIANT |
| R20 | Existing E2E stays green unedited | add-only diff (0 removed-content lines) | ✅ COMPLIANT |
| R21 | Ctor from state | node `build selects the candle Ctor…` | ✅ COMPLIANT |
| R21 | setScaleMode is option-only | node `setScaleMode is option-only…` | ✅ COMPLIANT |
| R21 | Build re-applies the scale | node `build re-applies the scale mode` | ✅ COMPLIANT |
| R21 | Rebuild preserves drawings and SMC | `buildChart()` re-attaches; type switch E2E rebuilds successfully | ✅ COMPLIANT |
| R21 | HA live is update-only | node HA live tests + probe: `update()` only, but **transform wrong on repeat** | ⚠️ PARTIAL (C1) |

**Compliance summary**: 15/15 requirements present; 55/56 scenarios COMPLIANT, 1 PARTIAL (R14 size ceiling), and **1 CRITICAL correctness defect (C1) under an unscored repeated-same-bucket input** — all spec-named scenarios pass at runtime.

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| CS1 core pure | ✅ | `chart-types-core.js` has no `import`/`require`; exports `CHART_TYPES,SCALE_MODES,isLineLike,isValidType,isValidScale,heikinAshi,nextHeikinAshi,toChartData` |
| CS1 formulas exact | ✅ | node probe: bar1 `haLow=10` (NOT 9.5), `haClose=(o+h+l+c)/4`, first-bar branch, `time` preserved, round nothing |
| CS1 deterministic / never throws | ✅ | node probe over `null/undefined/0/"x"/{}/[{}]` |
| CS2 symbol not magic number | ✅ | `LightweightCharts.PriceScaleMode[member]` at call time; grep finds no `mode: <number>`; stub uses 70/71/72 |
| CS2 no data rewrite on scale | ✅ | node asserts no `setData`/`update`; E2E probe `__sd == 0` |
| CS3 Ctor map | ✅ | `candles`/`heikin-ashi`→`CandlestickSeries`, `line`→`LineSeries`, `area`→`AreaSeries`; unknown→candles |
| CS4 HA reset on setCandles | ✅ | `prevHa=null; lastHa=null; lastBarTime=0` in `setCandles` |
| CS4 HA live correctness | ❌ | **C1 — see Issues** |
| CS5 two core-fed selects | ✅ | `toolbar.js` imports `SCALE_MODES`/`CHART_TYPES`; options built in JS, no HTML copies |
| CS5 a11y / CSP | ✅ | `aria-label` on both; no inline handler; `select:focus-visible` rule present |
| CS6 boot apply before first build | ✅ | `start()` sets `state.scaleMode/chartType` then `buildChart()` |
| CS6 debounced per-field save | ✅ | `savePreference(patch)` merges + 500 ms debounce, changed field only |
| Persistence model/migration | ✅ | 2 `CharField(max_length=16)` defaults `linear`/`candles`; `0010` additive |
| Frozen seam | ✅ | literal in `main.js` is 8 keys; E2E asserts `=== 8` |
| `stream.js` byte-identical to develop | ✅ | `git diff origin/develop...HEAD -- controllers/stream.js` empty → the "Object is disposed" live race is pre-existing, not introduced here |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| D1 core API names (`CHART_TYPES,SCALE_MODES,isLineLike,isValidType,isValidScale,heikinAshi,nextHeikinAshi,toChartData`) | ✅ Yes | exports match exactly |
| D2 HA wraps `CandlestickSeries` (no HA series) | ✅ Yes | `CANDLE_CTORS` maps both to `CandlestickSeries` |
| D3 scale = `priceScale("right").applyOptions({mode: symbol})`, re-applied in `build` | ✅ Yes | `applyScale()` after `createChart` |
| D4 new `scale:changed`; type reuses `indicator:changed` | ✅ Yes | `EVENTS.scaleChanged`; toolbar emits `indicator:changed` on type |
| D5 HA live incremental, reset on `setCandles`, `update()`-only | ⚠️ Partial | reset + update-only correct; incremental chain **wrong on repeat (C1)** |
| D6 controls in `toolbar.js` (no new controller) | ✅ Yes | `CONTROLLER_ALLOWLIST` still 7 |
| D7 two additive fields + partial PUT | ✅ Yes | model/migration/view match |
| D8 options from core vocab (single source) | ✅ Yes | `fillOptions(el, SCALE_MODES/CHART_TYPES)` |
| Open Q: `autoScale` left at v5 default | ✅ Yes | no explicit toggle |

## Adversarial Probes (independent)

- **Grep**: `chart-types-core.js` has **no** `import`/`require`; no `Math.pow(10,` anywhere in `market/`; `PriceScaleMode` symbol used at `chart-host.js:240`; no `mode: <number>` magic values; `stream.js` unchanged vs develop; `chart.html`/`toolbar.js` add no `on*` handlers.
- **Node HA probe** (throwaway, exit 0): 2-bar fixture bar1 `low=10` (not 9.5); `nextHeikinAshi(prev,b1)` deep-equals the full recompute's last bar; vocab validators reject `"Heikin"`/`"Percent"`; never throws; deterministic; float-exact on v24.14.0.
- **HA live state-machine probe (found C1)**: driving the **real** host with repeated same-bucket `updateCandle` calls — the forming bar's `haOpen` should stay `11` (chain from the last closed bar's HA) but drifts to `11.5625` on the 3rd tick and **cascades** to the next bucket (`bar400.open` `11.95625` vs correct `11.675`). A 1-line scratch patch (only advance `prevHa = lastHa` on a genuinely new bucket) yields `[11,11,11,11]` and a matching `bar400`.
- **Endpoint probe** (throwaway Django client, exit 0): GET default = 4 keys; partial PUT `{chart_type:"line"}` keeps `interval`/`scale_mode`; A≠B; per-field 400 on `{scale_mode:"log", chart_type:"notreal"}` writes **nothing** (row stays `scale_mode≠log`, `chart_type=line`); invalid interval 400; empty body writes no row; anon GET/PUT → 302.
- **Real browser** (Playwright, logged in, `/market/`, throwaway, exit 0): 8 seam keys; scale select → `priceScale("right").options().mode` changes with `setData` call count `0` (no data rewrite); candles→line→area→heikin-ashi each change `seriesType()`; after a debounce wait, reload restores `log`/`heikin-ashi`; **0 hard page errors** — only the pre-existing live-stream `Object is disposed` (3×) reproduced, from byte-identical `stream.js`.
- **Holes checked**: no magic-number scale mode ✅; **HA live desync ❌ (C1)**; scale change rewrites data ❌ (it does not) ✅; partial write on invalid input ❌ (it does not) ✅; migration non-additive ❌ (it is additive) ✅.

## Issues Found

**CRITICAL**:
- **C1 — HA live desync on repeated same-bucket pushes (breaks the CS1 recursive formula on the live path; cascades).** `chart-host.js updateCandle()` (`web/market/templates/market/chart-host.js:271-286`) selects the HA base as `bar.time === lastBarTime ? prevHa : lastHa`, then **unconditionally** advances `prevHa = lastHa`. A live socket delivers many ticks per candle bucket (the codebase itself documents this: `tests/web/test_market_e2e.py::test_ws_same_bucket_updates_in_place`). On the **second** same-bucket replace, `prevHa` has already been overwritten with the forming bar's own HA, so `haOpen` chains from the *forming* bar instead of the last *closed* bar. Result: the HA open drifts while forming (`11 → 11 → 11.5625`) and the error **cascades into subsequent buckets** (`bar400.open` `11.95625` vs correct `11.675`). Repro is deterministic (throwaway `probe-ha3/ha5/ha6.mjs`). The committed test `HA live same-bucket forming bar re-transforms…` exercises only **one** same-bucket tick after a new bar, so it never reaches the drift.
  **Fix (1 line, verified in a scratch copy):** only advance the base on a genuinely new bucket:
  ```js
  const isNew = bar.time !== lastBarTime;
  const base = isNew ? lastHa : prevHa;
  const ha = Types.nextHeikinAshi(base, bar);
  candleSeries.update(ha);
  if (isNew) prevHa = lastHa;        // <-- only when the bar is truly new
  lastHa = { haOpen: ha.open, haClose: ha.close };
  lastBarTime = bar.time;
  ```
  A matching RED test should send ≥2 same-bucket pushes after a new bar and assert the forming `haOpen` stays constant.

**WARNING**:
- **W1 — `chart-host.js` is 322 lines, above the R14 "≤ ~300" ceiling** (was 243 pre-change; +82). The design's own size-ceiling decision lists every module ≤ ~300. The HA/scale/Ctor logic could extract the HA write path into a small helper to restore the ceiling. No functional impact.
- **W2 — repeated same-bucket HA has no committed regression test.** Even after the C1 fix, add the multi-tick test so the invariant cannot silently regress (the existing single-tick test gives false confidence).
- **W3 — E2E flakiness under SQLite/live-server contention.** Isolated runs intermittently raised `no such savepoint` / `database table is locked` (never a logic assertion). Full suite passes cleanly on re-run; recorded so future verifiers do not mistake it for a product defect.

**SUGGESTION**:
- **G1 — HA E2E coverage is smoke-only.** `test_type_select_heikin_ashi_chains_and_rebuilds` asserts the seam stays 8 keys and the select value, but does not assert HA values (the comment concedes "recompute from raw candles is not exposed"). The node tests carry the real HA math; consider exposing the last HA candle on a test-only seam if browser-level HA verification is wanted.
- **G2 — `tasks.md`/openspec artifacts carry unmarked checkboxes** (executor contract); consistent with F0–F2.

## Verdict

**PASS (after C1 fix)** — every L1 gate is green with fresh exit-0 evidence (132 node / 337 py / **51** E2E / ruff clean / `makemigrations --check` clean / empty `requirements.txt`, `src/` diffs), the L2 patch gate is a genuine 100% across all 27 changed Python lines, all 15 requirements are implemented and every spec-named scenario passes at runtime, the frozen 8-key seam holds, scale changes prove `setData`-free, `stream.js` is byte-identical to develop, and the real-browser probe confirms scale/type switching and persistence with no *new* page errors.

**C1 (Heikin Ashi live desync) — RESOLVED.** The verify found a reachable CRITICAL defect: `updateCandle()` unconditionally advanced `prevHa = lastHa`, so on the 2nd+ same-bucket tick the forming bar chained its `haOpen` onto a stale version of itself and drifted (cascading into later buckets). **Fix** (`chart-host.js`): advance `prevHa = lastHa` ONLY when the bar is a genuinely new bucket (`if (!sameBucket) prevHa = lastHa;`). **Regression test** added: `tests/js/chart-host.test.js::"HA live is stable across MULTIPLE same-bucket ticks (C1 regression)"` asserts `haOpen` is stable across 3 same-bucket ticks (`[11,11,11]`) and the next bucket chains correctly (`12.375`). Proven red-on-old-code/green-on-fix (the test fails with the old `prevHa = lastHa`). Node count 131→132.
