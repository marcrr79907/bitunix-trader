# Archive Report: drawing-interaction

**Archived**: 2026-10-14
**Verdict**: `pass_with_warnings` (0 blockers, 0 critical; 3 non-blocking warnings —
W1 delegated verify cut off → verified inline, W2 E2E drag env-dependent class-C
DEBT-8, W3 `drawing-interaction-core.js` at 230 lines) — `chart-drawings` R2/R6
(MODIFIED) + R9–R14 (ADDED), `market-chart` R11 (MODIFIED), `per-user-isolation`
R14.6 (ADDED), `design-system` R6 (MODIFIED) + R9 (ADDED).
**Delivery**: Feature Branch Chain, 3 PRs, all **based on the tracker**
`feat/drawing-interaction` — **#166** (S1 core + render extraction) + **#167** (S2
controller + interaction + dialog) + **#168** (S3 `PUT` + API/E2E) → **#169**
(tracker → `develop`), merged.
**Issue**: #117 (Ola 4 / F4) — **first Ola 4 feature**. Ola 4 continues with
F5/F6/F7/F9 (not closed here).
**Branch**: `feat/drawing-interaction-put` (tip of the 3-slice chain; tracker
`feat/drawing-interaction`) ← S1 `…-core` (`af2f025`) + S2 `…-ui` (`03c2ba9`) +
S3 `…-put` (`9825c53`). Merge `#169` on `develop`.

## What Shipped

Drawings go from create/delete-only to select / drag / restyle / keyboard-delete —
still read-only annotation. The two files that were AT the R14 ceiling
(`drawings.js` 300, `chart-host.js` 297) were cleared by extraction as a hard
precondition.

