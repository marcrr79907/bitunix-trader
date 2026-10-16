# Tasks: f5-chart-toolbar (issue #118, Fase F5)

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | S1 ~300, S2 ~300, S3 ~350 → **~950** |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 (extractions + drawing flags + migration 0014 + API/parse) → PR2 (tool-icons-core + draw-toolbar + setSeriesVisible + wiring) → PR3 (object-tree + indicator visibility + wiring) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

### Suggested Work Units

| Unit | Goal | Likely PR | Base / boundary |
|------|------|-----------|-----------------|
| S1 | `chart-registry-core` extraction + `Drawing.visible/locked` + migration `0014` + API/parse flags; host ≤300 | PR 1 | base = tracker `feat/f5-chart-toolbar` |
| S2 | `tool-icons-core` + `controllers/draw-toolbar` + `setSeriesVisible` + wiring; legacy text buttons gone | PR 2 | base = S1 branch; merge S1→tracker first |
| S3 | `controllers/object-tree` + indicator visibility (store key, `indicator:visibility`, layout `visible`) + wiring | PR 3 | base = S2 branch; merge S2→tracker first |

All PRs base on the tracker `feat/f5-chart-toolbar`; merge each slice to the tracker before branching the next. Only the tracker merges to `develop`; `main` untouched. Total ≈ 950 > 400.

## Archive Note (2026-10-16)

