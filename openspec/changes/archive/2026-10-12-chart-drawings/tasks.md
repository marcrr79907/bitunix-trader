# Tasks: chart-drawings (issue #72, Fase A3)

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

## Guard/Edge Matrix

- [ ] `Drawing` in `OWNED_MODELS` + negative-control `Drawing.objects.all()` fixture (guard blind spot)
- [ ] cross-user DELETE: B deletes A's id → 404, A unchanged; B GET never leaks A (no id-only lookup)
- [ ] create owner-injection: `for_user(qs).create(user=request.user, …)`; omit `user` → IntegrityError (A2 gotcha)
- [ ] POST 400 BEFORE write: bad kind / interval ∉ `INTERVALS` / empty symbol / wrong point count / malformed point / `text` w/o label
- [ ] many per `(user,symbol,interval)` — NO unique constraint, no `IntegrityError`; two rows distinct `id`
- [ ] `timeToCoordinate` → `null` off-bar: core skips leg, no throw
- [ ] interval switch: clear primitives + reload per `(symbol,interval)`; shapes don't cross keys
- [ ] read-only: no order verb/endpoint; order scanner clean; no new dep; CSP unchanged; `src/` framework-free; `requirements.txt` unchanged
- [ ] #68 single-write-path untouched: primitives separate canvas layer, no extra `setData`/`update`
- [ ] failed drawings fetch non-fatal: chart renders, no error surfaces
- [ ] patch 100% Python; `node --test` green for JS (`drawing-core.js`); ruff + `pytest` + `makemigrations --check` green

## WU1 — Model + migration + guard (PR1)

Base `feature/chart-drawings` (tracker); branch `feat/chart-drawings-model`; deps none. Rollback: revert branch → drop `Drawing` + `0006` (additive, no data loss).

- [ ] 1.1 **RED** `test_owned_model_guard.py` + `test_isolation.py`: `OWNED_MODELS += {"Drawing"}` + negative control `Drawing.objects.all()`; A≠B `DoesNotExist`; two rows same key coexist; JSON list/object round-trip; owner-less forbidden. Acceptance: guard flags the Drawing fixture; isolation green.
- [ ] 1.2 **GREEN** `web/trading/models.py`: `Drawing(UserOwnedModel)` — `Kind` TextChoices (`hline|trendline|fib|rect|text`), `symbol`(32), `interval`(8), `kind`(16, choices), `points` JSONField `default=dict`, `style` JSONField `default=dict`, `created_at` auto_now_add; `Meta.indexes=[Index(["user","symbol","interval"], name="ix_drawing_user_symbol_interval")]`; **no UniqueConstraint**. Acceptance: `test_isolation` green.
- [ ] 1.3 **GREEN** `web/trading/migrations/0006_drawing.py`, `dependencies=[("trading","0005_chartlayout")]`, additive. Acceptance: `makemigrations --check` green.
- [ ] 1.4 **REFACTOR** ruff clean. Acceptance: WU1 tests green.

## WU2 — Endpoint + validation (PR2)

Base: PR1 branch; deps WU1. Rollback: remove `api_drawings` + detail route + `parse_drawing`/`DRAWING_KINDS`; revert endpoint tests.

