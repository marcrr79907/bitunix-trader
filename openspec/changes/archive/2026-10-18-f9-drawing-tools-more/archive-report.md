# Archive Report: f9-drawing-tools-more

**Archived**: 2026-10-18
**Change**: `f9-drawing-tools-more` (issue #122, Fase F9)
**Verdict**: `PASS_WITH_WARNINGS` (0 blockers, **1 CRITICAL C1 resolved in-chain**,
2 warnings, 3 suggestions)
**Delivery**: Feature Branch Chain — **#212 / #213 / #214 / #215** on the tracker
`feat/f9-drawing-tools-more`, plus the fix slice **#218**, the `/impeccable
needs-rework` remediation slices **#224 (R1) / #225 (R2)**, then tracker **#226**
→ `develop` @ **0757be4**, merged.
**Base**: `develop` @ `1150b07`. Verify ran on the tracker tip `729612a` (S3b);
the R1/R2 rework slices landed after.

## What Shipped

The eight TradingView-parity drawing kinds the F5/F6/F7 substrate was built to
carry, over the SAME persistence / render / interaction stack — each a new
geometry, not a new subsystem.

- **Persistence** — `Drawing.Kind` gains `RAY`/`VLINE`/`CHANNEL`/`PRICE`/
  `CALLOUT`/`FIB_EXT`/`FIB_TIME`/`FIB_ZONE` (`web/trading/models.py`), widened by
  ONE choices-only `AlterField` migration `0016_drawing_kind_tools` (deps `0015`,
  no column, no row, reversible to `0015`). `parse_drawing` gains one branch per
  kind, so a valid payload is 201 and a malformed one 400s before any write.
- **Three pure cores** — `drawing-tools-core.js` (one descriptor per kind:
  clicks/style/path/handles/bodyHit/drag, per-kind `--draw-*` token, delegates fib
  geometry), `fib-tools-core.js` (`FIB_EXT_RATIOS` + fib extension/time/zone
  math), `drawing-click-flow-core.js` (ONE 1/2/3-click machine replacing the
  ad-hoc `pendingAnchor`/`positionDraft` pair, plus `peek`/`previewRow` for the
  draft preview).
- **Render** — `drawing-primitive.js` gains ONE `Tools.NEW_KINDS` guard and
  `priceRangeFor` includes `p3`; the eight-kind canvas switch lives in
  `tool-render-core.js` (ray extends to the live pane edge, callout balloon +
  arrowhead, right-axis price tag via `priceFormatter()`, fib labels with one
  shared font + `--bg` halo, off-bar x legs skipped for `fib_ext`/`fib_zone`).
- **Interaction** — `drawing-interaction-core.js` gains ONE guard in each of
  `handlesFor`/`bodyHit`/`applyDrag`; counts are ray 2 / callout 2 / fib_time 2 /
  fib_zone 2 / channel 3 / fib_ext 3 / vline 1 / price 1; anchor drags move only
  the grabbed anchor, body drags translate all.
- **Toolbar** — 15 instruments in 6 groups (`6/4/1/2/1/1`), eight new CSP-clean
  SVG icons, non-colliding letters `A/I/C/U/O/E/W/Z`, human `TOOL_LABELS` names
  feeding both the toolbar `aria-label`/`title` and the object-tree row labels,
  and the `#chart`-scoped letter router extended to the new set.
- **Draft feedback** — a pending 2/3-click draft renders on a transient preview
  primitive (never POSTed, excluded from autoscale) and `#chart` shows a
  crosshair while a tool is active.

| Area | Delivered |
|------|-----------|
| `chart-drawings` | R1 `Kind` +8 + reversible choices-only `0016`; R4/R5 per-kind `parse_drawing` branches + the 400 matrix; R6 render for all eight kinds (ray edge, vline, parallel channel, labelled/formatted price, callout balloon, fib ext/time/zone, per-kind `--draw-*` tokens, off-bar skip, shared label font + halo); R10 per-kind handles/drag (2/2/2/2/3/3/1/1). R2/R8/R15 and R3/R7/R9/R11–R14 preserved. |
| `chart-toolbar` | R1 15 tools in 6 groups with 8 new icons + non-colliding letters + human names/titles; R3 letter router extended and still `#chart`-scoped (inside fires, outside does nothing). R2/R4/R5 preserved. |
| `market-chart` | R14 inventory gains `drawing-tools-core`/`fib-tools-core`/`drawing-click-flow-core`/`tool-render-core`/`object-tree-dom-core` + `controllers/draft-preview`; `MODULE_ALLOWLIST` = **28**, `CONTROLLER_ALLOWLIST` = **16**; `drawings.js` 298→282, `object-tree.js` 299→263, `smc.js` byte-untouched. R18/R20: seam 8 keys, `STORE_KEYS` 11, no new bus event, F9 render option-only. |
| `design-system` | R6 per-kind not-color-only (formatted price label, callout balloon+arrow, fib ratio labels), human tool labels, draft preview + crosshair; R9 per-kind `--draw-*` palette via `theme-core.token` in BOTH theme sets (light strokes ≥3:1, labels ≥4.5:1), one label font + `--bg` halo. R1–R5/R7/R8/R10 preserved. |

| Area | Held |
|------|------|
| Size ceiling | `test_module_size_guard.py` green, EMPTY allowlist; `smc.js`=300 (byte-untouched, pre-existing), `drawings.js`=282, `drawing-interaction.js`=291 (byte-untouched), `drawing-tools-core.js`=284, `drawing-interaction-core.js`=285, `drawing-primitive.js`=196, `draft-preview.js`=44, `object-tree-dom-core.js`=41, `tool-render-core.js`=117, `fib-tools-core.js`=109, `drawing-click-flow-core.js`=91. |
| Seams held | `window.marketChart` exactly 8 keys, `STORE_KEYS` exactly 11, no new `EVENTS` member, #68 (create only via `createDrawing`), CSP unchanged, `src/` + `requirements.txt` unchanged, no new dependency/build. |
| Read-only | no order/execution path touched; SMC internals unchanged. |

## Requirements Satisfied

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| chart-drawings | R1/R4/R5/R6/R10 (MODIFIED) | ✅ 8 kinds persisted, validated, rendered, drag-able. R2/R3/R7/R8/R9/R11–R15 preserved. |
| chart-toolbar | R1/R3 (MODIFIED) | ✅ 15 tools, 8 icons, 8 non-colliding letters, `#chart`-scoped router. R2/R4/R5 preserved. |
| market-chart | R14/R18/R20 (MODIFIED) | ✅ Inventory + allowlists reconciled to the delivered `28`/`16`; seam 8, store 11, no new event. R1–R13, R15–R17, R19, R21–R23 preserved. |
| design-system | R6/R9 (MODIFIED) | ✅ Per-kind palette in both themes, not-color-only labels, human names, draft preview, crosshair, shared label font + halo. R1–R5, R7, R8, R10 preserved. |

**Compliance summary**: 67/69 scenarios fully compliant at verify; 1 PARTIAL
(chart-drawings R6 off-bar anchor) and 1 MISSING/CRITICAL (market-chart R20 F9
option-only coverage). **Both were resolved in-chain** (see below); the canonical
specs reflect DELIVERED behavior.

**Preserved untouched** (no requirement dropped):
- `chart-drawings`: R2, R3, R7, R8, R9, R11–R15.
- `chart-toolbar`: R2, R4, R5.
- `market-chart`: R1–R13, R15–R17, R19, R21–R23.
- `design-system`: R1–R5, R7, R8, R10.

## Verify Findings Carried and Remediation

The verify-report (`PASS_WITH_WARNINGS`) reported **1 CRITICAL** and **2
warnings**. Both the CRITICAL and W1 were remediated in-chain; the specs record
the delivered state.

- **C1 — `market-chart` R20 "F9 render is option-only" had no covering test.** The
  delivered E2E asserted the ONE POST / ONE PUT write counts but never installed
  the `setData`/`update` spies for an F9 gesture. **Remediated** in the fix slice
  (#218, `f18e58d`): `drawing-primitive.test.js::an F9 primitive never calls
  setData/update (option-only, #68/#217)` drives every F9 kind against throwing
  stubs and asserts a single `requestUpdate`. Production code was already clean
  (`drawings.js` contains no writer call).
- **W1 — `fib_ext`/`fib_zone` coerced a null x leg to pixel 0** instead of
  skipping it. **Remediated** in #218 (`f18e58d`): both skip the whole body when
  an x anchor is off-bar, and `fib_zone` skips a band whose level is off-scale,
  with three non-vacuous node tests. The canonical R6 records the skip clause.
- **W2 — `diff-cover` could not be executed** (binary absent from the venv). The
  proxy is `quotes.py` 100% line coverage plus the forward/reverse
  `test_migration_0016.py`; **documented gap**, no code impact.
- **S1** (`tasks.md` unticked), **S2** (a `debug` comment said "right-axis tag"
  while the label sat at `x=2`) and **S3** (an F9 handle index could resolve
  across a pan mid-drag) were non-blocking. S1 is closed by this archive
  reconciliation; S2's label position and formatting were reworked in R1/R2
  (`ea8161c`).

## `/impeccable needs-rework` → R1/R2 Remediation

The `/impeccable` review of the merged feature returned **needs-rework**. Two
remediation slices followed, each its own PR into the tracker:

**R1 (#224)** — render/geometry/a11y:
- **#219** `fd9226c` — a ray rendered exactly like a trendline because the pure
  geometry had no canvas width. `renderShape` now refreshes `map.right` from the
  media size every draw (core stays pure); ray extends to the pane edge.
- **#220** `c24bdd8` — `fib_ext` drew only `p1..p2` while `p3` was a live handle
  feeding autoscale, so dragging `p3` changed nothing. The x extent now runs
  `p1..p3` (falling back to `p2`).
- **#221** `1a76849` — the eight kinds used hard-coded literals; `callout`'s
  `#e6edf3` was 1.18:1 on the white canvas. Each kind now reads its own
  `--draw-*` token, declared in BOTH theme sets (light ≥3:1 strokes, ≥4.5:1
  labels), resolved at read time so a theme flip repaints.

**R2 (#225)** — feedback/labels/modularity:
- **#222** `1a9d7de` + `bfb4e78` — a 2/3-click draft drew nothing until the final
  click. The flow exposes `peek`/`previewRow`; `controllers/draft-preview.js`
  attaches ONE transient preview primitive (never POSTed, `autoscaleInfo` null so
  the axis does not jump), and `#chart` shows a crosshair while a tool is active.
- **#223** `ea8161c` + `4afab32` — callout draws a rounded balloon + arrowhead;
  the price tag moves to the right edge and uses the series formatter; labels
  share one `LABEL_FONT` with a `--bg` halo. One `TOOL_LABELS` map now feeds the
  toolbar `aria-label`/`title`, the group captions, and the object-tree row names,
  so a slug (`fib_ext`) never reaches the user.
- Ceiling-forced extractions (no behavior change): `e47130d` moved the F9 canvas
  renderer to `tool-render-core.js` (`drawing-primitive` 300→196), `11cef54` moved
  the draft preview to `controllers/draft-preview.js`, `a0152b1` moved the tree's
  row-DOM factories to `object-tree-dom-core.js` (`object-tree` 299→263), and
  `6a2f27b` allowlisted + preloaded the three new modules.

## Follow-up Issues Created and Closed In-Chain

The verify report and the `/impeccable` review raised the follow-up issues
**#216–#223** (7 issues; #218 is the fix PR); **every one is closed within the
chain**:

| Issue | Slice / PR | Fix |
|-------|-----------|-----|
| #216 | fix slice · PR #218 | off-bar `fib_ext`/`fib_zone` legs no longer paint at pixel 0 |
| #217 | fix slice · PR #218 | F9 option-only contract now has a throwing-stub test |
| #219 | R1 · PR #224 | ray extends to the canvas edge |
| #220 | R1 · PR #224 | `fib_ext` bounded by `p3`; dragging `p3` is visible |
| #221 | R1 · PR #224 | per-kind `--draw-*` palette (light/dark a11y) |
| #222 | R2 · PR #225 | pending draft preview + crosshair, out of autoscale |
| #223 | R2 · PR #225 | callout balloon+arrow, formatted right-axis price, human labels, clearer icons, label font + halo |

## Final Invariant State (verified on develop @ 0757be4)

| Invariant | Proof | Result |
|---|---|---|
| `window.marketChart` EXACTLY 8 keys | `main.js` untouched; E2E `test_shell_keeps_seam_at_eight_keys` (11 assertions) | ✅ |
| `STORE_KEYS` EXACTLY 11 | `chart-store.js` untouched; `chart-store.test.js` | ✅ |
| Every `market/**/*.js` ≤300, empty allowlist | `test_module_size_guard.py` (`ALLOWLIST=frozenset()`); `smc.js`=300 byte-untouched, `drawings.js`=282, `object-tree.js`=263 | ✅ |
| #68: no `setData`/`update` writer for F9 | `drawings.js` has zero writer calls; `drawing-primitive.test.js` throwing-stub test (#217) | ✅ |
| `CONTROLLER_ALLOWLIST` = **16** | `views.py:76-95`; `test_market_ux.py:146,195` | ✅ |
| `MODULE_ALLOWLIST` = **28** incl. the five F9 cores | `views.py:44-75`; `test_f9_cores_are_served` (200 each) | ✅ |
| No new `EVENTS` member | `chart-bus.js` byte-untouched; F9 uses the `drawing:created` literal | ✅ |
| Migration chain `…→0015→0016`, `makemigrations --check` green | `test_migration_0016.py` forward/reverse; `--check --dry-run` | ✅ |
| CSP / `requirements.txt` / `src/` unchanged | `middleware.py` untouched; `test_csp_present_on_market_page`; `git diff` empty | ✅ |
| No inline handler/script | `test_market_page_has_no_inline_script_or_handler`; icons are plain strings | ✅ |

**Test gates** (from verify-report, tracker `729612a`): `node --test` **486/486**;
`pytest -m 'not e2e'` **1048 passed, 101 deselected**; `ruff check`/`format
--check` clean; E2E **100/101** (the one failure is the pre-existing class-C
`#149` flake, rotating across untouched tests and green in isolation; F9 subset
`-k f9` 2/2). Re-run at archive on `develop` @ `0757be4`: `node --test` **522
pass / 0 fail** (the suite grew with the R1/R2 tests).

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| chart-drawings | Updated | R1 (+8 kinds + `0016` + 3 scenarios), R4 (+`parse_drawing` F9 branches + matrix scenario), R5 (+per-kind F9 schemas + 5 scenarios), R6 (+F9 render contract + ray-edge/token/off-bar scenarios), R10 (+F9 handles/drag + 3 scenarios). R2/R3/R7/R8/R9/R11–R15 preserved. |
| chart-toolbar | Updated | R1 (15 tools, `6/4/1/2/1/1`, 8 icons/letters, human labels, 3 F9 scenarios), R3 (letter set extended, F9 letter scenario, `#chart`-scoping kept). R2/R4/R5 preserved. |
| market-chart | Updated | R14 (5 new cores + `draft-preview`, `MODULE_ALLOWLIST`=28, `CONTROLLER_ALLOWLIST`=16, `object-tree` shrink, reconciliation note), R18 (F9 seam clause + scenario), R20 (F9 envelope/clauses + `STORE_KEYS` + option-only scenario). R1–R13, R15–R17, R19, R21–R23 preserved. |
| design-system | Updated | R6 (F9 not-color-only + human labels + draft preview + crosshair, 2 scenarios), R9 (per-kind `--draw-*` palette in both sets + shared label font/halo, 2 scenarios). R1–R5, R7, R8, R10 preserved. |

Every MODIFIED requirement matched by name and replaced in place. No requirement
dropped.

## Rollback (per-slice, independently revertible)

- **#225 (R2)**: revert PR — draft preview, crosshair, callout balloon, formatted
  price, human labels and the label font/halo revert; the three extracted modules
  are deleted; `drawings.js`/`object-tree.js` regain their inline helpers.
- **#224 (R1)**: revert PR — rays stop at `p2`, `fib_ext` ignores `p3`, and the F9
  palette falls back to the dark literals (light-theme contrast regresses).
- **#218 (fix)**: revert PR — off-bar `fib_ext`/`fib_zone` legs paint at pixel 0
  again and the F9 option-only test disappears.
- **#215 (S3b)**: revert PR — E2E F9 coverage and the preload/serve check revert.
- **#214 (S3)**: revert PR — dispatch, toolbar, click-flow extraction and the
  allowlist entries revert; `drawings.js` restores its 2-click flow.
- **#213 (S2)**: revert PR — drop the 8 `parse_drawing` branches and `0016`;
  `manage.py migrate trading 0015_drawing_kind_position` restores prior choices
  (zero data loss).
- **#212 (S1)**: revert PR — the three pure cores are deleted; no app impact.
- **Tracker**: drop `feat/f9-drawing-tools-more`; nothing merged to `main`.

## Known State / Fragility

- `controllers/smc.js` = **300** — at the ceiling, PRE-EXISTING and byte-untouched
  by F9; one edit away from tripping the empty-allowlist guard.
- `controllers/drawing-interaction.js` = **291** (byte-untouched).
- `drawing-interaction-core.js` = 285, `drawing-tools-core.js` = 284,
  `drawings.js` = 282 — the tightest touched modules (~15–18 lines of headroom).
- Every other market module is ≤274.
- The E2E class-C flake (#149) is pre-existing and unrelated; the default suite
  excludes E2E.

## Bookkeeping

`tasks.md` checkboxes were reconciled to `[x]` at archive (the apply hard contract
forbids editing `openspec/**` during apply), with a header note recording the S3b
and R1/R2 slices beyond the original 3-slice plan and the fact that
`CONTROLLER_ALLOWLIST` grew to 16 rather than staying unchanged. The change dir
was UNTRACKED before this commit; the canonical spec edits, the `tasks.md` update,
this archive report, and the archive move are committed together. `cov.xml` is
gitignored and was not added.
