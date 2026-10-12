# Proposal: chart-indicators

## Intent

The chart shows only SMA/EMA (price overlays) + RSI as text. Issue #70 (Fase
A1) asks for **configurable indicators in separate panes** (TradingView-style:
price overlays + sub-panes), with all math server-side. `src/indicators.py`
lacks `macd`, `bollinger`, `stochastic`; the endpoint returns a fixed overlay
set; the adapter cannot create panes or toggle indicators.

## Scope

### In Scope
- `src/indicators.py`: add pure `macd` (12/26/9 → 3 arrays), `bollinger`
  (20, 2σ → upper/middle/lower), `stochastic` (14,3 → %K/%D), same
  index-aligned/`None`-warm-up/stdlib-only contract.
- `/market/api/kline`: selectable indicators via query params
  (`indicators=macd,rsi,...&rsi_len=14`); computed warm-up
  (`max(20, max first-valid-index)`; MACD→33); response gains `panes` +
  volume while candles stay exactly 5 keys; DB-first + gap-fill unchanged.
- `chart.js`: price overlays (Bollinger/VWAP/SMA/EMA) + sub-panes via v5
  `paneIndex` (RSI, MACD, Stochastic, ATR, Volume); per-indicator toggle;
  single-write-path preserved (the stream uses `update()` only; close refresh
  advances each active series' last point).
- `chart.html`: toggle controls in the side panel (keyboard-operable).
- Tests: pure fixtures; payload selection/warm-up/shape; dev-only pane/toggle E2E.

### Out of Scope
- Any indicator math in JS (hard invariant). Any npm/build; CSP relaxation.
- Drawing (A3), config persistence (A2), SMC (B/C). Order execution (HARD).
- `node --test` core changes (pane/registry config is chart-side, not core math).

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `technical-indicators`: R1 function set gains `macd`/`bollinger`/`stochastic`;
  R2 warm-up table gains their rows.
- `market-chart`: R3 payload gains selectable indicators + a `panes` bucket +
  volume; R4 warm-up becomes indicator-derived (not a fixed 20).
- `chart-live-stream`: R6 overlay close-refresh generalizes from the SMA/EMA
  pair to every active overlay/pane series (still `update()`, never `setData`).

## Approach

Extend the existing seam, change nothing structural: pure math lands in
`src/indicators.py` (single source); `quotes.py` selects the requested set,
computes the warm window, and serializes `{candles, overlays, panes}`; the
adapter owns a static pane registry and renders it. Toggle = request-set change
→ refetch (a config change legitimately uses `setData`, like symbol/interval
switch). Default set stays `{sma20, ema20, rsi14}` for backward compatibility.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/indicators.py` | Modified | + `macd`, `bollinger`, `stochastic` |
| `web/market/quotes.py` | Modified | selection, computed warm-up, `panes`, volume |
| `web/market/views.py` | Modified | validate `indicators` + param names |
| `web/market/templates/market/chart.js` | Modified | overlays, panes, toggles |
| `web/market/templates/market/chart.html` | Modified | toggle controls |
| `tests/test_indicators.py` | Modified | fixtures for 3 new functions |
| `tests/web/test_market_api.py` | Modified | selection/warm-up/shape |
| `tests/web/test_market_e2e.py` | Modified | pane + toggle E2E |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| BitUnix `limit ≤ 200` vs `limit+warmup` (233 w/ MACD) | Med | clamp upstream to 200, rely on DB; design decision |
| LWC v5 empty-pane lifecycle on toggle | Med | verify in design; refetch-rebuild over incremental surgery |
| Exact-shape payload tests break | Low | default set unchanged; update deliberately |
| Volume source (quote vs base) | Low | decide in spec |
| `sd==0` Bollinger semantics | Low | decide in spec |

## Rollback Plan

Revert the branch: restore `indicators.py`, `quotes.py`, `views.py`, `chart.js`,
`chart.html`, and the three test files. No migration, no DB change, no CSP or
`requirements.txt` change. The 3 new pure functions are additive and unused by
other callers, so removing them is safe.

## Open Questions

1. `limit + warmup > 200`: clamp upstream and rely on DB, or cap `limit`?
2. Volume series: quote volume or base volume?
3. Bollinger flat window (`sd == 0`): collapse bands to the middle or `None`?
4. Default set when `indicators` omitted: keep `{sma20,ema20,rsi14}` (recommended)?
5. Keep the side-panel RSI text alongside the RSI pane?

## Success Criteria

- [ ] `macd`/`bollinger`/`stochastic` exact on known fixtures; length/warm-up/no-mutation invariants hold.
- [ ] Payload returns a selectable set with correct warm-up; candles exactly 5 keys; MACD pane edge non-null on the first page candle.
- [ ] Chart shows price overlays + separate panes; toggle works; dev-only E2E green.
- [ ] `python -m pytest` green; patch gate 100%; ruff clean; boundary + order-scanner green.
- [ ] No new runtime dependency; CSP unchanged; UI audited with `/impeccable`.

## Review Workload Forecast

- Estimated diff: **~550–650 lines** (indicators ~120, tests ~180, quotes
  ~60, views ~30, chart.js ~120, chart.html ~25, E2E ~40).
- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: High