- [ ] 2.1 **RED** `test_market_api.py`: anon→302; GET empty list (never 404); POST 201 → GET lists; 400 bad kind/interval/symbol/point-count/point-shape/`text` label BEFORE write; DELETE 204 + second DELETE 404; cross-user DELETE 404; CSRF 403. Acceptance: all cases green.
- [ ] 2.2 **GREEN** `web/market/quotes.py`: `DRAWING_KINDS` (TextChoices) + pure `parse_drawing(kind, points, style) -> (points, style)` validating per-kind schema (R5) and raising `ValueError`. Acceptance: unit-passed via 2.1 (400 paths).
- [ ] 2.3 **GREEN** `web/market/views.py`: `api_drawings` `@login_required @require_http_methods(["GET","POST"])`; GET `?symbol=&interval=` empty symbol / interval ∉ `INTERVALS` → 400, else `for_user.filter(...)` → `{"drawings":[...]}`; POST validate symbol/interval then `parse_drawing` → 400, else `for_user(request.user).create(user=request.user, …)` → 201 `{id,kind,points,style}`. `api_drawing_detail` DELETE `@require_http_methods(["DELETE"])`: `for_user.filter(id=id)` miss → 404, hit → 204. Acceptance: 2.1 green; no write on 400.
- [ ] 2.4 **GREEN** `web/market/urls.py`: `market/api/drawings` (`market_api_drawings`) + `market/api/drawings/<int:id>` (`market_api_drawing_detail`). Acceptance: routes resolve.
- [ ] 2.5 **REFACTOR** endpoint tests green; patch 100% on new `views.py`/`quotes.py` lines.

## WU3 — drawing-core.js + v5 primitive + toolbar/UI + E2E (PR3)

Base: PR2 branch; deps WU2. Rollback: restore `chart.js`/`chart.html`; delete `drawing-core.js` + JS test; revert E2E edits; drop `drawings` seam.

Note: JS is **outside the Python patch gate** (`diff-cover` covers Python only). `drawing-core.js` MUST be UMD pure geometry covered by `node --test`; Playwright E2E is the integration/adapter net (DOM seam + network assertions, no image diffs).

- [x] 3.1 **RED** `tests/js/drawing-core.test.js` (`node --test`): per-kind path builders (`hlinePath`/`trendlinePath`/`fibLevels`/`rectPath`), hit-test math, off-bar `null` guard skips leg. Acceptance: fails before 3.2, green after.
- [x] 3.2 **GREEN** `web/market/templates/market/drawing-core.js` (NEW UMD): pure geometry + null guards, no chart import. Acceptance: `node --test` green.
- [x] 3.3 **RED** `test_market_e2e.py`: seed via endpoint → boot attaches N primitives (`window.marketChart.drawings` seam + POST/GET network); click → POST fired; delete-by-id → DELETE fired; interval switch clears then reloads; failed fetch → no drawings, no error. Acceptance: red first, green after 3.4/3.5.
- [x] 3.4 **GREEN** `chart.js`: one `DrawingPrimitive` per kind (`paneViews`/`draw` via `useMediaCoordinateSpace`, `autoscaleInfo` for rays/rects, `attached({requestUpdate})`); attach on boot after `buildChart` + on `switchTo` (clear previous); `subscribeClick`/`subscribeCrosshairMove` → `drawing-core` → POST → attach; `state.tool`; `window.marketChart.drawings` seam. Acceptance: 3.3 green.
- [x] 3.5 **GREEN** `chart.html`: `<fieldset class="drawings">` of `<button type="button" class="draw-tool" data-kind=…>` + delete list (mirrors `.pair`); CSP-safe `addEventListener`; **text input via native `<dialog>`** (locked, proposal-recommended); CSRF meta reused. Acceptance: 3.3 green; no inline handler.
- [x] 3.6 **REFACTOR** E2E green; no console errors; DOM-only assertions.

## Phase 4 — Verification

- [ ] 4.1 `pytest` green; patch 100%; `node --test` green; ruff clean; `makemigrations --check` green.
- [ ] 4.2 Order scanner clean; CSP + `requirements.txt` unchanged; `src/` framework-free.
- [ ] 4.3 Playwright: restore-on-boot, create/delete round-trip after reload, switch clears+loads, no console errors.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | PR1 ~90, PR2 ~150, PR3 ~200 → ~400–440 |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR1 (model+0006+guard+index) → PR2 (endpoint+validation+parse_drawing) → PR3 (drawing-core.js+v5 primitive+toolbar/E2E) |
| Delivery strategy | feature-branch-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes — confirm text input via native `<dialog>` (proposal-recommended) vs fixed label; chain strategy already fixed to feature-branch-chain.
