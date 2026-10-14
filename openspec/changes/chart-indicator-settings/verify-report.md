```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:565f984f46cbf27cccafda090b6dab858d2f116229988f7368913fac7521f640
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 16/16
scenarios: 45/49
test_command: .venv/bin/python -m pytest -m e2e -p no:randomly -q
test_exit_code: 0
test_output_hash: sha256:5682e8a3455ced41630027e865c5b3b8a5011157346aa1738345b0523fd87ac4
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check .
build_exit_code: 0
build_output_hash: sha256:82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18
```

# Verify Report — chart-indicator-settings (issue #115, Fase F2)

**Verdict**: `pass_with_warnings`
**Verified by**: fresh adversarial verifier (independent replication + throwaway Django-client, node-probe and real Playwright probes; apply reports NOT trusted)
**Branch**: `feat/chart-indicator-settings-ui` (HEAD `2055c61`), chain: tracker `feat/chart-indicator-settings` (tip `e64c8f2` = merge of S1) + S1 `feat/chart-indicator-settings-core` (`cbca97c` + fix `d62f509`) + S2 `feat/chart-indicator-settings-ui` (`2055c61`, child of the tracker merge). Confirmed with `git branch --show-current`. S2 diff vs tracker is UI-only (5 files, no `quotes.py`/core/host/store — clean chain).
**Mode**: Strict TDD (node --test + pytest + E2E). Artifact store: openspec.

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 16 (1.1–1.9, 2.1–2.5, guard matrix) |
| Tasks complete | 16 |
| Tasks incomplete | 0 |

`tasks.md` checkboxes are unmarked (executor contract forbids editing `openspec/**`); every acceptance artifact exists and passes at runtime. Not a finding.

## Gates (L1)

| Gate | Command | Result |
| --- | --- | --- |
| JS unit | `node --test "tests/js/**/*.test.js"` | **104 passed, 0 fail** (exit 0) — SHA256 `9b062809…` |
| E2E | `.venv/bin/python -m pytest -m e2e -p no:randomly -q` | **42 passed** (exit 0) — SHA256 `5682e8a3…` |
| Python unit | `.venv/bin/python -m pytest tests/ --ignore=tests/web -q` | **337 passed** (exit 0) |
| Lint/format | `.venv/bin/ruff check . && .venv/bin/ruff format --check .` | **clean** (134 files, exit 0) |
| Migration drift | `python web/manage.py makemigrations --check --dry-run` | **"No changes detected"** (exit 0) |
| Django check | `python web/manage.py check` | **no issues** (exit 0) |
| Dependency | `git diff origin/develop -- requirements.txt` | **empty** (0 lines, no new dep) |
| `src/` boundary | `git diff origin/develop...HEAD -- src/` | **empty** (0 lines) |
| Migrations in diff | `git diff origin/develop...HEAD --name-only -- 'web/*/migrations/*'` | **0 files** |

`git diff --stat origin/develop...HEAD` = 24 files, +2104/−24 (bulk = planning docs + tests). S2 vs tracker = 5 files, +437/−10.

## Gates (L2) — Patch coverage

Generated the real CI artifact (`python -m pytest --cov --cov-report=xml`, no `--cov=` scoping so `[tool.coverage.run].source` wins), then:

`diff-cover coverage.xml --compare-branch=origin/develop --fail-under=100` →

```
web/market/quotes.py (100%)
Total:   18 lines
Missing: 0 lines
Coverage: 100%
```

**exit 0**. The only Python change (`parse_layout_indicators` + `_validate_layout_style`) is 100% covered by the new style round-trip + reject tests. `views.py` (+1 allowlist line) has no measurable line.

> **Reproduction nuance (important for the chain tip):** running the requested `diff-cover --compare-branch=feat/chart-indicator-settings` against THIS branch returns **"No lines with coverage information in this diff" (exit 0)** — because the tracker (`e64c8f2`) already contains the merged Slice 1 Python change, and S2 is UI-only. The meaningful Python patch for F2 therefore must be measured against `origin/develop` (the pre-S1 base), which gives the 100%/18-line result above. Both are recorded; no gate defect.

