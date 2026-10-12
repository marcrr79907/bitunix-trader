# Archive Report: chart-drawings

**Archived**: 2026-10-12
**Verdict**: PASS WITH WARNINGS (0 blockers, 0 criticals) — 8/8 new requirements (32 scenarios); per-user-isolation R14.2/R14.3 delta; market-chart R11
**Delivery**: tracker PR #91; feature-branch chain #88 → #89 → #90
**Chain commits**: PR1 `2e2771f` (model) → PR2 `2377131` (endpoint) → PR3 `2f01eed` (primitive+UI)
**Merged commit**: PR #91 merge `aeb2e20` on `develop`
**Consolidated range**: `develop` tip `aeb2e20`; code diff vs pre-change base `a03059a` — 15 files, +1548/−6 (excluding openspec)

## What Shipped

Per-user drawing collection (issue #72, Fase A3): the chart gains hline /
trendline / fib / rect / text shapes a user marks on what they see, persisted
server-side and restored on open and symbol/interval switch. Unlike `chart-config`
(one row per key), a chart holds **many** drawings — **no unique constraint**,
CRUD keyed by `id`, scoped per `(user, symbol, interval)`. Third pillar of the
trading view; prerequisite for Fase B/C. Visual annotations only — never order
execution.

| Area | Delivered |
|------|-----------|
| Model | `web/trading/models.py`: `Drawing(UserOwnedModel)` — `symbol`, `interval`, `kind` (TextChoices `hline|trendline|fib|rect|text`), JSON `points`/`style`, `created_at`; index `(user,symbol,interval)`; **no unique constraint**; additive migration `web/trading/migrations/0006_drawing.py` |
| Endpoint | `web/market/views.py` + `urls.py`: `api_drawings` GET/POST + `api_drawing_detail` DELETE, all `@login_required`; GET lists per key (empty, never 404); POST validates before write then `for_user(request.user).create(user=request.user, …)` → 201 `{id,kind,points,style}`; DELETE `<id>` via `for_user` (miss → 404, idempotent) |
| Validation | `web/market/quotes.py`: `DRAWING_KINDS` (TextChoices) + pure `parse_drawing(kind, points, style)` raise-`ValueError`, per-kind point/style schema |
| Isolation | `Drawing` in `OWNED_MODELS` + negative-control fixture (`Drawing.objects.all()` flagged); A≠B read/delete tests; cross-user DELETE → 404 |
| Render | `web/market/templates/market/chart.js` + `drawing-core.js`: one v5 `ISeriesPrimitive` per kind on `candleSeries` (separate canvas layer, single-write-path #68 preserved); `drawing-core.js` pure UMD geometry (`node --test`) |
| UI | `chart.html`: CSP-safe `<fieldset class="drawings">` toolbar (`addEventListener`, no inline handler); native `<dialog>` for text; `window.marketChart.drawings` seam |
| Tests | `tests/js/drawing-core.test.js` (new), `tests/web/{test_isolation,test_market_api,test_market_e2e,test_owned_model_guard}.py` |

## Verify Findings

Verdict `pass_with_warnings`; 0 blockers, 0 criticals. Full chain present
(`2e2771f` → `2377131` → `2f01eed`, all ancestors of HEAD). Every L1/L2 gate green:
523 passed + 19 deselected, E2E `-m e2e -p no:randomly` 19 passed, `node --test`
26 passed (9 chart-core + 17 drawing-core), ruff + format clean,
`makemigrations --check` clean, patch gate 100% (94 lines, `views.py` +
`models.py`), `requirements.txt`/CSP unchanged, boundary + order-scanner green.

### Warnings carried (non-blocking)

- **W1 — Index name deviation**: design/spec literal `ix_drawing_user_symbol_interval`
  is 31 chars and fails Django `E034` (30-char limit). Implemented as
  `ix_drawing_user_sym_interval`. R1 requires the tuple be indexed, not the literal
  name → requirement holds.
- **W2 — `style` not key-validated**: `parse_drawing` requires `style` to be an
  object but does not enforce per-kind style keys (`{color, lineWidth}`). Spec R5
  requires only point-count/label rejection; style stays open-ended like
  `ChartLayout`. Acceptable.
- **W3 — Pre-existing E2E flake (not drawings-specific)**: the threaded live server
  + SQLite session contention makes some tests intermittently 302/500 under
  parallel load. PR3 serialized the drawings boot path
  (layout→build→connect→drawings→history). Run `-m e2e -p no:randomly` on an idle
  machine.
- **W4 — `timeToCoordinate` null off-bar** is guarded by inspection and E2E covers
  the happy path; a drawing anchored outside the loaded range degrades gracefully
  (skipped leg) rather than crashing.
- **SUGGESTION 1** — WU1/WU2 checkboxes in `tasks.md` were left unmarked by apply
  (orchestrator hard contract); WU3 marked.
- **SUGGESTION 2** — No node unit test for the adapter layer itself (geometry only);
  E2E is the adapter net.

### Process note (topology — durable lesson confirmed)

The chain used the **documented topology**: all slice PRs base on the tracker
branch `feat/chart-drawings`. PR1 `feat/chart-drawings-model` → tracker (PR #88);
after #88 merged, PR2 `feat/chart-drawings-endpoint` → tracker (PR #89, parent
`44728de`); after #89 merged, PR3 `feat/chart-drawings-ui` → tracker (PR #90,
parent `643ffff`); then tracker → `develop` (PR #91 merge `aeb2e20`). Merge-parent
inspection confirms each slice's merge commit has the previous tracker state as
its first parent. **Durable lesson: merge each slice to the tracker BEFORE
branching the next; never chain slice-to-slice.** This contrasts with the earlier
`chart-config` chain (#85/#86/#87 opened chained to each other and re-consolidated
via an explicit merge) — the all→tracker topology keeps every child diff clean
against the tracker.

## Requirement Outcomes

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| chart-drawings (new) | R1 drawing model, ownership, index | ✅ `Drawing` + additive `0006` + index; no unique constraint |
| chart-drawings (new) | R2 drawings CRUD API | ✅ GET/POST/DELETE; 302/400/201/204/404; idempotent by id |
| chart-drawings (new) | R3 cross-user isolation (A≠B) | ✅ `for_user` everywhere; B DELETE of A id → 404 |
| chart-drawings (new) | R4 validation before write | ✅ `parse_drawing` → 400, no write |
| chart-drawings (new) | R5 kind-specific point/style schemas | ✅ per-kind point/label checks; style keys open (W2) |
| chart-drawings (new) | R6 v5 primitive render contract | ✅ per-kind primitive; null off-bar guard (W4); separate layer |
| chart-drawings (new) | R7 load/restore on boot and switch | ✅ boot + `switchTo`; failed fetch non-fatal; `drawings` seam |
| chart-drawings (new) | R8 read-only boundary, CSP, no new dep | ✅ CSP/`requirements.txt`/`src/` unchanged; order scanner clean |
| per-user-isolation | R14.2 cross-user read denied | ✅ + `Drawing` in delivered set & +1 scenario |
| per-user-isolation | R14.3 unscoped-query guard | ✅ `OWNED_MODELS` + `Drawing`; + negative-control scenario |
| market-chart | R11 drawings endpoint & render/restore | ✅ endpoint contract + render/restore + CSP-clean (7 scenarios) |

## Gates

`python -m pytest` 523 passed / 19 deselected (exit 0); E2E `-m e2e -p no:randomly`
19 passed; `node --test tests/js/**/*.test.js` 26 passed; `ruff check` +
`ruff format --check` clean; `makemigrations --check` clean; patch gate 100% (94
lines, 0 missing); `requirements.txt`, CSP, and `chart-core.js` (#68
single-write-path) unchanged; boundary + order-scanner green.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| chart-drawings | Created | New capability — R1–R8 (32 scenarios) copied verbatim from the change spec |
| per-user-isolation | Updated | R14.2 delivered set + `Drawing` & +1 scenario; R14.3 `OWNED_MODELS` + `Drawing` & + negative-control scenario; R14.1/R14.4 preserved |
| market-chart | Updated | + R11 (7 scenarios); R1–R10 preserved untouched |

## Carry-forward

- None blocking. W1 is a recorded naming deviation (requirement holds).
- W2 is a non-blocking API hole: style keys are not validated per kind. If a future
  change tightens `parse_drawing`, enforce the frozen per-kind style schema.
- W3 is a pre-existing E2E infra flake; keep `-p no:randomly` for E2E runs.
- W4 degrades gracefully; no action unless off-bar anchoring needs richer UX.

## SDD Cycle Complete

Planned → implemented (3-PR feature-branch chain, #88/#89/#90, all→tracker) →
verified (pass_with_warnings; no CRITICAL/BLOCKER) → merged (tracker PR #91,
`aeb2e20`) → archived.

Traceability: `openspec/changes/archive/2026-10-12-chart-drawings/`
(explore, proposal, design, specs, tasks, verify-report); engram
`sdd/chart-drawings/{proposal,spec,design,tasks,verify-report}`.
