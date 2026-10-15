# Archive Report: chart-theme

**Archived**: 2026-10-14
**Verdict**: `pass_with_warnings` (0 blockers, 0 criticals) — 17/17 requirements, 53/53 scenarios verified at runtime.
**Delivery**: Feature Branch Chain — PR #159 (`feat/chart-theme-engine`, S1) + PR #160 (`feat/chart-theme-persistence`, S2) → tracker PR #161 (`feat/chart-theme`) → `develop` merged. All slices base on the tracker.
**Issue**: #148 — **DEBT-7** (P3, chart canvas/shell theme coherence; fixes smc-overlay W1).
**Branch**: `feat/chart-theme-persistence` (final slice) → tracker `feat/chart-theme` → `develop`.

## What Shipped

A user-global, persisted theme (`light`/`dark`/`system`) driving BOTH the
LightweightCharts v5 canvas and the shell CSS from one resolved value. Fixes
smc-overlay W1 (white canvas on dark chrome) by making both layers theme-aware
from a single `data-theme` on `<html>`. No new dependency, CSP unchanged, `src/`
untouched, `window.marketChart` seam frozen at 8 keys.

| Area | Delivered |
|------|-----------|
| `theme-core.js` (NEW) | Pure core (imports nothing): `resolve(theme, prefersDark)` + `optionsFor(resolved)`; frozen v5 option tables; lazy `ColorType.Solid` symbol; never throws. Added to `MODULE_ALLOWLIST` + `modulepreload`. |
| `chart-host.js` (MODIFIED) | Born-themed `build()` (reads `state.theme`, merges `optionsFor` into the single `createChart`); `applyTheme(resolved)` as an option-only `chart.applyOptions` path (#68, no `setData`/rebuild). `chart-host.js` 309 → **297** lines (≤300). |
| `chart-store.js` (MODIFIED) | `STORE_KEYS` 9 → 10, adds `theme` (resolved). |
| `chart-bus.js` | **Unchanged** — no new bus event (R20); the flip routes through a `main`-injected `onTheme` callback. |
| `main.js` (MODIFIED) | Seed `theme:"system"`; `loadPreference` + `theme` (fail → `"system"`); `onTheme` → `state.theme` + `host.applyTheme` + debounced `savePreference({theme:pref})`; boot applies the resolved theme **before** the first build. |
| `controllers/toolbar.js` (MODIFIED) | Native theme `<select>` + applier: sets `document.documentElement.dataset.theme` (resolved, never `"system"`), owns the `matchMedia('(prefers-color-scheme: dark)')` `change` listener (system-only re-resolve), `setTheme(pref)` restore. No new controller (`CONTROLLER_ALLOWLIST` still 7). |
| `theme.css` (MODIFIED) | Authored `[data-theme="light"]` token block (same names as `:root`, dark stays default) + `--chart-text`/`--chart-connector` in both blocks. |
| `controllers/drawings.js`, `controllers/smc.js` (MODIFIED) | Series-color fork: drawing text from `--chart-text`; SMC swing connector from `--chart-connector` (light keeps `#616161`, dark `#8b949e`). |
| `trading/models.py` + `migrations/0011_chartpreference_theme.py` (NEW) | `theme = CharField(max_length=16, default="system")` — additive `AddField`, no data migration. |
| `quotes.py` / `views.py` (MODIFIED) | `THEMES = ("light","dark","system")`; `_preference_body`/GET-miss/nothing-to-apply gain `"theme"`; PUT adds per-field `theme` validation → 400 on invalid, no write. |
| `chart.html` (MODIFIED) | Labelled `<select id="theme">` (3 static options) + `theme-core` `modulepreload`. |
| Tests | `theme-core.test.js` (+node), `chart-host.test.js`, `chart-store.test.js`, `test_market_api.py` (+8), `test_market_e2e.py` (+7, add-only), `test_market_ux.py` (+1). |

### Chart + shell coherence

One resolved value (`"light"`/`"dark"`) drives both layers: the `data-theme`
attribute selects the CSS token block and the host paints the canvas from the
same palette. Canvas and chrome never disagree (CT2). Contrast holds both ways
(axis text vs background ≈16:1 dark / ≈15.8:1 light; grid/border ≥3:1).

## Mid-slice incident (S1 apply)

The **S1 apply subagent died with a connection error** partway through. The
**orchestrator completed S1 inline**: the contrast-color fix (grid/border to the
contrast-passing values), the host size reduction **309 → 297 lines**, and the
`MODULE_ALLOWLIST` / `modulepreload` registration. S1 was verified green before
S2 began; the chain was not restarted. Recorded for auditability of the delivery
process, not as a correctness concern.

## Requirements Satisfied (verification-evidence only)

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| chart-theme (NEW) | CT1–CT7 | ✅ Pure `resolve`/`optionsFor`; `data-theme` transport; system media-query; v5 canvas theming + contrast; option-only live toggle; persistence; 8-key seam / no-dep boundary. |
| chart-config | R8 (MODIFIED) | ✅ `theme` field added; `0011` additive `AddField(default="system")`; `makemigrations --check` clean. |
| chart-config | R9 (MODIFIED) | ✅ GET body carries `theme` (default `"system"`); partial PUT `{theme}` round-trips; invalid → 400 no write. |
| chart-config | R13 (ADDED) | ✅ `THEMES` frozen vocabulary; A≠B isolation via `for_user`; CSP unchanged. |
| chart-config | R1–R7, R10–R12 | ✅ Preserved untouched. |
| design-system | R1 (MODIFIED) | ✅ `[data-theme="light"]` block with the same token names; dark `:root` default. |
| design-system | R6 (MODIFIED) | ✅ AA contrast holds in both themes. |
| design-system | R2–R5, R7–R8 | ✅ Preserved untouched. |
| market-chart | R14 (MODIFIED) | ✅ Inventory adds `theme-core.js`; store vocabulary adds `theme`; size guard empty-allowlist, `chart-host.js` 297 ≤ 300. |
| market-chart | R20 (MODIFIED) | ✅ 8-key seam intact; no new bus event; existing E2E green unedited. |
| market-chart | R22 (ADDED) | ✅ Born-themed `build()`; option-only `setTheme`; rebuild preserves theme. |
| market-chart | R1–R13, R15–R19, R21 | ✅ Preserved untouched. |
| chart-shell | R25 (MODIFIED) | ✅ Theme control focus/name; CSP + manifest unchanged. |
| chart-shell | R27 (ADDED) | ✅ Native theme control; live flip both layers + debounced PUT; boot restore; no new controller/bus event. |
| chart-shell | R20–R24, R26 | ✅ Preserved untouched. |

**No requirement dropped.** No destructive merge — R8/R9/R14/R20/R25 replaced in place, R13/R22/R27 added, chart-theme created new. All other requirements preserved.

## Warnings Carried (non-blocking)

- **W1 — design grid-color drift — CORRECTED.** `design.md`'s originally-drafted
  frozen grid/border colors (`#2a3240` dark / `#d0d7de` light) measured
  **1.47:1 / 1.45:1**, failing the design's own ≥3:1 grid floor. The shipped
  values **`#5a6a80` (3.43:1) / `#7d8794` (3.64:1)** pass. `design.md` was
  **corrected to the shipped values**, with the failed-draft note retained so the
  rationale is visible. Spec (≥3:1) is satisfied by the shipped table.
- **W2/W3 — several spec scenarios are probe-only; the series-fork test is
  absent.** Seven spec-named scenarios (CT3 "OS change re-applies", CT4 "Drawing
  text is theme-aware", CT5 "Rebuild is born themed", CT6 "Fetch failure falls
  back to system", design-system "Tokens present in both sets" / "AA holds in the
  light theme", market-chart R22 "Rebuild preserves theme") have **no committed
  covering test** — verified only by throwaway probes (deleted). Task 2.9 (series
  fork) likewise shipped with no committed test. **Carried as test-debt**: add
  committed regression tests so these invariants cannot silently regress; the
  committed E2E for "system" re-selects rather than firing a real media change,
  so the `matchMedia` listener path carries false confidence.
- **G1 — E2E env flake (pre-existing, DEBT-8 / #149, do NOT chase).** Three WS
  tests fail locally with `KeyError: 'route'` (Playwright `route_web_socket`
  harness), identically on `develop`; CI deselects E2E. All 7 theme E2E tests
  passed in both verifier runs; the theme suite is decoupled from the WS path.
- **G3 — light-preference first-paint is briefly dark** (accepted design Open
  Question): no server-side `data-theme` / inline script under CSP. Future
  no-FOUC pass noted.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| chart-theme | Created | New canonical spec (CT1–CT7) — no prior spec; full copy of the delta. |
| chart-config | Updated | R8 modified (adds `theme` field, migration `0011`); R9 modified (body gains `theme`, per-field 400); R13 added (theme vocabulary + isolation + CSP). R1–R7, R10–R12 preserved. |
| design-system | Updated | R1 modified (light `[data-theme="light"]` block, dark default, token parity); R6 modified (AA in both themes). R2–R5, R7–R8 preserved. |
| market-chart | Updated | R14 modified (`theme-core.js` in inventory, store `theme`, host 297 ≤ 300); R20 modified (theme control in the envelope, no new bus event); R22 added (theme host contract). R1–R13, R15–R19, R21 preserved. |
| chart-shell | Updated | R25 modified (theme control focus/name/CSP); R27 added (theme control contract). R20–R24, R26 preserved. |

## Carry-forward

- **DEBT-8 (#149)** — the `route_web_socket` `KeyError: 'route'` harness issue
  remains open; local E2E WS coverage gap persists until fixed.
- **Test-debt (W2/W3)** — committed regression tests for the seven probe-only
  scenarios and the series fork (2.9) remain to be added.
- **No-FOUC pass (G3)** — light-preference first paint is briefly dark; a future
  server-side `data-theme` or equivalent would remove the flash.
- **Frozen seams** — layered ESM inventory, 8-key `window.marketChart`,
  `window.SmcOverlayCore`, #68 single-write-path, per-user ownership remain in
  force.

## SDD Cycle Complete

Planned (explore/proposal/specs/design/tasks) → implemented (chain PR #159/#160 →
tracker #161) → verified (`pass_with_warnings`, 17/17 req, 53/53 scenarios) →
merged to `develop` → archived.

Traceability: `openspec/changes/archive/2026-10-14-chart-theme/`
(explore, proposal, specs, design, tasks, verify-report, archive-report); engram
`sdd/chart-theme/{archive-report,proposal,spec,design,tasks,verify-report}`.
