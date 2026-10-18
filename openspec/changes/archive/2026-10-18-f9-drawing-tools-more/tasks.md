# Tasks: f9-drawing-tools-more (issue #122, Fase F9)

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

> **Archive reconciliation (2026-10-18).** All checkboxes are reconciled to `[x]`
> at archive — the apply hard contract forbids editing `openspec/**` during apply.
> The DELIVERED chain went beyond the original 3 slices: S1/S2/S3 as planned, plus
> **S3b** (E2E coverage + preload/serve check, PR #215) and the `/impeccable
> needs-rework` remediation slices **R1** (PR #224) and **R2** (PR #225), which
> added `tool-render-core`, `object-tree-dom-core`, and `controllers/draft-preview`
> and reworked the render/a11y details. The 3.11 goal "`CONTROLLER_ALLOWLIST`
> unchanged" did NOT hold: the R2 draft-preview extraction added `draft-preview`
> (16 entries) — the canonical `market-chart` R14 records the delivered value.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | S1 ~560, S2 ~285, S3 ~405 → **~1250** |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 (3 pure cores + node tests) → PR2 (`Kind`+8 + `0016` + `parse_drawing` +8 + API/migration tests) → PR3 (dispatch guards + `drawings.js` shrink + toolbar icons/letters + allowlist +3 + E2E) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

### Suggested Work Units

| Unit | Goal | Likely PR | Base / boundary |
|------|------|-----------|-----------------|
| S1 | Pure cores `drawing-tools-core.js` (~235), `fib-tools-core.js` (~95), `drawing-click-flow-core.js` (~85) + node tests; unimported, no app impact | PR 1 | base = tracker `feat/f9-drawing-tools-more` |
| S2 | `Drawing.Kind` +8 (`models.py:244-249`) + `0016_drawing_kind_tools` + `parse_drawing` +8 branches (`quotes.py:427-461`) + `test_migration_0016.py` + per-kind API matrix | PR 2 | base = S1 branch; merge S1→tracker first |
| S3 | Dispatch guards (`drawing-core:13,28` / `drawing-primitive:14,37` / `drawing-interaction-core:31,107,162`) + `drawings.js:193-230` click-flow extraction (298→~262) + `tool-icons-core`/`draw-toolbar` +8 + `MODULE_ALLOWLIST` +3 (`views.py:44`) + E2E | PR 3 | base = S2 branch; merge S2→tracker first |

All PRs base on the tracker `feat/f9-drawing-tools-more`; merge each slice to the tracker before branching the next. Only the tracker merges to `develop`; `main` untouched. Total ≈ 1250 > 400 (S1 and S3 each individually exceed 400 → review in ≤60 min slices; if S1 exceeds 400 in practice, promote `drawing-tools-core`+tests to its own PR).

## Guard / Edge Matrix

- [x] **300-line ceiling**: `controllers/smc.js`=300 (`wc -l`), `controllers/object-tree.js`=299 stay **byte-untouched** (`git diff --stat` empty for both every slice) and `controllers/drawings.js` **SHRINKS** 298→~262. Enforced by empty-allowlist `tests/web/test_module_size_guard.py` (`CEILING=300`, `ALLOWLIST=frozenset()`).
- [x] **`window.marketChart` 8-key freeze** (`main.js:59-66`, R18/R20): new kinds reuse the `drawings` key (`drawings.js:50,111`); asserted via `window.marketChart.drawings` + captured POST/PUT/DELETE, never a 9th key. Enforced by E2E seam check.
- [x] **`STORE_KEYS` 11 freeze** (`chart-store.js:13-27`): F9 adds no store key — activates the existing `tool` value only. Enforced by `tests/js/chart-store.test.js`.
- [x] **#68 single-write-path**: new kinds render on primitives + `requestUpdate`; POST only via `createDrawing` (`drawings.js:152`); no new bus event. `setData`/`update` spies stay green. Enforced by `chart-host.test.js` + E2E.
- [x] **R14 `for_user`**: CRUD reuses `api_drawings`/`api_drawing_detail` (`views.py:407,491`); cross-user id → 404. Enforced by `test_market_api.py` isolation.
- [x] **8 `parse_drawing` branches**: per-kind valid/invalid matrix (ray/vline/channel/price/callout/fib_ext/fib_time/fib_zone schemas, `quotes.py:427-461`), exact-key `set(points)` checks; valid→201, malformed→400, no row. Enforced by `test_market_api.py` + `diff-cover`.
- [x] **`0016` choices-only reversible**: mirrors `0015`; forward adds 8 choices, reverse to `0015`, every prior row keeps its `kind`, no column/row change; `makemigrations --check` green. Enforced by `test_migration_0016.py`.
- [x] **`MODULE_ALLOWLIST` +3 cores** (`views.py:44`): `drawing-tools-core`,`fib-tools-core`,`drawing-click-flow-core` served 200; `CONTROLLER_ALLOWLIST` (`views.py:71`) **unchanged** (`== 15`). Enforced by `test_market_ux.py::test_f9_cores_are_served` + count test.
- [x] **CSP unchanged** (`middleware.py` header): 8 icons are plain strings on native `<button>`, no inline `on*`/`<script>`; `callout` reuses `#text-dialog`. Enforced by CSP + source-scan tests.
- [x] **E2E readiness gate**: dev-only, `_wait_ready`-gated (`test_market_e2e.py:563`); assert DOM + captured network, never pixels (#149). Enforced by `test_market_e2e.py`.
- [x] **patch coverage 100%** on new Python (`parse_drawing`, migration). Enforced by `diff-cover` vs `origin/develop`.
- [x] **fib-ratio orientation** `ratio 0 == p2` (`fibExtLevels` mirrors `drawing-core.js:96-101`); `fib_ext` uses `FIB_EXT_RATIOS`, `fib_time`/`fib_zone` reuse `FIB_RATIOS`. Enforced by `fib-tools-core.test.js`.
- [x] **undo/history replay of new kinds**: `undo.js`/`history-core.js` kind-agnostic (F7); `fib_ext`/`channel`/… replay verbatim, no new event/key. Enforced by E2E undo.

## Phase 1 — S1: pure cores + node tests (PR1)

Base tracker `feat/f9-drawing-tools-more`; branch `feat/f9-drawing-tools-more-s1`; deps none. Rollback: revert branch → delete 3 files, no app impact (unimported, no allowlist yet).

- [x] 1.1 **RED** `tests/js/drawing-tools-core.test.js`: `NEW_KINDS` = 8; `TOOL_SPECS[k]` completeness (clicks/path/handles/bodyHit/drag for each); `clicksFor`; each `toolPath` (ray right-edge projection, channel parallel); `toolDrag` moves only the target anchor / whole body. Acceptance: red before 1.2.
- [x] 1.2 **GREEN** NEW `web/market/templates/market/drawing-tools-core.js` (~235, pure; imports `drawing-core`/`fib-tools-core`): `NEW_KINDS`, `TOOL_SPECS`, `defaultToolStyle`, `toolPath`, `toolHandles`, `toolBodyHit`, `toolDrag`, `clicksFor` (design `Descriptor-Map Contract`). Acceptance: 1.1 green; ≤300.
- [x] 1.3 **RED** `tests/js/fib-tools-core.test.js`: `fibExtLevels` (ratio 0 == `price2`; ratio 1 projects beyond p2); `fibTimePath` (null when no bar); `fibZoneBands` (band skipped on null y). Acceptance: red before 1.4.
- [x] 1.4 **GREEN** NEW `web/market/templates/market/fib-tools-core.js` (~95, pure; imports `drawing-core` only): `FIB_EXT_RATIOS=[0,0.618,1,1.272,1.618,2.618]`, `fibExtLevels`, `fibTimePath`, `fibZoneBands` (design `Interfaces`). Acceptance: 1.3 green; ≤300.
- [x] 1.5 **RED** `tests/js/drawing-click-flow-core.test.js`: 1/2/3-click per kind; kind switch resets; `text`/`callout`→`dialog`; `cancel`/`reset`/`active`; kind-shaped points (`channel`/`fib_ext` `{p1,p2,p3}`). Acceptance: red before 1.6.
- [x] 1.6 **GREEN** NEW `web/market/templates/market/drawing-click-flow-core.js` (~85, pure; imports `drawing-tools-core`/`position-core`): `createFlow()→{collect,cancel,active,reset}` (design `Interfaces`). Acceptance: 1.5 green; ≤300.
- [x] 1.7 **REFACTOR** `node --test "tests/js/**/*.test.js"` green; size guard green (empty allowlist). Acceptance: chain green.

## Phase 2 — S2: `Kind` +8 + `0016` + `parse_drawing` + API/migration tests (PR2)

Base S1 branch; branch `feat/f9-drawing-tools-more-s2`; deps S1. Rollback: revert branch; `.venv/bin/python web/manage.py migrate trading 0015_drawing_kind_position`.

- [x] 2.1 **RED** `tests/web/test_migration_0016.py` (copy `test_migration_0015.py`): pin at `0015`, seed a row of every prior kind, forward proves all 8 kinds selectable + rows survive, reverse proves every row survives. Acceptance: red before 2.2–2.3.
- [x] 2.2 **GREEN** `web/trading/models.py:244-249` `Kind` +8 (`RAY`/`VLINE`/`CHANNEL`/`PRICE`/`CALLOUT`/`FIB_EXT`/`FIB_TIME`/`FIB_ZONE`). Acceptance: 2.1 (choices) red still (migration pending).
- [x] 2.3 **GREEN** NEW `web/trading/migrations/0016_drawing_kind_tools.py` (deps `0015`; choices-only `AlterField`, max_length=16, mirrors `0015`). Acceptance: 2.1 green; `makemigrations --check` green.
- [x] 2.4 **RED** `tests/web/test_market_api.py` per-kind 400 matrix (ray/vline/channel/price/callout/fib_ext/fib_time/fib_zone; exact keys, missing `time`/`price`/`text`, non-numeric, wrong count) + 8-kind round-trip + A≠B→404. Acceptance: red before 2.5.
- [x] 2.5 **GREEN** `web/market/quotes.py:427-461` `parse_drawing` +8 branches (one `elif` each, reuse `_parse_point:412`; `vline`=1 `{time}`, `price`=1 `{price}`). Acceptance: 2.4 green; `DRAWING_KINDS` (`:402`) auto-includes 8.
- [x] 2.6 **REFACTOR** `.venv/bin/python -m pytest -p no:randomly` green; `diff-cover` vs `origin/develop` → 100% on new Python; ruff clean. Acceptance: chain green.

## Phase 3 — S3: dispatch + click-flow extraction + toolbar + allowlist + E2E (PR3)

Base S2 branch; branch `feat/f9-drawing-tools-more-s3`; deps S2. Rollback: revert branch; `drawings.js` restores its 2-click flow; nothing persisted.

- [x] 3.1 **RED** `tests/js/drawing-core.test.js`: `DRAWING_KINDS` (`:13`) includes 8; `defaultStyle` delegates new kinds; `fromApi` accepts 8. Acceptance: red before 3.2.
- [x] 3.2 **GREEN** `drawing-core.js:13,17,28`: `DRAWING_KINDS` +8, `COLORS` +8, ONE `defaultStyle` guard `Tools.NEW_KINDS.includes(kind)`; import `Tools` (+13, ≤300). Acceptance: 3.1 green.
- [x] 3.3 **RED** `tests/js/drawing-primitive.test.js`: each F9 kind draws its geometry (ray ext/vline/parallel channel/labelled price/callout/fib levels); `autoscaleInfo` includes `p3`; null leg skipped. Acceptance: red before 3.4.
- [x] 3.4 **GREEN** `drawing-primitive.js:14,37`: `priceRangeFor` pushes `p3`; ONE `renderTool` guard in `renderShape` + 8-branch canvas switch; import `Tools`/`FibTools` (+50, ~228 ≤300). Acceptance: 3.3 green.
- [x] 3.5 **RED** `tests/js/drawing-interaction-core.test.js`: `handlesFor` counts (ray 2/callout 2/fib_time 2/fib_zone 2/channel 3/fib_ext 3/vline 1/price 1); drag F9 anchor moves only it; body translates all. Acceptance: red before 3.6.
- [x] 3.6 **GREEN** `drawing-interaction-core.js:31,107,162`: 3 ONE-guards → `Tools.toolHandles`/`toolBodyHit`/`toolDrag`; import `Tools` (+10, ≤300). Acceptance: 3.5 green.
- [x] 3.7 **RED** `tests/js/chart-controllers.test.js`: 1/2/3-click create for each F9 kind → ONE POST; tool switch / `Escape` / `clearForSwitch` cancel the draft; `text`/`callout` open `#text-dialog`. Acceptance: red before 3.8.
- [x] 3.8 **GREEN** `drawings.js:193-230` `onChartClick` → ~11-line `flow.collect` delegate; move `pendingAnchor`/`positionDraft` into `createFlow`; dialog merge for `text`+`callout` (298→~262, ≤300). Acceptance: 3.7 green.
- [x] 3.9 **RED** `tests/js/tool-icons-core.test.js` + `draw-toolbar.test.js`: `TOOL_GROUPS` 6/4/1/2/1/1 (15 instruments); 8 CSP-clean distinct icons; `TOOL_KEYS` +8 non-colliding letters (`ray=A,vline=I,channel=C,price=U,callout=O,fib_ext=E,fib_time=W,fib_zone=Z`); letters `#chart`-scoped. Acceptance: red before 3.10.
- [x] 3.10 **GREEN** `tool-icons-core.js:14,27,37` +8 icons/groups; `draw-toolbar.js:20,31` `TOOL_KEYS`/`TOOL_LABELS` +8 (+28, ≤300). Acceptance: 3.9 green.
- [x] 3.11 **GREEN** `views.py:44` `MODULE_ALLOWLIST` +3 cores; `CONTROLLER_ALLOWLIST` (`:71`) unchanged. Acceptance: served 200; no 404.
- [x] 3.12 **RED** `tests/web/test_market_ux.py::test_f9_cores_are_served` (3 cores 200) + keep `CONTROLLER_ALLOWLIST == 15` unedited. Acceptance: red before 3.11.
- [x] 3.13 **RED** `tests/web/test_market_e2e.py` (mirror `:976-1010`): F9 tool click → captured 8-kind POST; drag → ONE PUT; undo replays a new kind; `setData` spy green. Readiness-gated, DOM+network only. Acceptance: red before 3.4–3.10 land.
- [x] 3.14 **REFACTOR** `node --test`/`pytest`/`ruff` clean; guard green (empty allowlist); 8-key seam + `STORE_KEYS` 11; `smc.js`/`object-tree.js` `git diff --exit-code` unchanged; `drawings.js` shrunk. Acceptance: chain green.

## Verification

- [x] V.1 `node --test "tests/js/**/*.test.js"` green.
- [x] V.2 `.venv/bin/python -m pytest -p no:randomly` green; `diff-cover` vs `origin/develop` → 100% patch on new Python.
- [x] V.3 `.venv/bin/ruff check . && .venv/bin/ruff format --check .` clean.
- [x] V.4 `.venv/bin/python web/manage.py makemigrations --check --dry-run` clean.
- [x] V.5 Guard/Edge Matrix fully checked; every module ≤300 (empty allowlist); `wc -l` proves `smc.js`=300/`object-tree.js`=299 unchanged and `drawings.js` shrunk; 8-key seam + 11-key store.
- [x] V.6 Read-only: CSP + `requirements.txt` unchanged; `src/` unchanged; no new dependency/build.
- [x] V.7 E2E readiness-gated, DOM+network only (no pixels); existing assertions green unedited.

## Rollback

- **S1**: `git revert` the S1 commits → the three core files are deleted; no app impact (unimported, no allowlist yet).
- **S2**: `git revert` the S2 commits → drop 8 `elif`s + `0016`; `.venv/bin/python web/manage.py migrate trading 0015_drawing_kind_position` restores prior choices (zero data loss); `Kind` reverts.
- **S3**: `git revert` the S3 commits → dispatch/toolbar/click-flow reverted; `MODULE_ALLOWLIST` back to -3; `drawings.js` restores its 2-click flow; nothing persisted.
- **Tracker**: drop `feat/f9-drawing-tools-more` and all slices; nothing merged to `develop`/`main` until green.
