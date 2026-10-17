# Tasks: f6-measure-position (issue #119, Fase F6)

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

## Archive Note (2026-10-17)

Delivered as a 6-PR chain, not the 3-slice plan. **S1–S3** are the tasks below;
beyond them: **S4** remediation (issues **#186–#189**, delivered in PRs
**#190/#191** — position draft Escape-cancel, readout/tree-select sync,
non-vacuous measure E2E readiness gate, S4 wiring), the **UI slice** (issues
**#192–#194**, PR #195 — coalesced `aria-live` readout writes, theme-token reads
for canvas position/measure colors, the `position-seed` controller split + its own
group/styling/seed state), and the **final slice** (PR #196 — off-scale position
band degrades to null; drop the per-move readout write). The tracker merged to
`develop` as PR **#197**. All
S1–S6 tasks and the Guard/Edge Matrix are complete per the verify-report. Three
reconciliations applied at archive: `CONTROLLER_ALLOWLIST` is **13** (not 12 — the
UI slice added `position-seed`); `position-draft-core.js` and
`readout-coalesce-core.js` join the pure-core inventory; and verify CRITICALs
**C1** (position R:R `aria-live` DOM) / **C2** (Escape cancels a pending position
draft) were remediated in S4/UI and are now reflected in the canonical specs. See
the archive-report for details.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | S1 ~300, S2 ~300, S3 ~350 → **~950** |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 (`measure-core`+`position-core`+node tests) → PR2 (`Kind.POSITION`+migration `0015`+`parse_drawing`+allowlists+API/migration tests) → PR3 (`controllers/measure`+toolbar groups+position render/interaction+3-click flow+SMC seed+E2E) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

### Suggested Work Units

| Unit | Goal | Likely PR | Base / boundary |
|------|------|-----------|-----------------|
| S1 | Pure cores `measure-core.js`/`position-core.js` + node tests; no DOM, no app impact | PR 1 | base = tracker `feat/f6-measure-position` |
| S2 | `Drawing.Kind.POSITION` + migration `0015` + `parse_drawing` branch + 3 allowlist entries + API/migration tests | PR 2 | base = S1 branch; merge S1→tracker first |
| S3 | `controllers/measure.js` + toolbar groups + position render/interaction + `drawings.js` 3-click + SMC seed + E2E | PR 3 | base = S2 branch; merge S2→tracker first |

All PRs base on the tracker `feat/f6-measure-position`; merge each slice to the tracker before branching the next. Only the tracker merges to `develop`; `main` untouched. Total ≈ 950 > 400.

## Guard / Edge Matrix

