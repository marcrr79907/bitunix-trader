# Proposal: chart-drawings

## Intent

The chart is analysis-neutral: a user cannot mark what they see. Drawing tools
(hline, trendline, fib, rect, text) are the third pillar of a trading view and
the prerequisite for Fase B/C. A3 extends A2's per-user persistence seam from a
single blob (`ChartLayout`) to a **collection** of owned shapes — distinct key
semantics, not a copy-paste. Issue #72 (Fase A3).

## Scope

### In Scope
- `Drawing(UserOwnedModel)`: `symbol`, `interval`, `kind`
  (`hline|trendline|fib|rect|text`), `points` JSON, `style` JSON, `created_at`.
  **Collection** — one row per shape, index `(user, symbol, interval)`, **NO
  unique constraint** (many per chart, unlike `ChartLayout`). Additive `0006`.
- `market/api/drawings`: `GET ?symbol=&interval=` (list, empty when none, never
  404) / `POST` (create→row+id, 400 before write) / `DELETE <id>` (by id,
  idempotent). All via `for_user`; A≠B.
- Pure `parse_drawing`/`DRAWING_KINDS` in `quotes.py`.
- v5.2.0 series primitive per kind (already-loaded CDN, no new dep); pure geometry
  in `drawing-core.js` (`node --test`); toolbar + load/save in
  `chart.js`/`chart.html`; E2E + `window.marketChart.drawings` seam.

### Out of Scope
- SMC automation (OB/FVG detection, Fase C) — manual rectangle only.
- Shared/multi-user drawings; versioning/undo.
- Order execution (HARD); npm/build; CSP relaxation; new runtime dependency.

## Capabilities

### New Capabilities
- `chart-drawings`: per-user drawing collection — model, CRUD endpoint, v5
  primitive render, pure geometry core, restore/delete UI.

### Modified Capabilities
- `per-user-isolation`: R14.2 owned-model list gains `Drawing`.
- `market-chart`: new R11 — drawings GET/POST/DELETE contract.

## Approach

Mirror A2's seams with collection semantics. `Drawing(UserOwnedModel)` in
`web/trading/models.py`; `api_drawings` reads/writes through `for_user`, keyed by
`id` (not upsert). Pure `parse_drawing(kind, points, style)` validates before
write. One v5 `ISeriesPrimitive` per kind draws via `priceToCoordinate`/
`timeToCoordinate`; pointer capture via `subscribeClick`/`subscribeCrosshairMove`;
persistence reuses the A2 CSRF/debounce seam. Geometry extracted to
`drawing-core.js` for patch coverage. No new dependency; CSP unchanged; #68
single-write-path untouched (separate canvas layer).

**Locked** (explore Q2/Q3/Q6): per-interval storage (shared deferred);
delete-by-id; delete via panel list, not canvas hit-testing.
**Decision needed**: text input — native `<dialog>` vs fixed label (recommend
`<dialog>`).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/trading/models.py` | Modified | + `Drawing` |
| `web/trading/migrations/0006_drawing.py` | New | additive |
| `web/market/{views,urls,quotes}.py` | Modified | endpoint, route, validator |
| `web/market/templates/market/{chart.html,chart.js}` | Modified | toolbar, primitives, save |
| `web/market/templates/market/drawing-core.js` | New | pure geometry |
| `tests/web/*.py` (guard, isolation, api, e2e) | Modified | contract tests |
| `tests/js/drawing-core.test.js` | New | pure geometry |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| v5 primitive quirks (CanvasRenderingTarget2D, requestUpdate, autoscaleInfo) | Med | one primitive per kind, E2E-exercised |
| `timeToCoordinate` null off-bar / after interval switch | Med | null-guard draw; spec scenario |
| E2E canvas not DOM-observable | Med | JS seam + network assertions (A2 pattern) |
| JS patch-coverage gap | Med | pure geometry in `drawing-core.js` |
| Guard blind spot (`OWNED_MODELS`) | Med | explicit task + negative-control fixture |
| Scope creep into SMC (Fase C) | Low | manual rectangle only; fenced |

## Rollback Plan

Revert the feature branch: drop `Drawing` + `0006`, remove `api_drawings` +
route, restore `chart.js`/`chart.html`, revert test edits. The additive migration
reverses to dropping one new table — no data loss. No CSP, `requirements.txt`, or
boundary change. Each chained PR is independently revertible.

## Read-Only Boundary

Drawings are visual annotations only. The change MUST NOT place, modify, or
cancel orders, MUST NOT expose order-execution endpoints, and MUST NOT relax R11.
Client code MUST stay order-silent; the order scanner MUST remain clean. `src/`
stays framework-free; `requirements.txt` unchanged.

## Dependencies

- A2 (`chart-config`) merged: `ChartLayout`, `0005`, CSRF meta, async boot seam.
- Lightweight Charts v5.2.0 (pinned CDN; `attachPrimitive` present).
- `node --test` + Playwright (existing infra). No new runtime dep.

## Delivery (Feature Branch Chain)

- **PR1 — model**: `Drawing` + `0006` + `OWNED_MODELS` + isolation/guard tests. ~90 lines.
- **PR2 — endpoint**: `api_drawings` + route + `parse_drawing`/`DRAWING_KINDS` + tests. ~150 lines.
- **PR3 — primitive + UI**: `drawing-core.js`, v5 primitives, toolbar, E2E + seam. ~200 lines.

PR1 → tracker branch; PR2 → PR1; PR3 → PR2. Total ≈ 400–440 lines.

- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: Medium

## Success Criteria

- [ ] Drawings persist per user/key; GET lists only the caller's; A≠B isolated.
- [ ] POST 400 before write on bad kind/points/style/interval; DELETE idempotent by id.
- [ ] Chart renders saved shapes on open + switch; add/delete round-trips.
- [ ] `pytest` green; `node --test` green; patch gate 100%; ruff clean; `makemigrations --check` green.
- [ ] No new runtime dependency; CSP unchanged; order scanner clean; `src/` framework-free.
