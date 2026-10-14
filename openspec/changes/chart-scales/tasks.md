# Tasks: chart-scales (issue #121, Fase F8)

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

All slice PRs base on the tracker `feat/chart-scales`; merge each slice into the
tracker before branching the next. Base boundaries: PR1 base = tracker; PR2 base =
PR1 branch; PR3 base = PR2 branch (retarget/rebase if a child diff shows a prior
slice). Strict TDD (`node --test` + `pytest` + E2E). Read-only: no `src/`, no new
dep, CSP unchanged, `window.marketChart` stays 8 keys, indicators/SMC stay real
OHLC. Python touched only by `views.py` (allowlist + pref API), `models.py`,
migration `0010`, tests.

## Guard/Edge Matrix

- [ ] **HA-live #68**: `nextHeikinAshi` chains `haOpen=(prevHaOpen+prevHaClose)/2`; `lastHaOpen`/`lastHaClose` reset on `setCandles`; live path is `update()` only (E2E setData spy untouched).
- [ ] **type-switch rebuild**: route through `rebuild()`/`buildChart()` only; `attachAllDrawings()`+`attachSmcLayer()` re-attach; no in-place series transfer.
- [ ] **scale = option, not data**: `priceScale("right").applyOptions({mode})`; never `setData`/`update`.
- [ ] **PriceScaleMode symbol**: `LightweightCharts.PriceScaleMode.<...>`, never a magic number; confirmed against served v5.2.0 bundle.
- [ ] **migration additive + pref-body change**: `0010` passes `makemigrations --check`; GET body gains 2 keys — only the sanctioned pref assertions edited (Slice 3), all E2E assertions unedited.
- [ ] **vocab validation**: JS `isValidType`/`isValidScale`, Python `CHART_TYPES`/`SCALE_MODES`; unknown → candles/linear degrade, per-field 400.
- [ ] **8-key seam**: nothing added to `window.marketChart`; assert type/scale via select value + `priceScale("right").options().mode`.
- [ ] **allowlist served**: `chart-types-core` in `MODULE_ALLOWLIST`; import-graph route test green.
- [ ] **Ctor map**: candles/HA→`CandlestickSeries`, line→`LineSeries`, area→`AreaSeries`; overlays/panes unchanged across types.
- [ ] **no-new-dep / CSP**: pure core + native `<select>`s; `requirements.txt` + CSP unchanged.

## Slice 1 — Pure core (PR1)

Base tracker; branch `feat/chart-scales-core`; deps none. Rollback: revert core +
test + allowlist → prior candles-only chart, no type/scale. ~120 lines.

- [ ] 1.1 **RED** `tests/js/chart-types-core.test.js`: HA exact (bars 0/1, single, empty, 2-bar chain), `nextHeikinAshi` state chain, line/area `{time,value}`, unknown no-throw, no-import. Acceptance: fails pre-1.2.
- [ ] 1.2 **GREEN** `market/chart-types-core.js`: export frozen `CHART_TYPES`,`SCALE_MODES` + `isLineLike`,`isValidType`,`isValidScale`,`heikinAshi`,`nextHeikinAshi`,`toChartData`; pure, imports nothing, never throws. Acceptance: 1.1 green.
- [ ] 1.3 **GREEN** `market/views.py`: `MODULE_ALLOWLIST += "chart-types-core"`; `docs/architecture/chart-modules.md` inventory row. Acceptance: `/market/chart-types-core.js` 200 JS; import-graph test green.
- [ ] 1.4 **REFACTOR** `node --test "tests/js/**/*.test.js"` + `pytest` + `makemigrations --check` green. Acceptance: Slice 1 green.

## Slice 2 — Host + store + UI (PR2)

Base PR1 branch; deps Slice 1. Rollback: restore hardcoded `CandlestickSeries`,
drop store keys/bus event/selects → Slice 1 core inert. ~180 lines.