- [x] **300-line ceiling (prove by construction)**: `controllers/smc.js`=300 and `controllers/object-tree.js`=299 stay **byte-untouched** — measure is a separate controller that never imports `smc.js`; the position row rides the existing kind-agnostic loop `object-tree.js:106-144` (`row.kind+" #"+row.id`) and `TREE_GROUPS[0].kinds` is never consumed (`object-tree.js:22`). Largest touched module `drawings.js` 240→~262. Enforced by `tests/web/test_module_size_guard.py` (`CEILING=300`, empty `ALLOWLIST`) + `git diff --exit-code` on the two files.
- [x] **`window.marketChart` 8-key freeze** (`main.js:55-64`, R18/R20): no 9th key; measure asserted via `#measure-readout` DOM, position via `marketChart.drawings` + captured POST/PUT. Enforced by E2E seam check.
- [x] **`STORE_KEYS` 11 freeze** (`chart-store.js:13-27`): no new key (D3); both tools use `store.tool` + literals. Enforced by `tests/js/chart-store.test.js`.
- [x] **#68 option-only/primitive**: measure + position render on primitives via `requestUpdate`; never `setData`/`update`. `setData` spy stays green. Enforced by `chart-host.test.js` + E2E.
- [x] **Single-source (no JS SMC recompute)**: seed copies `setups` verbatim from `smc:loaded` payload (`controllers/smc.js:241`; `quotes.py:697-708`); client only re-derives R:R during drag. Enforced by `chart-controllers.test.js` + E2E seed assertion.
- [x] **`parse_drawing` position branch (bad → 400)**: full matrix — valid 201; missing `stop`/`take_profit` 400; `entry` not dict/`time` non-int/`price` non-num 400; non-num or bool level 400; extra/missing key 400; degenerate `entry.price==stop` 400; `interval` ignored (not 400); unknown kind 400. Enforced by `test_market_api.py` (`diff-cover` 100%).
- [x] **Migration `0015` choices-only reversible**: one `AlterField` on `kind` (deps `0014_drawing_visible_locked`); `migrate trading 0014` reverses, zero row loss (`makemigrations --check` green). Enforced by new `test_migration_0015.py`.
- [x] **R14 `for_user`**: position POST/PUT/GET/DELETE reuse `api_drawings` (`views.py:397-534`), `for_user`-scoped; A≠B / miss → 404 no leak. Enforced by `test_market_api.py` isolation + `test_isolation.py`.
- [x] **`CONTROLLER_ALLOWLIST` 11→12 + `MODULE_ALLOWLIST` +2 + modulepreload +3**: `views.py:44-77` gains `measure-core`,`position-core` (cores) + `measure` (controller); `test_market_ux.py:146` count `11→12`; `chart.html:102-128` modulepreload +3. Enforced by allowlist + preload tests.
- [x] **CSP unchanged**: no inline handler/script; measure/position icons are JS-built SVG strings, no `on*` (`tool-icons-core.js:28-46`); readouts are `textContent`; `requirements.txt` and `script-src` unchanged. Enforced by CSP + source-scan tests.
- [x] **E2E readiness gate**: dev-only, `marketChart.ready`-gated; assert DOM + network, never pixels (#149). Enforced by `test_market_e2e.py`.
- [x] **patch coverage 100%** on new Python (`0015` + `parse_drawing` branch). Enforced by `diff-cover` vs `origin/develop`.
- [x] **R14 `for_user` + no new bus event**: position reuses `drawing:changed`/`drawing:selected`; measure adds none (no `measure:*`/`position:*`). Enforced by `chart-bus.test.js` + E2E.

## Phase 1 — S1: pure cores + node tests (PR1)

Base tracker `feat/f6-measure-position`; branch `feat/f6-measure-position-s1`; deps none. Rollback: revert branch → delete 2 files, no app impact.

- [x] 1.1 **RED** `tests/js/measure-core.test.js`: `measure(a,b,iv)` returns `{priceDelta,pricePct,timeDelta,bars,candles}` for known inputs; negative deltas kept (direction by sign); `bars===candles===round(timeDelta/iv)`; `timeDelta/bars/candles` null when `a.time`/`b.time` null. `formatMeasure(m)` → `{price,pct,time,bars}` strings. Acceptance: red before 1.2.
- [x] 1.2 **GREEN** NEW `web/market/templates/market/measure-core.js` (pure): `measure`/`formatMeasure`; imports `intervalSeconds` from `chart-core.js:16-38` (single source, R2); no DOM, never throws. Acceptance: 1.1 green; ≤300.
- [x] 1.3 **RED** `tests/js/position-core.test.js`: `levelsFrom` `{entry:{time,price},stop,take_profit}`→`{entry,stop,takeProfit,long}` (long=stop<entry; null on invalid/missing/non-num); `riskReward` long `(tp-entry)/(entry-stop)`, short `(entry-tp)/(stop-entry)`, `rr===null` when `entry===stop`; `positionBox`/`positionHandles` geometry + `null` when entry.x off-bar; `defaultPositionStyle`. Acceptance: red before 1.4.
- [x] 1.4 **GREEN** NEW `web/market/templates/market/position-core.js` (pure, no imports): `BOX_WIDTH`, `levelsFrom`, `riskReward`, `positionBox`, `positionHandles`, `defaultPositionStyle` per design `Interfaces`. Acceptance: 1.3 green; ≤300.
- [x] 1.5 **REFACTOR** `node --test "tests/js/**/*.test.js"` green; `ruff` untouched; both cores ≤300 (guard green). Acceptance: chain green.

## Phase 2 — S2: Kind.POSITION + migration 0015 + parse_drawing + allowlists (PR2)

Base S1 branch; branch `feat/f6-measure-position-s2`; deps S1. Rollback: revert branch → `migrate trading 0014`, drop one `elif`.

- [x] 2.1 **RED** `tests/web/test_migration_0015.py` (copy `test_migration_0014.py`): pin `0014_drawing_visible_locked`; seed rows of every prior kind; forward → `"position"` selectable, rows survive; reverse → prior choices, no row lost. Acceptance: red before 2.2.
- [x] 2.2 **GREEN** `web/trading/models.py:244-252` add `POSITION = "position"` to `Kind`; NEW `web/trading/migrations/0015_drawing_kind_position.py` choices-only `AlterField` (deps `0014`, per design `Server Design`). Acceptance: 2.1 green; `makemigrations --check` clean.
- [x] 2.3 **RED** `tests/web/test_market_api.py` + `test_isolation.py`: position POST/GET/PUT round-trip; full 400 matrix incl. degenerate `entry.price==stop`; `interval` ignored (not 400); A≠B / miss → 404; `DRAWING_KINDS` auto-includes `position`. Acceptance: red before 2.4.
- [x] 2.4 **GREEN** `web/market/quotes.py:453` append `elif kind == "position"` branch (exact keys `{entry,stop,take_profit}`; `_parse_point(entry,require_time=True)`; `_is_number(stop/take_profit)`; reject `stop==entry.price`) per design `Server Design`; `DRAWING_KINDS` (`quotes.py:402`) auto-includes it. Acceptance: 2.3 green; patch 100%.
- [x] 2.5 **GREEN** `web/market/views.py:44-77` `MODULE_ALLOWLIST` +`measure-core`,`position-core`; `CONTROLLER_ALLOWLIST` +`measure` (→12); `tests/web/test_market_ux.py:146` count `11→12`; `open` chart route unaffected. Acceptance: served 200; no 404.
- [x] 2.6 **GREEN** `web/market/templates/market/chart.html:102-128` modulepreload +3 (`measure-core`,`position-core`,`measure`) mirroring the existing blocks. Acceptance: preload test green.
- [x] 2.7 **REFACTOR** `ruff check . && ruff format --check .`, `node --test`, `pytest` clean; guard green with empty allowlist; `smc.js`=300/`object-tree.js`=299 `git diff --exit-code` unchanged. Acceptance: chain green.

## Phase 3 — S3: measure controller + toolbar + position render/interaction + E2E (PR3)

Base S2 branch; branch `feat/f6-measure-position-s3`; deps S2. Rollback: revert branch → no measure/position UI; nothing persisted beyond S2's schema.

- [x] 3.1 **RED** `tests/js/tool-icons-core.test.js`: `TOOL_GROUPS` gains `{label:"Measure",kinds:["measure"]}` + `{label:"Positions",kinds:["position"]}`; `iconFor("measure")`/`iconFor("position")` return valid SVG strings with NO `on*` attribute. Acceptance: red before 3.2.
- [x] 3.2 **GREEN** `tool-icons-core.js:14` +2 groups; `tool-icons-core.js:33` `ICON_BODIES` +2 (inline SVG, `currentColor`, no `on*`); optional `"position"` in `TREE_GROUPS[0].kinds` (non-load-bearing); `controllers/draw-toolbar.js:17-23` `TOOL_LABELS` +`measure`,`position` (no new wiring). Acceptance: 3.1 green.
- [x] 3.3 **RED** `tests/js/drawing-core.test.js` + `drawing-interaction-core.test.js` + `drawing-primitive.test.js`: `DRAWING_KINDS` includes `position` + `defaultStyle("position")`; `handlesFor` returns 4 (`stop`/`take_profit`/entry-price + entry anchor); drag a level → only that price; drag body → all three shift; `bodyHit` = entry→stop ∪ entry→tp band; `fromApi` accepts `position`; render branch delegates to `position-core.positionBox`; `priceRangeFor` includes `stop`/`take_profit`; hidden/off-bar degrade. Acceptance: red before 3.4.
- [x] 3.4 **GREEN** `drawing-core.js:13` add `"position"` + `defaultStyle` branch (`:25-30`); `drawing-interaction-core.js:30,103,148` position cases in `handlesFor`/`bodyHit`/`applyDrag` (delegating to `position-core`; never mutate); `drawing-primitive.js:13,32` `position` branch → `position-core.positionBox` + `priceRangeFor` pushes `stop`/`take_profit` + import. Acceptance: 3.3 green; each module ≤300.
- [x] 3.5 **RED** `tests/js/chart-controllers.test.js` + `test_market_e2e.py`: measure drag → `#measure-readout aria-live` DOM, no POST/PUT; new measure replaces old; Esc/tool-change/symbol-switch clear; measure `autoscaleInfo` null + `setData`/`update` spies untouched; position 3-click → captured POST; drag → ONE PUT; seed copies a setup's levels verbatim. Acceptance: red before 3.6.
- [x] 3.6 **GREEN** NEW `controllers/measure.js` (~180, `createMeasure({store,bus,host,config})`→`{attach,clearForSwitch}`): own `#chart` pointer listeners guarded by `state.tool==="measure"`; one `ISeriesPrimitive`; `autoscaleInfo` null; `requestUpdate` only; `#measure-readout` `textContent`; Escape/guard clear (design `Render + Interaction`). Acceptance: 3.5 (measure) green; ≤300.
- [x] 3.7 **GREEN** `controllers/drawings.js` `onChartClick` (`:171-200`) `pendingPosition` 3-click branch; `setups` cache via `bus.on("smc:loaded")` + `seedFromSetup` copying `entry/stop/take_profit` verbatim (D5); `#position-seed` listener reusing the `textDialog` block (`:212-225`); extend `store.subscribe` guard (`:205-210`) to reset `pendingPosition`. Acceptance: 3.5 (position/seed) green.
- [x] 3.8 **GREEN** `main.js:19-24` `createMeasure` import+create; `buildChart` `measure.attach()`; `switchTo` `measure.clearForSwitch()` (+6 lines, ≤~255); `chart.html` add `#measure-readout`/`#position-seed` markup; `theme.css` readout tokens. Acceptance: wiring green; no new seam key; CSP clean.
- [x] 3.9 **REFACTOR** `ruff`/`node --test`/`pytest` clean; guard green (empty allowlist); seam 8 keys; `STORE_KEYS` 11; `smc.js`/`object-tree.js` byte-untouched. Acceptance: chain green.

## Verification

- [x] V.1 `node --test "tests/js/**/*.test.js"` green.
- [x] V.2 `.venv/bin/python -m pytest` green; `diff-cover` vs `origin/develop` → 100% patch on new Python.
- [x] V.3 `.venv/bin/ruff check . && .venv/bin/ruff format --check .` clean.
- [x] V.4 `.venv/bin/python web/manage.py makemigrations --check --dry-run` clean (`0015` present, no drift).
- [x] V.5 Guard/Edge Matrix fully checked; every module ≤300 (empty allowlist); 8-key seam + 11-key store intact; `smc.js`/`object-tree.js` unchanged.
- [x] V.6 Read-only: order scanner (`test_no_order_surface.py`) clean; CSP + `requirements.txt` unchanged; `src/` unchanged.
- [x] V.7 E2E readiness-gated, DOM+network only (no pixels); existing assertions green unedited.

## Rollback

- **S1**: `git revert` the S1 commits → the two core files are deleted; no app impact.
- **S2**: `git revert` the S2 commits → `position` kind gone; run `.venv/bin/python web/manage.py migrate trading 0014` (choices-only, zero data loss); allowlists back to 11.
- **S3**: `git revert` the S3 commits → measure/position UI gone; nothing persisted that S2 did not already allow (measure is ephemeral — no state to unwind).
- **Tracker**: drop `feat/f6-measure-position` and all slices; nothing merged to `develop`/`main` until green.
