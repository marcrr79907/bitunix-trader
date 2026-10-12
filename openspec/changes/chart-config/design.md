# Design: chart-config (issue #71, Fase A2)

## Technical Approach

Extend three existing seams, change nothing structural. `ChartLayout` joins
`trading.models` (R14 seam); a small `market/api/layout` view reads/writes it via
`for_user`; the adapter fetches the layout before building the chart and debounce-saves
on change. SMA/EMA move to the server's param-driven `sma`/`ema`. No new dep, CSP
unchanged, single write path (#68) preserved.

    boot:   GET layout ─→ apply to state + sync panel DOM ─→ buildChart ─→ connect ─→ fetchHistory
    change: toggle/param ─→ rebuild + setData (config change) ─→ debounce PUT {symbol,interval,indicators}

## Architecture Decisions

| Decision | Choice + rationale |
|---|---|
| Unique key `(user,symbol,interval)` vs `(user,symbol)` | **per-key** (settled, not reopened): TradingView-faithful; the adapter always knows the active interval. |
| Storage: JSON `indicators` vs granular columns | **JSON `[{token,params}]`**: registry is open-ended and panes are multi-series (MACD/Bollinger=3); granular churns a migration per token. SQLite `JSONField`, no dep. |
| Boot: async vs sync | **async `boot()`**: layout must precede `buildChart`; fetch failure falls back to `readIndicators()` (DOM defaults) — never blank. |
| Endpoint home: `market` vs `trading` | **`market/views.py`**: chart concern; `market → trading.models` is the existing direction. |

## Data Model

```python
class ChartLayout(UserOwnedModel):        # web/trading/models.py
    symbol = models.CharField(max_length=32)
    interval = models.CharField(max_length=8)
    indicators = models.JSONField(default=list)   # [{"token": str, "params": {..}}]
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "symbol", "interval"],
                                               name="uniq_layout_user_symbol_interval")]
```

Migration `web/trading/migrations/0005_chartlayout.py`, **additive**,
`dependencies = [("trading", "0004_private_snapshots")]`. No admin change (owned
self-service data; admin stays credential-only).

## Endpoint (`web/market/views.py` + `urls.py`)

Route `path("market/api/layout", views.api_layout, name="market_api_layout")`.

- **GET** `?symbol=&interval=` — `@login_required @require_http_methods(["GET"])`.
  Empty `symbol` or `interval ∉ INTERVALS` → `400 {"error"}` (mirrors `api_kline`).
  Hit → `200 {"symbol","interval","indicators",[...],"exists":true}`; miss → `200`
  with `DEFAULT_LAYOUT = [{"token":"sma"},{"token":"ema"},{"token":"rsi"}]`,
  `exists:false` (never 404).
- **PUT** — `@login_required @require_http_methods(["PUT"])`, CSRF enforced by
  `CsrfViewMiddleware` (no decorator). Body `{"symbol","interval","indicators"}`.
  Validate `symbol`, `interval ∈ INTERVALS`, `indicators` a list; each `token ∈
  quotes.REGISTRY` and its `params` via `quotes._parse_params` (new helper
  `parse_layout_indicators(list) -> list[tuple[str,dict]]`, raises `ValueError`) —
  **before any write** → `400` on failure. Then
  `ChartLayout.for_user(request.user).update_or_create(symbol=…, interval=…,
  defaults={"indicators": indicators})`. Returns the saved layout (`exists:true`).
- **CSRF (CSP-clean)**: add `<meta name="csrf-token" content="{{ csrf_token }}">` in
  `chart.html` `{% block head %}`; `chart.js` sets `X-CSRFToken`. No inline script.

## Adapter (`chart.js`)

- `boot()`: `fetch('/market/api/layout?symbol='+state.symbol+'&interval='+state.interval)`
  → set `state.indicators`/`state.params`, **sync toggle checkboxes + param inputs**,
  then `buildChart(); connect(); fetchHistory()`. `.catch` → `readIndicators()`.
- `switchTo(symbol, interval)`: set state, `sendSubscribe`, load that key's layout,
  apply, then `fetchHistory()` (same path as boot).
- **Save**: on toggle/param change (already config change → rebuild + `setData`),
  debounce ~500 ms and `PUT` `{symbol, interval, indicators}` with the captured key.
  `.catch` silent. WS stays `update()` only; the PUT never touches the stream.
- **Token migration**: JS `REGISTRY`, `DEFAULT_INDICATORS`, and `chart.html` toggle
  `value`s move `sma20`→`sma`, `ema20`→`ema` (server builders already param-driven);
  `sma_len`/`ema_len` default 20 → identical rendering. Server `DEFAULT_INDICATORS`
  (kline omitted-param back-compat) untouched.

## Param-editing UI (`chart.html`)

Reuse the checkbox `fieldset`; per param-capable overlay add one native input inside
its label, e.g. `<input type="checkbox" class="indicator-toggle" value="sma"> SMA
<input type="number" class="indicator-param" data-token="sma" data-param="sma_len"
min="1" value="20">`. Native `<input type="number">` = keyboard-operable + CSP-clean;
design-system tokens (`.panel`/`.indicators`/`--border`). `chart.js` collects
`.indicator-param` into `state.params` and appends them to `klineUrl()`.

## Guard

Add `ChartLayout` to the `OWNED_MODELS` frozenset and a parametrized negative-control
case (`ChartLayout.objects.all()`) in `tests/web/test_owned_model_guard.py`.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Model | `for_user` scoping; A≠B `DoesNotExist`; unique `(user,symbol,interval)` `IntegrityError`; same symbol+different interval coexists; JSON round-trip | `test_isolation.py` / `test_chart_layout.py` |
| Endpoint | anon → 302; GET default `exists:false`; PUT→GET `exists:true`; PUT upsert one row; unknown token / bad interval / bad symbol → 400; A≠B | `test_market_api.py` |
| E2E | seed layout, reload, assert toggles/panes restored; toggle → debounced PUT | `test_market_e2e.py` |
| Gate | patch 100% on new Python; ruff; `makemigrations --check`; guard | CI |

## Boundary Note

`src/` unchanged/framework-free; `requirements.txt`, CSP, DB shape (new table only),
`chart-core.js` unchanged; read-only — no order surface. No npm/build. Existing E2E
(rsi/macd) stay green — only SMA/EMA tokens move.

## File Changes

| File | Action | Description |
|---|---|---|
| `web/trading/models.py` | Modify | + `ChartLayout(UserOwnedModel)` |
| `web/trading/migrations/0005_chartlayout.py` | Create | additive |
| `web/market/quotes.py` | Modify | + `DEFAULT_LAYOUT`, `parse_layout_indicators` |
| `web/market/views.py` | Modify | + `api_layout` (GET/PUT) |
| `web/market/urls.py` | Modify | + `market/api/layout` |
| `web/market/templates/market/chart.html` | Modify | CSRF meta, param inputs, token values |
| `web/market/templates/market/chart.js` | Modify | async boot/restore, debounced save, params, token migration |
| `tests/web/test_owned_model_guard.py` | Modify | `OWNED_MODELS` + fixture |
| `tests/web/test_isolation.py` | Modify | ChartLayout A≠B / unique |
| `tests/web/test_market_api.py` | Modify | endpoint contract |
| `tests/web/test_market_e2e.py` | Modify | restore-on-boot E2E |

## Task Breakdown Hint

~400–470 lines. Chained PRs (orchestrator confirms with user — ask-on-risk):

- **PR1** — `ChartLayout` + migration + `OWNED_MODELS` + model/isolation tests.
- **PR2** — `api_layout` + route + `parse_layout_indicators` + endpoint tests.
- **PR3** — `chart.js`/`chart.html` async boot + save + token migration + param UI + E2E.

Each slice autonomous, own-tested, trivially revertible.

Decision needed before apply: Yes
Chained PRs recommended: Yes
400-line budget risk: Medium

## Open Questions

None blocking. Resolved: key `(user,symbol,interval)`; default `[{sma},{ema},{rsi}]`;
debounce ~500 ms auto-save; GET-miss 200 (not 404).