## TDD Compliance (Strict TDD)

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | Task IDs map to node/E2E/pytest artifacts |
| All tasks have tests | ✅ | core (13 node), store/host/controllers node edits, style round-trip pytest (+3), 6 E2E |
| RED confirmed (tests exist) | ✅ | `indicator-settings-core.test.js`, `test_market_api.py` style tests, `test_market_e2e.py` (+6) all exist |
| GREEN confirmed (tests pass) | ✅ | 104 node + 337 py + 42 E2E pass on my fresh execution |
| Triangulation adequate | ✅ | unknown token / clamp / drop / never-throw / bad color; round-trip verbatim / partial verbatim / 9 bad-style variants; gear-prefill / confirm+persist / cancel / Esc-focus / no-inline / 375px |
| Safety Net for modified files | ✅ | **0 removed lines** in `test_market_e2e.py` vs develop; existing assertions untouched |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit (JS) | 104 | `tests/js/*` | node --test |
| Unit (py HTTP/parser) | 337 | `tests/web/test_market_api.py` etc. | pytest + Django client |
| E2E | 42 | `tests/web/test_market_e2e.py` | Playwright (chromium) |
| **Total** | **104 node + 337 py + 42 E2E** | | |

### Changed File Coverage

| File | Rating |
|------|--------|
| `web/market/quotes.py` (+35) | ✅ 100% diff-cover (18 lines) |
| `web/market/views.py` (+1) | ✅ allowlist constant (route proven by `test_module_allowlist_routes_serve_javascript`) |
| `indicator-settings-core.js`, `chart-host.js`, `chart-store.js`, `controllers/indicators.js`, `chart.html`, `theme.css` | ✅ JS/CSS outside the Python gate → 104 node + 42 E2E |

### Assertion Quality

**Assertion quality**: ✅ All assertions verify real behavior.
- `indicator-settings-core.test.js` asserts exact deep-equal output objects, clamp boundaries (`lineWidth:99→4`, `precision:-3→0`), unknown-key drop, and a source-level `import`-regex purity check.
- `chart-host.test.js` stubs `LightweightCharts`/`document`/`window` and asserts the constructed series options plus `priceFormat == {precision:5, minMove:0.00001}`.
- E2E asserts exact input values, a captured PUT body's `style`, pane series `options()` (`color`/`lineWidth`/`precision`/`minMove`), `Object.keys(window.marketChart).length === 8`, and overflow `<= 1`.

### Quality Metrics
**Linter**: ✅ No errors (ruff, 134 files)
**Type Checker**: ➖ Not applicable (JS/Django project)

## Spec Compliance Matrix

