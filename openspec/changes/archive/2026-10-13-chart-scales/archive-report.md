# Archive Report: chart-scales

**Archived**: 2026-10-13
**Verdict**: `pass_with_warnings` (after the C1 CRITICAL found by verify was fixed;
0 blockers, 1 critical found-and-resolved, 15/15 requirements, 56/56 scenarios)
— new `chart-scales` capability (CS1–CS7) + `chart-config` update (R8/R9/R12: two
additive `ChartPreference` fields + partial-body PUT + the new-field isolation
requirement) + `market-chart` update (R14 store vocabulary + core inventory;
R20 envelope relaxes by exactly one bus event; new R21 host contract) +
`chart-shell` update (R25 extends to the two selects; new R26 controls)
**Delivery**: 3-slice Feature Branch Chain — PR #139 (pure core) → #140 (host +
store + UI) → #141 (persistence), all slices base on tracker `feat/chart-scales`
(#142), tracker merged to `develop` via PR #142
**Issue**: #121 (Fase F8 — Ola 2)
**Branch**: `feat/chart-scales-persistence` (HEAD `4649d4f`); tracker
`feat/chart-scales` (`11ace8c`); Slice 1 `…-core` (`0d69ebe`) + Slice 2 `…-ui`
(`1afba65`) + Slice 3 `…-persistence` (`4649d4f`); chain all → tracker

## What Shipped

Fase F8 — two user-global, persisted preferences (price-scale mode and chart type)
on the MERGED F0–F3 layered ESM chart. No new dependency, `src/` untouched, #68
single-write-path held, the frozen 8-key `window.marketChart` seam preserved.

| Area | Delivered |
|------|-----------|
| Pure core | `market/chart-types-core.js` (NEW) — imports nothing; exports frozen `CHART_TYPES` (`["candles","line","area","heikin-ashi"]`), frozen `SCALE_MODES` (`["linear","log","percentage"]`), `isLineLike`, `isValidType`, `isValidScale`, `heikinAshi`, `nextHeikinAshi`, `toChartData`. HA transform: `haClose=(o+h+l+c)/4`, `haOpen = i===0 ? (o+c)/2 : (prevHaOpen+prevHaClose)/2`, `haHigh=max(h,haOpen,haClose)`, `haLow=min(l,haOpen,haClose)`; preserves `time`, rounds nothing, never throws. |
| Store slot | `chart-store.js` `STORE_KEYS` 7→9 gains `scaleMode`, `chartType`. |
| Bus | `chart-bus.js` adds exactly one event `scale:changed` (`{mode}`, host option only); a chart-type change reuses `indicator:changed` → `rebuild()`. |
| Host apply | `chart-host.js` `build()` picks the series Ctor from `state.chartType` (`candles`/`heikin-ashi`→`CandlestickSeries`, `line`→`LineSeries`, `area`→`AreaSeries`); applies the scale after `createChart` via `priceScale("right").applyOptions({mode: symbol})` (never a magic number); `setScaleMode(mode, autoScale)` is option-only; candle write path routes through `toChartData`/`nextHeikinAshi` carrying incremental HA state (`lastHaOpen`/`lastHaClose` reset on `setCandles`). |
| UI | `controllers/toolbar.js` renders two native `<select>`s (scale mode, chart type) with accessible names, options built from `SCALE_MODES`/`CHART_TYPES`; `chart.html` labelled empty selects near Interval + `chart-types-core` modulepreload; no new controller. |
| Boot/wiring | `main.js` seeds defaults, `loadPreference` returns all 3 (fallback linear/candles) applied before first build; `scale:changed`→`host.setScaleMode` (no rebuild, no fetch); type reuses `indicator:changed`→`rebuild()`; `savePreference` debounce-PUTs only the changed key, non-fatal. |
| Persistence | `trading/models.py` + additive migration `0010_chartpreference_scale_type.py` (two `AddField`s, `CharField(max_length=16)`, defaults `linear`/`candles`); `quotes.py` `SCALE_MODES`/`CHART_TYPES` vocabularies; `views.api_preference` GET returns `{interval, scale_mode, chart_type, exists}` (defaults on miss) and PUT accepts a partial body with per-field validation → 400 (no partial write). |
| Allowlist | `views.py` `MODULE_ALLOWLIST += "chart-types-core"` (route proven). |
| Tests | `tests/js/chart-types-core.test.js` (NEW), `chart-host.test.js` (+8 incl. the C1 regression), `chart-store.test.js` (9-key), `test_market_api.py` (+9: 4-key GET, partial PUT, per-field 400, A≠B), `test_market_e2e.py` (+6: scale→`options().mode`, type→series shape, reload persists, HA smoke, 8-key seam) |

## Verify Findings

Verdict (verify-report.md) `fail` on first pass due to one CRITICAL, **resolved**
before archive → effective `pass_with_warnings`. L1: `node --test "tests/js/**/*.test.js"`
**132 passed, 0 fail**; E2E `pytest -m e2e -p no:randomly -q` **51 passed**;
`pytest tests/ --ignore=tests/web` **337 passed**; `ruff check .` + `ruff format
--check .` clean (135 files); `makemigrations --check --dry-run` "No changes
detected"; `requirements.txt` and `src/` diffs vs develop empty; migration in
diff additive only. L2: `diff-cover coverage.xml --compare-branch=feat/chart-scales
--fail-under=100` → exit 0, **100%** across 27 changed Python lines (`quotes.py`,
`views.py`, `models.py`, 0 missing). L3: all 15 requirements / 56 scenarios
verified with fresh runtime evidence; independent node HA state-machine, Django
endpoint, and real Playwright browser probes.

### C1 CRITICAL (found by verify, FIXED)

**HA live desync on repeated same-bucket pushes.** `chart-host.js updateCandle()`
selected the HA base as `bar.time === lastBarTime ? prevHa : lastHa` then
**unconditionally** advanced `prevHa = lastHa`. A live socket delivers many ticks
per candle bucket, so on the 2nd+ same-bucket replace the forming bar chained its
`haOpen` onto a stale version of itself — drifting (`11 → 11 → 11.5625`) and
**cascading** into later buckets (`bar400.open` `11.95625` vs correct `11.675`).
The committed single-tick test never reached the drift.

**Fix**: advance `prevHa = lastHa` ONLY on a genuinely new bucket
(`if (!sameBucket) prevHa = lastHa;`). **Regression test** added:
`tests/js/chart-host.test.js::"HA live is stable across MULTIPLE same-bucket ticks
(C1 regression)"` asserts `haOpen` stays `[11,11,11]` across 3 same-bucket ticks
and the next bucket chains correctly (`12.375`). **Proven red-on-old-code /
green-on-fix.** Node count 131→132.

### CI-caught gitleaks FALSE POSITIVE (allowlisted)

CI's gitleaks run flagged a false positive on `openspec/**/*.md` markdown docs
(secret-scanner pattern matching documentation prose). Resolved by adding an
`openspec/**/*.md` allowlist entry to `.gitleaks.toml`. No real secret; no code
impact.

### Warnings carried (non-blocking)

- **W1 — `chart-host.js` is 322 lines, above the R14 "≤ ~300" ceiling** (was 243
  pre-change; +82). Could extract the HA write path into a small helper to restore
  the ceiling. No functional impact.
- **W2 — repeated same-bucket HA had no committed regression test — ADDED.** The
  multi-tick test now locks the invariant so it cannot silently regress. Resolved.
- **W3 — E2E flakiness under SQLite/live-server contention (pre-existing).**
  Isolated runs intermittently raise `no such savepoint` / `database table is
  locked` (never a logic assertion). Full suite passes cleanly on re-run;
  pre-existing harness behaviour, unrelated to this change.

## Requirement Outcomes

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| chart-scales | CS1 — `chart-types-core` contract | ✅ pure/imports-nothing; exact HA recursive formula; empty/single/unknown safe; line/area `{time,value}`; served |
| chart-scales | CS2 — Price-scale mode contract | ✅ `priceScale("right").applyOptions({mode: symbol})`; no `setData`/`update`; re-applied on rebuild; unknown → linear |
| chart-scales | CS3 — Chart-type rebuild contract | ✅ Ctor per type; type change routes through `build()`/`rebuild()`; drawings/SMC re-attach; overlays/panes unchanged |
| chart-scales | CS4 — Heikin Ashi live contract | ✅ incremental state reset on `setCandles`; `update()`-only; new-bar chain; **C1 fixed** + regression test (W2 resolved) |
| chart-scales | CS5 — UI control contract | ✅ two native labelled selects; scale emits light event; type triggers rebuild; controls restore preference |
| chart-scales | CS6 — Persistence contract | ✅ round-trip persists; fetch failure falls back; only changed field sent |
| chart-scales | CS7 — Boundary, seam, no dependency | ✅ 8-key seam held; no `src/` change; no new dep; CSP unchanged |
| chart-config | R8 — User-global preference model | ✅ two additive `CharField`s + `0010`; `makemigrations --check` clean |
| chart-config | R9 — Preference API | ✅ 4-key GET; partial PUT; per-field 400 no-write |
| chart-config | R12 — Isolation and CSP for the new fields | ✅ A≠B isolation; CSP unchanged |
| market-chart | R14 — Layered ESM boundary | ✅ `chart-types-core.js` in core inventory; store vocabulary 9 keys; served; size ceiling ⚠️ **W1** (`chart-host.js` 322) |
| market-chart | R20 — Frozen host/seam envelope | ✅ 8 keys; exactly one new bus event `scale:changed`; E2E unedited green |
| market-chart | R21 — Chart type and scale host contract | ✅ Ctor from state; `setScaleMode` option-only; scale re-applied on build; rebuild preserves drawings/SMC; HA live update-only (C1 fixed) |
| chart-shell | R25 — Accessibility, CSP, no new dependency | ✅ focus + accessible names on both selects; CSP + `requirements.txt` unchanged |
| chart-shell | R26 — Scale and chart-type controls | ✅ two native selects; light scale event; type rebuild; restore preference; no new controller |
| per-user-isolation | (N/A) | ✅ No requirement change — ownership shape unchanged; `scale_mode`/`chart_type` ride on the already-owned `ChartPreference`; every read/write routes through `for_user`; no owned model, no `OWNED_MODELS` entry, no new isolation path |

R1–R7 and R10/R11 (chart-config), R1–R13 and R15–R19 (market-chart),
R20–R24 (chart-shell), and the `per-user-isolation` contract preserved untouched.

## Gates

`node --test "tests/js/**/*.test.js"` 132 passed; E2E `-m e2e -p no:randomly` 51
passed; `pytest tests/ --ignore=tests/web` 337 passed; `ruff check` + `ruff format
--check` clean (135 files); `makemigrations --check --dry-run` "No changes
detected"; `diff-cover --compare-branch=feat/chart-scales --fail-under=100` 100%
(27 changed Python lines); `requirements.txt` and `src/` diffs empty;
`window.marketChart` 8 keys.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| chart-scales | Created | New canonical spec from the change delta — CS1–CS7 (7 requirements, 28 scenarios) + edge-case matrix |
| chart-config | Updated | R8 modified (two additive fields + migration `0010` + expanded round-trip scenario); R9 modified (4-key GET + partial-body PUT + per-field 400 scenarios); R12 added (new-field isolation + CSP). R1–R7/R10/R11 preserved untouched |
| market-chart | Updated | R14 modified (`chart-types-core.js` in the pure-core inventory; store vocabulary 9 keys; new-core-served scenario); R20 modified (envelope allows exactly `scale:changed`; only-one-new-event scenario); R21 added (chart-type/scale host contract, 5 scenarios). R1–R13/R15–R19 preserved untouched |
| chart-shell | Updated | R25 modified (a11y/CSP/no-dep extends to the two selects); R26 added (scale/chart-type controls, 5 scenarios). R20–R24 preserved untouched |
| per-user-isolation | Skipped | N/A confirmed — no requirement change (delta marked N/A); ownership unchanged |

## Carry-forward

- **W1 (size ceiling) and W3 (E2E flake) remain open** — W1 is a cheap refactor
  candidate (extract the HA write path); W3 is pre-existing harness behaviour, not
  a product defect. W2 was resolved during verify (regression test added).
- **F8 completes Ola 2** of the chart-frontend roadmap. The frozen seams (layered
  module inventory, store boundary + 9-key vocabulary, bus protocol,
  `window.marketChart` 8 keys, `window.SmcOverlayCore`, the `per_user` ownership
  contract) remain in force until a new change.

## SDD Cycle Complete

Planned (explore/proposal/design/tasks) → implemented (3-slice chain PRs
#139/#140/#141 → tracker #142) → verified (C1 CRITICAL found and fixed;
`pass_with_warnings` after fix) → merged → archived.

**F8 (chart-scales) is complete — Ola 2 of the chart-frontend roadmap is done.**

Traceability: `openspec/changes/archive/2026-10-13-chart-scales/`
(explore, proposal, design, specs, tasks, verify-report); engram
`sdd/chart-scales/{archive-report,proposal,spec,design,tasks,verify-report}`.
