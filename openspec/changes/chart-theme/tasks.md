# Tasks: chart-theme (issue #148, DEBT-7 — P3)

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

All slice PRs base on the tracker `feat/chart-theme`; merge each slice into the
tracker before branching the next. Base boundaries: PR1 base = tracker; PR2 base =
PR1 branch (retarget/rebase if a child diff shows Slice 1). Strict TDD
(`node --test` + `pytest` + Playwright E2E). Read-only: no `src/`, no new dep, CSP
unchanged, `window.marketChart` stays 8 keys, `window.SmcOverlayCore` untouched.
Python touched only by `views.py` (allowlist + pref API), `quotes.py`, `models.py`,
migration `0011`, tests.

## Guard/Edge Matrix

- [ ] **Option-only #68**: `setTheme(resolved)` = `chart.applyOptions(optionsFor(resolved))` only; no `setData`/`update`/rebuild/refetch; test asserts the series call count is unchanged.
- [ ] **Born themed**: `build(state)` reads `state.theme` inside the single `createChart` options; every rebuild carries the theme, no re-apply.
- [ ] **`ColorType.Solid` symbol**: never a magic number; host stub uses a non-standard `Solid` value so a numeric impl fails (mirrors `PriceScaleMode`).
- [ ] **8-key seam**: nothing added to `window.marketChart`; theme lives in `state.theme` + `data-theme`; E2E `test_shell_keeps_seam_at_eight_keys` stays green.
- [ ] **Migration additive**: `0011` = `AddField(default="system")` only; `makemigrations --check` green; no data migration.
- [ ] **Host ≤300**: `chart-host.js` 286/300; additions ≤~14 lines (import 1, `createChart` merge ~5, `setTheme` ~5); option tables live in `theme-core`; size guard enforces.
- [ ] **`data-theme` = resolved**: never `"system"`; explicit pref ignores the OS; `matchMedia` `change` re-applies only while pref==`"system"`.
- [ ] **No-deps/CSP**: pure core + native `<select>`; `getComputedStyle`/`matchMedia`/dataset same-origin ESM; `requirements.txt` + CSP unchanged; `CONTROLLER_ALLOWLIST` count stays 7.
- [ ] **Patch 100%**: every branch (unknown→dark, system fallback, 400, fetch fail) covered by a committed test.
- [ ] **Contrast ≥4.5:1**: axis text vs background both sets; grid/border/connector ≥3:1; drawing text from `--chart-text`.
- [ ] **WS E2E flake (DEBT-8)**: theme E2E decoupled from the WS path; run `-p no:randomly` on an idle machine.

## Slice 1 — Theme engine + host canvas (PR1)

Base tracker; branch `feat/chart-theme-core`; deps none. Rollback: delete
`theme-core.js` + allowlist/preload + doc row, host back to v5 defaults; chart
renders unthemed. ~175 lines.

- [ ] 1.1 **RED** `tests/js/theme-core.test.js`: `resolve` pass-through/system/unknown/no-throw; `optionsFor` exact `{layout,grid,crosshair,rightPriceScale,timeScale}` shape, `layout.background` is `{type,color}` object, both sets, unknown→dark; `contrastRatio` helper asserts axis ≥4.5:1 both, grid/border/connector ≥3:1; no-import. Acceptance: fails pre-1.2.
- [ ] 1.2 **GREEN** `market/templates/market/theme-core.js`: export `resolve(theme,prefersDark)` + `optionsFor(resolved)`; frozen tables (§ design); `solidColorType()` lazy-symbol w/ `"solid"` fallback; pure, imports nothing, never throws. Acceptance: 1.1 green.
- [ ] 1.3 **RED** extend `tests/js/chart-host.test.js` stub: capture `createChart` args, stub `ColorType:{Solid:<non-standard>}`; assert born-themed `layout.background`/`textColor`; `setTheme` calls `applyOptions` only (no `setData`/`update`); ColorType symbol≠number. Acceptance: fails pre-1.4.
- [ ] 1.4 **GREEN** `market/templates/market/chart-host.js`: import `optionsFor`; merge `optionsFor(state.theme)` into the `createChart` options; add `setTheme(resolved)` (option-only); add to return. Acceptance: 1.3 green; host ≤300.
- [ ] 1.5 **GREEN** `market/views.py`: `MODULE_ALLOWLIST += "theme-core"`; `market/templates/market/chart.html`: `theme-core` `modulepreload`; `docs/architecture/chart-modules.md`: inventory row. Acceptance: `/market/theme-core.js` 200 JS; import-graph + allowlist tests green.
- [ ] 1.6 **REFACTOR** `node --test "tests/js/**/*.test.js"` + `pytest` + `makemigrations --check` green; ruff clean. Acceptance: Slice 1 green.

## Slice 2 — Persistence + shell + UI + a11y + E2E (PR2)

