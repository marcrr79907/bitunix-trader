# Archive Report: chart-indicator-settings

**Archived**: 2026-10-13
**Verdict**: `pass_with_warnings` (0 blockers, 0 critical, 16/16 requirements, 45/49 scenarios compliant, 4 partial) — new `chart-indicator-settings` capability (F2.1–F2.9, 9 requirements) + `chart-config` update (R1/R2/R5: `style` preserved, validated, round-trips verbatim — the server-drop bug fix) + `market-chart` update (R14 store `styles` slot + core inventory; R17 style on the rebuild path) + `chart-legend` clarification (LC1/LC2: style `precision` feeds the series `priceFormat` only, `DECIMALS` frozen)
**Delivery**: 2-slice Feature Branch Chain — PR #136 (core + persistence) → #137 (dialog UI + E2E), all slices base on tracker `feat/chart-indicator-settings`, tracker merged to `develop` via PR #138
**Issue**: #115 (Fase F2 — Ola 2)
**Branch**: `feat/chart-indicator-settings-ui` (HEAD `2055c61`); tracker `feat/chart-indicator-settings` (tip `e64c8f2` = merge of S1); Slice 1 `cbca97c` + fix `d62f509`; chain all→tracker

## What Shipped

Fase F2 — a per-indicator settings panel (TradingView-style gear + accessible
`<dialog>`) to edit **color, line width, period and precision**, persisted
additively on `ChartLayout.indicators[].style` (JSONField, **no migration**) and
re-rendered through the existing config-change → `rebuild()` path (#68 preserved).
No new dependency, CSP strict, `src/` untouched.

| Area | Delivered |
|------|-----------|
| Pure core | `market/indicator-settings-core.js` (NEW) — imports nothing; exports exactly `FIELDS`, `TOKENS`, `defaultsFor`, `normalize`, `validate`; `clamp` internal. Never throws; drops unknown keys, clamps out-of-range, falls back on malformed color; `defaultsFor(registry, token)` derives color from the injected registry (single color source, no hardcoded color) |
| Store slot | `chart-store.js` `STORE_KEYS` 6→7 gains top-level `styles` (`{token: style}`), never under `params` — so `history.klineUrlFrom` cannot leak style into `/market/api/kline` |
| Host apply | `chart-host.js` `build(state)` reads `state.styles[token]` (REGISTRY fallback) → `addSeries(Ctor, {color, lineWidth}, idx)` + `applyOptions({priceFormat: {precision, minMove}})` |
| **Server fix (the bug)** | `quotes.parse_layout_indicators` previously rebuilt each entry as `{"token"}` + `params` and **silently dropped `style`**; now it preserves + validates `style` via new `_validate_layout_style(token, style)` (whitelists `color` `#rrggbb`, `lineWidth` 1..4, `precision` 0..8; unknown key/bad shape → `ValueError` → 400 before write), stored verbatim (no defaults injected). **Only Python change** → 100% patch coverage |
| Gear + dialog | `controllers/indicators.js` (261 lines) — `button.indicator-settings[data-token][aria-haspopup=dialog]` per token; shared `<dialog id="indicator-settings-dialog">` with labelled color/width/period/precision inputs; apply-on-confirm (one `indicator:changed` + one `saveLayout()`); `buildIndicators(..., styles)` emits `style`; `loadLayout` reads `indicators[].style` into `state.styles` |
| Markup/CSS | `chart.html` gear buttons + dialog + `modulepreload` core; `theme.css` gear/dialog styling (visible focus, no horizontal overflow at 375px); no inline script/handler |
| Allowlist | `views.py` `MODULE_ALLOWLIST += "indicator-settings-core"` (route proven) |
| Migration | **NONE** — additive JSONField key; `makemigrations --check` "No changes detected" |
| Tests | `tests/js/indicator-settings-core.test.js` (NEW, 13), `chart-store.test.js` (7-key), `chart-host.test.js`, `test_market_api.py` (style round-trip + 9 reject variants), `test_market_e2e.py` (+6 DOM/E2E) |

### Migration-free

The change is fully **migration-FREE**: `style` rides inside the existing
`ChartLayout.indicators` JSONField, so ownership, `OWNED_MODELS`, the model, and
the schema are unchanged. `makemigrations --check --dry-run` is green. Stray
`style` keys are ignored by the reverted parser — no data loss.

## Verify Findings

Verdict `pass_with_warnings` (verify-report.md). L1: `node --test "tests/js/**/*.test.js"`
**104 passed, 0 fail**; E2E `pytest -m e2e -p no:randomly -q` **42 passed**;
`pytest tests/ --ignore=tests/web` **337 passed**; `ruff check .` + `ruff format
--check .` clean (134 files); `makemigrations --check --dry-run` "No changes
detected"; `manage.py check` no issues; `requirements.txt`, `src/` and migrations
diffs vs develop empty. L2: `diff-cover coverage.xml --compare-branch=origin/develop
--fail-under=100` → exit 0, **100%** across 18 changed Python lines (`quotes.py`,
0 missing). L3: all 16 requirements / 45 of 49 scenarios have passing runtime
coverage; independent Django-client, node and real-browser Playwright probes
reproduced the style round-trip (verbatim, 400 on bad shape, no write), the exact
`Number("1e-"+n)` `minMove`, store/params separation (no kline leak), one-rebuild
via `indicator:changed`, the frozen 8-key seam, persist-across-reload and 375px
safety with **0 page errors**.

### CI-caught float bug (durable lesson)

The first implementation used `Math.pow(10, -precision)` for the series
`priceFormat.minMove`. On CI it produced a `minMove` that did not equal the
literal `1e-5` constant the E2E asserted — because `Math.pow` is implemented via
`exp(log(x))` and its last-bit result is **V8-version-dependent**. Fixed by using
`Number("1e-" + n)`, which is a **language guarantee** (`Number("1e-5") === 0.00001`
regardless of V8 build), verified exact for n=0..8. `chart-host.js` now contains
no `Math.pow(10,` for `minMove`. This is the kind of defect only a real CI run
catches; keep it in mind for any future precision/rounding seam.

### Warnings carried (non-blocking)

- **W1 — F2.6 "empty required fields block submit" — FIXED.** The verify pass found that a *cleared* control closed the dialog and persisted the default (valid, but the literal "dialog stays open" was unmet) with no committed test. Resolved by adding `required` to the four dialog inputs plus the committed regression test `test_empty_required_field_blocks_submit`. The scenario now has runtime coverage.
- **W2 — F2.5 "one rebuild per style change (#68)" is probe-only.** Compliant by construction (one `indicator:changed` emit, one `rebuild` listener) and the series visibly rebuilds, but no committed count test fails if a future edit double-emits.
- **W3 — LC1 "style precision does not change the legend" proven by static evidence only.** `legend.js`/`legend-core.js` never read `styles`/`priceFormat` and `DECIMALS` is frozen (covered), but no committed test asserts legend output is unchanged when `styles.sma.precision` differs.
- **W4 — R14 "size ceiling" (~300 lines) checked statically, not by a test.** All modules comply (max 298; new core 86).
- **W5 — F2.9 style-specific A≠B is inherited/probe-proven.** `test_layout_isolation_b_get_never_sees_a` proves layout isolation; the style-specific case (B never sees A's style) was reproduced by probe. Extending the isolation test to assert `style` absence would close it.

## Requirement Outcomes

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| chart-indicator-settings | F2.1 — Pure settings core contract | ✅ exports exact; imports nothing; `defaultsFor` unknown-token safe; no hardcoded color |
| chart-indicator-settings | F2.2 — normalize (clamp/defaults/drop unknowns) | ✅ round-trip, clamp (`99→4`, `-3→0`), unknown-key drop, never-throw |
| chart-indicator-settings | F2.3 — validate contract | ✅ names each offender; valid passes |
| chart-indicator-settings | F2.4 — Style store slot | ✅ `STORE_KEYS` 7 incl. `styles`; no kline leak; no candles |
| chart-indicator-settings | F2.5 — Host apply contract | ✅ color/lineWidth at construct; `priceFormat` precision; registry fallback; rebuild path (#68); **W2** count test probe-only |
| chart-indicator-settings | F2.6 — Gear and settings dialog | ✅ gear→dialog prefill; confirm applies once + persists; cancel no change; empty-required blocks submit (**W1 fixed**, committed test) |
| chart-indicator-settings | F2.7 — Persistence round-trip + validation | ✅ PUT→GET verbatim; bad style → 400 no write |
| chart-indicator-settings | F2.8 — Accessibility, CSP, no new dep | ✅ keyboard (Enter/Esc, focus returns); labelled inputs; CSP + `requirements.txt` unchanged; 375px no overflow |
| chart-indicator-settings | F2.9 — Scope and isolation | ✅ per-`(user,symbol,interval)`; style A≠B (probe-only, **W5**) |
| chart-config | R1 — Per-user layout persistence | ✅ `indicators[].style` optional `{color,lineWidth,precision}`; JSON round-trip preserves style; additive/no migration |
| chart-config | R2 — Layout API | ✅ parser preserves + validates `style`; invalid style → 400 before write; parser is the sole drop point (bug fixed) |
| chart-config | R5 — Save on change | ✅ confirming a style debounce-saves; PUT body carries `style` |
| market-chart | R14 — Layered ESM boundary | ✅ `styles` in store vocabulary (7); `indicator-settings-core.js` in the pure-core inventory; served (allowlist); size ceiling static (**W4**) |
| market-chart | R17 — Preserved behavior invariants | ✅ style uses `indicator:changed` → `rebuild()`; no second `setData` writer; no kline leak; `DECIMALS` untouched |
| chart-legend | LC1 — legend-core formatter contract | ✅ `DECIMALS` static/frozen; style precision does not change legend output (static, **W3**) |
| chart-legend | LC2 — Single-source, no recompute | ✅ no style dependency (static, **W3**) |
| per-user-isolation | (N/A) | ✅ No requirement change — ownership shape unchanged; `style` rides inside `ChartLayout`; every read/write still routes through `for_user`; no owned model, no `OWNED_MODELS` entry, no migration |

R3/R4/R6/R7 (chart-config), LC3–LC6 (chart-legend), R1–R13 and R15/R16/R18–R20
(market-chart) and the `per-user-isolation` contract preserved untouched.

## Gates

`node --test "tests/js/**/*.test.js"` 104 passed; E2E `-m e2e -p no:randomly` 42
passed; `pytest tests/ --ignore=tests/web` 337 passed; `ruff check` + `ruff format
--check` clean (134 files); `makemigrations --check --dry-run` "No changes
detected"; `manage.py check` no issues; `diff-cover --compare-branch=origin/develop
--fail-under=100` 100% (18 changed Python lines); `requirements.txt`, `src/` and
migrations diffs empty; `window.marketChart` 8 keys.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| chart-indicator-settings | Created | New canonical spec from the change delta — F2.1–F2.9 (9 requirements, 25 scenarios) + edge-case matrix + non-applicable domains |
| chart-config | Updated | R1 modified (optional `indicators[].style` + JSON round-trip scenario + additive-migration scenario); R2 modified (parser preserves/validates `style`; invalid-style scenario; parser-sole-drop-point scenario); R5 modified (style confirm saves; style-in-payload scenario). R3/R4/R6/R7 preserved untouched |
| market-chart | Updated | R14 modified (`styles` in store vocabulary 7 keys; `indicator-settings-core.js` in the pure-core inventory; store-never-holds-candles + new-modules-served scenarios updated); R17 modified (style on the rebuild path; style-never-leaks scenario). R1–R13/R15/R16/R18–R20 preserved untouched |
| chart-legend | Updated | LC1 modified (DECIMALS frozen / style precision must not change legend output; style-precision + static-frozen scenarios); LC2 modified (no style dependency; no-style-dependency scenario). LC3–LC6 preserved untouched |
| per-user-isolation | Skipped | N/A confirmed — no requirement change (delta marked N/A); ownership unchanged |

## Carry-forward

- **W2–W5 are cheap test-debt items** (one rebuild-count E2E, one legend-precision test, one size-ceiling test, one style-specific isolation assertion) — candidates for a small F2 follow-up or a test-debt pass.
- **F2 completes part of Ola 2** of the chart-frontend roadmap. The frozen seams (layered module inventory, store boundary + 7-key vocabulary, bus protocol, `window.marketChart` 8 keys, `window.SmcOverlayCore`, the `per_user` ownership contract) remain in force until a new change.

## SDD Cycle Complete

Planned (explore/proposal/design/tasks) → implemented (2-slice chain PRs
#136/#137 → tracker #138) → verified (`pass_with_warnings`; no CRITICAL/BLOCKER)
→ merged → archived.

**F2 (chart-indicator-settings) is complete — part of Ola 2 of the chart-frontend
roadmap.**

Traceability: `openspec/changes/archive/2026-10-13-chart-indicator-settings/`
(explore, proposal, design, specs, tasks, verify-report); engram
`sdd/chart-indicator-settings/{archive-report,proposal,spec,design,tasks,verify-report}`.
