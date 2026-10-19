# Tasks: f11-layout-templates (issue #248, Fase F11-B)

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

> **Key insight pinned as a constraint.** The apply path already exists:
> `controllers/indicators.js:loadLayout` writes `indicators/params/styles/
> indicatorVisible` into the store and emits `layout:loaded`; `main.rebuild()`
> then renders and calls `indicators.saveLayout()`. A template apply MUST reuse
> that path — no new bus event, no new store key, no server-side apply endpoint.

> **Hard limits.** `main.js` is 295/300 and may end at **297** (exactly +2 lines).
> `smc.js` is already at 300. Every module ≤300 with an EMPTY allowlist.
> `window.marketChart` = 8 keys and `STORE_KEYS` = 11 are frozen.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | S1 ~65, S2 ~240, S3 ~300 → **~605** |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR1 (model + migration + `OWNED_MODELS` + API + tests) → PR2 (controller + markup + CSS + allowlists + docs + UX/size tests) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

### Suggested Work Units

| Unit | Goal | Likely PR | Base / boundary |
|------|------|-----------|-----------------|
| B-S1 | `ChartTemplate` + migration `0017` + model/constraint tests + guard | PR 1 | base = tracker `feat/f11-layout-templates` |
| B-S2 | `web/market/templates.py` + 2 routes + full API matrix | PR 1 | same PR as S1 (together ~305 lines) |
| B-S3 | `templates-core.js` + `controllers/templates.js` + markup + CSS + allowlists + `main.js` +2 + UX/size | PR 2 | base = tracker; S1+S2 merged first |

