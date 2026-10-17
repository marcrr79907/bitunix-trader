# Archive Report: f6-measure-position

**Archived**: 2026-10-17
**Change**: `f6-measure-position` (issue #119, Fase F6)
**Verdict**: `PASS_WITH_WARNINGS` (0 blockers, **2 CRITICALs carried then
remediated**, 3 warnings W1–W3, 3 suggestions S1–S3)
**Delivery**: Feature Branch Chain, 6 PRs, all **based on the tracker**
`feat/f6-measure-position` — **#184 / #185 / #190 / #191 / #195 / #196** →
tracker **#197** → `develop` @ `32ff521`, merged.
**Branch**: `feat/f6-measure-position` (tracker) → `develop`.
**Issue**: #119 (Ola 4 / F6). Slice chain: S1 (#184) → S2 (#185) → S3+S4
(#190/#191) → UI (#195) → final (#196). All slices merged to the tracker.

## What Shipped

The two TradingView instruments the F5 substrate (`2026-10-16-f5-chart-toolbar/`)
was built to carry:

- **Measure** — an *ephemeral gesture*: press-drag-release across the chart reads
  the delta between two points (price Δ abs + %, elapsed time, bar count, candle
  count). Persists nothing: no store key, no seam key, no server call, no tree
  row. Renders on its own primitive (`autoscaleInfo` null) + a DOM `aria-live`
  readout.
- **Position** — a *persisted `Drawing.Kind.POSITION`*: a Long/Short box with
  entry / stop-loss / take-profit, a risk zone (entry→stop), a reward zone
  (entry→take_profit), three labelled levels, an R:R readout, and 4 drag handles.
  Seedable **verbatim** from the single-source SMC `setups`.

| Area | Delivered |
|------|-----------|
| `chart-measure` (NEW) | Ephemeral measure gesture, pure `measure-core.js`, DOM `aria-live` readout, Esc/tool-change/symbol-switch clear, primitive + null autoscale, no seam/store/persistence. |
| `chart-drawings` | `Kind.POSITION` + choices-only migration `0015`; `position` points schema + 400 matrix; position render (zones/levels/R:R/LONG-SHORT) with `autoscaleInfo` incl. stop/tp and **off-scale band degrade to null**; 4 handles + level/body drag; **R15** explicit SMC seed (`position-seed` controller, verbatim, works without a setup). |
| `chart-toolbar` | `TOOL_GROUPS` gains `Measure` + `Positions` groups (2/1/1/1/1/1); 2 `TOOL_LABELS` + 2 CSP-clean inline-SVG icons; activation writes `store.tool`, no new bus event. |
| `market-chart` | Inventory gains `measure-core`/`position-core`/`position-draft-core`/`readout-coalesce-core` (cores) + `measure`/`position-seed` (controllers); `CONTROLLER_ALLOWLIST` = **13**; seam stays 8 keys; `STORE_KEYS` stays 11; no `measure:*`/`position:*` event; render option-only. |
| `design-system` | Measure + position readouts are `aria-live` DOM (`#measure-readout`, `#position-readout`), **coalesced per frame** via `readout-coalesce-core.js`; Escape cancels a measure AND a pending position draft; Long/Short not color-only (label + arrow); canvas position/measure colors read **theme tokens** via `theme-core.token()` (no hard-coded literals). |

| Area | Delivered |
|------|-----------|
| Size ceiling held | `test_module_size_guard.py` green, EMPTY allowlist; `smc.js`=300 (byte-untouched), `object-tree.js`=299 (byte-untouched), `drawings.js`=281, `drawing-interaction.js`=291, `measure.js`=215, `position-core`=127, `measure-core`=67. |
| Seams held | `window.marketChart` exactly 8 keys; `STORE_KEYS` exactly 11; #68 no `setData`/`update` in the measure/position paths; CSP unchanged; `src/` + `requirements.txt` unchanged. |
| Patch coverage | `diff-cover` vs `origin/develop` = **100%** (`quotes.py`/`models.py`, 11 lines, 0 missing). |
| Migration `0015` | Choices-only `AlterField` on `kind`, deps `0014_drawing_visible_locked`; reversible, zero data loss. Chain `0012 → 0013 → 0014 → 0015`. |

## Requirements Satisfied

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| chart-measure | R1–R5 (NEW) | ✅ Ephemeral gesture, pure-core readout, null autoscale + option-only render, Esc/tool/symbol clear, a11y/CSP/size/seam. |
| chart-drawings | R1 (MODIFIED) | ✅ `position` kind + choices-only reversible `0015`; `DRAWING_KINDS` auto-includes `position`; `0012`/`0014` preserved. |
| chart-drawings | R5 (MODIFIED) | ✅ `position` `{entry:{time,price},stop,take_profit}` schema; 400 matrix incl. degenerate `entry.price==stop`; `interval` accepted-ignored. |
| chart-drawings | R6 (MODIFIED) | ✅ Position zones/levels/R:R/LONG-SHORT; `autoscaleInfo` incl. stop/tp; off-scale band → null; hidden-blank + null autoscale; off-bar degrade; drag option-only. |
| chart-drawings | R10 (MODIFIED) | ✅ 4 position handles (stop/tp/entry-price + entry anchor); level drag moves one price; body drag shifts all three; `bodyHit` = entry→stop ∪ entry→tp. |
| chart-drawings | R15 (ADDED) | ✅ Verbatim SMC seed via `#position-seed` (disabled until a setup); no JS recompute; works without a setup. |
| chart-toolbar | R1 (MODIFIED) | ✅ `Measure`+`Positions` groups (2/1/1/1/1/1), 2 labels + 2 icons; activation writes `store.tool`, no new event. R2–R5 preserved. |
| market-chart | R14 (MODIFIED) | ✅ Cores + controllers inventoried; `CONTROLLER_ALLOWLIST` = **13** (W1 reconciled); new modules served 200. |
| market-chart | R18 (MODIFIED) | ✅ 8-key seam frozen; measure asserted via DOM, position via `drawings` + captured POST/PUT. |
| market-chart | R20 (MODIFIED) | ✅ Envelope extends to measure/position; no new event; render option-only. |
| design-system | R6 (MODIFIED) | ✅ Measure/position not-color-only; readouts `aria-live` DOM (C1 remediated); Escape cancels draft (C2 remediated); readout writes coalesced per frame. |
| design-system | R9 (MODIFIED) | ✅ Position handles canvas-drawn, not-color-only; zones/strokes read theme tokens (W2/#193 remediated). |

**Compliance summary**: all 5 requirements compliant per the verify-report once
C1/C2 were remediated (see below); all scenarios compliant-or-documented.

**Preserved untouched** (no requirement dropped):
- `chart-drawings`: R2, R3, R4, R7, R8, R9, R11–R14.
- `chart-toolbar`: R2–R5.
- `market-chart`: R1–R13, R15–R17, R19, R21–R23.
- `design-system`: R1–R5, R7, R8, R10.

## Verify Findings Carried and Remediation

The verify-report (`PASS_WITH_WARNINGS`) reported **2 CRITICALs** and **3
warnings**. All were remediated in-chain (S4 / UI / final slices) — the canonical
specs reflect the DELIVERED behavior, not the original gap.

- **C1 — design-system R6 position R:R not `aria-live` DOM** (canvas `fillText`
  only). **Remediated** in the S4/UI slices: a real `#position-readout`
  `[aria-live="polite"]` node now carries the R:R figure
  (`chart.html:63`, `controllers/drawing-interaction.js:53,92`). The canvas
  `R:R` text remains supplementary. Canonical `design-system` R6 "Readouts are
  live DOM" now names `#position-readout`; `chart-drawings` R6 notes the R:R text.
- **C2 — design-system R6 Escape did not cancel a pending position draft**.
  **Remediated** in S4 (`7730b36`): `controllers/drawings.js:239-245` registers a
  `keydown` handler that cancels the draft on `Escape` via
  `position-draft-core.cancel()`; `position-draft-core.js` is the extracted state
  machine. Canonical `design-system` R6 "Escape cancels a draft" now names both
  the measure and the position-draft paths.
- **W1 — design-system R6 Long/Short tested only indirectly** (asserted
  `fillText >= 2`, not the literal strings). The render IS correct
  (`drawing-primitive.js` writes `"LONG"`/`"SHORT"` + ▲/▼). **Documented** in the
  canonical `design-system` R6 scenario (notes the render writes the label +
  arrow); coverage breadth, not logic.
- **W2 — position zone colors were hard-coded literals** (`#ef5350`/`#26a69a`).
  **Remediated** in the UI slice (`0c79cbc`): `drawing-primitive.js` now reads
  them through `theme-core.token("--dn"/"--up"/"--muted"/"--accent")` with a
  fallback literal, as does `controllers/measure.js`. Canonical `design-system`
  R9 now requires token reads via `token()` (this is the /impeccable HIGH #193).
- **W3 — chart-toolbar R1 position `store.tool` had no direct assertion**. Low
  risk (the toolbar writes `store.tool` uniformly for every kind). **Documented**
  in the canonical `chart-toolbar` R1 scenario citing the shared write path and
  the E2E POST assertion.
- **S1–S3** (measure-core zero-price baseline; `riskReward` `entry===tp` edge;
  tree header token-name assertion) — non-blocking, left as documented gaps.

## Follow-up Issues Created and Closed In-Chain

All seven were raised during verify/S4/UI and **closed within the chain**:

- **#186–#189** (S4 remediation, PRs #190/#191) — position draft Escape-cancel,
  readout/tree-select sync, non-vacuous measure E2E readiness gate, S4 wiring.
- **#192–#194** (UI slice, PR #195) — coalesced per-frame `aria-live` writes,
  theme-token reads for canvas position/measure colors, the `position-seed`
  controller split (own group/styling/seed state).

## Final Invariant State (verified on develop @ 32ff521)

| Invariant | Proof | Result |
|---|---|---|
| `window.marketChart` EXACTLY 8 keys | `main.js:57-65`; E2E `test_shell_keeps_seam_at_eight_keys` | ✅ |
| `STORE_KEYS` EXACTLY 11 | `chart-store.js:13-27`; `chart-store.test.js` | ✅ |
| Every `market/**/*.js` ≤300, empty allowlist | `test_module_size_guard.py` (ALLOWLIST `frozenset()`); `smc.js`=300, `object-tree.js`=299 byte-untouched | ✅ |
| `#68`: no `setData`/`update` writer for measure/position | E2E + `chart-controllers.test.js` stubs throw | ✅ |
| measure `autoscaleInfo` null | `measure.js`; `chart-controllers.test.js` | ✅ |
| Single-source: no JS SMC recompute | grep `find_setups|computeSetup` → NONE; seed copies `setups` verbatim | ✅ |
| Controller allowlist = **13** | `views.py:66-81`; `test_market_ux.py:146` | ✅ |
| Module allowlist incl. new cores | `views.py:44-65` (measure-core/position-core/position-draft-core/readout-coalesce-core) | ✅ |
| No inline handler/script in the diff | `test_market_page_has_no_inline_script_or_handler` | ✅ |
| `requirements.txt`/`src/` unchanged | `git diff` empty | ✅ |
| Migration `0015` choices-only + reversible | `test_migration_0015.py`; `makemigrations --check` clean | ✅ |
| Patch coverage 100% | `diff-cover` vs `origin/develop` | ✅ |

**Test gates** (from verify-report): `node --test` **306 pass / 0 fail**; `pytest`
**996 passed, 88 deselected**; `ruff check`/`format --check` clean; E2E **87/88**
(the one failure is the pre-existing class-C `#149` flake, not introduced by F6).

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| chart-measure | **Created** | Full canonical spec (R1–R5); ephemeral gesture, pure-core readout, null autoscale + option-only, Esc/tool/symbol clear, a11y/CSP/size/seam. |
| chart-drawings | Updated | R1 (`position` kind + `0015` + `DRAWING_KINDS` + `0012`/`0014` chain), R5 (`position` schema + 400 matrix + 2 scenarios), R6 (position render + autoscale + off-scale band→null), R10 (4 handles + level/body drag), R15 **appended**. R2/R3/R4/R7/R8/R9/R11–R14 preserved. |
| chart-toolbar | Updated | R1 (Measure/Positions groups 2/1/1/1/1/1, `measure` `data-kind` is not a drawing kind, 2 labels + 2 icons, activation writes `store.tool`, no new event; 3 scenarios reconciled). R2–R5 preserved. |
| market-chart | Updated | R14 (cores + controllers, `CONTROLLER_ALLOWLIST` = **13**, W1 reconciled), R18 (measure/position seam clause + scenario), R20 (envelope + 1 new-event clause + option-only scenario). R1–R13, R15–R17, R19, R21–R23 preserved. |
| design-system | Updated | R6 (measure/position a11y, `#measure-readout`/`#position-readout` `aria-live`, coalesced writes, Escape cancels draft — C1/C2 remediated), R9 (position handles tokenized + canvas colors via `token()` — W2/#193). R1–R5, R7, R8, R10 preserved. |

Delta fit: 1 capability NEW (created whole); `chart-drawings` R1/R5/R6/R10
MODIFIED + R15 ADDED; `chart-toolbar` R1 MODIFIED; `market-chart`
R14/R18/R20 MODIFIED; `design-system` R6/R9 MODIFIED. Every MODIFIED requirement
matched by name and replaced in place; R15 appended. No requirement dropped.

## Rollback (per-slice, independently revertible)

- **Final slice (#196)**: revert PR — off-scale band no longer degrades to null;
  per-move readout write restored.
- **UI slice (#195)**: revert PR — readout not coalesced; canvas colors back to
  literals; `position-seed` folded back into `drawings.js` (allowlist back to 12).
- **S3/S4 (#190/#191)**: revert PR → measure/position UI gone; position draft
  Escape-cancel / readout sync reverted.
- **S2 (#185)**: revert PR → `position` kind gone; run
  `.venv/bin/python web/manage.py migrate trading 0014` (choices-only, zero data
  loss).
- **S1 (#184)**: revert PR → the two core files are deleted; no app impact.
- **Tracker**: drop `feat/f6-measure-position`; nothing merged to `develop`/`main`
  until green.

## Bookkeeping

`tasks.md` checkboxes were reconciled to `[x]` at archive (the apply hard contract
forbids editing `openspec/**` during apply); all S1–S3 tasks and the Guard/Edge
Matrix are complete per the verify-report. S4, the UI slice, and the final slice
were remediation/add work beyond the original 3-slice task list — noted in the
tasks header and here. The change dir was UNTRACKED before this commit; the
canonical spec edits, the tasks.md update, the archive report, and the archive
move are committed together.
