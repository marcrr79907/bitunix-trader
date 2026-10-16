# Proposal: drawing-interaction

## Intent

Drawings are create/delete-only: a placed shape cannot be selected, moved,
resized, restyled, or deleted. F4 (issue #117, Ola 4) makes them usable —
select, drag, edit, delete. Read-only annotation.

## Scope

### In Scope
- Pure `drawing-interaction-core.js` (node-tested): `handlesFor`, `grabHandle`,
  `applyDrag` → points, clamp + null-guard.- NEW thin `controllers/drawing-interaction.js`; extract renderer to
  `drawing-primitive.js` so `drawings.js` (AT 300) and `chart-host.js` (297)
  clear the ceiling.
- Pointer `pointerdown/move/up` on `#chart` + host converters, gutter/off-bar
  guarded; Delete/Backspace deletes, Escape deselects, `#chart` focusable.
- Double-click → properties `<dialog>` (F2 pattern): `style` color/lineWidth.
- NEW `PUT /market/api/drawings/<id>`: `for_user`, miss/A≠B → 404, partial
  `{points?,style?}`, `kind` immutable, validate via `parse_drawing`.

### Out of Scope
Undo/versioning; shared drawings; fill/levels/fontSize editing; order execution
(HARD); npm/build; CSP relaxation; new dep; SMC.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `chart-drawings`: R2 gains `PUT /<id>`; NEW selection, per-kind drag, keyboard
  delete/deselect, properties-dialog requirements.
- `market-chart`: R11 gains the PUT contract and interaction/render seam.

## Approach

Layered F0 extension. Pure core owns geometry, reusing `drawing-core.hitTest` and
`*Path` builders. The controller keeps selection/drag/keyboard/dialog state in
its closure, syncs via `bus.emit("drawing:selected")`, PUTs once on `pointerup`.
#68 preserved: re-render via `requestUpdate`, never `setData`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `drawing-interaction-core.js`, `drawing-primitive.js` | New | drag math; renderer |
| `controllers/drawing-interaction.js` | New | pointer/keyboard/dialog |
| `controllers/drawings.js` | Modified | shrink ≤300 |
| `main.js`, `chart-host.js`, `chart.html`, `theme.css` | Modified | wiring, dialog, focus |
| `web/market/{views,urls,quotes}.py` | Modified | PUT + `parse_drawing` |
| `tests/js/*`, `tests/web/{api,e2e,ux}.py` | Modified | drag math, PUT, allowlists |

## Risks

| Risk | L | Mitigation |
|------|---|------------|
| #68 drag re-render | Med | `requestUpdate` only; spies green |
| both files at ceiling | High | extraction is a precondition |
| page→pane offset math | High | pane-relative; E2E; crosshair fallback |
| E2E drag not DOM-assertable | Med | seam + PUT network |
| class-C E2E flake (#149) | Med | readiness-gated, dev-only |
| a11y (pointer-only drag) | Med | list+Delete path; focus ring |
| PUT patch 100% | High | 200/400/404/CSRF/A≠B |

## Rollback Plan

Revert the three PRs. S3: drop PUT (in-session drag works, unsaved). S2: drop
controller/wiring/dialog. S1: drop core+split. No migration, schema, CSP, or dep
change; each PR independently revertible.
## Dependencies

`drawing-core.hitTest` + `*Path` builders; v5 primitive render + host converters;
`parse_drawing`. All merged. No new dep.

## Read-Only Boundary

MUST NOT place/modify/cancel orders, expose order endpoints, or relax R11.
`src/` framework-free; `requirements.txt` unchanged.

## Delivery (Feature Branch Chain, 3 slices)

S1 core + render extraction + wiring + JS tests ~250 | S2 controller + wiring +
dialog + allowlist 7→8 ~300 | S3 PUT + API/E2E tests ~200. Base: tracker
`feat/drawing-interaction`. Total ≈ 750.

- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: High

## Success Criteria

- [ ] Select → drag → PUT round-trips; survives reload.
- [ ] Per-kind handles/translate correct (hline/trendline/fib/rect/text).
- [ ] Delete/Escape/dialog work; keyboard path exists.
- [ ] PUT partial, `kind` immutable, 404 on miss/A≠B, CSRF enforced.
- [ ] Selection clears on symbol switch, survives interval-only switch.
- [ ] `node --test` + `pytest` green; patch 100%; #68 spies green.