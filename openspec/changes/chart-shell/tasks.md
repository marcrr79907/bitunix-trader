# Tasks: chart-shell (issue #116, Fase F3)

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

All slice PRs base on the tracker `feat/chart-shell`; merge each slice into the
tracker before branching the next. Base boundaries: PR1 base = tracker; PR2 base
= PR1 branch. Strict TDD (`node --test` + `pytest` + E2E). Read-only: no `src/`,
no new dep, CSP unchanged, `window.marketChart` stays 8 keys, `SmcOverlayCore`
untouched. JS is outside the Python patch gate (`diff-cover` Python-only) → JS net
is `node --test` + E2E. Frozen seam: intervals single-sourced from `select.options`.

## Guard/Edge Matrix

- [ ] **hidden-select invariant (R18)**: `<select id="interval">` kept, `.visually-hidden` via `clip`, NEVER `display:none`/`hidden`; chips only add listeners → the 15 `select_option("#interval",…)` calls stay green, zero assertion edits.
- [ ] **autoSize resize (v5)**: `height:480` removed, `autoSize:true` added; `#chart` resolves via flex/grid chain; E2E asserts canvas bbox > 480 and tracks `#chart` (no zero-height).
- [ ] **8-key seam**: chips/toggle write no global; E2E asserts `Object.keys(window.marketChart).length === 8`; `SmcOverlayCore` reachable.
- [ ] **375px no-overflow**: `.interval-chips{flex-wrap:wrap}`; `scrollWidth <= clientWidth + 1` asserted.
- [ ] **migration additive**: `CreateModel` only; `makemigrations --check` green; `OWNED_MODELS += "ChartPreference"` (+1 offender param).
- [ ] **R14 / A≠B**: preference GET/PUT route through `ChartPreference.for_user`; no unscoped query; A≠B isolation tested.
- [ ] **no-new-dep / CSP**: template buttons + `theme.css` + existing ESM; no inline handler; CSP + `requirements.txt` unchanged.
- [ ] **boot ordering**: pref GET precedes `start()`; failure → `"1m"`; `gen` guard intact.

## Slice 1 — Shell (PR1)

Base tracker; branch `feat/chart-shell-shell`; deps none. Rollback: revert `chart.html`/`theme.css`/`chart-host.js`/`toolbar.js` + added E2E → restore `height:480`, no chips/toggle. ~150 lines.

- [ ] 1.1 **GREEN** `theme.css`: `body{display:flex;flex-direction:column;min-height:100dvh}`, `main{flex:1 1 auto;min-height:0}` (keep `max-width:1200px`), `.market-layout{height:100%}`, `#chart` `dvh`+floor, `.visually-hidden` (clip), `.interval-chips`/`.interval-chip[aria-pressed]`, `.panel-toggle`, `.panel-collapsed`, 820px block. Acceptance: shell styles present, desktop unchanged.
- [ ] 1.2 **GREEN** `chart.html`: add `<button class="panel-toggle" aria-expanded="true" aria-controls="panel">`, `id="panel"` on `<aside>`; interval chips rendered by JS (no template dup). Acceptance: DOM has toggle + `#panel` + `#interval`.
- [ ] 1.3 **GREEN** `chart-host.js`: drop `height:480`, add `autoSize:true` (keep `timeScale`). Acceptance: no numeric height; `autoSize` present.
- [ ] 1.4 **GREEN** `controllers/toolbar.js`: build `.interval-chips` from `select.options` (`role=group`, `button.interval-chip[data-interval][aria-pressed]`), add `.visually-hidden` to select; chip↔select bidirectional sync emitting ONE existing `config:changed`; panel-toggle `classList.toggle("panel-collapsed")`+`aria-expanded`; export `setInterval` to reflect store. Acceptance: chip click switches + `aria-pressed` moves; select still actionable.
- [ ] 1.5 **RED** `tests/web/test_market_e2e.py` ADD-ONLY: chips `aria-pressed` + click switches; hidden select `select_option` still works; panel toggle collapse/expand; 375px `scrollWidth` no overflow; canvas bbox > 480 + tracks `#chart`; seam 8 keys. No edits to existing assertions. Acceptance: fails pre-1.4.
- [ ] 1.6 **REFACTOR** `node --test "tests/js/**/*.test.js"` green (existing unedited); `pytest -m e2e` green; ruff clean. Acceptance: Slice 1 suite green.

## Slice 2 — Interval persistence (PR2)

Base PR1 branch; deps Slice 1. Rollback: revert model/`0009` + reverse migration, endpoints, `main.js` read/save → boot falls back `"1m"`; Slice 1 shell intact. ~160 lines.

- [ ] 2.1 **RED** `tests/web/test_market_api.py`: preference GET default `{interval:"1m",exists:false}`, PUT→GET round-trip, invalid interval→400 (no row), anonymous→302, A≠B isolation. Acceptance: fails pre-2.2.
- [ ] 2.2 **GREEN** `trading/models.py`: `ChartPreference(UserOwnedModel)` — `OneToOneField(user, related_name="chart_preference")`, `last_interval CharField(8, default="1m")`, `updated_at auto_now`. Acceptance: import + fields correct.
- [ ] 2.3 **GREEN** migration `trading/migrations/0009_chartpreference.py` additive `CreateModel`. Acceptance: `makemigrations --check` green.
- [ ] 2.4 **GREEN** `market/views.py` `api_preference` GET/PUT via `for_user(user).update_or_create`, validate `interval in INTERVALS` before write; `market/urls.py` route name `market_api_preference`; `chart.js` `CONFIG.urls.preference`. Acceptance: 2.1 green.
- [ ] 2.5 **GREEN** `main.js`: GET preference before `start()` (failure→`"1m"`, `gen` intact), apply to select/`state.interval`/`toolbar.setInterval`; debounced PUT on interval change (mirror `saveLayout`, non-fatal). Acceptance: restore + debounced save observed.
- [ ] 2.6 **GREEN** `tests/web/test_owned_model_guard.py`: `OWNED_MODELS += "ChartPreference"` + one offender param. Acceptance: guard flags unscoped `ChartPreference.objects.*`.
- [ ] 2.7 **REFACTOR** `pytest` + `node --test` + `pytest -m e2e` green; patch 100% on Python lines; ruff clean. Acceptance: Slice 2 suite green.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | Slice1 ~150, Slice2 ~160 → ~310 |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR1 (shell: CSS + template + chips + collapse + autoSize) → PR2 (persistence: model + `0009` + endpoint + boot + tests) |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Each slice is autonomous with its own verification and trivial rollback. PR1 bases
on tracker `feat/chart-shell`; PR2 bases on the PR1 branch (retarget/rebase if a
child diff shows Slice 1).

## Dependency / Rollback Boundaries

- **Slice 1**: no dependency; rollback = revert 4 files + added E2E → prior fixed-height shell.
- **Slice 2**: depends on Slice 1 (uses `toolbar.setInterval`); rollback = reverse migration + revert endpoint/boot → Slice 1 state, boot defaults `"1m"`.
