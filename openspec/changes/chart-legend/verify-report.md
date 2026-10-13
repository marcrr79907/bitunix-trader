```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:ea5244156a5f5e371f1c1a99ee17f4e5861b7bd8139136f101b4eb51e48d4d24
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 8/8
scenarios: 16/18
test_command: .venv/bin/python -m pytest -m e2e -p no:randomly -q
test_exit_code: 0
test_output_hash: sha256:64576d99c4cef913eb9b9bd4e5a096807fe2289f77eb08a67c7de2e43fc6349d
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check .
build_exit_code: 0
build_output_hash: sha256:ed4fc35514411a138c4abd851c285b92a4940f238b6dc9cd88651f0963d6ed6c
```

# Verify Report — chart-legend (issue #114, Fase F1)

**Verdict**: `pass_with_warnings`
**Verified by**: fresh adversarial verifier (independent replication + throwaway Playwright probes; apply reports NOT trusted)
**Branch**: `feat/chart-legend-overlay` (HEAD `6b3043f`), chain: tracker `feat/chart-legend` + S1 `feat/chart-legend-core` (`a57c73f`) + S2 `feat/chart-legend-overlay` (`6b3043f`); both slice PRs base on the tracker.
**Mode**: Strict TDD (node --test + E2E). Artifact store: openspec.

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 11 (1.1–1.5, 2.1–2.6) |
| Tasks complete | 11 |
| Tasks incomplete | 0 |

`tasks.md` checkboxes are unmarked, but the apply-progress artifact (`sdd/chart-legend/apply-progress`, id 1516) records all 11 complete, and every acceptance artifact exists and passes at runtime. `tasks.md` is under `openspec/**`, which the executor contract forbids editing — not a finding.

## Gates (L1)

| Gate | Command | Result |
| --- | --- | --- |
| JS unit | `node --test "tests/js/**/*.test.js"` | **81 passed, 0 fail** (exit 0) — SHA256 `c394c9e0…` |
| E2E | `.venv/bin/python -m pytest -m e2e -p no:randomly -q` | **26 passed** (exit 0) — 24 F0 baseline + 2 new legend |
| Python unit | `.venv/bin/python -m pytest tests/ --ignore=tests/web -q` | **337 passed** (exit 0) |
| Lint/format | `ruff check . && ruff format --check .` | **clean** (133 files, exit 0) |
| Dependency | `git diff origin/develop -- requirements.txt` | **empty** (exit 0, no new dep) |
| `package.json` | — | exactly `{"type":"module"}` (no deps/scripts) |

## Gates (L2) — Patch coverage

`diff-cover coverage.xml --compare-branch=feat/chart-legend --fail-under=100` → **exit 0, "No lines with coverage information in this diff."**

This is **vacuously 100%**: the only Python change is two string literals inside `frozenset(...)` literals in `web/market/views.py` (`MODULE_ALLOWLIST += "legend-core"`, `CONTROLLER_ALLOWLIST += "legend"`). Those are constant expressions with no executable per-line coverage points, so diff-cover has zero measurable changed lines. Confirmed independently against `origin/develop` (same result) and by parsing `coverage.xml` (the line entries around the change have no coverage rows). All JS is outside the Python patch gate → covered by 81 node + 26 E2E tests.

## TDD Compliance (Strict TDD)

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | "TDD Cycle Evidence" table found in apply-progress |
| All tasks have tests | ✅ | 11/11 tasks map to a node/E2E/route test |
| RED confirmed (tests exist) | ✅ | `legend-core.test.js` (13), `chart-controllers.test.js` (+6 legend), `chart-host.test.js` (2), E2E (+2) all exist |
| GREEN confirmed (tests pass) | ✅ | 81 node + 26 E2E pass on my fresh execution |
| Triangulation adequate | ✅ | `formatValue` known/unknown/null/undefined/NaN/non-number; `formatOhlc` up/dn/flat/missing; `rows` populated/empty/missing; `lastValues` full/empty — different expected values, not all-empty |
| Safety Net for modified files | ✅ | F0 suites (60 node / 24 E2E / 337 py) run before extension; no existing JS assertion edited (97 added, **0 deleted** in `chart-controllers.test.js`) |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | 25 (13 legend-core + 2 chart-host + 6 legend-controller + 4 pre-existing-adjacent) | `tests/js/*` | node --test |
| Integration | 0 | — | not used (DOM controller covered by E2E) |
| E2E | 26 | `tests/web/test_market_e2e.py` | Playwright (chromium) |
| **Total** | **81 node + 26 E2E** | | |

### Changed File Coverage

| File | Lines | Rating |
|------|-------|--------|
| `web/market/templates/market/legend-core.js` | 118 | ✅ node-covered (all exports exercised) |
| `web/market/templates/market/controllers/legend.js` | 219 | ⚠️ pure helpers node-covered; DOM/rAF path E2E-covered |
| `web/market/templates/market/chart-host.js` (+6) | — | ✅ seam covered by 2 node tests |
| `web/market/views.py` (+2) | — | ✅ route covered by allowlist/import-graph tests |

