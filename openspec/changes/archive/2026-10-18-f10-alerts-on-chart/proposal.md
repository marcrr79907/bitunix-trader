# Proposal: f10-alerts-on-chart

Issue #123, Fase F10. Branch `develop` @ `b12c0df`. Read-only audit, no code
changed. Builds on F0/F1 (chart) and the D1/D2 alert stack.

## Intent

Two deliverables on `/market/`:

- **Bell at the crosshair** — a button pinned to the cursor price that opens an
  in-place condition dialog and persists an `AlertRule` (create; edit when the
  cursor is near an existing `price` rule).
- **Alert markers** — `createSeriesMarkers` markers on the candle series
  distinguishing **armed** from **fired** for the active `(symbol, interval)`.

**The issue's "reuse the existing CRUD" is not literally achievable.** The only
alert CRUD today is Django HTML form views (`web/trading/urls.py:13-17` →
`views.py:205-258`), returning `render`/`redirect`; the chart is an ESM app that
speaks JSON only (`chart.js:24-34`). Navigating away destroys chart state
(store/bus/host are page-scoped, `main.js:52-68`). So F10 MUST ship a JSON
endpoint. **Reuse means**: the engine `parse_condition`
(`src/alert_rules.py:108-119`, already used by `trading/forms.py:31-37`), the
`AlertRule` model + `for_user` (`trading/models.py:288-304`), the S4 state
precedence (`market/views.py:104-116`), and the `api_drawings` CRUD shape
(`views.py:411-554`).

## Scope

### In Scope
- `GET/POST /market/api/alerts`, `PUT/DELETE /market/api/alerts/<id>` — `for_user`
  scoped, `symbol`+`interval` keyed, `parse_condition` validation, CSRF via the
  existing `X-CSRFToken` pattern (`drawings.js:12-15`).
- Pure cores: `alert-markers-core.js` (rule → marker[]) and
  `alert-condition-core.js` (dialog fields → `{type:"price", op, level}`).
- `controllers/alerts.js`: crosshair→bell placement, dialog, marker lifecycle.
- One `<dialog id="alert-dialog">` in `chart.html`; bell CSS in `theme.css`.
- Allowlists: `MODULE_ALLOWLIST` 28→30, `CONTROLLER_ALLOWLIST` 16→17.
- Node, API, UX and E2E tests; patch coverage 100%.

### Out of Scope
- **Order execution — HARD** (read-only repo). No placement, cancel or modify.
- SMC internals (`find_setups`/scoring) and `src/` changes (engine stays frozen).
- `indicator` / `smc_setup` condition types from the chart bell — `/rules/` owns them.
- New dependency, build step, CSP relaxation; store key or seam changes.
- Telegram delivery changes; worker/polling for live fired state.
- Extending `CANDLE_INTERVALS` with `1m` or the non-evaluable intervals.

## Capabilities

### New Capabilities
- `chart-alerts`: the crosshair bell, the in-place condition dialog (price-only),
  the interval eligibility guard, and armed/fired marker rendering from the
  `for_user` rule list.

### Modified Capabilities
- `alert-rules`: gains a JSON transport over the frozen model/engine — no R2/R3/R4
  semantic change; new R10 (JSON CRUD contract) and R11 (API `for_user` scope).
- `market-chart`: **R14** inventory + 2 cores + 1 controller; **R18** seam stays 8
  keys; **R20** stays inside the frozen host/store envelope.
- `design-system`: **R6/R7** — bell is a real focusable `<button>`, dialog is
  native `<dialog>` with focus return, rules state also announced in DOM
  (`aria-live`), never color-only.

## Approach

- **Endpoint** (`web/market/alerts.py` or a views block, +3 URL lines,
  `urls.py:9-37`): GET keys on `symbol` **and** `interval` (a rule is
  interval-scoped, `models.py:292`; missing → 400 mirroring `views.py:425-427`),
  returns `{id, symbol, interval, condition, is_active, last_fired_at,
  telegram_chat_id}` with `last_fired_at` as epoch seconds (chart time convention,
  `Candle.time` is `BigIntegerField`, `models.py:68`). POST/PUT validate
  `interval ∈ CANDLE_INTERVALS` (`candles.py:30`), `symbol ∈ SYMBOLS` (parity
  `forms.py:24-25`), then `parse_condition` → `ValueError` = 400. Owner set from
  `request.user` (`for_user` filters, never injects, `views.py:472`).
  `symbol`/`interval` immutable on PUT (mirrors `views.py:526-527`). Miss → 404.
- **Pure cores**: `alert-markers-core.js` — `stateOf(rule)` with the frozen
  precedence (`views.py:104-116`), `markersFor(rules, anchorTime)` emitting
  `{time, position, shape, text, color}`; no imports. `alert-condition-core.js` —
  `conditionFrom({op, level})` + `levelFromInput` (reject NaN/≤0) + `opFor(level,
  lastClose)` default above/below.
