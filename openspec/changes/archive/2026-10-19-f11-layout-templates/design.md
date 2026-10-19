# Design: f11-layout-templates

Issue #248 (F11-B). Branch `feat/f11-layout-templates` off `develop` @ `e9409ed`.
Three slices B-S1..B-S3. Normative contracts live in
`specs/chart-layout-templates/spec.md`; this decides **how**.

## 1. Model (B-S1)

```python
class ChartTemplate(UserOwnedModel):
    """Per-user named indicator setup (F11-B, R14).

    A template is user-GLOBAL by design: it is a *setup*, and applying it to a
    different (symbol, interval) is the whole point. ``indicators`` is the exact
    list shape ``ChartLayout`` stores, so one validator serves both.
    """
    name = models.CharField(max_length=40)
    indicators = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "name"],
                                    name="uniq_template_user_name"),
        ]
        ordering = ["name"]
```

Migration `0017_charttemplate.py`: `CreateModel` only. Additive; the reverse is a
clean table drop. Added to `OWNED_MODELS` in `tests/web/test_owned_model_guard.py`.

`TEMPLATE_NAME_MAX = 40` lives next to the model as a class constant
(`ChartTemplate.NAME_MAX`) so the API validator and the field cannot drift.

## 2. API (B-S2)

New module `web/market/templates.py` (precedent: `alerts.py`, `watchlist.py` —
`views.py` is 616 lines and does not grow).

```
GET    /market/api/templates        -> 200 {"templates":[{id,name,indicators}]}
POST   /market/api/templates        -> 201 {id,name,indicators}
DELETE /market/api/templates/<id>   -> 204
```

Validation order in POST (mirrors the established style: cheap shape checks first,
expensive/DB last):

1. JSON parses and is a dict → else 400 `invalid JSON` / `invalid body`.
2. `name`: `isinstance(str)` → `.strip()` → non-empty and `len <= NAME_MAX` → else
   400 `invalid name`.
3. `indicators`: `parse_layout_indicators(body.get("indicators"))` → `ValueError`
   → 400 with the message. This is the single drop point (same as the layout API).
4. Duplicate: `ChartTemplate.for_user(user).filter(name=name).exists()` → 400
   `template exists`. The unique constraint is the backstop; the pre-check gives a
   clean 400 instead of an `IntegrityError`.

DELETE uses `<int:id>` (not a symbol string — there is nothing to validate) and
`for_user(...).filter(pk=id).delete()`; when the deleted count is 0 → 404. That
covers both "absent" and "someone else's" without leaking which.

`GET` orders by the model's `Meta.ordering` (`name`), so the select is stable.

## 3. UI (B-S3)

### 3.1 Markup (`chart.html`, static, CSP-clean)

```html
<h2 id="templates-heading">Templates</h2>
<div class="templates">
  <label class="visually-hidden" for="template-select">Template</label>
  <select id="template-select" class="control-select" aria-labelledby="templates-heading">
    <option value="">—</option>
  </select>
  <button type="button" id="template-apply" disabled>Apply</button>
  <button type="button" id="template-save">Save as…</button>
  <button type="button" id="template-delete" disabled>Delete</button>
  <p id="template-status" class="visually-hidden" aria-live="polite"></p>
</div>

<dialog id="template-dialog" aria-label="Save chart as template">
  <form method="dialog">
    <label for="template-name">Name</label>
    <input id="template-name" type="text" maxlength="40" autocomplete="off" required>
    <p id="template-error" class="alert-error" role="alert" hidden></p>
    <button type="submit" value="ok">Save</button>
    <button type="submit" value="cancel">Cancel</button>
  </form>
</dialog>
```

`maxlength="40"` mirrors `NAME_MAX` for the native constraint; the server still
validates (client constraints are not a trust boundary).

### 3.2 Controller (`controllers/templates.js`, leaf)

```js
export function createTemplates({ store, bus, config }) -> { refresh }
```

- Imports: `buildIndicators` from `./indicators.js` (a leaf-to-leaf import, no
  cycle: `indicators.js` never imports `main` or `templates`) and nothing else.
