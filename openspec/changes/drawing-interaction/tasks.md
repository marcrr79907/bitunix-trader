# Tasks: drawing-interaction (issue #117, Fase F4 — Ola 4)

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | S1 ~250, S2 ~300, S3 ~200 → **~750** |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 (core+primitive extraction) → PR2 (controller+interaction+dialog) → PR3 (PUT+E2E) |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

### Suggested Work Units

| Unit | Goal | Likely PR | Base / boundary |
|------|------|-----------|-----------------|
| S1 | Pure core + renderer extracted; both files ≤300 | PR 1 | base = tracker `feat/drawing-interaction` |
| S2 | Interaction controller + wiring + dialog | PR 2 | base = PR1 branch; depends S1 |
| S3 | `PUT` + API/E2E tests | PR 3 | base = PR2 branch; depends S2 |

All PRs base on the tracker `feat/drawing-interaction`; merge each slice to the tracker before branching the next. Total ≈ 750 > 400.

## Guard / Edge Matrix

- [ ] **S1 extraction is a PRECONDITION**: after S1, `drawings.js` and `chart-host.js` both ≤300 (R14 `test_module_size_guard.py`); `chart-host.js` (297) untouched.
- [ ] #68: drag re-render via primitive `requestUpdate` ONLY; `setData`/`update` spies stay green.
- [ ] Pointer math: pane-relative; gutter/off-bar via converter `null`; never a hardcoded pane width.
- [ ] No new `STORE_KEYS` (frozen 10-key); selection lives in controller closure + bus (`drawing:selected`/`drawing:changed`).
- [ ] Frozen 8-key `window.marketChart` seam: no 9th key; E2E asserts via seam + captured PUT.
- [ ] `kind` immutable on PUT: differing → 400, no write; only `points`/`style` written.
- [ ] PUT routes `Drawing.for_user`; miss → 404, A≠B → 404 no leak; A unchanged.
- [ ] a11y: `#chart` `tabindex="0"` + label + `:focus-visible`; Delete/Backspace `preventDefault`; list-delete path exists (not pointer-only).
- [ ] Selection clears on SYMBOL switch (`clearForSwitch`), survives interval-only switch.
- [ ] patch 100% on new Python (`diff-cover`); `node --test`, `pytest`, ruff, `makemigrations --check` green.
- [ ] E2E class-C flake (#149): readiness-gated (`marketChart.ready`), dev-only; assert seam+network, never DOM pixels.

## S1 — Pure core + render extraction (PR1)

Base tracker `feat/drawing-interaction`; branch `feat/drawing-interaction-core`; deps none. Rollback: revert branch → chart renders unchanged (no core/split).

- [ ] 1.1 **RED** `tests/js/drawing-interaction-core.test.js`: per-kind handle counts (hline 1/trendline 2/fib 2/rect 4/text 1); grab handle-wins-over-body; `applyDrag` per-kind; off-bar inverse `null` keeps old component; determinism, no throw. Acceptance: red before 1.2, green after.
- [ ] 1.2 **GREEN** NEW `market/drawing-interaction-core.js` (pure ESM, imports nothing): `handlesFor`, `grabHandle`, `applyDrag`, `HANDLE_RADIUS=6`, `BODY_RADIUS=4`; reuses `drawing-core.hitTest`/`*Path`. Acceptance: `node --test` green.
- [ ] 1.3 **GREEN** NEW `market/drawing-primitive.js`: move `renderShape`+`makeDrawingPrimitive` out of `drawings.js`; add `selected` highlight (thicker stroke + handle dots), `isSelected` read live. Acceptance: `drawings.js` shrinks; guard green.
- [ ] 1.4 **GREEN** `web/market/views.py`: `MODULE_ALLOWLIST` +2 (`drawing-interaction-core`, `drawing-primitive`); `chart.html` `modulepreload` ×2. Acceptance: modules serve; no 404.
- [ ] 1.5 **REFACTOR** delete dead renderer from `drawings.js`; ruff/node clean; both files ≤300. Acceptance: `test_module_size_guard.py` green.

## S2 — Interaction controller + dialog (PR2)

Base PR1 branch; deps S1. Rollback: revert branch → no interaction; S1 core stays pure/unused.

- [ ] 2.1 **RED** `tests/web/test_market_ux.py`: `len(views.CONTROLLER_ALLOWLIST) == 8`; `drawing-interaction` serves. Acceptance: red before 2.2, green after.
- [ ] 2.2 **GREEN** NEW `market/controllers/drawing-interaction.js` (DI `create({store,bus,host,config})` → `{attach,clearForSwitch}`): `#chart` pointerdown/move/up/cancel via `host` map (`coordinateToTime`/`coordinateToPrice`); `setPointerCapture`; select→`drawing:selected`; drag→`drawing:changed`+`requestUpdate`; PUT once on `pointerup`; Delete/Backspace→delete, Escape→deselect; dblclick→`<dialog>`. Acceptance: 2.1 green.
- [ ] 2.3 **GREEN** `views.py`: `CONTROLLER_ALLOWLIST` 7→8 (`drawing-interaction`). Acceptance: allowlist test green.
- [ ] 2.4 **GREEN** `controllers/drawings.js`: listen `drawing:selected` (mark+`requestUpdate`) / `drawing:changed` (replace row+`requestUpdate`); pass `isSelected` to `makeDrawingPrimitive`; `<dialog id="drawing-settings-dialog">` color/lineWidth → merge style + PUT. Acceptance: ≤300; dialog round-trips.
- [ ] 2.5 **GREEN** `main.js` (create controller; `attach()` after every `buildChart`; `clearForSwitch` on symbol switch), `chart.html` (`#chart tabindex="0"`+aria-label; dialog; preload ×1), `registration/theme.css` (dialog + `#chart:focus-visible` tokens). Acceptance: select/drag/delete/keyboard work; no inline handler.
- [ ] 2.6 **REFACTOR** no new `STORE_KEYS`; frozen 8-key seam; #68 spies green. Acceptance: `node --test`+pytest green.

## S3 — PUT + API/E2E tests (PR3)

Base PR2 branch; deps S2. Rollback: revert branch → in-session drag works, unsaved (`PUT` 405).

- [ ] 3.1 **RED** `tests/web/test_market_api.py` + `test_isolation.py`: PUT 200 points/style; partial keeps other; `kind` differs → 400 no write; malformed → 400 no write; miss 404; A≠B 404 A unchanged; anon 302; CSRF 403. Acceptance: red before 3.2, green after.
- [ ] 3.2 **GREEN** `views.py` `api_drawing_detail` `["PUT","DELETE"]`: parse body (bad JSON/body → 400) → `for_user` (miss 404) → `kind` immutable 400 → `parse_drawing` 400 → save `update_fields` → 200 row. Acceptance: 3.1 green; patch 100%.
- [ ] 3.3 **RED→GREEN** `tests/web/test_market_e2e.py`: seed→select→`page.mouse.down/move/up`→exactly one captured `PUT /market/api/drawings/<id>`; seam shows new points; reload persists. Readiness-gated, dev-only. Acceptance: green; class-C flake (#149) documented.
- [ ] 3.4 **REFACTOR** ruff/pytest/node clean; `makemigrations --check` green; no `urls.py` change. Acceptance: chain green.

## Verification (post-chain, pre-merge to main)

- [ ] 4.1 `node --test` + `pytest` green; patch 100%; ruff check/format; `makemigrations --check`.
- [ ] 4.2 Read-only: order scanner clean; CSP + `requirements.txt` unchanged; `src/` framework-free.
- [ ] 4.3 Guard/Edge Matrix fully checked; both S1 files ≤300; frozen 8-key seam + 10-key store intact.
- [ ] 4.4 Per-slice `git revert` verified independently revertible (S1 pure / S2 interaction / S3 persistence).
