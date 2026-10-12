# Proposal: chart-config

## Intent

The chart's indicator toggles are ephemeral: closing or reloading `/market/`
discards the selection, parameters (e.g. SMA length) cannot be edited in the UI,
and nothing is saved per user. Users expect TradingView-style saved layouts (R14):
their chart restores which indicators are on and with what parameters. Issue #71
(Fase A2).

## Scope

### In Scope
- `ChartLayout(UserOwnedModel)` — `symbol`, JSON `indicators`
  (`[{"token", "params"}]`), `updated_at`; unique `(user, symbol)`; `for_user`.
- Additive migration; `makemigrations --check` green.
- `market/api/layout` GET (default when none) / PUT (CSRF-gated) scoped by
  `for_user`.
- `chart.js`: restore the layout on boot (syncing the panel DOM) and symbol
  switch; debounced save on toggle/param change.
- `chart.html`: param inputs; CSRF meta; SMA/EMA toggle tokens moved to the
  param-driven `sma`/`ema` (default 20, identical rendering).
- `OWNED_MODELS` + tests: model, endpoint (GET/PUT/default/CSRF/A≠B),
  restore-on-boot E2E (dev-only).

### Out of Scope
- Drawing (A3), SMC, alerts. Per-interval layouts (`interval` in the unique key)
  — deferred, additive later. Any indicator math in JS; any npm/build; CSP
  relaxation; order execution (HARD).

## Capabilities

### New Capabilities
- `chart-config`: per-user persisted chart layout — model, GET/PUT endpoint,
  default-on-missing, restore-on-boot, debounced save.

### Modified Capabilities
- `per-user-isolation`: R14.2 owned-model list gains `ChartLayout`.
- `market-chart`: new R10 — layout GET/PUT endpoint contract (default, CSRF, 400s).

## Approach

Extend the existing seams: `ChartLayout` joins the owned models in
`web/trading/models.py`; a small `web/market` view reads/writes it through
`for_user` (upsert on PUT, default set on missing GET). The adapter boots
asynchronously — fetch the layout, apply it to the panel + `state.indicators`,
then `buildChart()`/`fetchHistory()` — and a debounced PUT persists each change.
SMA/EMA switch to the server's param-driven `sma`/`ema` tokens so length edits
take effect. No new dependency; CSP unchanged.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/trading/models.py` | Modified | + `ChartLayout` |
| `web/trading/migrations/0005_chartlayout.py` | New | additive |
| `web/market/views.py` | Modified | + `api_layout` (GET/PUT) |
| `web/market/urls.py` | Modified | + `market/api/layout` |
| `web/market/templates/market/chart.html` | Modified | param inputs, CSRF meta |
| `web/market/templates/market/chart.js` | Modified | async boot, debounced save |
| `tests/web/test_owned_model_guard.py` | Modified | `OWNED_MODELS` + fixture |
| `tests/web/test_isolation.py` | Modified | ChartLayout A≠B |
| `tests/web/test_market_api.py` | Modified | endpoint contract |
| `tests/web/test_market_e2e.py` | Modified | restore-on-boot E2E |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Guard blind spot (`OWNED_MODELS` literal) | Med | explicit task + negative-control fixture |
| SMA/EMA token mismatch (hard-coded 20) | Med | switch tokens to `sma`/`ema`; E2E keys on `rsi`/`macd` |
| Async boot ordering / blank chart | Med | layout fetch before build; DOM-default fallback on failure |
| Debounced PUT races symbol switch | Low | payload carries `symbol`; server upserts per symbol |
| JSON token drift | Low | validate tokens against `quotes.REGISTRY` on PUT → 400 |

## Rollback Plan

Revert the branch: drop `ChartLayout` + migration `0005`, remove `api_layout` +
route, restore `chart.js`/`chart.html`, and revert the test edits. The migration
is additive (new table only) — reversing it drops one table with no data loss to
existing tables. No CSP, `requirements.txt`, or boundary change.

## Success Criteria

- [ ] Layout persists per user; GET returns default when none; A≠B isolated.
- [ ] Chart restores toggles + params on open and symbol switch; edits save (debounced).
- [ ] `python -m pytest` green; patch gate 100%; ruff clean; `makemigrations --check` green.
- [ ] No new runtime dependency; CSP unchanged; UI audited with `/impeccable`.

## Review Workload Forecast

- Estimated diff: **~380–470 lines** (model+migration ~30, views+urls ~60,
  chart.js ~90, chart.html ~30, tests ~170). Borderline vs the 400 budget.
- Decision needed before apply: Yes
- Chained PRs recommended: Yes
- 400-line budget risk: Medium
