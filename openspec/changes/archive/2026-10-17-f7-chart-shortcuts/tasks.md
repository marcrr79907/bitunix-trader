# Tasks: f7-chart-shortcuts (issue #120, Fase F7)

> **Archive reconciliation (2026-10-17).** All checkboxes below are marked `[x]`
> at archive (the apply hard contract forbids editing `openspec/**` during apply).
> Beyond the original 3-slice plan (S1 pure cores / S2 undo / S3 context menu),
> three further slices shipped and are folded into the recorded tasks: the **S4
> remediation** slice (#200 committed-cache freshness across an undo, #201 unblock
> a failed restore, plus the C1 letter-router remediation), the **UI slice**
> (#204 keyboard menu open, #205 undo/redo announcement, #206 visible shortcut
> letters + honest `aria-keyshortcuts`, #207 elevation shadow), and the
> **concurrency slice** (#209 ignore undo/redo while a replay is in flight). The
> canonical specs reflect the DELIVERED behavior.

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
| Suggested split | PR1 (`history-core`+`context-menu-core`+node tests) → PR2 (`controllers/undo`+`drawing:duplicate`/`restore`/`created`+`Ctrl/Cmd+Z`+main wiring+allowlist 13→14+E2E) → PR3 (`controllers/context-menu`+`draw-toolbar` `aria-keyshortcuts`+allowlist 14→15+preloads+menu CSS+`test_market_ux` count+E2E) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

### Suggested Work Units

| Unit | Goal | Likely PR | Base / boundary |
|------|------|-----------|-----------------|
| S1 | Pure cores `history-core.js`/`context-menu-core.js` + node tests; no DOM, no app impact | PR 1 | base = tracker `feat/f7-chart-shortcuts` |
| S2 | `controllers/undo.js` + `drawing:duplicate`/`restore`/`created` in `drawings.js` + `Ctrl/Cmd+Z` + main wiring + allowlist 13→14 + E2E | PR 2 | base = S1 branch; merge S1→tracker first |
| S3 | `controllers/context-menu.js` + `draw-toolbar` `aria-keyshortcuts` + allowlist 14→15 + preloads + menu CSS + `test_market_ux` count + E2E | PR 3 | base = S2 branch; merge S2→tracker first |

All PRs base on the tracker `feat/f7-chart-shortcuts`; merge each slice to the tracker before branching the next. Only the tracker merges to `develop`; `main` untouched. Total ≈ 950 > 400.

## Guard / Edge Matrix

- [x] **300-line ceiling**: `controllers/smc.js`=300, `controllers/object-tree.js`=299, `controllers/drawing-interaction.js`=291 stay **byte-untouched** — menu binds its OWN `contextmenu`; duplicate/delete reuse bus events; undo replays bus commands. Enforced by empty-allowlist `tests/web/test_module_size_guard.py` (`CEILING=300`) + `git diff --stat` empty for the three paths every slice.
- [x] **`window.marketChart` 8-key freeze** (`main.js:57-66`, R18/R20): no 9th key; undo asserted via captured POST/PUT/DELETE, menu via DOM `role="menu"`. Enforced by E2E seam check.
- [x] **`STORE_KEYS` 11 freeze** (`chart-store.js:13-27`, D1/#68): no 12th key — stack is a pure core. Enforced by `tests/js/chart-store.test.js`.
- [x] **#68 single-write-path**: menu/undo replay the existing bus commands; never `setData`/`update`. `setData` spy stays green. Enforced by `chart-host.test.js` + E2E.
- [x] **Drag coalescing**: record ONLY on `drawing:changed persist:true` (`drawing-interaction.js:201`); `before` from the `drawings:changed` cache (`drawings.js:51`), never per-frame. Enforced by `chart-controllers.test.js` + E2E.
- [x] **Undo/server consistency**: operation stack + `replaying` guard + async `drawing:created {id}` patch re-mint; undo-delete re-POSTs (new id), undo-create DELETEs, undo-move PUTs `before`. Enforced by `history-core` node tests + E2E network intercept.
- [x] **R14 `for_user` + `clear()` on symbol switch**: replay routes `Drawing.for_user`; `clearForSwitch` clears stack + `committed` (`main.js:161-167`). Enforced by `test_market_api.py` isolation + E2E.
- [x] **Shortcut non-conflict**: only `Ctrl/Cmd+Z`/`Shift+Z`/`Y`; tree `v`/`l`/`s` (`object-tree.js:137-142,201-205`) and `#chart` Escape/Delete (`drawing-interaction.js:213-231`) untouched. Enforced by E2E key tests.
- [x] **CSP unchanged**: JS-built menu, no inline `oncontextmenu`/`<script>`; `middleware.py:28` header unchanged. Enforced by CSP + source-scan tests.
- [x] **E2E readiness gate**: dev-only, `_wait_ready`-gated (`test_market_e2e.py:563`); assert DOM + network, never pixels (#149). Enforced by `test_market_e2e.py`.
- [x] **patch coverage 100%** on new Python (allowlists). Enforced by `diff-cover` vs `origin/develop`.
- [x] **Allowlists**: `MODULE_ALLOWLIST` +2 (`history-core`,`context-menu-core`); `CONTROLLER_ALLOWLIST` 13→15 (+`undo`,`context-menu`, `views.py:44-85`); `test_market_ux.py:146` `== 13`→`== 15`; `chart.html:107-127` modulepreload +4. Enforced by allowlist + preload tests.

## Phase 1 — S1: pure cores + node tests (PR1)

Base tracker `feat/f7-chart-shortcuts`; branch `feat/f7-chart-shortcuts-s1`; deps none. Rollback: revert branch → delete 2 files, no app impact.

- [x] 1.1 **RED** `tests/js/history-core.test.js` (mirror `drawing-interaction-core.test.js`): `push`/`undo`/`redo`/`canUndo`/`canRedo`/`clear`/`size`; redo-clear on push; bound-50 drops oldest; empty→`null`; LIFO; a returned entry's in-place `id` mutation survives `redo`. Acceptance: red before 1.2.
- [x] 1.2 **GREEN** NEW `web/market/templates/market/history-core.js` (pure, imports NOTHING): `createHistory({limit=50})` per design `Interfaces`; opaque `{op,id,before,after}`, core never inspects fields. Acceptance: 1.1 green; ≤300.
- [x] 1.3 **RED** `tests/js/context-menu-core.test.js`: `menuModel({hit,row,scaleMode})` row → `[delete,duplicate]`; empty → `[add-indicator]` (+`reset-scale` only when non-linear); unknown hit → empty-chart list; never throws. `nextIndex`/`clampIndex` wrap+clamp (`count<=0`→0). Acceptance: red before 1.4.
- [x] 1.4 **GREEN** NEW `web/market/templates/market/context-menu-core.js` (pure, imports NOTHING): `menuModel`, `nextIndex`, `clampIndex` per design `Interfaces`. Acceptance: 1.3 green; ≤300.
- [x] 1.5 **REFACTOR** `node --test "tests/js/**/*.test.js"` green; size guard green (empty allowlist). Acceptance: chain green.

## Phase 2 — S2: undo controller + duplicate/restore + Ctrl/Cmd+Z + wiring (PR2)

Base S1 branch; branch `feat/f7-chart-shortcuts-s2`; deps S1. Rollback: revert branch → stack is in-session only, no state to unwind.

- [x] 2.1 **RED** `tests/js/chart-controllers.test.js`: `drawing:duplicate` → `createDrawing(kind, clone(points), style)` → one POST; one `persist:true` drag → exactly ONE history entry; `Ctrl+Z` on `document` → PUT `before`; `Cmd+Shift+Z`/`Ctrl+Y` → redo; input-focus exempt; `Escape`/`Delete` ignored; `switchTo` clears. Acceptance: red before 2.2–2.5.
- [x] 2.2 **GREEN** `controllers/drawings.js`: `createDrawing` `.then` emits `drawing:created {id,kind,points,style}` (`:139`); `bus.on("drawing:duplicate")` finds row + `createDrawing(kind, clone(points), style)`; `bus.on("drawing:restore")` re-POSTs `before` (design §b). Acceptance: 2.1 (duplicate/created) green; `drawings.js` ≤300.
- [x] 2.3 **GREEN** NEW `web/market/templates/market/controllers/undo.js` (~150, `createUndo({store,bus,host,config})`→`{clearForSwitch}`): `committed[id]` cache on `drawings:changed` (`drawings.js:51`); record on `persist:true` (`drawing-interaction.js:201`) + `drawing:delete` (`:125`); `replay(entry,dir)` emits bus commands; `replaying` guard patches `entry.id` from `drawing:created`; `document` keydown router (design `Keyboard Router`); `clearForSwitch` clears stack+committed. Acceptance: 2.1 (undo/redo/router) green; ≤300.
- [x] 2.4 **GREEN** `main.js:73-105` import + `createUndo`; `switchTo` (`:161`) `undo.clearForSwitch()` (+~4, ≤~268). Acceptance: wiring green; no new seam key.
- [x] 2.5 **GREEN** NEW `tests/js/undo.test.js`: `replay` op matrix (`update`→PUT, `create`→DELETE, `delete`→POST, duplicate≡create) + `replaying` re-entrancy skip. Enforce op payloads (design `Undo/Server Consistency`). Acceptance: `diff-cover` 100% on new JS test.
- [x] 2.6 **GREEN** `web/market/views.py:44-68` `MODULE_ALLOWLIST` +`history-core`; `:69-85` `CONTROLLER_ALLOWLIST` +`undo` (→14); `tests/web/test_market_ux.py:146` count `13→14`. Acceptance: served 200; no 404.
- [x] 2.7 **RED** `tests/web/test_market_e2e.py` (mirror `:1286-1365`): drag → exactly ONE PUT then `Ctrl+Z` → a second PUT with prior points; duplicate → POST then Undo → DELETE. Readiness-gated, DOM+network only. Acceptance: red before 2.2–2.3 land.
- [x] 2.8 **REFACTOR** `node --test`/`pytest`/`ruff` clean; guard green (empty allowlist); 8-key seam + `STORE_KEYS` 11; `smc.js`/`object-tree.js`/`drawing-interaction.js` `git diff --exit-code` unchanged. Acceptance: chain green.

## Phase 3 — S3: context-menu controller + toolbar aria + allowlist 15 (PR3)

Base S2 branch; branch `feat/f7-chart-shortcuts-s3`; deps S2. Rollback: revert branch → menu UI gone; nothing persisted.

- [x] 3.1 **RED** `tests/js/draw-toolbar.test.js`: each tool button carries an `aria-keyshortcuts` value; `TOOL_KEYS` map exported/assertable; letters fire only when focus is inside `#chart`. Acceptance: red before 3.2.
- [x] 3.2 **GREEN** `controllers/draw-toolbar.js:17-23` `TOOL_KEYS` map + `btn.setAttribute("aria-keyshortcuts", …)` (~+5, ≤300). No global letter router (D8). Acceptance: 3.1 green.
- [x] 3.3 **RED** `tests/js/chart-controllers.test.js` + `test_market_e2e.py`: `contextmenu` on a row → DOM `role="menu"` shows Delete/Duplicate; Duplicate → captured POST then Undo → captured DELETE; Delete → DELETE then Undo → captured re-POST (new id); `reset-scale` emits `scale:changed` (no PUT); `setData`/`update` spies green; hit-test uses `grabHandle`/`pointerRows`. Acceptance: red before 3.4–3.6.
- [x] 3.4 **GREEN** NEW `web/market/templates/market/controllers/context-menu.js` (~170, `createContextMenu({store,bus,host,config})`→`{attach,clearForSwitch}`): bind `contextmenu` ONCE on `#chart` (mirror `drawing-interaction.js:270`) + `preventDefault`; hit-test via pure `grabHandle(pointerRows(rows),…)` (`drawing-interaction-core.js:85`) importing `localPoint`/`pointerRows` (`drawing-interaction.js:17,27`) + local `map()`; JS-built `role="menu"`/`role="menuitem"`; roving focus via `nextIndex`/`clampIndex`; `Escape` closes + returns focus; `ACTION[id]` reuses `drawing:delete`/`drawing:duplicate`/`scale:changed`/`add-indicator-core` seam (design §c/§R4). Acceptance: 3.3 (menu) green; ≤300.
- [x] 3.5 **GREEN** `main.js:73-105` import + `createContextMenu`; `buildChart` `contextMenu.attach()`; `switchTo` (`:161`) `contextMenu.clearForSwitch()` (+~4). Acceptance: wiring green; no new seam key.
- [x] 3.6 **GREEN** `web/accounts/templates/registration/theme.css` `.chart-context-menu` tokens (`--surface`,`--border`,`--fs-3`,`--r`,`z-index`); no new color literals (design-system). Acceptance: CSS scan clean.
- [x] 3.7 **GREEN** `web/market/views.py:44-68` `MODULE_ALLOWLIST` +`context-menu-core`; `:69-85` `CONTROLLER_ALLOWLIST` +`context-menu` (→15); `tests/web/test_market_ux.py:146` count `14→15`; `chart.html:107-127` modulepreload +4 (`history-core`,`context-menu-core`,`undo`,`context-menu`). Acceptance: allowlist + preload tests green.
- [x] 3.8 **REFACTOR** `node --test`/`pytest`/`ruff` clean; guard green (empty allowlist); 8-key seam + 11-key store; three tight modules byte-untouched; CSP unchanged. Acceptance: chain green.

## Verification

- [x] V.1 `node --test "tests/js/**/*.test.js"` green.
- [x] V.2 `.venv/bin/python -m pytest -p no:randomly` green; `diff-cover` vs `origin/develop` → 100% patch on new Python.
- [x] V.3 `.venv/bin/ruff check . && .venv/bin/ruff format --check .` clean.
- [x] V.4 `.venv/bin/python web/manage.py makemigrations --check --dry-run` clean (no model change).
- [x] V.5 Guard/Edge Matrix fully checked; every module ≤300 (empty allowlist); 8-key seam + 11-key store; `smc.js`/`object-tree.js`/`drawing-interaction.js` unchanged.
- [x] V.6 Read-only: order scanner clean; CSP + `requirements.txt` unchanged; `src/` unchanged.
- [x] V.7 E2E readiness-gated, DOM+network only (no pixels); existing assertions green unedited.

## Rollback

- **S1**: `git revert` the S1 commits → the two core files are deleted; no app impact (unimported, no allowlist yet).
- **S2**: `git revert` the S2 commits → undo gone; allowlist back to 13; stack is in-session only, no migration to unwind.
- **S3**: `git revert` the S3 commits → menu gone; allowlist back to 14; nothing persisted.
- **Tracker**: drop `feat/f7-chart-shortcuts` and all slices; nothing merged to `develop`/`main` until green.