- [ ] 2.1 **RED** `tests/js/chart-host.test.js` (extend stub: `AreaSeries`/`LineSeries` + `priceScale()`): Ctor per type; `setScaleMode` option-only (no setData/update); scale re-applied on build; HA live `update()`-only; `tests/js/chart-store.test.js` 9-key assertion. Acceptance: fails pre-2.2/2.3.
- [ ] 2.2 **GREEN** `market/chart-store.js`: `STORE_KEYS += "scaleMode","chartType"`; `market/chart-bus.js`: `EVENTS.scaleChanged = "scale:changed"`. Acceptance: 2.1 store green.
- [ ] 2.3 **GREEN** `market/chart-host.js`: `build()` picks Ctor from `state.chartType`; apply scale after `createChart`; `setScaleMode(mode, autoScale)`; route `setCandles`/`updateCandle` through `toChartData`/`nextHeikinAshi` with reset-on-`setCandles`. Acceptance: 2.1 host green.
- [ ] 2.4 **GREEN** `market/controllers/toolbar.js`: two native `<select>`s, options from core, accessible names, emit `scale:changed` / `indicator:changed`, `setScaleMode`/`setChartType` reflect; `market/chart.html`: labelled empty selects near Interval + `chart-types-core` modulepreload. Acceptance: both selects render, no inline handler.
- [ ] 2.5 **GREEN** `market/main.js`: seed `scaleMode`/`chartType` defaults; subscribe `scale:changed`→`host.setScaleMode` (no rebuild, no fetch); type reuses `indicator:changed`→`rebuild()`. Acceptance: in-session E2E scale/type green.
- [ ] 2.6 **REFACTOR** `node --test` + `pytest` + `pytest -m e2e` green; ruff clean. Acceptance: Slice 2 green.

## Slice 3 — Persistence (PR3)

Base PR2 branch; deps Slice 2. Rollback: drop 2 fields/view branches/`0010`;
defaults hold, unknown fields ignored. ~150 lines.

- [ ] 3.1 **RED** `tests/web/test_market_api.py`: 4-key GET default + round-trip; partial PUT per-field; invalid scale/type/interval → 400 no-write; A≠B isolation. Acceptance: fails pre-3.2/3.3.
- [ ] 3.2 **GREEN** `web/trading/models.py` + `market/migrations/0010_*`: `scale_mode`/`chart_type` `CharField(max_length=16)` defaults `linear`/`candles`; `market/quotes.py`: `SCALE_MODES`/`CHART_TYPES` vocab. Acceptance: `makemigrations --check` clean; model assert green.
- [ ] 3.3 **GREEN** `market/views.py _put_preference`/`api_preference`: GET returns `{interval, scale_mode, chart_type, exists}` (defaults on miss); PUT partial-body, per-field validation → 400, applies only present keys. Acceptance: 3.1 green; 100% patch.
- [ ] 3.4 **GREEN** extend the 2 sanctioned pref assertions — `test_preference_get_default_when_absent` and `test_preference_put_then_get_round_trip` — to the 4-key body (spec R9 sanctioned). The other GET-body asserts (isolation, 12h) mirror the same 2 keys or they break; every E2E assertion stays unedited.
- [ ] 3.5 **GREEN** `market/main.js`: `loadPreference` returns all 3 (fallback linear/candles) applied before first build; `savePreference` PUTs only the changed key, non-fatal. Acceptance: reload restores both.
- [ ] 3.6 **GREEN** `tests/web/test_market_e2e.py` ADD-ONLY: scale select → `options().mode`; type select → series data shape + rebuild re-attaches drawings/SMC; reload persists; HA smoke; 8-key seam. Acceptance: fails pre-Slices 1–2.
- [ ] 3.7 **REFACTOR** `pytest` + `node --test` + `pytest -m e2e` + `makemigrations --check` green; ruff clean. Acceptance: full suite green.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | Slice1 ~120, Slice2 ~180, Slice3 ~150 → ~450 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 core → PR2 host/store/UI → PR3 persistence |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Each slice is autonomous with its own verification and trivial rollback. PR1 bases
on tracker `feat/chart-scales`; PR2 bases on the PR1 branch; PR3 bases on the PR2
branch (retarget/rebase if a child diff shows a prior slice).

## Dependency / Rollback Boundaries

- **Slice 1**: no dependency; rollback = revert core + test + allowlist → prior candles-only render.
- **Slice 2**: depends on Slice 1 (uses core exports); rollback = hardcoded `CandlestickSeries`, drop store keys/bus/selects; core stays inert.
- **Slice 3**: depends on Slice 2 (uses store keys); rollback = drop fields/view branches/`0010`; defaults hold, unknown fields ignored.
