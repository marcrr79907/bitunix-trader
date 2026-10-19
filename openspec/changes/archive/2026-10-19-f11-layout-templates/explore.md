# Exploration: f11-layout-templates

Issue **#248** (F11-B, closes the second half of #124). Branch
`feat/f11-layout-templates` off `develop` @ `e9409ed`. Read-only exploration: no
code changed.

## 1. Problem framing

A user's indicator configuration is already persisted, but only **per chart**:

```
ChartLayout: (user, symbol, interval) -> indicators[]
```

`web/trading/models.py:210-230`, unique `uniq_layout_user_symbol_interval`. Every
`(symbol, interval)` is an island. To reuse a setup the user must rebuild it by
hand on each chart. TradingView solves this with **layout templates**: a named,
user-owned snapshot you can apply to any chart.

## 2. Current state (cited)

| Concern | Where | Behavior |
|---|---|---|
| Layout model | `web/trading/models.py:210-230` | `ChartLayout` keyed `(user, symbol, interval)`, `indicators` JSONField |
| Layout API | `web/market/views.py:257-330` | `GET/PUT /market/api/layout`, `exists:false` on miss returning `DEFAULT_LAYOUT` |
| Layout validation | `web/market/quotes.py:300-336` | `parse_layout_indicators` — validates token against `REGISTRY`, params, `style`, `visible` |
| Default set | `web/market/quotes.py:90` | `DEFAULT_LAYOUT = [{token:sma},{token:ema},{token:rsi}]` |
| Client load | `controllers/indicators.js:97-137` | `loadLayout` → writes `indicators/params/styles/indicatorVisible` into the **store** |
| Client save | `controllers/indicators.js:141-160` | `saveLayout` → `buildIndicators(...)` → debounced `PUT` pinned to `symbol/interval` |
| Rebuild path | `main.js:167-181` | `rebuild()` reads the store, `buildChart()`, `fetchHistory()`, `saveLayout()` |
| Layout-loaded event | `chart-bus.js:16` | `layout:loaded` → the object tree re-renders from the store |
| Indicator payload shape | `controllers/indicators.js:60-70` | `buildIndicators(indicators, params, styles, visible)` → `[{token, params?, style?, visible?}]` |

**Finding 2.1 — the apply path already exists.** `loadLayout` writes the four
store keys that the render path consumes (`indicators`, `params`, `styles`,
`indicatorVisible`) and emits `layout:loaded`. Applying a template is therefore
**exactly the same operation as loading a layout**, minus the network call.
No new render path, no new bus event, no new store key.

**Finding 2.2 — no migration is needed for the payload.** A template stores the
same `indicators` list `ChartLayout` already stores, validated by the same
`parse_layout_indicators`. Only a new **table** is needed, not a schema change to
an existing one.

## 3. Design constraints

| Constraint | Source | Consequence |
|---|---|---|
| `main.js` = **295/300** | `test_module_size_guard.py` | The wiring must be ≤3 lines, or live inside the controller |
| `window.marketChart` = 8 frozen keys | e2e seam | The controller cannot expose state there |
| `STORE_KEYS` = 11 frozen | `chart-store.js:13-27` | No new store key |
| CSP: no inline script/handler | `design-system` R7 | Static `<dialog>` + `<select>` markup |
| R14: request paths use `for_user` | `test_owned_model_guard.py` | `ChartTemplate` must join `OWNED_MODELS` |
| Patch coverage 100% | CI gate | Every branch needs a test |
| `src/` framework-free | `test_boundary.py` | No Django import in `src/` |

## 4. Slice feasibility

### B-S1 — Model + migration

`ChartTemplate(UserOwnedModel)`:

| Field | Type | Why |
|---|---|---|
| `name` | `CharField(max_length=40)` | Short, user-facing; a select option must fit |
| `indicators` | `JSONField(default=list)` | Same shape as `ChartLayout.indicators` — reuses the validator |
| `created_at` | `DateTimeField(auto_now_add=True)` | Stable ordering for the select |

`UniqueConstraint(user, name)` → a duplicate name is a 400, not a silent
overwrite. Migration `0017` is **additive** (new table only): `makemigrations
--check` must stay green and the reverse is a clean table drop.

### B-S2 — API

`web/market/templates.py` (new module, mirroring the `alerts.py`/`watchlist.py`
precedent — `views.py` is already 616 lines):

