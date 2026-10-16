# Design: drawing-interaction (issue #117, Fase F4 — Ola 4)

## Technical Approach

Layered F0 extension. A pure interaction core owns geometry; a new thin
controller owns the DOM; the renderer is extracted so both clear R14 (300). One
new `PUT` reuses `parse_drawing`. #68 held: re-render via primitive
`requestUpdate`, never `setData`/`update`.

    pointerdown(#chart) ─▶ core.grabHandle ─▶ select (emit drawing:selected)
      pointermove ─▶ core.applyDrag ─▶ emit drawing:changed ─▶ requestUpdate (live)
      pointerup ─▶ PUT /drawings/<id> (one write)
    dblclick ─▶ <dialog> style ─▶ emit drawing:changed ─▶ PUT {style}
    Delete/Escape (keydown on #chart) ─▶ DELETE / deselect

## Architecture Decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Home | Pure `drawing-interaction-core.js` + NEW `controllers/drawing-interaction.js` (7→8) + extract renderer to `drawing-primitive.js` | `drawings.js` AT 300 — extraction is a hard precondition |
| D2 | Gesture | DOM `pointerdown/move/up/cancel` on `#chart` + `host` converters | only real gesture lifecycle + `pointerup`; CSP-clean; converters already used |
| D3 | Coords | pane-relative; gutter via converter `null`, never a hardcoded width | `coordinateToTime/Price` already null off-plot |
| D4 | Capture | `el.setPointerCapture(id)` on drag start | keeps the gesture when pointer leaves `#chart` |
| D5 | State | controller closure + bus (`drawing:selected`/`drawing:changed`); NO new `STORE_KEYS` | frozen 10-key store, #68 boundary |
| D6 | Live render | `drawing:changed` per move → row update + `requestUpdate` | single source of truth; option/data-safe |
| D7 | Persist | single `PUT` on `pointerup` | one write per gesture |
| D8 | Rect | 4 corner handles; dragging one keeps the opposite corner fixed | issue says "4 corners" |
| D9 | `kind` on PUT | differing → 400; equal → ignored; only `points`/`style` written | immutable kind + `interval` accept-and-ignore precedent |
| D10 | Extract | renderer to `drawing-primitive.js`; `chart-host.js` (297) untouched | no host headroom; primitive belongs with drawings |

## Frozen Core API — `drawing-interaction-core.js` (pure ESM, imports nothing)

```js
// map = { x(t)->px|null, y(p)->px|null, time(px)->t|null, price(px)->p|null }
export function handlesFor(kind, points, map)            // -> [{id, x, y}] (off-bar anchors omitted)
export function grabHandle(rows, x, y, map, radius)      // -> {id, target:"body"|handleIndex} | null
export function applyDrag(row, target, dxPx, dyPx, map)  // -> newPoints (fresh; never null keys)
export const HANDLE_RADIUS = 6;
export const BODY_RADIUS   = 4;
```

`map.time(px)`/`map.price(px)` are inverses of `map.x`/`map.y`. `applyDrag`
computes `map.time(map.x(oldTime)+dxPx)` / `map.price(map.y(oldPrice)+dyPx)`;
**any null conversion keeps the old component** (the clamp/off-bar guard — never
emits `null`, which `_parse_point` would 400 and which breaks render).

### Handles per kind (frozen)

| kind | handles | index → field | body drag |
|---|---|---|---|
| `hline` | 1 `price` (x:0, y:map.y) | 0→price | translate price |
| `trendline` | 2 `p1`,`p2` (anchor) | 0→p1 1→p2 | translate p1,p2 |
| `fib` | 2 `p1`,`p2` (anchor) | 0→p1 1→p2 | translate p1,p2 |
| `rect` | 4 `tl/tr/bl/br` (rectPath box) | 0..3 corners | translate p1,p2 |
| `text` | 1 `anchor` (textPath.x/y) | 0→{time,price} | translate {time,price} |

`grabHandle`: handles first (nearest within `HANDLE_RADIUS`), then body
(`hline |dy|≤BODY_RADIUS`; trendline/fib point-segment; rect point-in-box;
text anchor prox), else `null`.

## Contracts

**`drawing-primitive.js`**: `renderShape(ctx, size, row, map, selected)` (thicker
stroke + handle dots when selected) and `makeDrawingPrimitive(row, {isSelected})`
— same v5 primitive as today, reading `isSelected` live so selection needs no
re-attach.

**`controllers/drawing-interaction.js`** — `create({store,bus,host,config})` →
`{attach, clearForSwitch}`. `attach()` rebinds `#chart` listeners (chart is
recreated each build); main calls it after every `buildChart`. Closure holds
`selectedId`,`drag`; reads rows via `bus.on("drawings:changed",{rows})`; emits
`drawing:selected {id}` / `drawing:changed {id, points, style}`.

**`controllers/drawings.js`** (~300→~210): listens `drawing:selected` (mark +
`requestUpdate`) and `drawing:changed` (replace row, `requestUpdate`, refresh
seam); passes `isSelected` to `makeDrawingPrimitive`.

**PUT `api_drawing_detail`** (no `urls.py` change):

```python
@login_required
@require_http_methods(["PUT", "DELETE"])
def api_drawing_detail(request, id):
    drawing = Drawing.for_user(request.user).filter(pk=id).first()
    if drawing is None:
        return JsonResponse({"error": "not found"}, status=404)
    if request.method == "DELETE":
        drawing.delete(); return HttpResponse(status=204)
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "invalid body"}, status=400)
    if "kind" in body and body["kind"] != drawing.kind:
        return JsonResponse({"error": "kind is immutable"}, status=400)
    try:
        points, style = parse_drawing(
            drawing.kind, body.get("points", drawing.points),
            body.get("style", drawing.style))
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    drawing.points, drawing.style = points, style
    drawing.save(update_fields=["points", "style"])
    return JsonResponse({"id": drawing.id, "kind": drawing.kind,
                         "points": drawing.points, "style": drawing.style})
```

`for_user` gives A≠B → 404, A unchanged. CSRF via middleware.

## File Changes

| File | Action |
|---|---|
| `market/drawing-interaction-core.js` | Create — handles/grab/drag/clamp |
| `market/drawing-primitive.js` | Create — renderer (selected-aware) |
| `market/controllers/drawing-interaction.js` | Create — pointer/keyboard/dialog/PUT |
| `market/controllers/drawings.js` | Modify — shrink; bus listeners; `isSelected` |
| `market/main.js` | Modify — create controller; `attach()` in `buildChart`; `clearForSwitch` on symbol switch |
| `market/chart.html` | Modify — `<dialog id="drawing-settings-dialog">`; `#chart` `tabindex="0"`+`aria-label`; preloads ×3 |
| `market/views.py` | Modify — `MODULE_ALLOWLIST` +2, `CONTROLLER_ALLOWLIST` +1, PUT |
| `registration/theme.css` | Modify — dialog + `#chart:focus-visible` |
| `tests/js/drawing-interaction-core.test.js` | Create |
| `tests/web/test_market_api.py` | Modify — PUT cases |
| `tests/web/test_market_e2e.py` | Modify — select→drag→save |
| `tests/web/test_market_ux.py` | Modify — `len(CONTROLLER_ALLOWLIST) == 8` |

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit (node) | handles count/coords; grab handle>body precedence; applyDrag per-kind + off-bar keeps-old; existing `drawing-core.test.js` unchanged | `node --test` |
| Integration | PUT round-trip, partial, kind-immutable 400, malformed 400 (no write), 404, A≠B, CSRF | `test_market_api.py` (only new Python → 100% patch) |
| E2E | `page.mouse.down/move/up` on `#chart`; assert moved via `window.marketChart.drawings` points + captured PUT (not DOM pixels) | `test_market_e2e.py`, readiness-gated, dev-only (#149) |

## Delivery — Feature Branch Chain (3 slices; all base on trailer `feat/drawing-interaction`)

| Slice | Scope | ~Lines | Rollback |
|---|---|---|---|
| S1 core + render extraction | core, primitive, `drawings.js` shrunk, allowlist +2, preloads, node tests | ~250 | no core/split; chart renders unchanged |
| S2 controller + interaction + dialog | controller, allowlist 7→8, main wiring, chart.html, css, ux bump | ~300 | no interaction; S1 stays pure |
| S3 PUT + E2E | PUT + api/e2e tests | ~200 | in-session drag works, unsaved |

Total ≈ 750. Decision needed before apply: Yes; Chained PRs: Yes; 400-line risk: High.

### Guard / Edge Matrix

| Edge | Handling |
|---|---|
| #68 drag re-render | `requestUpdate` only; `setData`-spy tests green |
| both files at ceiling | S1 extraction precondition; new files ≤300 |
| offset / gutter | pane-relative; converter null off-plot; crosshair-hybrid fallback if E2E bristles |
| no new STORE_KEY | closure state; store 10-key assertion untouched |
| frozen 8-key seam | no 9th `window.marketChart` key; E2E via seam + PUT capture |
| a11y | `#chart` focusable + `:focus-visible`; Delete/Backspace `preventDefault`; list-delete path |
| PUT patch 100% | 200/400/404/CSRF/A≠B |
| symbol vs interval switch | `clearForSwitch` on symbol change; interval keeps selection |
| off-bar drag | `applyDrag` keeps old component when inverse null |

## Migration / Rollout

No migration, model, flag, dependency, or CSP change. Per-slice `git revert`.
`src/`, `requirements.txt`, R11 read-only boundary untouched.

## Open Questions

None blocking. Explore Q1–Q8 resolved (D2/D5/D7/D9; style color+lineWidth only;
canvas handles in the existing primitive; no new seam key).
