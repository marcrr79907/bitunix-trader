# Archive Report: f11-layout-templates

**Change**: `f11-layout-templates` (issue **#248**, closes the second half of **#124**)
**Archived**: 2026-10-19
**Delivered on**: `develop` via PR #254 (tracker `feat/f11-layout-templates`), after a
4-PR chain (#250–#253)
**Verdict**: PASS — 5/5 requirements compliant, 0 CRITICAL, 0 blockers

## What shipped

| Slice | Delivered |
|---|---|
| B-S1 | `ChartTemplate(UserOwnedModel)` — `name` (max 40), `indicators` JSON, `created_at`, unique `(user, name)`, `Meta.ordering=["name"]`; additive migration `0017_charttemplate` |
| B-S2 | `web/market/templates.py` — `GET/POST /market/api/templates`, `DELETE /market/api/templates/<id>`, `for_user`-scoped, `parse_layout_indicators` as the single validator |
| B-S3 | `templates-core.js` (pure entry↔store mapping) + `controllers/templates.js` (select, Save-as dialog, Apply/Delete), static markup, tokens-only CSS |
| review | one HIGH finding fixed (dialog closed before an invalid name could be reported) |

## Specs synced

| Canonical spec | Action |
|---|---|
| `openspec/specs/chart-layout-templates/spec.md` | **CREATED** (5 requirements T1–T5, 22 scenarios) |

No destructive deltas. One schema addition (`0017`), additive and cleanly
reversible.

## Bugs found and fixed before merge

| Severity | Finding |
|---|---|
| **HIGH** | A whitespace-only name passes the native `required` check. Validation lived in the dialog's `close` handler, so it ran **after** the dialog closed and wrote the error to an invisible element — the exact F10 defect this code's own comment warns about. The user saw nothing happen. Moved to `submit` + `preventDefault()`, with focus returned to the input; Cancel still closes normally. Two controller tests cover it. |
| **MEDIUM (test hygiene)** | `test_migration_0016` asserted the migration leaf was *exactly* `0016`, so any later additive migration broke it. Now asserts "at least 0016". |
| **LOW** | The guard required an explicit scoping seam: `ChartTemplate.objects.create(...)` was flagged, `for_user(...).create(...)` was not. The API uses the scoped form with the owner passed explicitly (matching `ChartPreference` in `views.py:428`). |

## Process notes

- **The 400-line budget was measured, not estimated.** S1+S2 initially landed as
  one 460-line commit; split into S1 (197) / S2 (289). S3 then grew to 485 with
  the review fix, so the fix became its own review slice (134). Final:
  **S1 197 · S2 289 · S3 373 · review 134** — every slice under 400.
- **Stacked-chain merging worked this time** because no `--delete-branch` was
  passed. The first attempt at merging (#250) landed on the tracker while #251/#252
  still targeted their slice bases; the final PR was opened from the branch that
  contained the complete chain (`s3`), after verifying it was byte-identical to the
  gated tree (`git diff <verified-tree>` = 0 lines).
- **SDD artifacts were authored inline again** (the sub-agent timeout gotcha from
  the handoff); the code, gates and review were also done in-thread with direct
  evidence.

## Accepted notes

- Applying a template **overwrites** the active chart's layout. That is the stated
  intent: the template is applied to the chart you are looking at, and the previous
  layout was itself persisted per chart.
- A stored template may reference a token later removed from `REGISTRY`; the
  documented degraded-render path in `loadLayout` handles it (candles render, no
  series), and `templates-core.js` keeps the token verbatim instead of throwing.

## Follow-ups

None required. `#124` closes with this change. The remaining roadmap item is
`chore: railway.json → IaC` (#54, deadline 2026-12-01).