| Route | Behavior |
|---|---|
| `GET /market/api/templates` | `{"templates": [{id, name, indicators}]}`, caller-scoped, ordered by `name` |
| `POST /market/api/templates` | `{name, indicators}` → 201; validates `name` (1..40, trimmed, non-empty) and `indicators` via `parse_layout_indicators` **before writing**; duplicate name → 400 |
| `DELETE /market/api/templates/<id>` | 204; a foreign/absent id → 404 (no leak) |

Every access via `ChartTemplate.for_user(request.user)`; the owner is never taken
from the body.

**Decision: apply is client-side.** No `POST /templates/<id>/apply` route. The
template payload is already in the client (the `GET` returns it), and applying is
a store write plus the existing `saveLayout()`. A server-side apply would need to
know the target `(symbol, interval)` and would duplicate the layout `PUT` that
already exists — two write paths for one concern, violating #68's spirit.

### B-S3 — UI

`controllers/templates.js` (new leaf controller):

```
createTemplates({ store, bus, config }) -> { refresh }
```

- **Markup** (static, CSP-clean): `<select id="template-select">`, a
  "Save as…" button, an "Apply" button, a "Delete" button, and
  `<dialog id="template-dialog">` with a name input.
- **Save**: serialise the active chart with the **same** `buildIndicators(...)`
  the layout save uses (imported from `controllers/indicators.js` — a leaf import,
  no cycle) → `POST`.
- **Apply**: write `indicators/params/styles/indicatorVisible` into the store from
  the template's entries, emit the existing `indicator:changed` (main rebuilds and
  calls `saveLayout()`), then `bus.emit("layout:loaded")` so the object tree
  re-renders. **No new bus event.**
- **Delete**: `DELETE /templates/<id>`, then refresh the select.

**Wiring cost**: one import + one `createTemplates({store, bus, config})` call =
**+2 lines → `main.js` = 297/300**. If a third line is needed, the extraction
target is the symbol-picker call block, not `main.js`.

## 5. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| `main.js` hits 300 | High | +2 lines exactly; measure with `wc -l` in the gate |
| Applying a template with a token the client cannot render (legacy `sma20`) | Medium | `parse_layout_indicators` accepts it server-side today; the client renders degraded (spec `chart-config` R2 already documents this) |
| Template `indicators` carrying a token removed from `REGISTRY` later | Medium | Validation happens on **write**; a stored template can still reference a dropped token. `loadLayout`'s degraded-render path already handles it |
| Name collision UX | Low | 400 → the dialog shows an inline error, mirroring `alert-error` |
| Applying a template silently overwrites the current layout | Medium | That is the intent (and the current layout is itself persisted per chart); the spec states it explicitly |

## 6. Test strategy

| Layer | What | Where |
|---|---|---|
| Model | constraint, `for_user`, field round-trip | `tests/web/test_market_templates.py` |
| Migration | additive, `makemigrations --check`, reverse is a table drop | same file + the existing migration test pattern |
| API | GET/POST/DELETE matrix, validation order, duplicate name, isolation A≠B, CSRF, owner-from-body | same file |
| Guard | `ChartTemplate` in `OWNED_MODELS` | `test_owned_model_guard.py` |
| Node | `buildIndicators` reuse (already covered), template `applyEntries` pure helper | `tests/js/templates-core.test.js` |
| Markup | select/dialog present, no inline handler, module+controller allowlisted | `tests/web/test_market_ux.py` |
| Size | every module ≤300, `main.js` measured | `test_module_size_guard.py` |

## 7. Estimated size

| Slice | Prod | Test | Total |
|---|---|---|---|
| B-S1 model + migration | ~25 | ~40 | ~65 |
| B-S2 API module + 2 routes | ~90 | ~150 | ~240 |
| B-S3 controller + markup + CSS + allowlists + docs | ~180 | ~120 | ~300 |
| **Total** | **~295** | **~310** | **~605** |

Over the 400-line budget → a 2-PR chain (S1+S2 backend, S3 UI), tracker
`feat/f11-layout-templates`.

## 8. Open questions

None blocking. Two defaults recorded: (a) a 40-character template name,
(b) templates are user-global (not per-symbol) — a template is a *setup*, and
applying it to a different symbol is the whole point.