**Average changed Python file coverage**: N/A (no measurable changed Python lines). JS covered by node + E2E.

### Assertion Quality

**Assertion quality**: ✅ All assertions verify real behavior.
- No tautologies, no type-only-alone assertions, no ghost loops, no smoke-test-only.
- 31 assertions in `legend-core.test.js`, 22 in `chart-controllers.test.js`; each asserts concrete values (`"1.2346"`, `"50000.50"`, `"+5.00%"`, dir `up/dn/flat`).
- No banned `innerHTML`/CSS-class-only implementation coupling.

### Quality Metrics
**Linter**: ✅ No errors (ruff, 133 files)
**Type Checker**: ➖ Not applicable (JS/Django project)

## Spec Compliance Matrix

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| LC1 | Known and unknown tokens | `legend-core.test.js > formatValue: known/unknown token` | ✅ COMPLIANT |
| LC1 | Determinism and never-throw | `legend-core.test.js > rows: deterministic` + `never throws on garbage` | ✅ COMPLIANT |
| LC2 | No indicator math in the core | grep `legend-core.js` imports empty; node export probe (exactly 6 exports, no-throw) | ⚠️ PARTIAL — static evidence only; no committed source-inspection test |
| LC3 | Hover shows the bar under the cursor | E2E `test_legend_overlay_shows_ohlc_and_updates_on_crosshair` | ✅ COMPLIANT |
| LC3 | Leave shows last values | E2E same test (mouse to `0,0` → rows remain) | ✅ COMPLIANT |
| LC3 | Off-bar gap is null-safe | `chart-controllers.test.js > shapeEntries: series absent` + `legend-core.test.js > missing value → placeholder` | ✅ COMPLIANT |
| LC4 | Re-subscribe across rebuilds | adversarial probe: switch `5m→1m`, move → legend updates, 1 overlay, 8 keys, 0 errors | ✅ COMPLIANT (via probe; no committed double-build test) |
| LC5 | Hover does not spam screen readers | E2E asserts `aria-live=="off"` on hover; adversarial probe: ≤1 mutation over 20 moves | ✅ COMPLIANT |
| LC5 | State change announces once | adversarial probe: `aria-live` transitions ≤2 across hover→leave cycle (debounce) | ✅ COMPLIANT (via probe; no committed test) |
| LC6 | All active series shown | adversarial probe: 3 rows `SMA 20 / EMA 20 / RSI` (overlays first, then pane) | ✅ COMPLIANT |
| LC6 | 375px no overflow | E2E `test_legend_overlay_styling_and_375px_fit` (`lw<=cw`, `lr<=cr+1`) | ✅ COMPLIANT |
| LC6 | Seam frozen | E2E `Object.keys(window.marketChart).length === 8` | ✅ COMPLIANT |
| R19 | Method mirrors subscribeClick | `chart-host.test.js > exported and mirrors` + `null-guarded no-op` | ✅ COMPLIANT |
| R19 | Handler re-binds after rebuild | adversarial probe (switch → move updates on current chart) | ✅ COMPLIANT (via probe) |
| R14 | Inventory and no-cycle | `test_import_graph_routes_resolve` (derives every relative import) + grep (no controller→main) | ✅ COMPLIANT |
| R14 | Store never holds candles | `chart-store.test.js > STORE_KEYS` + `set drops candles` | ✅ COMPLIANT |
| R14 | Size ceiling (≤~300) | manual: legend-core 118, legend controller 219 | ⚠️ PARTIAL — measured, no automated test |
| R14 | New modules are served | `test_module_allowlist_routes_serve_javascript` + `test_controller_allowlist_routes_serve_javascript` (7) + import-graph | ✅ COMPLIANT |