| Area | Delivered |
|------|-----------|
| Pure core `drawing-interaction-core.js` (230 lines) | Imports ONLY `drawing-core.js`; ZERO DOM/chart-lib. `handlesFor(kind, points, map)` (hline 1 / trendline 2 / fib 2 / rect 4 corners `tl/tr/bl/br` / text 1), `grabHandle(rows, x, y, map, radius)` (handle hit / body / miss → null; off-bar null-map → null), `applyDrag(row, target, dxPx, dyPx, map)` → NEW points (body translate, anchor move, null-inverse keeps the old component, clamp). `HANDLE_RADIUS=6` / `BODY_RADIUS=4`. Deterministic, never throws. |
| `drawing-primitive.js` (126 lines) | Renderer extracted from `drawings.js`; `renderShape(ctx, size, row, map, selected)` + `makeDrawingPrimitive(row, {isSelected})` — selection-aware (thicker stroke + handle dots), `isSelected` read live (no re-attach); `requestUpdate` present (5×). |
| `controllers/drawing-interaction.js` (217 lines) | `create({store,bus,host,config})` → `{attach,clearForSwitch}`. DI; `#chart` `pointerdown`/`move`/`up`/`cancel` with `setPointerCapture`; `keydown` Delete/Backspace/Escape; `#chart tabindex=0`; properties `<dialog>` (color/lineWidth); selects via `bus.emit("drawing:selected")`, drags via `drawing:changed` + `requestUpdate`; **one PUT per gesture on `pointerup`**; selection in the controller closure. |
| `PUT /market/api/drawings/<id>` (`api_drawing_detail`) | `["PUT","DELETE"]`; partial `{points?,style?}`; `kind` immutable (differing → **400**); miss/A≠B → **404**; `parse_drawing` validation before write; 200 updated row `{id,kind,points,style}`. CSRF via middleware. No `urls.py` change. |
| Size precondition held | `drawings.js` **261**, `drawing-interaction.js` **217**, `chart-host.js` **297**, core 230, primitive 126 — ALL ≤300 (`test_module_size_guard` green, empty allowlist). |
| Seams held | `window.marketChart` exactly 8 frozen keys (no 9th); ZERO `setData`/`update()` in the controller AND the core (#68) — drag re-renders via primitive `requestUpdate` only; NO new `STORE_KEYS`; `src/` framework-free; CSP unchanged; no new runtime dependency. |

## Requirements Satisfied

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| chart-drawings | R2 — Drawings CRUD API (MODIFIED) | ✅ `PUT /<id>` added: `for_user` resolve, miss/A≠B → 404 no leak, partial `{points?,style?}`, `kind` immutable → 400, `parse_drawing` → 400 before write, 200 updated row; GET/POST/DELETE unchanged. 13 scenarios. |
| chart-drawings | R6 — Render contract (MODIFIED) | ✅ Selection highlight + per-kind handles drawn in the SAME primitive; drag re-renders via `requestUpdate` only, never `setData`/`update` on the series (#68). 6 scenarios. |
| chart-drawings | R9 — Selection (hit-test + highlight) (ADDED) | ✅ Single selection; handles hit-tested before body via `drawing-core.hitTest`; miss clears; highlight; `drawing:selected` emitted; state in closure. 3 scenarios. |
| chart-drawings | R10 — Per-kind handles and drag (ADDED) | ✅ `handlesFor`/`grabHandle`/`applyDrag` pure, deterministic, chart-lib-free; handle move / body translate; hline updates only `price`; null-coordinate clamp. 4 scenarios. |
| chart-drawings | R11 — Keyboard delete and deselect (ADDED) | ✅ `#chart tabindex=0` + label; Delete/Backspace deletes; Escape deselects; Backspace `preventDefault`; keyboard path exists. 3 scenarios. |
| chart-drawings | R12 — Properties dialog (ADDED) | ✅ `dblclick` → native `<dialog>` seeded with `style`; confirm merges `color`/`lineWidth`, re-renders, PUTs; `kind`/`points` not editable. 2 scenarios. |
| chart-drawings | R13 — Edge-case handling matrix (ADDED) | ✅ Off-bar clamp, gutter ignore, no-op delete, Escape-anchor/selection, PUT 404/400, interval-survives / symbol-clears. 2 scenarios. |
| chart-drawings | R14 — Selection lifecycle across switches (ADDED) | ✅ Clears on SYMBOL switch (with drawings), survives interval-only switch; no stale id. 2 scenarios. |
| market-chart | R11 — Drawings endpoint and render/restore contract (MODIFIED) | ✅ `PUT` contract added (partial, kind-immutable, 404 miss/A≠B); interaction/render seam: select/drag/keyboard/restyle, ONE PUT on `pointerup` via `requestUpdate` only. 11 scenarios. |
| per-user-isolation | R14.6 — Cross-user update denied (PUT) (ADDED) | ✅ PUT resolves through `Drawing.for_user`; A≠B → 404 no leak, A unchanged; owner PUT → 200; committed assertion in `tests/web/test_market_api.py`. 3 scenarios. |
| design-system | R6 — Accessibility (MODIFIED) | ✅ `#chart` focusable (`tabindex="0"`) + accessible label + visible focus ring; properties `<dialog>` traps focus and closes on `Escape`. 4 scenarios. |
| design-system | R9 — Drawing selection and handles styling (ADDED) | ✅ Highlight/handles use tokens, not color-only; handles canvas-drawn (not DOM); properties `<dialog>` uses tokens. 3 scenarios. |

**Compliance summary**: 12/12 requirements, 56/56 scenarios compliant (verify-report
pass_with_warnings; E2E interaction subset 6/6).

**Preserved untouched** (no requirement dropped):
- `chart-drawings`: R1 (model/ownership/index), R3 (A ≠ B isolation), R4 (validation
  before write), R5 (kind-specific point/style schemas), R7 (load/restore on boot and
  switch), R8 (read-only boundary / CSP / no new dependency). R2 re-worded only to add
  the PUT verb; R6 re-worded only to add the selection/handles render clause — no
  existing semantic removed.
- `market-chart`: R1–R10, R12–R23 (kline client, auth page, kline endpoint, indicators,
  live WS, CSP, boundary, infinite scroll, manage coverage, layout endpoint, SMC overlay,
  signals route, ESM module boundary, ESM serving, config injection, invariants, seam,
  crosshair, host envelope, type/scale, theme, E2E readiness). R11 re-worded to add PUT
  + the interaction seam.
- `per-user-isolation`: R14.1–R14.5 (ownership contract, cross-user read denied,
  unscoped-query guard, worker trusted zone, analytics scoping).
- `design-system`: R1–R5, R7, R8 (token stylesheet, shell, POST logout, script block,
  behavior preserved, CSP/no inline, boundary/no dep). R6 replaced in place with the
  chart-canvas + dialog clause appended.

Delta fit: `chart-drawings` had R2/R6 MODIFIED and R9–R14 ADDED; `market-chart` R11
MODIFIED; `per-user-isolation` R14.6 ADDED; `design-system` R6 MODIFIED and R9 ADDED.
Every MODIFIED requirement matched by name and was replaced in place; every ADDED was
appended. No requirement name collision; `chart-drawings` now has 14 requirements,
`market-chart` 23, `per-user-isolation` 6, `design-system` 9.

## Warnings Carried (non-blocking)

- **W1 — Delegated verify was cut off**: the delegated verify sub-agent emitted only a
  partial tool call and no report. Verification was completed **inline** by the
  orchestrator (adversarial): the 6 interaction E2E tests + core/endpoint probes
  substitute for it. Not a code issue; a process warning.
- **W2 — E2E drag is environment-dependent** (class-C SQLite/live_server flake,
  DEBT-8): the drag E2E is readiness-gated and passed 6/6 here but is **not CI-run**
  (CI does not run E2E). Pre-existing infra flake, not a regression.
- **W3 — `drawing-interaction-core.js` is 230 lines** — under the 300 ceiling but the
  largest pure core. If F5/F7 add more handle kinds, watch the ceiling (extraction or a
  per-kind module split is the escape hatch).

## Rollback (per-slice, independently revertible)

- **S3 (PUT)**: revert PR — drop `PUT`; in-session drag still works but is unsaved
  (`PUT` → 405).
- **S2 (interaction)**: revert PR — drop the controller/wiring/dialog; S1's core stays
  pure and unused.
- **S1 (core + extraction)**: revert PR — no core/split; the chart renders unchanged.

No migration, schema field, CSP, or dependency change — no data loss on any revert.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| chart-drawings | Updated | R2 replaced (adds `PUT /<id>`: partial body, `kind` immutable, 404 miss/A≠B, 400 validation). R6 replaced (adds selection highlight/handles in the same primitive; drag via `requestUpdate` only). R9–R14 appended (selection, per-kind handles/drag, keyboard delete/deselect, properties dialog, edge matrix, selection lifecycle). R1/R3/R4/R5/R7/R8 preserved. 14 requirements retained. |
| market-chart | Updated | R11 replaced (adds the PUT contract + select/drag/keyboard/restyle seam; ONE PUT on `pointerup`). R1–R10, R12–R23 preserved. 23 requirements retained. |
| per-user-isolation | Updated | R14.6 appended (cross-user update denied on PUT: `for_user` resolve, A≠B → 404 no leak, A unchanged, committed assertion). R14.1–R14.5 preserved. 6 requirements retained. |
| design-system | Updated | R6 replaced (adds focusable `#chart` + accessible label + focus ring; dialog traps focus / closes on Escape). R9 appended (selection/handles styling: tokens, not color-only, canvas-drawn, dialog uses tokens). R1–R5, R7, R8 preserved. 9 requirements retained. |

## Verification Evidence (from verify-report)

- `node --test "tests/js/**/*.test.js"`: **193 passed, 0 fail**.
- `pytest tests/ --ignore=tests/web`: **337 passed**.
- `ruff check .`: clean.
- `requirements.txt` diff vs `develop`: **empty** (JS + one view).
- E2E drawing-interaction subset: **6/6 pass** (drag single-PUT, drag persist,
  keyboard delete, escape, symbol-switch clears, dialog style).
- `makemigrations --check`: **No changes**.
- Patch: `views.py` PUT (`_put_drawing`) 100% patch on new lines (L2).
- Core probes: handles per kind exact (incl. rect 4 corners); grab handle/body/miss;
  off-bar null-map → `handlesFor` `[]` / `grabHandle` null; `applyDrag` null-inverse
  keeps component; endpoint PUT points round-trip 200, `kind`→400, A≠B→404, miss→404,
  anon→302; grep `setData`/`update` count = 0 in controller + core; no 9th seam key;
  all modules ≤300.

## Bookkeeping

`tasks.md` checkboxes were reconciled to `[x]` at archive (the apply hard contract
forbids editing `openspec/**` during apply); all S1/S2/S3/Verification tasks and the
Guard/Edge Matrix are complete per the verify-report.