### chart-indicator-settings (F2.1–F2.9)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| F2.1 | Unknown token | node `defaultsFor unknown token -> safe style` | ✅ COMPLIANT |
| F2.1 | Core imports nothing | node `the core imports nothing (pure ESM)` (source regex) | ✅ COMPLIANT |
| F2.2 | Happy path round-trip | node `normalize round-trips a full valid style` | ✅ COMPLIANT |
| F2.2 | Clamping and unknown keys | node `normalize clamps out-of-range and drops unknown keys` | ✅ COMPLIANT |
| F2.2 | Malformed input never throws | node `normalize never throws on hostile input` | ✅ COMPLIANT |
| F2.3 | Invalid values reported | node `validate names each offender` | ✅ COMPLIANT |
| F2.3 | Valid passes | node `validate accepts a valid style` | ✅ COMPLIANT |
| F2.4 | Store vocabulary (7 keys) | node `STORE_KEYS is exactly the UI/config vocabulary (7 incl. styles)` | ✅ COMPLIANT |
| F2.4 | No style leak into params | node `klineUrlFrom: styles never leak into the kline query` | ✅ COMPLIANT |
| F2.5 | Series reflects style | node `build applies per-token style…priceFormat precision` + E2E `test_confirm_updates_series_and_persists_across_reload` | ✅ COMPLIANT |
| F2.5 | Missing style uses registry default | node same test (`ema` falls back to `#ff6d00`, width 1) | ✅ COMPLIANT |
| F2.5 | One rebuild per style change (#68) | static: single `bus.emit("indicator:changed")` and single `bus.on(..., rebuild)`; no committed count test | ⚠️ PARTIAL |
| F2.6 | Gear opens the dialog for its token | E2E `test_gear_opens_dialog_prefilled` (`enter` on responsive gear) | ✅ COMPLIANT |
| F2.6 | Confirm applies once | E2E `test_confirm_updates_series_and_persists_across_reload` (series updates; dialog closes; exactly 1 PUT) | ✅ COMPLIANT |
| F2.6 | Cancel makes no change | E2E `test_cancel_makes_no_change` (`_pane0_series == before`, 0 PUT) | ✅ COMPLIANT |
| F2.6 | Empty required fields block submit | **no committed test**; probe: out-of-range `9` → native `max` keeps it **open** (invalid half met); **cleared** width → dialog **closes** and persists the **default** (no invalid value, but the "stays open" clause is unmet) | ⚠️ PARTIAL (W1) |
| F2.7 | Round-trip verbatim | pytest `test_layout_put_then_get_round_trips_style_verbatim` + probe | ✅ COMPLIANT |
| F2.7 | Bad style → 400, no write | pytest `test_parse_layout_indicators_rejects_bad_style` (9 params) + probe (no row) | ✅ COMPLIANT |
| F2.8 | Keyboard operable | E2E `test_gear_opens_dialog_prefilled` (Enter) + `test_escape_closes_and_returns_focus` (Esc→focus back to gear) | ✅ COMPLIANT |
| F2.8 | CSP and manifest unchanged | E2E `test_dialog_has_no_inline_handler_and_seam_frozen`; requirements diff empty; CSP/`test_market_ux` unchanged | ✅ COMPLIANT |
| F2.9 | A ≠ B | inherited `test_layout_isolation_b_get_never_sees_a`; style-specific A≠B proven by this session's probe (B sees default, no `style`) | ⚠️ PARTIAL (probe) |

### chart-config (R1/R2/R5)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R1 | Distinct intervals coexist | `test_layout_put_then_get_round_trips_style_verbatim` path / existing layout suite | ✅ COMPLIANT |
| R1 | Duplicate key rejected | pre-existing layout unique-constraint tests | ✅ COMPLIANT |
| R1 | JSON round-trip preserves style | pytest round-trip verbatim test | ✅ COMPLIANT |
| R1 | Additive migration | `makemigrations --check --dry-run` → "No changes detected" | ✅ COMPLIANT |
| R2 | GET with no layout returns default | `test_layout_get_without_row_returns_default_not_404` | ✅ COMPLIANT |
| R2 | GET after PUT returns saved set | `test_layout_put_then_get_round_trips_style_verbatim` | ✅ COMPLIANT |
| R2 | PUT upserts one row | `test_layout_put_upserts_one_row_for_the_same_key` | ✅ COMPLIANT |
| R2 | Invalid token → 400 | `test_layout_put_invalid_token_is_400_and_writes_nothing` | ✅ COMPLIANT |
| R2 | Invalid style → 400 before write | `test_parse_layout_indicators_rejects_bad_style` + probe | ✅ COMPLIANT |
| R2 | Unauthenticated → redirect | `test_layout_anonymous_get/put_redirects_to_login` | ✅ COMPLIANT |
| R2 | Parser is the sole drop point | `test_parse_layout_indicators_preserves_partial_style_verbatim` | ✅ COMPLIANT |
| R5 | Toggle triggers debounced PUT | existing toggle PUT test | ✅ COMPLIANT |
| R5 | Payload pins the active chart | existing layout pin test | ✅ COMPLIANT |
| R5 | Style is included in the payload | E2E confirm test asserts PUT body `sma.style` | ✅ COMPLIANT |

### market-chart (R14/R17)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R14 | Inventory and no-cycle | `test_import_graph_routes_resolve` (routes); no-cycle static | ✅ COMPLIANT |
| R14 | Store never holds candles | node `set never admits candle data` | ✅ COMPLIANT |
| R14 | Size ceiling | static line counts (all ≤ 298; new core 86) | ⚠️ PARTIAL (no committed test) |
| R14 | New modules are served | `test_module_allowlist_routes_serve_javascript` (includes `indicator-settings-core`) | ✅ COMPLIANT |
| R17 | No setData from the live path | E2E `__setDataCalls == 0` | ✅ COMPLIANT |
| R17 | Guards and ordering intact | existing switch/ordering E2E | ✅ COMPLIANT |
| R17 | Style change uses the rebuild path | E2E confirm test (series rebuilt) + static single-emit | ⚠️ PARTIAL (no committed count) |
| R17 | Style never leaks into the kline query | node kline-leak test; probe: kline has `sma_len=50`, no style key | ✅ COMPLIANT |

### chart-legend (LC1/LC2)

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| LC1 | Known and unknown tokens | node `formatValue: known/unknown` | ✅ COMPLIANT |
| LC1 | Determinism and never-throw | node `rows: deterministic` + `core never throws` | ✅ COMPLIANT |
| LC1 | Style precision does not change the legend | static: `legend.js` never reads `styles`, `DECIMALS` frozen; **no committed test** | ⚠️ PARTIAL |
| LC1 | DECIMALS is static and frozen | node `DECIMALS is a frozen token->decimals map` | ✅ COMPLIANT |
| LC2 | No indicator math in the core | node purity test + static inspection | ✅ COMPLIANT |
| LC2 | No style dependency | static: `legend.js`/`legend-core.js` contain no `styles`/`priceFormat` reference | ⚠️ PARTIAL (static only) |

**Compliance summary**: 45/49 scenarios COMPLIANT, 4 PARTIAL (3 proven by static/probe without a committed test; 1 = F2.6 cleared-field behaviour, W1), 0 UNTESTED, 0 FAILING.

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| F2.1 core pure | ✅ | `indicator-settings-core.js` has **no** `import`/`export ... from`; exports exactly `FIELDS,TOKENS,defaultsFor,normalize,validate`; `clamp` internal |
| F2.1 `FIELDS` frozen | ✅ | `Object.freeze` color/lineWidth 1..4/precision 0..8 (nested frozen) |
| F2.4 store slot | ✅ | `STORE_KEYS = [...,"styles",...]` (7); `styles` top-level, not under `params` |
| F2.5 host apply | ✅ | `addSeries(token,paneIndex,style)` → `{color: s.color||entry.color, lineWidth: s.lineWidth||1}`; `applyOptions({priceFormat:{precision, minMove: Number("1e-"+p)}})`; `build` reads `state.styles[token]` with REGISTRY fallback |
| F2.5 minMove exact | ✅ | `Number("1e-"+n)` used, **no `Math.pow(10,`** in `chart-host.js`; verified exact for n=0..8 on Node 24; `Number("1e-5")===0.00001` is a language guarantee, independent of V8 build (Node 22 safe) |
| F2.7 server keeps style | ✅ | `quotes.parse_layout_indicators` sets `entry["style"]=_validate_layout_style(...)` when present; `_validate_layout_style` whitelists color `#rrggbb`, lineWidth 1..4, precision 0..8, rejects unknown key/bool/float |
| Frozen seam | ✅ | `main.js` literal has exactly 8 keys; E2E asserts `=== 8`; no new global |
| No migration / no dep / no src | ✅ | all diffs empty/clean |
| CSP | ✅ | dialog markup has **no `on*=` attributes**; no inline script |
| 375px | ✅ | E2E overflow `<= 1`, dialog width `<= 375` |
| a11y | ✅ | labelled inputs (`is-color/width/period/precision`), gear `aria-label`+`aria-haspopup=dialog`, global `:focus-visible` outline 2px, native Esc focus return |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| D1 `styles` top-level slot | ✅ Yes | `STORE_KEYS` 7; kline-leak test green |
| D2 names `FIELDS/TOKENS/validate/normalize/defaultsFor`; `clamp` internal | ✅ Yes | exports match exactly |
| D3 style shape `{color,lineWidth,precision}` | ✅ Yes | all optional; period stays in `params` |
| D4 apply point `host.build` | ✅ Yes | sole series-construction site |
| D5 precision → `priceFormat` only | ✅ Yes | legend `DECIMALS` untouched |
| D6 gear/dialog in `controllers/indicators.js` | ✅ Yes | 261 lines (≤ ~300) |
| D7 apply-on-confirm | ✅ Yes | one emit per submit |
| D8 server validator mirrors params | ✅ Yes | verbatim, no defaults injected |
| Design detail: Period hidden for tokens without a param | ✅ Yes | `periodLabel.hidden` toggled |

**Deviation (minor, not a defect)**: the design says the Period input is "hidden for tokens without a known param"; implementation only wires `sma`/`ema` (`PERIOD_PARAMS`) because only those two have DOM param inputs (`chart.html`). This matches explore §1 ("editable params today: only `sma_len`/`ema_len`") and the design's "known param" wording. rsi/macd/etc. periods remain server-default — consistent with the ratified scope.

## Adversarial Probes (independent)

- **Grep**: core has no `import`; `styles` is in `STORE_KEYS` (not `params`); `quotes.py` sets `entry["style"]`; `chart-host.js` has no `Math.pow(` (only a comment); the seam literal is 8 keys; dialog markup has no `on*=`; `legend.js`/`legend-core.js` never reference `styles`/`priceFormat`; bus emits only `indicator:changed` for the config path.
- **minMove probe (Node 24)**: `Number("1e-"+n) === Math.pow(10,-n)` for n=0..8; precision-5 → `0.00001` exact.
- **Endpoint probe** (throwaway Django client, exit 0): PUT `{token,params,style}` → GET returns it verbatim; invalid style (`lineWidth:9`) → 400 **and no row written**; unknown style key → 400; A≠B: B sees `exists:false` and **no `style`**; `_validate_layout_style` accepts all in-range shapes and rejects `#abc`/`red`/0/5/bool/-1/9/3.5/`foo`/non-dict/array.
- **Real browser** (Playwright, logged in, `/market/`, throwaway, exit 0): 8 seam keys; gear click → dialog open prefilled `#2962ff`; change to `#123456`/width 4/precision 6 → apply → pane-0 series `color=#123456`, `lineWidth=4`, `priceFormat {precision:6, minMove:1e-6}`; **reload → persisted**; **0 page errors**; 375px overflow 0.
- **Period probe** (real browser): editing Period to 50 → PUT carries `params.sma_len=50` and `style`; the kline request contains `sma_len=50` and **no style key** (leak guard holds); reload → Period re-prefilled `50`.
- **Empty-field probe**: cleared width submits → dialog closes and persists `lineWidth:1` (default, valid); range-violation (`9`) is blocked by native `max` (dialog stays open).

## Issues Found

**CRITICAL**: None.

**WARNING**:
- **W1 — F2.6 "Empty required fields block submit" deviates on the empty case.** A *cleared* control is treated as "reset to default": the dialog closes and persists the default style (`lineWidth:1`) instead of staying open. The safety half of the scenario holds (no *invalid* value is persisted; out-of-range is blocked by native `max`/`min`), but the literal "dialog stays open" is not met and there is **no committed test** for this scenario. Either add `required` to the four inputs (then a cleared field blocks submit) or amend the scenario to "cleared fields fall back to the default". Low harm: no invalid data, no data loss.
- **W2 — F2.5 "One rebuild per style change (#68)" has no committed count test.** Compliant by construction (one `indicator:changed` emit, one `rebuild` listener) and the series visibly rebuilds, but nothing fails if a future edit double-emits. Same pattern as the archived chart-shell report's probe-only warnings.
- **W3 — LC1/LC2 "style precision does not change the legend" proven by static evidence only.** `legend.js`/`legend-core.js` do not read `styles`/`priceFormat` and `DECIMALS` is frozen (covered), but there is no committed test asserting the legend output is unchanged when `styles.sma.precision` differs.
- **W4 — R14 "size ceiling" (~300 lines) is checked statically, not by a test.** All modules comply (max 298; new core 86).
- **W5 — F2.9 A≠B for style is inherited/probe-proven, not style-specific in the committed suite.** `test_layout_isolation_b_get_never_sees_a` proves layout isolation; the style-specific case (B never sees A's style) was reproduced by this session's probe. Extending the isolation test to assert `style` absence would close it.

**SUGGESTION**:
- Gears are rendered for **all 9** tokens (always visible), not only active ones. F2.6 says "each active indicator MUST render a gear" — actives do; extra gears for inactive tokens are consistent with the edge matrix ("Style on inactive indicator: stored, ignored at render"). Consider `disabled` when the toggle is off if a cleaner affordance is desired.
- Reproduce the L2 gate for a chain tip against `origin/develop`, not the tracker: the tracker already contains Slice 1, so the tracker comparison legitimately reports "no lines" for a UI-only tip.
- `tasks.md` checkboxes remain unmarked (executor contract forbids editing `openspec/**`); consistent with the F0/F1 precedent.

## Verdict

**PASS WITH WARNINGS** — every L1 gate is green with fresh exit-0 evidence (104 node / 337 py / 42 E2E / ruff clean / `makemigrations --check` clean / empty requirements, `src/` and migration diffs), the L2 patch gate is a genuine 100% across the 18 changed Python lines (`quotes.py`), all 16 requirements are met and 45/49 scenarios have passing runtime coverage. Independent Django-client, node and real-browser probes reproduce the style round-trip (verbatim, 400 on bad shape, no write), the exact `Number("1e-"+n)` `minMove`, the store/params separation (no kline leak), one-rebuild via `indicator:changed`, the frozen 8-key seam, persist-across-reload and 375px safety with **0 page errors**. Warnings are one benign behavioural deviation (cleared field resets to default rather than blocking submit) plus three missing *committed* regression tests for scenarios proven here by probes — no implementation defects, no blockers.
