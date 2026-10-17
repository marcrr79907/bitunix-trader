# Archive Report: f7-chart-shortcuts

**Archived**: 2026-10-17
**Change**: `f7-chart-shortcuts` (issue #120, Fase F7)
**Verdict**: `PASS_WITH_WARNINGS` (0 blockers, **1 CRITICAL C1 resolved in-chain**,
5 warnings W1–W5, 3 suggestions S1–S3)
**Delivery**: Feature Branch Chain, all PRs **based on the tracker**
`feat/f7-chart-shortcuts` — **#198 / #199 / #202 / #203 / #208 / #210** →
tracker **#211** → `develop` @ `9ba478f`, merged.
**Base**: `develop` @ `0c2e3e8`. Verify ran on S3 tip `ab6d9d7`; the S4/UI/
concurrency slices landed after.

## What Shipped

The three TradingView interaction instruments the F5/F6 drawing substrate was
built to carry:

- **Undo/redo** — an in-session operation stack, not pixels. Pure
  `market/history-core.js` (bounded LIFO of opaque `{op,id,before,after}` records,
  redo-clear rule) owned by `controllers/undo.js` (named so because
  `controllers/history.js` already owns REST pagination). Records ONLY at the
  `persist:true` gesture boundary (one drag = one entry), replays through the
  EXISTING `drawings.js` HTTP verbs (undo-delete re-POSTs a new id, undo-create
  DELETEs, undo-move PUTs `before`), with a `replaying` re-entrancy guard and an
  async id re-mint patch. `Ctrl/Cmd+Z` / `Ctrl/Cmd+Shift+Z` / `Ctrl/Cmd+Y`
  router on `document`. The store stays at **11** keys (#68).
- **Context menu** — a transient view over `(target-under-cursor, selection)`.
  Pure `market/context-menu-core.js` (`menuModel` + `nextIndex`/`clampIndex`) and
  `controllers/context-menu.js` (DOM `role="menu"`, hit-test via the reused pure
  `grabHandle(pointerRows(rows),…)`, roving focus, `Escape` focus-return, JS-built
  for CSP). Commands: delete / duplicate / reset-scale (F8 seam) / add-indicator
  (F5 seam). Keyboard open via `Shift+F10`/`ContextMenu` at the selection.
- **Shortcuts** — `aria-keyshortcuts` per tool button plus a VISIBLE
  `<span class="tool-key">` letter; the per-tool letter router fires ONLY inside
  `#chart` (h/t/f/r/x/m/p), so the tree's `v`/`l`/`s` are never stolen.

| Area | Delivered |
|------|-----------|
| `chart-history` (NEW) | Pure bounded operation stack; `persist:true` coalescing; server-coupled replay (re-POST/DELETE/PUT, id re-mint); `replaying` guard; Ctrl/Cmd+Z/Shift+Z/Y router; `#history-status` `aria-live` announcement; symbol-switch `clear()`; store stays 11. |
| `chart-context-menu` (NEW) | Pure `menuModel`/`nextIndex`/`clampIndex`; DOM `role="menu"`; pointer + keyboard open (`Shift+F10`/`ContextMenu`, #204); roving focus; `Escape` focus-return; delete/duplicate/reset-scale/add-indicator; token-only CSS. |
| `chart-drawings` | R2 gains **duplicate** = plain create via the existing `POST` with cloned `kind`/`points`/`style` (verbatim, no offset), new id; no new endpoint. |
| `chart-toolbar` | R1 `aria-keyshortcuts` + visible `.tool-key` per button; R3 per-tool letter router that fires ONLY inside `#chart` (C1 remediated). |
| `market-chart` | R14 inventory gains `history-core.js`/`context-menu-core.js` + `controllers/undo.js`/`context-menu.js`; `MODULE_ALLOWLIST` 21→23; `CONTROLLER_ALLOWLIST` **15** (`test_market_ux.py:146`). R18/R20 seam stays 8 keys, `STORE_KEYS` 11, no new `EVENTS` member (the F7 drawing events are string literals). |
| `design-system` | R6 context menu keyboard-navigable + focus return + item `aria-keyshortcuts`; undo/redo announces in `#history-status` `aria-live`; visible tool shortcut letter; R7 menu CSP-clean (JS-built, `addEventListener`, no inline `oncontextmenu`). |

| Area | Held |
|------|-----------|
| Size ceiling | `test_module_size_guard.py` green, EMPTY allowlist; `smc.js`=300 (byte-untouched), `object-tree.js`=299 (byte-untouched), `drawing-interaction.js`=291 (byte-untouched), `drawings.js`=298, `main.js`=274, `context-menu.js`=208, `undo.js`=170, `history-core.js`=65, `context-menu-core.js`=57. |
| Seams held | `window.marketChart` exactly 8 keys; `STORE_KEYS` exactly 11; #68 no `setData`/`update` in the undo/menu paths; CSP unchanged; `src/` + `requirements.txt` unchanged. |
| No inline handler | `test_market_page_has_no_inline_script_or_handler`; menu bound via `addEventListener`. |

## Requirements Satisfied

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| chart-history | R1–R7 (NEW) | ✅ Operation stack, gesture-boundary coalescing, server-coupled replay, symbol-switch clear, Ctrl/Cmd+Z router, replay safety + `aria-live` feedback, store/seam/CSP/size bounds. |
| chart-context-menu | R1–R5 (NEW) | ✅ Pure menu model, DOM `role="menu"` + CSP, keyboard nav + focus return + keyboard open, commands reuse existing seams, untouched controllers/size. |
| chart-drawings | R2 (MODIFIED) | ✅ Duplicate = create-with-cloned-points via the existing POST (new id); no new endpoint. R1, R3–R15 preserved. |
| chart-toolbar | R1/R3 (MODIFIED) | ✅ `aria-keyshortcuts` + visible `.tool-key`; letter router fires only inside `#chart` (C1 remediated). R2/R4/R5 preserved. |
| market-chart | R14/R18/R20 (MODIFIED) | ✅ Cores + controllers inventoried; `CONTROLLER_ALLOWLIST` = **15**; seam stays 8; store stays 11; no new `EVENTS` member. R1–R13, R15–R17, R19, R21–R23 preserved. |
| design-system | R6/R7 (MODIFIED) | ✅ Context menu a11y + focus return + `aria-keyshortcuts`; undo/redo `aria-live` announcement; visible shortcut letter; menu CSP-clean, no inline handler. R1–R5, R8–R10 preserved. |

**Compliance summary**: 50/55 scenarios fully compliant at verify; 4 PARTIAL
(chart-history R3 negative; chart-history R4 reload; chart-context-menu R5
hit-test reuse and no-series-write; market-chart R20 no-series-write) and 1
MISSING/CRITICAL (chart-toolbar R3 letter-fires-inside-chart) — the CRITICAL was
resolved in-chain (see below), the PARTIALs are documented reconciliation warnings.

**Preserved untouched** (no requirement dropped):
- `chart-drawings`: R1, R3–R15.
- `chart-toolbar`: R2, R4, R5.
- `market-chart`: R1–R13, R15–R17, R19, R21–R23.
- `design-system`: R1–R5, R8–R10.

## Verify Findings Carried and Remediation

The verify-report (`PASS_WITH_WARNINGS`) reported **1 CRITICAL** and **5
warnings**. C1 was remediated in-chain; the canonical specs reflect the DELIVERED
behavior, not the original gap.

- **C1 — chart-toolbar R3 "Letter fires inside the chart" was unimplemented and
  untested.** The delta spec required the scenario, but the implementation only
  *advertised* the letters (design D8 had deferred the router). **Remediated** in
  the S4 slice (`ff13c1b`): `draw-toolbar.js` now binds a letter `keydown` on
  `#chart` (inverse `TOOL_KEYS`, ignoring modifiers and text fields), and the UI
  slice (`06828c6`) surfaces the letter visibly via `.tool-key`. The canonical
  `chart-toolbar` R3 now states the router exists and fires ONLY inside `#chart`.
- **W1 — chart-history R3 "Local-patch-only fails" has no negative covering
  test.** The positive replay path is proven (E2E captured verbs + `undo.test.js`
  op matrix); the anti-pattern is forbidden by construction. **Documented** gap.
- **W2 — market-chart R20 "Undo and menu never touch the series data path" has no
  explicit spy assertion for those two paths.** Source inspection confirms
  `replayOps` and `ACTION` emit only bus commands. **Scenario retained**; the
  canonical spec keeps the clause (the invariant holds by construction).
- **W3 — chart-context-menu R5 "Hit-test reuses the pure helpers" is
  source-verified only.** `context-menu.js` calls
  `grabHandle(pointerRows(rows), …)`, exactly as required. **Documented**.
- **W4 — chart-history R4 "Reload starts empty" is untested.** True by
  construction (no persistence in `undo.js`). **Documented**.
- **W5 — No test asserts the 4 F7 `modulepreload` links.** A dropped F7 preload
  would degrade speed, not correctness. **Documented**.
- **S1–S3** (vacuous `diff-cover`; `drawings.js` at 298/300; no user-facing docs
  for the undo keys) — non-blocking, left as documented gaps.

## Follow-up Issues Created and Closed In-Chain

The S4, UI, and concurrency slices were remediation/add work beyond the original
3-slice plan; all raised issues were **closed within the chain**:

- **#200 / #201** (S4, PR **#203**) — committed-cache freshness across an undo;
  unblock a failed restore (`drawing:create-failed`). Plus the C1 letter-router
  remediation (`ff13c1b`).
- **#204 / #205 / #206 / #207** (UI slice, PR **#208**) — keyboard menu open
  (`Shift+F10`/`ContextMenu`), undo/redo announcement (`#history-status`), visible
  shortcut letters + honest `aria-keyshortcuts`, context-menu elevation shadow.
- **#209** (concurrency slice, PR **#210**) — ignore undo/redo while a replay is
  in flight.

C1 (chart-toolbar R3 letter router) was resolved in-chain by S4, not filed as a
separate issue.

## Final Invariant State (verified on develop @ 9ba478f)

| Invariant | Proof | Result |
|---|---|---|
| `window.marketChart` EXACTLY 8 keys | `main.js`; E2E `test_shell_keeps_seam_at_eight_keys` | ✅ |
| `STORE_KEYS` EXACTLY 11 | `chart-store.js:13-27`; `chart-store.test.js` | ✅ |
| Every `market/**/*.js` ≤300, empty allowlist | `test_module_size_guard.py` (ALLOWLIST `frozenset()`); `smc.js`=300, `object-tree.js`=299, `drawing-interaction.js`=291 byte-untouched | ✅ |
| `#68`: no `setData`/`update` writer for undo/menu | `replayOps`/`ACTION` emit only bus verbs; source inspection | ✅ |
| Controller allowlist = **15** | `views.py:71-88`; `test_market_ux.py:146` | ✅ |
| Module allowlist = 23 incl. new cores | `history-core`, `context-menu-core` served 200 | ✅ |
| No new `EVENTS` member | `chart-bus.js` byte-untouched; drawing events are string literals | ✅ |
| No inline handler/script in the diff | `test_market_page_has_no_inline_script_or_handler`; E2E no `oncontextmenu` | ✅ |
| No new color literals in menu CSS | `theme.css` `.chart-context-menu`/`.tool-key` use existing tokens | ✅ |
| `requirements.txt`/`src/` unchanged | `git diff` empty | ✅ |

**Test gates** (from verify-report): `node --test` **394 pass / 0 fail**;
`pytest -m 'not e2e'` **999 passed, 96 deselected**; `ruff check`/`format --check`
clean; E2E **95/96** (the one failure is the pre-existing class-C `#149` flake,
not in the F7 diff), F7 E2E subset **6/6**.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| chart-history | **Created** | Full canonical spec (R1–R7); operation stack, gesture-boundary coalescing, server-coupled replay, lifecycle, keyboard router, replay safety + `#history-status` feedback, constraints. |
| chart-context-menu | **Created** | Full canonical spec (R1–R5); pure menu model, DOM `role="menu"` + CSP, a11y/keyboard + keyboard open, commands reuse seams, constraints. |
| chart-drawings | Updated | R2 gains the duplicate clause + 2 scenarios (create-with-cloned-points, no new endpoint). R1, R3–R15 preserved. |
| chart-toolbar | Updated | R1 (`aria-keyshortcuts` + visible `.tool-key`, 2 scenarios reconciled), R3 (per-tool letter router fires only inside `#chart` — C1 remediated; letter scenarios + coverage note reconciled). R2/R4/R5 preserved. |
| market-chart | Updated | R14 (cores + controllers, `CONTROLLER_ALLOWLIST` = **15**, 2 scenarios + note reconciled), R18 (undo/menu seam clause + scenario), R20 (envelope + string-literal bus events clause + scenario + no-series-write scenario). R1–R13, R15–R17, R19, R21–R23 preserved. |
| design-system | Updated | R6 (context menu a11y + focus return + `aria-keyshortcuts`, undo/redo `#history-status` announcement, visible `.tool-key`; 3 scenarios added), R7 (menu CSP-clean clause + scenario). R1–R5, R8–R10 preserved. |

Delta fit: 2 capabilities NEW (created whole); `chart-drawings` R2 MODIFIED;
`chart-toolbar` R1/R3 MODIFIED; `market-chart` R14/R18/R20 MODIFIED;
`design-system` R6/R7 MODIFIED. Every MODIFIED requirement matched by name and
replaced in place. No requirement dropped.

## Rollback (per-slice, independently revertible)

- **#210 (concurrency)**: revert PR — the in-flight replay guard is dropped
  (#209 regresses).
- **#208 (UI slice)**: revert PR — menu keyboard open, undo announcement, visible
  shortcut letters, and elevation shadow are gone; F7 still functional.
- **#203 (S4)**: revert PR — committed-cache freshness and failed-restore unblock
  revert; the C1 letter router is removed (`chart-toolbar` R3 regresses to the
  verify C1 gap).
- **#202 (S3)**: revert PR — context menu gone; allowlist back to 14.
- **#199 (S2)**: revert PR — undo gone; allowlist back to 13; stack is in-session
  only, no migration to unwind.
- **#198 (S1)**: revert PR — the two core files are deleted; no app impact.
- **Tracker**: drop `feat/f7-chart-shortcuts`; nothing merged to `develop`/`main`
  until green.

## Known Fragility

- `controllers/smc.js` = **300** (at ceiling, byte-untouched).
- `controllers/object-tree.js` = **299** (1-line headroom, byte-untouched).
- `controllers/drawings.js` = **298** (2-line headroom, touched — the design's
  documented fallback is to move the `drawing:duplicate`/`drawing:restore` handling
  into `undo.js` if a future edit needs the room).

The guard passes because it fails only when *over* the ceiling and both
at-ceiling modules are untouched.

## Bookkeeping

`tasks.md` checkboxes were reconciled to `[x]` at archive (the apply hard contract
forbids editing `openspec/**` during apply); S4, the UI slice, and the concurrency
slice were remediation/add work beyond the original 3-slice task list — noted in
the tasks header and here. The change dir was UNTRACKED before this commit; the
canonical spec edits, the tasks.md update, the archive report, and the archive
move are committed together. `cov.xml` is gitignored and was not added.
