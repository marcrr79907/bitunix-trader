# Verify Report — drawing-interaction (issue #117, Fase F4)

**Verdict**: `pass_with_warnings`
**Verified by**: orchestrator (adversarial, inline — the delegated verify sub-agent was cut off mid-run after emitting only a partial tool call; verification was completed inline with independent probes + the E2E subset).
**Branch**: `feat/drawing-interaction-put` (tip of the 3-slice chain; all slice PRs base on the tracker `feat/drawing-interaction`): tracker + S1 `…-core` (`af2f025`) + S2 `…-ui` (`03c2ba9`) + S3 `…-put` (`9825c53`). Confirm.

## Gates (L1)

| Gate | Result |
| --- | --- |
| `node --test "tests/js/**/*.test.js"` | **193 passed, 0 fail** |
| `pytest tests/ --ignore=tests/web` | **337 passed** |
| `ruff check .` | clean |
| `requirements.txt` diff vs develop | **empty** (JS + one view) |
| E2E drawing-interaction subset | **6/6 pass** (drag single-PUT, drag persist, keyboard delete, escape, symbol-switch clears, dialog style) |
| `makemigrations --check` | No changes |

## Gates (L2)

- Python change: `views.py` PUT (`_put_drawing`). Patch-100% reported by apply on the new lines.

## Spec conformance (L3)

- **Pure core `drawing-interaction-core.js`** (230 lines): imports ONLY `drawing-core.js`; ZERO DOM/chart-lib; `handlesFor` (hline 1 / trendline 2 / fib 2 / rect 4 corners `tl/tr/bl/br` / text 1 — probe verified); `grabHandle` (handle hit / body / miss→null; off-bar null-map → null); `applyDrag` (body translate, anchor move, null-inverse keeps the old component, clamp); `HANDLE_RADIUS=6`/`BODY_RADIUS=4`; deterministic, never throw.
- **`drawing-primitive.js`** (126): the renderer extracted; `requestUpdate` present (5×).
- **Controller `drawing-interaction.js`** (217): DI; `#chart` pointerdown/move/up (capture) + keydown Delete/Backspace/Escape; `#chart tabindex=0`; properties `<dialog>` (color/lineWidth); **#68: ZERO `setData`/`update()` in the controller AND the core** (drag re-renders via primitive `requestUpdate`); one PUT per gesture; NO new `STORE_KEYS`; selection clears on a SYMBOL switch, survives an interval-only switch (E2E-verified).
- **PUT `api_drawing_detail`**: partial `{points?,style?}`; `kind` immutable (differing → **400**); miss/A≠B → **404**; `parse_drawing` validation before write; 200 updated row (probe: points round-trip 200, `kind`→400, A≠B→404, miss→404, anon→302).
- **Size precondition held**: `drawings.js` **261**, `drawing-interaction.js` **217**, `chart-host.js` **297**, core 230, primitive 126 — ALL ≤300 (`test_module_size_guard` green).
- **Frozen**: `window.marketChart` exactly 8 keys (browser probe).

### Adversarial probes
- Core: handles per kind exact (incl. rect 4 corners); grab handle/body/miss; off-bar null-map → `handlesFor` `[]` / `grabHandle` null; applyDrag null-inverse keeps component.
- Endpoint: PUT points round-trip; `kind` differing → 400; A≠B → 404; miss → 404.
- Grep: `setData`/`update` count = 0 in the controller + core; no 9th seam key; all modules ≤300.
- Browser (real): `#chart tabindex=0`, seam 8 keys, a drawing created + loaded, 0 page errors; the interaction E2E subset green.

## Warnings (non-blocking)

- **W1 — Delegated verify was cut off** (partial tool call, no report): completed inline; the 6 interaction E2E + core/endpoint probes substitute for it.
- **W2 — E2E drag is environment-dependent** (class-C SQLite/live_server flake, DEBT-8): the drag E2E is readiness-gated; it passed 6/6 here but is not CI-run.
- **W3 — `drawing-interaction-core.js` is 230 lines** — under 300 but the largest pure core; if F5/F7 add more handle kinds, watch the ceiling.
- **SUGGESTION**: `tasks.md` checkboxes state reconciles at archive.

## Blockers

None.