Delivered as a 5-slice chain, not 3: **S1–S3** are the tasks below; **S4** was
remediation (`#177` lost-refetch coverage, `#176` reconciliation) and **S5** was
the add-indicator slice that produced the new `chart-indicator-add` capability
(issue #176). All S1–S5 tasks are complete per the verify-report. Two reconciliations
applied at archive: the controller count is **11**, not 10 (the D11 `preference.js`
extraction below became real), and drawing hit-testing excludes a
`locked:true` **OR** `visible:false` row. See the archive-report for details.

## Guard / Edge Matrix

- [x] **300-line ceiling (S1 PRECONDITION)**: after S1 `chart-host.js` 297→≈259; `smc.js` untouched AT 300; `main.js` 283→≈293 WATCHED — if apply crosses 300, apply contingency D11 (`controllers/preference.js`: `csrfToken` 184-187, `savePreference` 189-208, `loadPreference` 210-237). Enforced by `tests/web/test_module_size_guard.py` (`CEILING=300`, EMPTY allowlist).
- [x] **`window.marketChart` 8-key freeze** (`main.js:51-60`, R18/R20): no 9th key; tree/toolbar assert via DOM + bus + captured PUT. Enforced by E2E seam check.
- [x] **`STORE_KEYS` 10→11** (`chart-store.js:13-24`): add `"indicatorVisible"` only; explicit `market-chart` R14 delta; config-only (#68). Enforced by `tests/js/chart-store.test.js`.
- [x] **#68 option-only**: `setSeriesVisible` → `series.applyOptions({visible})`, never `setData`/`update`; host spies stay green. Enforced by `chart-host.test.js` + E2E setData spy.
- [x] **R14 `for_user`**: every drawing GET/POST/PUT/DELETE routes `Drawing.for_user` (`views.py:407,440,470`); miss/A≠B → 404 no leak. Enforced by `test_market_api.py` isolation.
- [x] **bool validation → 400 (no write)**: `parse_drawing` + `parse_layout_indicators` reject non-bool `visible`/`locked` (`isinstance(..., bool)`, int/str → 400). Enforced by full valid/bad/absent matrix.
- [x] **Migration `0014` additive + reversible**: two `AddField` (mirrors `0013:17-21`); `migrate trading 0013` reverts, zero data loss. Enforced by `test_migration_0014.py` round-trip + `makemigrations --check`.
- [x] **Controller allowlist 8→10 + preload**: `CONTROLLER_ALLOWLIST` (`views.py:62-73`) gains `draw-toolbar`,`object-tree`; `test_market_ux.py:128` count 8→10; `chart.html` modulepreload +2 (cores +2). Enforced by allowlist + preload tests.
- [x] **CSP unchanged**: no inline handler/script; icons JS-built inline SVG from `tool-icons-core` (no `on*` attr); `requirements.txt` unchanged. Enforced by CSP + source-scan tests.
- [x] **E2E readiness gate**: dev-only, `marketChart.ready`-gated; assert DOM + network, never pixels (#149). Enforced by `test_market_e2e.py`.
- [x] **patch coverage 100%** on new Python (0014 + flags + PUT/POST). Enforced by `diff-cover` vs `origin/develop`.
- [x] **TWO `SCALE_MODES` collision**: `chart-host.js:63-67` private map `SCALE_MODES` vs `chart-types-core.js:18` exported array `SCALE_MODES` → the moved registry constant MUST be **renamed** (e.g. `PRICE_SCALE_MODES`) in `chart-registry-core.js` to avoid an exported-name clash when both cores are imported. Enforced by an import/inventory test.

## Phase 1 — S1: extractions + drawing flags + migration 0014 (PR1)

Base tracker `feat/f5-chart-toolbar`; branch `feat/f5-chart-toolbar-s1`; deps none. Rollback: revert branch → no `visible`/`locked`, host registry back inline.

- [x] 1.1 **RED** `tests/js/chart-registry-core.test.js`: `REGISTRY`/`PANE_ORDER`/`PRICE_SCALE_MODES` shape (9 tokens; 5 pane order; 3 scale labels), no import, and the renamed constant does NOT collide with `chart-types-core.SCALE_MODES`. Acceptance: red before 1.2.
- [x] 1.2 **GREEN** NEW `market/chart-registry-core.js` (pure): move `REGISTRY` (`chart-host.js:16-56`), `PANE_ORDER` (`59`), scale map (`63-67`) **renamed** `PRICE_SCALE_MODES`; `chart-host.js` imports it (−52 lines); `indicators.js:9` re-points its `REGISTRY` import. Acceptance: host ≈259; guard green.
- [x] 1.3 **RED** `tests/web/test_migration_0014.py` (copy `0012` pattern): forward adds `visible=True`/`locked=False`, reverse drops both, rows survive. Acceptance: red before 1.4.
- [x] 1.4 **GREEN** `models.py:233-263` add `visible`(`BooleanField`,default True), `locked`(`BooleanField`,default False); NEW `migrations/0014_*.py` two `AddField`. Acceptance: 1.3 green; `makemigrations --check` clean.
- [x] 1.5 **RED** `tests/web/test_market_api.py` + `test_isolation.py`: POST/GET/PUT carry `visible`/`locked`; partial PUT keeps other fields; non-bool → 400 no write; miss/A≠B → 404 unchanged; `interval` key ignored (not 400). Acceptance: red before 1.6.
- [x] 1.6 **GREEN** `quotes.py` `parse_drawing` (`415-445`) validates real bools; `views.py` `_post_drawing`/`_put_drawing` (`419-455`,`479-512`) pass flags; `update_fields += ["visible","locked"]`; GET rows include both. Routes stay `for_user`. Acceptance: 1.5 green; patch 100%.
- [x] 1.7 **GREEN** `views.py:44` `MODULE_ALLOWLIST` +`chart-registry-core`; `chart.html` modulepreload +1. Acceptance: served 200; no 404.
- [x] 1.8 **REFACTOR** `ruff`/`node --test`/`pytest` clean; guard green with empty allowlist; `chart-host.js` ≤300; no `SCALE_MODES` clash. Acceptance: chain green.

## Phase 2 — S2: tool-icons-core + draw-toolbar + setSeriesVisible (PR2)

Base S1 branch; branch `feat/f5-chart-toolbar-s2`; deps S1. Rollback: revert branch → legacy draw buttons still work.

- [x] 2.1 **RED** `tests/js/tool-icons-core.test.js`: `TOOL_GROUPS` 5 kinds→2/1/1/1; `iconFor(kind)` returns a valid SVG string with NO `on*` attribute; `groupLabel`; no import. Acceptance: red before 2.2.
- [x] 2.2 **GREEN** NEW `market/tool-icons-core.js` (pure, no imports): `TOOL_GROUPS` (lines/fib/shapes/text), `TREE_GROUPS`, `iconFor`, `groupLabel`; inline SVG strings `currentColor`. Acceptance: 2.1 green.
- [x] 2.3 **RED** `tests/web/test_market_ux.py`: `CONTROLLER_ALLOWLIST` count `8→10`; `draw-toolbar` serves 200. Acceptance: red before 2.4.
- [x] 2.4 **GREEN** NEW `market/controllers/draw-toolbar.js` (`create({store,bus,config})`): `role="toolbar"` vertical, `role="group"` per group, native `<button aria-pressed>` + `data-kind` ∈ `DRAWING_KINDS`; sets `store.tool`; `store.subscribe` active state; roving `tabindex` + Up/Down/Home/End (mirror `toolbar.js:63-71`). Acceptance: 2.3 green; ≤300.
- [x] 2.5 **RED** `tests/js/chart-host.test.js` + `test_market_e2e.py`: `setSeriesVisible(token,false)` flips `options().visible`; `setData`/`update` spies stay untouched. Acceptance: red before 2.6.
- [x] 2.6 **GREEN** `chart-host.js` add option-only `setSeriesVisible` (~8 lines, `applyOptions({visible})`); `build()` applies initial hidden state. Acceptance: 2.5 green; host ≤300.
- [x] 2.7 **GREEN** `views.py:62` `CONTROLLER_ALLOWLIST` +`draw-toolbar`; `main.js` create+attach controller; `chart.html` replace `.draw-tool` block (`82-86`) with `#draw-tools` + modulepreload +1; `theme.css` `.draw-tools`/`.draw-tool` tokens. Acceptance: render + no inline handler.
- [x] 2.8 **REFACTOR** `drawings.js` drops tool/cancel DOM wiring (`19`,`218-232`) + `renderDrawingList` (`32-46`); delete dead code; ruff/node/pytest green; guard green. Acceptance: chain green.

## Phase 3 — S3: object-tree + indicator visibility (PR3)

Base S2 branch; branch `feat/f5-chart-toolbar-s3`; deps S2. Rollback: revert branch → no tree; drawings still render.

- [x] 3.1 **RED** `tests/js/chart-store.test.js` + `chart-host.test.js` + `test_market_api.py`: `STORE_KEYS==11` with `indicatorVisible`; `indicator:visibility` option-only; layout `visible` valid/bad/absent round-trip. Acceptance: red before 3.2–3.4.
- [x] 3.2 **GREEN** `chart-store.js:13-24` add 11th key `indicatorVisible`; `chart-bus.js:8-20` add `indicatorVisibility:"indicator:visibility"`; `main.js` route event → `host.setSeriesVisible` (mirror `main.js:179-182`). Acceptance: 3.1 (store/bus) green.
- [x] 3.3 **GREEN** `quotes.py` `parse_layout_indicators` (`300-328`): validate `visible` bool (absent = true, verbatim); `indicators.js` `buildIndicators` 4th arg `visible` (`absent=true` minimal payload); `loadLayout` writes `indicatorVisible`. Acceptance: layout tests green.
- [x] 3.4 **RED** `tests/js/object-tree.test.js` + `test_market_e2e.py`: tree groups (drawings + active-only), per-row eye/lock/delete/select; indicator eye → `indicator:visibility`, no refetch; keyboard nav. Acceptance: red before 3.5.
- [x] 3.5 **GREEN** NEW `market/controllers/object-tree.js` (`create({store,bus,config,onIndicatorSettings})`): `role="tree"`, group parents + rows; drawings eye/lock → `drawing:changed {visible|locked,persist:true}`, delete → `drawing:delete`, select → `drawing:selected`; indicator eye → `indicator:visibility`; subscribes `drawings:changed`/`layout:loaded`/`store.subscribe`; keyboard nav. Acceptance: 3.4 green; ≤300.
- [x] 3.6 **GREEN** `views.py:62` `CONTROLLER_ALLOWLIST` +`object-tree` (→10); `drawing-interaction.js` filter `locked` from `grabHandle` (`87`,`164`); `drawing-core.js` `fromApi` (`35-43`) carries flags; `drawing-primitive.js` `renderShape` (`32-74`) early-return hidden + `autoscaleInfo` null; `main.js` create tree (gear callback before first render, R12); `chart.html` replace indicators fieldset (`46-68`) + `#drawing-list` (`80-89`) with `#object-tree` + modulepreload +1; `theme.css` tree tokens; `indicators.js` delete DOM readers (`readIndicators` 49-56, `readParams` 37-46, `applyLayout` 95-110) re-source from store + `openSettings` (~12). Acceptance: wiring + a11y green.
- [x] 3.7 **REFACTOR** `ruff`/`node --test`/`pytest` clean; guard green (empty allowlist); seam 8 keys; `main.js` ≤300 (else D11). Acceptance: chain green.

## Verification (post-chain, pre-merge to `develop`)

- [x] 4.1 `node --test "tests/js/**/*.test.js"` green.
- [x] 4.2 `python -m pytest` green; `diff-cover` vs `origin/develop` → 100% patch on new Python.
- [x] 4.3 `ruff check . && ruff format --check .` clean.
- [x] 4.4 `python manage.py makemigrations --check` clean (0014 present, no drift).
- [x] 4.5 Guard/Edge Matrix fully checked; every module ≤300 (empty allowlist); frozen 8-key seam + 11-key store intact; no `SCALE_MODES` clash.
- [x] 4.6 Read-only: order scanner clean; CSP + `requirements.txt` unchanged; `src/` framework-free.
- [x] 4.7 E2E readiness-gated, DOM+network only (no pixels); existing assertions green unedited.

## Rollback

- **S1**: `git revert` the S1 commits → drawing flags gone; registry back inline in `chart-host.js`. Migration: `python manage.py migrate trading 0013` (additive, zero data loss).
- **S2**: `git revert` S2 commits → toolbar gone; legacy draw buttons restored; `setSeriesVisible` unused.
- **S3**: `git revert` S3 commits → tree gone; layout `visible` unset (absent = true) — no migration.
- **Tracker**: drop `feat/f5-chart-toolbar` and all slices; nothing merged to `develop`/`main` until green.