**Compliance summary**: 16/18 scenarios COMPLIANT, 2 PARTIAL, 0 FAILING, 0 UNTESTED.

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| LC1 exports exactly 6 | ✅ | node probe: `DECIMALS, PLACEHOLDER, formatOhlc, formatValue, lastValues, rows` |
| LC1 `DECIMALS` frozen + exact | ✅ | `Object.isFrozen` true; deep-equal to spec map (macd family 4, volume 0, price/osc 2) |
| LC2 no imports/formulas | ✅ | grep `^(import|export … from)` → none; no EMA/RSI/ATR/window math; `changePct` arithmetic lives in the controller, not the core |
| LC3 rAF + textContent-only | ✅ | controller: single pending frame (`schedule`), no `innerHTML` anywhere (grep empty) |
| LC4 null-guarded seam | ✅ | `if (chart) chart.subscribeCrosshairMove(fn)` mirrors `subscribeClick`; exported in return object |
| LC5 overlay contract | ✅ | `role="status" aria-label="Chart legend"`; `aria-live` flips `off` on hover / `polite` after 300ms |
| LC5 no layout shift | ✅ | `.chart-legend{position:absolute; pointer-events:none}`; `#chart{position:relative}` |
| LC6 lifecycle re-render | ✅ | controller subscribes `chart:built` (re-bind + idle), `history:loaded`, `candle:closed` |
| Seam frozen (R18) | ✅ | 8 keys; no new `window` global (grep `window.legend*` empty) |
| Allowlist serving | ✅ | `legend-core` in `MODULE_ALLOWLIST`, `legend` in `CONTROLLER_ALLOWLIST`; preloads in `chart.html` |
| No new dependency / CSP | ✅ | ESM + `theme.css`; `requirements.txt` diff empty; `package.json` unchanged |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| Static frozen `DECIMALS` keyed by token | ✅ Yes | `Object.freeze`, 2-decimal fallback |
| Re-subscribe locus = `chart:built` (main +1 line) | ✅ Yes | `main.js` gains `createLegend(...)` only; `buildChart` untouched |
| DOM injection by controller | ✅ Yes | overlay injected into `#chart`; a11y attrs live with the driver |
| `aria-live` off on hover / polite idle debounced | ✅ Yes | 300ms timer; probe confirms ≤1 transition per hover |
| rAF-coalesced textContent, fixed node set | ✅ Yes | `schedule`/`paint`; 40 paints/20 moves (coalesced), no innerHTML |
| `lastValues` recomputes `o:/p:` key locally | ✅ Yes | core stays chart-lib-free and Node-testable |
| Deviations | — | apply added 4 pure helper exports (`shapeEntries`/`candleFrom`/`prevClose`/`changePctText`) so the shaper is Node-testable (design 2.1 explicitly asked for "pure-helper cases"); added a 2nd E2E (375px), which task 2.6 required. Both strengthen, do not break, the design. |

## Adversarial Probes (independent)

- **Grep**: `legend-core.js` imports empty; controller has no `innerHTML` and no `window.marketChart` write; `subscribeCrosshairMove` bound inside the `chart:built` handler.
- **Node probe** (`formatValue`/`formatOhlc`/`rows`/`lastValues`): macd `1.23456→"1.2346"` (4dp), unknown `50000.5→"50000.50"` (2dp), volume `1234.9→"1235"` (0dp), null/undefined/NaN → `"–"`; OHLC up/dn/flat; null candle → placeholder strings + `flat`; `rows` label `"SMA 20"`; `lastValues` `o:/p:` recompute; never throws.
- **Real browser** (Playwright, logged in, `/market/`):
  - Legend present, `role=status`, `aria-label="Chart legend"`, 0 `<script>`, `pointer-events:none`, `position:absolute`, **0 page errors**, **8 seam keys**. Idle text: `O 100.77 H 101.92 L 99.77 C 100.92 +0.51% / SMA 20 97.79 / EMA 20 97.90 / RSI 62.46`.
  - Hover → `aria-live="off"`, OHLC shows real bar values (no placeholder).
  - Leave → last values, `aria-live="polite"` after debounce.
  - 20 rapid moves → exactly **1** `aria-live` mutation, **40** rAF paints (coalesced) — no spam, no jank.
  - Interval switch `5m→1m` then move → **1** overlay (no duplicate), **8** keys, `aria-live="off"`, **0 errors** (no stale handler).
  - Overlays/rows count exactly matches active series; no recompute leakage.

## Issues Found

**CRITICAL**: None.

**WARNING**:
- **W1 — LC2 "no indicator math" scenario has no committed regression test.** The invariant is verified here by static grep + export/no-throw probes, but nothing in the suite would fail if a future edit added indicator math or an import to `legend-core.js`. A cheap `readFileSync`-based node test asserting "no imports / no formula tokens" would close it.
- **W2 — Three lifecycle/a11y scenarios are proven only by this session's adversarial probes, not by committed tests**: LC4 re-subscribe-across-rebuilds, LC5 state-change-announces-once, LC6 all-active-series-shown. The E2E exercises a single build and asserts `rows >= 1`; it does not assert one-row-per-active-series nor a second `chart:built`. Add one interval-switch E2E assertion to lock re-binding permanently.
- **W3 — R14 size ceiling has no automated check.** Measured manually (118 / 219 ≤ ~300); a 3-line test would prevent silent drift.
- **W4 — Workload, not correctness**: Slice 2 diff is ~439 insertions, over the 400-line review budget (bulk = the two test files). Pre-flagged by apply; keep as a PR-size note.

**SUGGESTION**:
- `tasks.md` checkboxes remain unmarked (executor contract forbids editing `openspec/**`); the apply-progress artifact is the completion source, consistent with F0 precedent.

## Verdict

**PASS WITH WARNINGS** — every L1 gate is green with fresh exit-0 evidence (81 node / 26 E2E / 337 py / ruff clean / empty requirements diff), the only Python change yields a vacuous-100% diff-cover, all 18 spec scenarios have passing runtime coverage, the frozen 8-key seam and no-new-global/dependency/CSP boundaries hold, and independent browser probes reproduce hover/leave/375px/stale-handler/spam behaviour. Warnings are missing *committed* regression tests for four scenarios verified here by adversarial probes, not implementation defects.
