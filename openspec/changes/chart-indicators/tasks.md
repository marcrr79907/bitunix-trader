# Tasks: chart-indicators (issue #70, Fase A1)

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

## Guard/Edge Matrix

- [ ] `macd`/`bollinger`/`stochastic` exact fixtures (spec values)
- [ ] length == input; leading `None` warm-up (macd 25/33, bb 19, stoch 13/15)
- [ ] no input mutation
- [ ] flat Bollinger `sd==0` collapses (`upper==middle==lower`, no None)
- [ ] zero-range stochastic `%K` None, no raise
- [ ] default set unchanged `{sma20,ema20,rsi14}`, `panes={}`
- [ ] selection `macd,rsi` returns both panes
- [ ] warm-up derived (MACD→33); page-edge non-null with ≥33 prior
- [ ] candles exactly 5 keys; no `quote_vol` leak
- [ ] `panes.volume.volume` == `quote_vol`
- [ ] unknown indicator → 400 before payload
- [ ] upstream clamp ≤200; DB supplies older warm-up
- [ ] no mid-stream `setData`; toggle uses history path
- [ ] `src/` framework-free; no new dep; CSP unchanged
- [ ] patch gate 100%; ruff + pytest green

## WU1 — Pure indicators (PR1)

Base `develop`; branch `feat/chart-indicators-indicators`. Deps: none.
Rollback: delete the 3 additive functions + tests (unused elsewhere).

- [ ] 1.1 **RED** `tests/test_indicators.py`: exact `macd` (small + 25/33 warm-up), `bollinger` (exact + `sd==0` collapse), `stochastic` (exact, zero-range None); length/warm-up/no-mutation/bounded/band-order.
- [ ] 1.2 **GREEN** `src/indicators.py`: add `macd(series,12,26,9)`, `bollinger(series,20,2.0)`, `stochastic(highs,lows,closes,14,3)`; stdlib `statistics` only.
- [ ] 1.3 **REFACTOR**: reuse `sma`/`ema`; ruff clean; boundary test green.

## WU2 — Payload + registry + validation (PR2)

Base: PR1 branch (chain) or `develop`. Deps: WU1.
Rollback: restore `quotes.py`/`views.py`; revert the 2 exact-shape tests.

- [ ] 2.1 **RED** `tests/web/test_market_api.py`: default set unchanged; `macd,rsi` panes; MACD→33 page-edge non-null; candles exactly 5 keys / no `quote_vol`; `panes.volume`==`quote_vol`; unknown token → 400; clamp ≤200; update 200-shape + empty-shape to include `panes`.
- [ ] 2.2 **GREEN** `web/market/quotes.py`: token registry, selection, derived `warmup=max(20,max first_valid)`, `want=limit+warmup`, upstream `min(want,200)`; keep un-stripped rows → `volumes` before `CHART_KEYS` strip; emit `{candles,overlays,panes}`.
- [ ] 2.3 **GREEN** `web/market/views.py`: validate `indicators` + flat params (`rsi_len`,`sma_len`,`bb_len`,`bb_std`,`macd_fast/slow/signal`,`stoch_k/d`,`atr_len`) → 400.
- [ ] 2.4 `pytest tests/web/test_market_api.py` green.

## WU3 — Adapter panes + toggles + HTML + E2E (PR3)

Base: PR2 branch (chain) or `develop`. Deps: WU2.
Rollback: restore `chart.js`/`chart.html`; revert E2E file.

- [ ] 3.1 **RED** `tests/web/test_market_e2e.py`: panes render; toggle adds/removes pane (rebuild); no mid-stream `setData`; close refresh `update()` only; no console errors.
- [ ] 3.2 **GREEN** `chart.js`: `REGISTRY`, `PANE_ORDER`, pane indices (0=price), `addSeries(def,opts,paneIndex)`; toggle/param → `remove()` + fresh `createChart` + re-add active set → `fetchHistory()`; generalize `updateLastPoint` for every active series; URL from `state.indicators`+params; expose `window.marketChart.panes`.
- [ ] 3.3 **GREEN** `chart.html`: side-panel `<fieldset>` of native checkbox toggles (keyboard-operable, design tokens).
- [ ] 3.4 **VERIFY** `/impeccable` audit; E2E green.

## Phase 4 — Verification

- [ ] 4.1 `python -m pytest` green; patch gate 100%; ruff check/format clean.
- [ ] 4.2 `node --test tests/js` green (core unchanged).
- [ ] 4.3 Boundary + order-scanner green; CSP + `requirements.txt` unchanged.
- [ ] 4.4 Playwright: overlays + panes render, toggle refetch, no flicker.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | PR1 ~180, PR2 ~150, PR3 ~200 → total ~550–650 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 → PR2 → PR3 (PR4 optional: split Python integration tests if PR2 overruns) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending (stacked-to-main vs feature-branch-chain) |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High