- State: `templates[]` (from GET), `selected` (select value).
- **Save**: `buildIndicators(store.get().indicators, ...params, ...styles, ...indicatorVisible)`
  → `POST` `{name, indicators}`. On 400 show `#template-error` **inside the still-open
  dialog** (the F10 lesson: never write to a closed dialog), on 201 close + refresh.
- **Apply**: map the template entries back into the four store keys and
  `store.set(...)`, then `bus.emit("indicator:changed")` and
  `bus.emit("layout:loaded")`. `main.rebuild()` then renders and calls
  `indicators.saveLayout()` — the existing write path.
- **Delete**: `DELETE`, then refresh.
- Buttons disabled while no template is selected; the select is disabled when the
  list is empty (with a status announcement), mirroring the symbol picker's
  empty-state decision from F11-A.

Estimated ~170 lines; well under 300.

### 3.3 Wiring (`main.js`)

Two lines: one import, one `createTemplates({ store, bus, config })` call placed
next to `createSymbolPicker`. **293 → 297** (`symbol-picker` had already brought
it to 295, so this is +2). No other change.

### 3.4 CSS (`theme.css`)

```css
.templates{display:flex; flex-wrap:wrap; gap:var(--sp-1); align-items:center; margin-bottom:var(--sp-2)}
.templates select{flex:1 1 auto; min-width:0}
.templates button{min-width:32px; min-height:32px}
```

Tokens only; no literal colors. Touch targets follow the existing 32px rule.

### 3.5 Allowlists and docs

`CONTROLLER_ALLOWLIST` 18 → 19 (`templates`). `chart-modules.md` inventory
updated. No new pure core, so `MODULE_ALLOWLIST` is unchanged at 34.

## 4. Test design (patch coverage 100%)

| File | Proves | Negative control |
|---|---|---|
| `tests/web/test_market_templates.py` | model constraint + round-trip; GET ordered/empty; POST create + the four 400 branches (JSON/name/indicators/duplicate); DELETE 204/404; isolation; CSRF; anonymous | B's DELETE of A's id → 404 and A's row survives |
| `tests/web/test_migration_0017.py` | additive; only `charttemplate` created; reverse drops it | the migration name/`CreateModel` shape |
| `tests/web/test_owned_model_guard.py` | `ChartTemplate` in `OWNED_MODELS` | a synthetic unscoped call is flagged |
| `tests/web/test_market_ux.py` | select/dialog markup, no inline handler, controller served + allowlisted, `main.js` line count | size guard green with an empty allowlist |
| `tests/js/templates-core.test.js` | the pure entry↔store mapping (`templateToStore`, `storeToTemplate`) — extracted so the controller has no branch without a test | a template with an unknown token renders degraded, not a throw |

Every production branch maps to a named test: the four POST 400s, the DELETE
404/204 split, the empty-list disable, the dialog open/closed save paths.

## 5. Decisions

| Decision | Choice | Alternative | Why |
|---|---|---|---|
| Apply location | Client-side store write + existing `indicator:changed` | `POST /templates/<id>/apply` | The layout `PUT` already persists; a second write path duplicates it |
| API module | New `web/market/templates.py` | Extend `views.py` (616 lines) | `alerts.py`/`watchlist.py` precedent |
| Name uniqueness | Pre-check + DB constraint | Constraint only | A pre-check yields a clean 400 instead of `IntegrityError` handling |
| Template scope | User-global | Per-symbol | A setup is meant to be applied elsewhere |
| Entry mapping | Pure helpers in a core (`templates-core.js`) | Inline in the controller | Keeps the controller DOM-only and the mapping node-testable |
| Delete id | `<int:id>` | `<str:name>` | Names are mutable/user-facing; ids are stable and need no validation |

## 6. Risks

1. `main.js` at 297/300 — 3 lines of margin remain; any further F11 work must
   extract, not append.
2. A template may store a token later removed from `REGISTRY`; `loadLayout`'s
   documented degraded-render path already handles it.
3. Applying overwrites the current chart's layout by design; the previous layout
   was itself persisted per chart, so the change is one `PUT` away from revert.

## 7. Spec contradictions resolved

None found. `chart-config` R1 states `indicators` carries `{token, params, style}`;
this spec reuses that shape verbatim rather than defining a second one.