S1+S2 ≈ 305 which is under 400, so they ship as **one** PR. S3 ≈ 300 ships as the
second. Only the tracker merges to `develop`; `main` untouched. **Never pass
`--delete-branch` while a downstream PR still targets the branch being merged**
(handoff gotcha #1).

## Gates per slice (before each commit)

```bash
node --test "tests/js/**/*.test.js"
.venv/bin/python -m pytest -p no:randomly
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python web/manage.py makemigrations --check --dry-run
.venv/bin/diff-cover cov.xml --compare-branch=origin/develop --fail-under=100
wc -l web/market/templates/market/main.js   # must be <= 297
```

## Phase 1 — B-S1: model + migration (PR1)

Branch `feat/f11-layout-templates-s1`; base tracker. Rollback: drop migration
`0017` (clean table drop) and the model.

- [ ] 1.1 **RED** NEW `tests/web/test_market_templates.py` (model part): two rows
  `(A, "Scalping")` → `IntegrityError`; `(A,"Scalping")` + `(B,"Scalping")` coexist;
  `indicators` nested round-trip; `for_user` scopes. Acceptance: red before 1.2.
- [ ] 1.2 **GREEN** `web/trading/models.py`: add `ChartTemplate(UserOwnedModel)` with
  `name` (max 40), `indicators` JSONField, `created_at`, `UniqueConstraint(user,name)`,
  `Meta.ordering=["name"]`, `NAME_MAX = 40`. Acceptance: 1.1 green.
- [ ] 1.3 **GREEN** `makemigrations trading` → `0017_charttemplate.py`; confirm it is a
  single `CreateModel`. Acceptance: `makemigrations --check` clean.
- [ ] 1.4 **GREEN** `tests/web/test_owned_model_guard.py`: add `ChartTemplate` to
  `OWNED_MODELS` and a probe asserting an unscoped `ChartTemplate.objects.all()` is
  flagged. **RED first.** Acceptance: guard test green.
- [ ] 1.5 **GREEN** NEW `tests/web/test_migration_0017.py`: additive shape, creates
  only `charttemplate`, reverse drops it. Acceptance: green.

## Phase 2 — B-S2: JSON API (PR1, same branch)

Rollback: delete `templates.py` + the 2 routes.

- [ ] 2.1 **RED** extend `tests/web/test_market_templates.py` with the API matrix:
  GET ordered + empty-list not 404; POST 201; 400 for bad JSON, non-dict body,
  non-string name, blank name, 41-char name, invalid indicators (unknown token /
  bad style / non-bool visible), duplicate name; DELETE 204, foreign id 404, absent
  id 404; A≠B isolation on all three; owner-from-body ignored; CSRF 403 on writes;
  anonymous 302. Acceptance: red before 2.2.
- [ ] 2.2 **GREEN** NEW `web/market/templates.py`: `api_templates` (GET/POST) and
  `api_template_detail` (DELETE `<int:id>`), validation order JSON → name →
  indicators (`parse_layout_indicators`) → duplicate pre-check; every access via
  `ChartTemplate.for_user`. Acceptance: 2.1 green.
- [ ] 2.3 **GREEN** `web/market/urls.py`: +2 routes after the watchlist block.
  Acceptance: routes resolve; 2.1 green.
- [ ] 2.4 **REFACTOR** gates green; `diff-cover` 100% on `templates.py` and the
  migration; no dependency added.

## Phase 3 — B-S3: UI (PR2)

Branch `feat/f11-layout-templates-s3`; base tracker (S1+S2 merged). Rollback:
revert the controller/markup/allowlists; the chart is unaffected.

- [ ] 3.1 **RED** NEW `tests/js/templates-core.test.js`: the pure mapping
  `templateToStore(entries)` → `{indicators, params, styles, indicatorVisible}` and
  `storeToTemplate(state)` → entries via `buildIndicators`; a template referencing an
  unknown token maps without throwing. Acceptance: red before 3.2.
- [ ] 3.2 **GREEN** NEW `web/market/templates/market/templates-core.js` (~50, zero
  imports): the two pure mappers. Acceptance: 3.1 green.
- [ ] 3.3 **RED** extend `tests/web/test_market_ux.py`: `#template-select`,
  `id="template-dialog"`, `id="template-name"` present; no inline handler;
  `templates` in `CONTROLLER_ALLOWLIST` and served as JS; `main.js` line count
  `<= 297`; seams 8/11. Acceptance: red before 3.4-3.7.
- [ ] 3.4 **GREEN** NEW `controllers/templates.js` (~170): `createTemplates({store,bus,config})`
  → `{refresh}`; GET once; Save (buildIndicators → POST, inline error inside the open
  dialog); Apply (store.set → `indicator:changed` + `layout:loaded`); Delete;
  empty-state disables the select; `aria-live` status. Acceptance: 3.3 green; ≤300.
- [ ] 3.5 **GREEN** `chart.html`: static Templates section + `<dialog>` (markup from
  design §3.1). Acceptance: markup test green.
- [ ] 3.6 **GREEN** `views.py` `CONTROLLER_ALLOWLIST` 18→19; `main.js` **exactly +2**
  (one import, one call) → **297**. Acceptance: served 200; `wc -l` = 297.
- [ ] 3.7 **GREEN** `theme.css` (+~5, tokens only); `docs/architecture/chart-modules.md`
  inventory. Acceptance: no literal colors; docs updated.
- [ ] 3.8 **REFACTOR** gates green; size guard empty allowlist green; CSP and
  `requirements.txt` and `src/` unchanged.

## Close-out (tracker → develop)

- [ ] C.1 `sdd-verify` against the spec scenarios; record each.
- [ ] C.2 Fresh adversarial review of the full tracker diff.
- [ ] C.3 **`/impeccable` UI audit — MANDATORY** (S3 ships UI) + `impeccable detect --json`.
- [ ] C.4 Merge slice PRs into the tracker, tracker → `develop`. **Do not delete a
  branch that a downstream PR still targets.**
- [ ] C.5 Archive the change, sync the delta spec.
- [ ] C.6 Update `chart-modules.md` final counts and `CHANGELOG.md`.
- [ ] C.7 Update issues **#248** and **#124** (close both if templates complete #124).
- [ ] C.8 Save Engram memory + write the handoff.

## Verification

- [ ] V.1 `node --test "tests/js/**/*.test.js"` green.
- [ ] V.2 `pytest -p no:randomly` green; `diff-cover` vs `origin/develop` = 100%.
- [ ] V.3 ruff check + format clean.
- [ ] V.4 `makemigrations --check --dry-run` clean.
- [ ] V.5 `main.js` == 297; every module ≤300; `toolbar.js`, `symbol-picker.js` untouched.
- [ ] V.6 Seams 8/11 unchanged; no new bus event; CSP + `requirements.txt` + `src/` unchanged.
- [ ] V.7 `openspec/` never staged in a code commit.

## Rollback

- **S1**: drop `0017` (table drop) and remove the model.
- **S2**: delete `templates.py` + the 2 routes.
- **S3**: revert the controller/markup/CSS/allowlist entries; the chart works without it.
- **Tracker**: drop `feat/f11-layout-templates`; the reverse migration is the only
  schema action and it is non-destructive to other tables.