- **Controller** `controllers/alerts.js`: fetches on `chart:built` and on
  symbol/interval change; owns its **own** `createSeriesMarkers` handle (SMC
  precedent `smc.js:235`, never `setData`/`update` → #68). Anchors: fired →
  `last_fired_at`, armed → newest loaded candle time (LWC v5 requires an existing
  data point). Bell is a hover-placed `<button>` in `#chart`, hidden with `hidden`
  when the crosshair has no point (`legend.js:190-196`).
- **Interval guard**: bell disabled with `aria-describedby` reason on
  `1m/3d/6h/8h/12h` — the worker skips them (`worker.py:167-168`) and the form
  rejects them (`forms.py:25`), so a create there can never fire.
- **Ceiling discipline**: everything new, all ≤300; `smc.js` (300) byte-untouched,
  markers owned by `alerts.js`; `main.js` 274→~281 (+wire `createAlerts`/
  `attach`/`refresh`/`clearForSwitch`); `chart-host.js` and `chart-store.js`
  unchanged (no new key, no new event — reuse `chart:built`).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/market/urls.py` | Modified | +3 alert routes |
| `web/market/alerts.py` (or views block) | New | JSON CRUD, `parse_condition`, `for_user` |
| `web/market/views.py:44-95` | Modified | allowlists 28→30 / 16→17 |
| `market/chart.js:24-34` | Modified | `urls.alerts` |
| `market/alert-markers-core.js` | New | pure state→marker mapper |
| `market/alert-condition-core.js` | New | pure price-condition builder |
| `market/controllers/alerts.js` | New | bell, dialog, markers |
| `market/main.js`, `chart.html`, `theme.css` | Modified | wiring, `<dialog>`, bell styles |
| `controllers/smc.js` (300), `chart-host.js`, `chart-store.js` | Untouched | ceiling + frozen seam/store |
| `tests/js/*`, `tests/web/*` | Modified | cores, API matrix, UX, E2E |

## Rollback Plan

No migration, no schema change → nothing persistent to unwind. Revert the new
endpoint + 3 URL lines, the two cores, the controller, the `<dialog>`, the CSS and
the allowlist bump; `AlertRule` rows created through the UI stay valid and remain
editable on `/rules/`. Feature-branch chain → drop the tracker branch before any
merge to `develop`. Each slice is independently revertible; no dependency, CSP,
`src/` or store change to recover.

## Risks

| Risk | L | Mitigation |
|------|---|------------|
| 300-line ceiling (`smc.js`=300, guard ALLOWLIST empty, `test_module_size_guard.py:20-23`) | High | new files only; `smc.js` byte-untouched; `main.js` +~7 |
| Seam freeze 8 keys (`main.js:59-68`, asserted `test_market_e2e.py:2578-2586`) | High | no new key; assert via DOM + captured requests |
| `STORE_KEYS` frozen 11 (`chart-store.js:13-27`) | High | dialog/bell state in the controller closure |
| #68 single write path | High | markers via `createSeriesMarkers`, never `setData`/`update` |
| R14 `for_user` isolation | High | every query scoped (`views.py:429,473,507` discipline) |
| Patch coverage 100% | High | mirror the full drawings matrix (auth 302, CSRF 403, 400s, 404, A≠B) |
| Condition parity with `parse_condition` | High | server re-validates with the same function; core emits only `{type:"price",op,level}` |
| Interval guard regression | Med | disabled + accessible reason on 1m/3d/6h/8h/12h; 400 from the API |
| Fired-state staleness (`worker.py:178-183`) | Med | snapshot only; refetch on build/switch; copy says "when the candle close goes above X", not "crosses" |
| E2E class-C flake (#149) | Med | readiness-gate `window.marketChart.ready`, assert DOM/network, never pixels |

## Delivery (Feature Branch Chain)

Over the 400-line budget → chained PRs, base tracker `feat/f10-alerts-on-chart`.
S1 = JSON API + tests; S2 = pure cores + node tests; S3 = controller + dialog +
markers + allowlists + E2E. S3 depends on S1+S2. 400-line budget risk: **High**.

## Success Criteria

- [ ] Creating from the bell persists a `price` `AlertRule` owned by the caller.
- [ ] Editing a nearby rule updates it (PUT) without minting a duplicate.
- [ ] Markers render armed vs fired with distinct shape **and** text.
- [ ] Bell disabled, with an accessible reason, on non-evaluable intervals.
- [ ] `window.marketChart` stays 8 keys; `STORE_KEYS` stays 11; `smc.js` untouched at 300.
- [ ] `pytest` + `node --test` green; patch coverage 100%; no CSP or dependency change.