Base PR1 branch; deps Slice 1. Rollback: drop `theme` field/`0011`/view branches,
remove applier/control/light tokens/preload-event wiring → Slice 1 inert; reverted
view ignores the unknown field. ~230–280 lines.

- [ ] 2.1 **RED** `tests/web/test_market_api.py`: 5-key GET default incl. `theme:"system"`; PUT `{theme:"light"}` round-trips; `{theme:"bogus"}`→400 no-write; partial PUT applies only `theme`; A≠B isolation. Acceptance: fails pre-2.2/2.3.
- [ ] 2.2 **GREEN** `web/trading/models.py` + `web/trading/migrations/0011_chartpreference_theme.py`: `theme = CharField(max_length=16, default="system")`; `web/market/quotes.py`: `THEMES = ("light","dark","system")`. Acceptance: `makemigrations --check` clean.
- [ ] 2.3 **GREEN** `web/market/views.py`: `_preference_body`/GET-miss/nothing-to-apply bodies gain `"theme"`; `_put_preference` adds `if "theme" in body: validate vs THEMES else 400`. Acceptance: 2.1 green; 100% patch.
- [ ] 2.4 **RED** extend `tests/js/chart-store.test.js` (10-key incl. `theme`); `tests/js/chart-host.test.js` (rebuild born themed from `state.theme`). Acceptance: fails pre-2.5.
- [ ] 2.5 **GREEN** `market/templates/market/chart-store.js`: `STORE_KEYS += "theme"`. NO new bus event (R20 MUST NOT add one; design D2's `theme:changed` is overridden by R20): the applier calls a `main`-injected `onTheme({resolved, pref})` callback directly. Acceptance: 2.4 store green; bus event set unchanged.
- [ ] 2.6 **GREEN** `market/templates/market/main.js`: seed `theme:"system"`; `loadPreference` returns `theme` (fallback `"system"`); pass `onTheme` into `createToolbar` → `state.theme=resolved` + `host.setTheme(resolved)` (option-only) + `savePreference({theme:pref})`; boot applies the resolved theme pre-first-build. Acceptance: E2E live toggle + reload.
- [ ] 2.7 **GREEN** `market/templates/market/controllers/toolbar.js`: native theme `<select>` (options `light/dark/system`), `resolve(pref, matchMedia.matches)`, set `document.documentElement.dataset.theme`, `matchMedia` `change` listener (system-only, re-resolves while pref==`"system"`), call `onTheme`; `setTheme(pref)` restore; `market/templates/market/chart.html`: labelled `<select id="theme">`. No new controller, no bus event. Acceptance: control renders + labelled; `CONTROLLER_ALLOWLIST`==7.
- [ ] 2.8 **GREEN** `web/accounts/templates/registration/theme.css`: `[data-theme="light"]` token block (same var names as `:root`) + `--chart-text`/`--chart-connector` in both blocks. Acceptance: both sets declare identical names; dark is default.
- [ ] 2.9 **GREEN** theme-aware series fork: `controllers/drawings.js` text-create color from `--chart-text`; `controllers/smc.js` swing connector `#616161` → `--chart-connector` (light keeps `#616161`, dark `#8b949e`). Acceptance: light drawing text ≠ `#e6edf3`.
- [ ] 2.10 **GREEN** `tests/web/test_market_e2e.py` ADD-ONLY: theme select → `dataset.theme` flips + `window.marketChart.chart.options().layout.background.color` changes (no `setData`); reload persists; system → `emulate_media(color_scheme=...)`; 8-key seam. `tests/web/test_market_ux.py`: explicit `theme-core` served assertion. Acceptance: fails pre-Slice 1.
- [ ] 2.11 **REFACTOR** run `/impeccable` audit on the market page; `pytest` + `node --test` + `pytest -m e2e -p no:randomly` + `makemigrations --check` green; ruff clean. Acceptance: full suite green; audit issues resolved or noted.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | Slice1 ~175, Slice2 ~230–280 → ~405–455 |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR1 theme-core + host canvas → PR2 persistence + shell + UI + a11y + E2E |
| Delivery strategy | feature-branch-chain |
| Chain strategy | feature-branch-chain |

Each slice is autonomous with its own verification and trivial rollback. PR1 bases
on tracker `feat/chart-theme`; PR2 bases on the PR1 branch (retarget/rebase if the
child diff shows Slice 1).

## Dependency / Rollback Boundaries

- **Slice 1**: no dependency; rollback = delete core + allowlist/preload + doc row → host back to v5 defaults, chart unthemed.
- **Slice 2**: depends on Slice 1 (uses `optionsFor`/`setTheme`/`state.theme`); rollback = drop field/`0011`/view branches + applier/control/light tokens → Slice 1 inert; reverted view ignores the unknown field.
