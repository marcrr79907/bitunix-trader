# Proposal: f11-layout-templates

Issue **#248** (F11-B, second half of #124). Branch `feat/f11-layout-templates`
off `develop` @ `e9409ed`.

## Intent

Give the user **named, reusable indicator setups** that can be applied to any
chart. Today the configuration persists per `(user, symbol, interval)` island
(`ChartLayout`, `web/trading/models.py:210-230`); a user with four setups across
eight charts rebuilds them by hand.

## Scope

### In scope — three slices

- **B-S1 — Model.** `ChartTemplate(UserOwnedModel)`: `name` (max 40),
  `indicators` JSONField, `created_at`; `UniqueConstraint(user, name)`. Additive
  migration `0017` (new table only). `ChartTemplate` joins `OWNED_MODELS`.
- **B-S2 — API.** New `web/market/templates.py`: `GET/POST /market/api/templates`,
  `DELETE /market/api/templates/<id>`. `parse_layout_indicators` validates before
  any write; the name is validated and trimmed; a duplicate name is a 400; every
  access goes through `ChartTemplate.for_user`; the owner is never read from the
  body.
- **B-S3 — UI.** New leaf `controllers/templates.js` with a static `<select>`, a
  **Save as…** `<dialog>`, and Apply/Delete. Apply writes the four store keys and
  emits the **existing** `indicator:changed` + `layout:loaded`; the layout `PUT`
  already does the persistence. Allowlists, `test_market_ux`, and
  `docs/architecture/chart-modules.md` updated; CSS uses existing tokens only.

### Out of scope (explicit)

- **Named multi-chart workspaces / grids** — a template is a setup, not a layout
  of panes.
- **Sharing templates between users** — every template is `for_user`-scoped; a
  shared catalog would need a new visibility model and a different R14 contract.
- **Server-side "apply"** — the template payload is already client-side and
  applying it is a store write plus the existing layout `PUT`. A second write
  path would duplicate the layout save.
- **Templates that capture drawings/SMC toggles** — out of scope; this is the
  indicator configuration only (the same payload `ChartLayout` stores).
- **Order execution** — never; the repo stays read-only.
- New dependency, inline script/handler, store key, bus event, or `src/` change.

## Capabilities

### New
- `chart-layout-templates`: named per-user indicator setups, their CRUD, and the
  apply path.

### Modified
- `market-chart`: **R14** inventory grows by one controller (`templates`); the
  frozen seams (8-key `window.marketChart`, 11 `STORE_KEYS`) are unchanged.
- `chart-config`: notes that a template stores the same validated
  `indicators` payload as `ChartLayout`; no change to the layout contract.

## Approach

- **Reuse the validator, not a parallel one.** `parse_layout_indicators`
  (`web/market/quotes.py:300-336`) already validates token/params/style/visible
  and is the single drop point for bad input. A template stores exactly the shape
  it returns.
- **Reuse the apply path.** `controllers/indicators.js:loadLayout` already writes
  `indicators/params/styles/indicatorVisible` and emits `layout:loaded`; the
  template controller performs the same store write and lets `main.rebuild()`
  handle rendering and persistence. No new render path.
- **Reuse `buildIndicators` for save.** The template's payload is produced by the
  same pure helper the layout save uses (`controllers/indicators.js:60-70`), so a
  template and a layout can never disagree about shape.
- **`main.js` grows by exactly two lines** (one import, one call) to 297/300; the
  controller stays well under the module ceiling.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `web/trading/models.py` | Modified | + `ChartTemplate` |
| `web/trading/migrations/0017_charttemplate.py` | New | additive table |
| `web/market/templates.py` | New | JSON CRUD over `for_user` |
| `web/market/urls.py` | Modified | +2 routes |
| `web/market/constants.py` or `quotes.py` | Modified | shared name-max constant (single source) |
| `tests/web/test_owned_model_guard.py` | Modified | `ChartTemplate` in `OWNED_MODELS` |
| `web/market/templates/market/controllers/templates.js` | New | select + dialog + apply |
| `web/market/templates/market/chart.html` | Modified | static select/dialog markup |
| `web/market/templates/market/main.js` | Modified | **+2 lines** |
| `web/market/views.py` | Modified | allowlist + `templates` controller |
| `web/accounts/templates/registration/theme.css` | Modified | tokens only |
| `docs/architecture/chart-modules.md` | Modified | inventory |
| `tests/js/*`, `tests/web/*` | Modified | CRUD, isolation, markup, size |

## Rollback Plan

- **B-S1**: revert the model + drop migration `0017` (a clean table drop; no data
  in any other table depends on it).
- **B-S2**: delete `templates.py` + the two routes; no migration to reverse
  beyond B-S1.
- **B-S3**: revert the controller/markup/allowlist entries; the chart is
  unaffected (the controller is additive and self-bootstrapping).
- **Never destructive**: no existing column, constraint, or row is altered.

## Risks

| Risk | L | Mitigation |
|---|---|---|
| `main.js` at 300 | High | +2 lines, measured in the gate; extraction target named in the design |
| A stored template references a token later removed from `REGISTRY` | Med | Validation on write; the degraded-render path in `loadLayout` already covers it |
| Applying a template overwrites the current chart's layout | Med | That is the stated intent; the previous layout was itself persisted, and the spec says so |
| Duplicate name is a silent overwrite | Low | `UniqueConstraint` + explicit 400 |
| Name with only whitespace | Low | Trim then require non-empty |

## Dependencies

- `ChartLayout` + `parse_layout_indicators` (existing).
- F11-A shipped: no overlap with catalog/watchlist/ingestion.

## Success Criteria

- [ ] Saving the active chart as a named template persists it `for_user`.
- [ ] Applying a template changes the active chart's indicators/params/styles and
      persists the layout via the existing `PUT`.
- [ ] Duplicate name → 400; malformed symbol-free payload → 400 with no write.
- [ ] A≠B isolation on GET/POST/DELETE; a foreign id → 404.
- [ ] Additive migration, `makemigrations --check` green; patch coverage 100%.
- [ ] `main.js` ≤ 297, every module ≤ 300, seams unchanged, CSP unchanged.
