# Tasks: chart-indicator-settings (issue #115, Fase F2)

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

All slice PRs base on the tracker `feat/chart-indicator-settings`; merge each slice
into the tracker before branching the next. Base boundaries: PR1 base = tracker;
PR2 base = PR1 branch. Strict TDD (`node --test` + `pytest` + E2E). Read-only: no
`src/`, no new dep, CSP unchanged, no migration, `window.marketChart` stays 8 keys,
legend `DECIMALS` untouched. Only Python change = `quotes.py` (JS is outside the
Python patch gate; JS net = `node --test` + E2E).

## Guard/Edge Matrix

- [ ] **server-drop bug**: `quotes.parse_layout_indicators` (quotes.py:281) KEEPS+validates `style` via new `_validate_layout_style`; round-trip test proves `{token,params,style}` survives PUT→GET.
- [ ] **kline-leak → 400**: style MUST live in the top-level `styles` slot, never under `params`; test asserts no `color/lineWidth/precision` key in `klineUrlFrom`.
- [ ] **STORE_KEYS 6→7**: add `styles`; update `tests/js/chart-store.test.js:70` vocabulary assertion (deliberate edit).
- [ ] **rebuild #68**: style edit → `indicator:changed` → one `rebuild()`/`setData`; no second full-series writer.
- [ ] **no migration**: JSONField additive; `makemigrations --check` green.
- [ ] **legend DECIMALS untouched**: precision feeds `priceFormat` only; legend test unaffected.
- [ ] **frozen 8-key seam**: no 9th `window.marketChart` key; E2E asserts `Object.keys(...).length === 8`.
- [ ] **a11y**: native `<dialog>` focus-trap + Esc; labelled inputs; visible gear focus; 375px no overflow.
- [ ] **no-new-dep / CSP**: native `<input type=color>`/`<dialog>`, `theme.css`; `requirements.txt` + CSP unchanged.
- [ ] **allowlist**: `indicator-settings-core` in `MODULE_ALLOWLIST`; `test_import_graph_routes_resolve` fails loudly if missed.

## Slice 1 — Core + persistence (PR1)

Base tracker; branch `feat/chart-indicator-settings-core`; deps none. Rollback: revert `indicator-settings-core.js`, `chart-store`/`chart-host` threading, `quotes.py` + allowlist/preload → chart renders registry defaults, no persistence. ~330 lines.

- [ ] 1.1 **RED** `tests/js/indicator-settings-core.test.js`: `normalize` clamp/drop/default, `validate` ok/errors, `defaultsFor` unknown token, never-throw, no-import. Acceptance: fails pre-1.2.
- [ ] 1.2 **GREEN** new `market/indicator-settings-core.js`: export exactly `FIELDS, TOKENS, defaultsFor, normalize, validate` (internal `clamp`); pure, imports nothing. Acceptance: 1.1 green.
- [ ] 1.3 **RED** `tests/js/chart-store.test.js`: `STORE_KEYS` = 7 incl. `styles`; `chart-controllers.test.js`: `buildIndicators(tokens,params,styles)` emits `style`; `klineUrlFrom` carries no style key. Acceptance: fails pre-1.4/1.6.
- [ ] 1.4 **GREEN** `market/chart-store.js`: `STORE_KEYS += "styles"`. Acceptance: store 7 keys, no candles.
- [ ] 1.5 **RED** `tests/web/test_market_api.py`: PUT `{token,params,style}` round-trips verbatim; out-of-range style → 400 no write; unknown style key → 400. Acceptance: fails pre-1.6.
- [ ] 1.6 **GREEN** `market/quotes.py`: `parse_layout_indicators` preserves `style`; add `_validate_layout_style(token, style)` (keys `color` `#rrggbb`, `lineWidth` 1..4, `precision` 0..8; unknown key/range → `ValueError`), mirroring `_validate_layout_params`. Acceptance: 1.5 green; 100% patch.
- [ ] 1.7 **GREEN** `market/chart-host.js`: `addSeries(token, paneIndex, style)` / `build(state)` read `state.styles[token]` (REGISTRY fallback) → `addSeries(Ctor,{color,lineWidth},idx)` + `series.applyOptions({priceFormat:{precision,minMove:10**-precision}})`. Acceptance: node host test reflects style.
- [ ] 1.8 **GREEN** `market/views.py`: `MODULE_ALLOWLIST += "indicator-settings-core"`; `chart.html` modulepreload. Acceptance: route resolves 200 JS MIME.
- [ ] 1.9 **REFACTOR** `node --test "tests/js/**/*.test.js"` + `pytest` + `makemigrations --check` green; ruff clean. Acceptance: Slice 1 suite green.

## Slice 2 — Dialog UI + E2E (PR2)

Base PR1 branch; deps Slice 1. Rollback: revert gear/dialog markup, `controllers/indicators.js`, `theme.css`, E2E → Slice 1 still round-trips style, no gear. ~220 lines.

- [ ] 2.1 **RED** `tests/web/test_market_e2e.py` ADD-ONLY: gear opens dialog pre-filled; confirm updates `series.options().color/lineWidth` + persists across reload; cancel = no change; Escape returns focus; 8-key seam; 375px no overflow. No edits to existing assertions. Acceptance: fails pre-2.2/2.3.
- [ ] 2.2 **GREEN** `market/chart.html`: `button.indicator-settings[data-token][aria-haspopup=dialog]` per active toggle inside `.indicators`; shared `<dialog id="indicator-settings-dialog">` (form method=dialog: color/width/period/precision, Apply/Cancel). Acceptance: markup present, no inline handler.
- [ ] 2.3 **GREEN** `market/controllers/indicators.js`: gear click populates dialog from `styles[token]`+`params[token]`; on `returnValue==="ok"` write `store.styles[token]` via `store.set`, period into `params`, emit one `indicator:changed`, `saveLayout()`; `buildIndicators` 3rd `styles` arg; `loadLayout` reads `body.indicators[].style` into `state.styles`. Acceptance: 2.1 green.
- [ ] 2.4 **GREEN** `web/accounts/templates/registration/theme.css`: gear + dialog styling (visible focus, no horizontal overflow). Acceptance: `/impeccable` DOM/computed-style audit clean.
- [ ] 2.5 **REFACTOR** `pytest` + `node --test` + `pytest -m e2e` green; ruff clean. Acceptance: Slice 2 suite green.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | Slice1 ~330, Slice2 ~220 → ~550 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 (core + store/host threading + quotes.py + tests) → PR2 (gear/dialog + chart.html + theme.css + E2E) |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Each slice is autonomous with its own verification and trivial rollback. PR1 bases
on tracker `feat/chart-indicator-settings`; PR2 bases on the PR1 branch (retarget/
rebase if a child diff shows Slice 1).

## Dependency / Rollback Boundaries

- **Slice 1**: no dependency; rollback = revert core + `chart-store`/`chart-host` + `quotes.py` + allowlist → prior registry-default render, no style persistence.
- **Slice 2**: depends on Slice 1 (uses `styles` slot + core); rollback = revert UI slice → no gear/dialog; Slice 1 persistence intact.
