# Exploration: chart-config (issue #71, Fase A2)

## Current State

The chart already has indicator toggles but **no persistence** and **no parameter
editing**:

- `web/market/templates/market/chart.html` (L33–44) renders a
  `<fieldset class="indicators">` of nine `.indicator-toggle` checkboxes
  (`sma20 checked`, `ema20 checked`, `bollinger`, `vwap`, `rsi checked`,
  `macd`, `stochastic`, `atr`, `volume`). No param inputs.
- `web/market/templates/market/chart.js` reads DOM state once at boot
  (`readIndicators()`, L85–90) into `state.indicators` (L92). On toggle it
  rebuilds the chart and refetches (L368–374). `klineUrl()` (L201–206) appends
  `indicators=` only — **flat params are never sent**, even though the server
  (`quotes.parse_indicators`, L246) fully supports them. Nothing is saved;
  closing/reloading loses the selection.
- `/market/api/kline` (A1) accepts `indicators` (comma tokens) + flat params
  (`rsi_len`, `macd_fast`, `bb_len`, …) validated in `views.api_kline`
  (L52–55 → 400). The JS `REGISTRY`/`PANE_ORDER` (chart.js L36–79) mirror the
  server tokens.
- `UserOwnedModel` (`web/trading/models.py` L90–104) is the R14 seam: owner FK
  CASCADE + `for_user(user)`. Owned models live in `web/trading/models.py`;
  migrations in `web/trading/migrations/` (latest `0004`). `web/market` has **no
  `models.py` and no `migrations/`**; it already imports `trading.models.Candle`
  (`quotes.py` L25).
- Guard `tests/web/test_owned_model_guard.py` scans `web/{config,accounts,trading,market}`
  (L19) for unscoped `<Model>.objects.<verb>()`; `OWNED_MODELS` is a literal set
  (L22–24) — **`ChartLayout` MUST be added there** or the guard silently ignores it.
- `CN.` Every endpoint is `@login_required` + GET-only; CSRF middleware is on
  (`base.py` L90). Chart JS is served same-origin via `views.chart_js`
  (text/javascript) with `{{ symbols|safe }}` injected — the same seam can carry
  a CSRF token. CSP is strict (`script-src` no inline); `base.html` has a
  `{% block head %}` and `{% block scripts %}`.
- Design tokens in `theme.css` (`.panel`, `.indicators`, `--surface/--border/--accent`,
  `*:focus-visible`); no build/npm.

## Answers to the exploration questions

### 1. Model — shape and unique key

Add to `web/trading/models.py` (next to the other owned models):

```python
class ChartLayout(UserOwnedModel):
    """Per-user persisted chart layout: which indicators + their params (R14)."""
    symbol = models.CharField(max_length=32)
    indicators = models.JSONField(default=list)   # [{"token": "macd", "params": {...}}]
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "symbol"], name="uniq_layout_user_symbol")
        ]
```

- **Single JSON `indicators` field (recommended)** — a list of
  `{"token": str, "params": {}}`. Rationale: the registry is token-driven and
  open-ended; granular columns (`sma_bool`, `sma_len`, …) would need a migration
  per new indicator and cannot express a variable series count (Bollinger = 3
  lines, MACD = 3 series). JSON maps 1:1 to the adapter's `REGISTRY` and to the
  `indicators=`/flat-param query the server already accepts. SQLite + Django
  `JSONField` works natively (no new dep). Granular columns are rejected as
  spec-frozen and churn-heavy (YAGNI).
- **Unique `(user, symbol)` (recommended)** — matches the issue text and the
  stated goal ("restore *which indicators*"). Indicators/params are
  symbol-scoped in practice (BTCUSDT shows RSI+MACD; ETHUSDT shows Bollinger);
  interval is an orthogonal selector the user re-picks. This keeps one row per
  instrument and makes the "default when none exists" path trivial.
  - Alternative `(user, symbol, interval)` (TradingView-faithful, per-chart):
    rejected for v1 — it multiplies rows and complicates boot (the layout
    depends on the currently-selected interval, which is itself not persisted).
    Adding `interval` to the unique key later is an **additive** migration if
    per-timeframe params are ever needed.
- `updated_at` = `auto_now=True` (write stamp). No `created_at` needed (not used).
- **Placement**: `web/trading/models.py` reuses `UserOwnedModel`, the existing
  `trading` migrations, and the guard's scan path; `web/market` already imports
  from `trading.models`. Alternative (new `market/models.py` + `market/migrations/`)
  costs two new files for domain purity only — flagged as an ADR for design.

### 2. API — small GET/PUT endpoint

- **Where**: endpoint in `web/market/views.py` (chart concern), route in
  `web/market/urls.py` as `path("market/api/layout", views.api_layout, name="market_api_layout")`.
  The model stays in `trading` (see §1). `web/market → trading.models` is the
  existing dependency direction.
- **GET** `/market/api/layout?symbol=BTCUSDT` — `@login_required`, GET-only:
  - Reads `ChartLayout.for_user(request.user).filter(symbol=symbol).first()`.
  - Found → `200 {"symbol":…, "indicators":[{"token":…,"params":{…}}], "exists": true}`.
  - **None exists → `200` with the built-in default set
    (`[{token:"sma20"},{token:"ema20"},{token:"rsi"}]`) and `"exists": false`.**
    No 404 — the client always gets a usable layout shell (default-on-missing).
  - Invalid/empty `symbol` → `400 {"error":…}` (mirrors `api_kline`).
- **PUT** `/market/api/layout` — `@login_required` + `require_http_methods(["PUT"])`,
  **CSRF enforced** (Django middleware; client sends `X-CSRFToken`):
  - Body JSON `{"symbol":"BTCUSDT","indicators":[{"token":…,"params":{…}}]}`.
  - Validate: `symbol` non-empty; `indicators` a list; every `token` ∈ the
    adapter vocabulary (reuse `quotes.REGISTRY`); params numeric where the token
    declares them. Unknown token / bad shape → `400 {"error":…}` (BEFORE any write).
  - Upsert via `ChartLayout.for_user(request.user).update_or_create(symbol=…, defaults={"indicators":…})`
    — every access routed through `for_user` (R14); the unscoped manager is never used.
  - Returns the saved layout `200` (same shape as GET, `exists: true`).
- **CSRF token delivery (CSP-clean)**: add `<meta name="csrf-token" content="{{ csrf_token }}">`
  to `chart.html` (inside the existing `{% block head %}`); `chart.js` reads it
  and sets `X-CSRFToken`. No inline script/handler; CSP unchanged. (Alternative:
  render a hidden `{% csrf_token %}` form — the meta tag is smaller.)

### 3. Adapter (`chart.js`) — restore on boot, save on change

- **Boot becomes async**: today `buildChart(); connect(); fetchHistory();` run
  synchronously at L376–379. Introduce `boot()`:
  1. `fetch('/market/api/layout?symbol='+state.symbol)` → apply `indicators`
     to `state.indicators`, **sync the checkbox DOM** (`toggle.checked = …`) and
     the param inputs, so the panel reflects the restored layout;
  2. `buildChart()`; `connect()`; `fetchHistory()`.
  - The existing `readIndicators()` becomes a fallback used only if the layout
    fetch fails (chart still boots with DOM defaults — never blank).
- **Save on change (debounced)**: on any toggle/param change the adapter already
  rebuilds + refetches (L368–374). Add a debounced (~500 ms) `PUT` of
  `{symbol, indicators}` via `fetch(…, {method:"PUT", headers:{X-CSRFToken}, body})`.
  A failed save is non-fatal (console-silent); the in-session chart is unaffected.
- **Symbol switch**: `switchTo()` (L349) must also GET the new symbol's layout
  and apply it before `fetchHistory()` (same path as boot). Interval switch does
  **not** re-fetch the layout (layout is per symbol, §1).
- **Config panel — params**: the checkbox fieldset (chart.html L34–44) is
  **not enough** for "editar parámetros". Add one compact numeric input per
  param-capable indicator, e.g.:
  `<label><input type="checkbox" class="indicator-toggle" value="sma"> SMA
   <input type="number" class="indicator-param" data-token="sma" data-param="sma_len" min="1" value="20"></label>`
  `chart.js` collects `.indicator-param` into `state.params` and appends them to
  `klineUrl()` (e.g. `&sma_len=20&macd_fast=12`). Design-system tokens only;
  native `<input type="number">` keeps it CSP-clean and keyboard-accessible.
- **Token-vocabulary reconciliation (KEY FINDING)**: the toggles currently use
  `sma20`/`ema20`/`rsi`, but the server's param-driven builders are `sma`/`ema`/`rsi`
  (`sma20`/`ema20` hard-code 20 and **ignore `sma_len`/`ema_len`**). For an edited
  SMA/EMA length to actually take effect, the adapter's SMA/EMA entries must move
  to the `sma`/`ema` tokens (default 20 → identical rendering) and the JS
  `REGISTRY` keys `sma20`→`sma`, `ema20`→`ema`. `rsi`, `macd`, `bollinger`,
  `stochastic`, `atr` are already param-driven. This is the one real design
  wrinkle; recommend the token switch (E2E toggle tests key on `rsi`/`macd`
  values only, so they are unaffected). Alternative — teach `sma20` to honor
  `sma_len` — leaves a lying token name; rejected.
- **Single-write-path preserved**: restore/save never touches the live stream;
  toggle/param change stays a config change (`setData`, as today). No new
  `setData` during the stream.

### 4. R14 — scoping

- Model inherits `UserOwnedModel`; ALL reads/writes use
  `ChartLayout.for_user(request.user)` (`.filter`, `.update_or_create` — the
  guard's `UNSCOPED_VERBS` already covers `filter`/`update_or_create`, and
  `for_user` is the sanctioned accessor).
- **`ChartLayout` MUST be added to `OWNED_MODELS`** in
  `tests/web/test_owned_model_guard.py` (L22) — otherwise the scanner is blind to
  the new model. The scanner's negative-control/parametrized tests should gain a
  `ChartLayout.objects.*` fixture (R14.3 "scanner flags the new models").
- A≠B: `ChartLayout.for_user(B).get(pk=A's row)` raises `DoesNotExist`; both
  users may hold the same `symbol` (unique is per user).
- `per-user-isolation` spec gains `ChartLayout` in the R14.2 model list and a
  scenario. Cascade delete on user removal follows from the base FK.

### 5. Tests

- **Model** (`tests/web/test_chart_layout.py` or extend `test_isolation.py`):
  `for_user` returns only owner rows; empty owner not an error; A≠B
  `DoesNotExist`; unique `(user, symbol)` raises `IntegrityError`; same symbol
  across users allowed; JSON round-trips.
- **Endpoint** (`tests/web/test_market_api.py` or a new file):
  - anonymous GET/PUT → 302;
  - GET default when none → 200 `exists:false` + default set;
  - GET after PUT → returns saved set, `exists:true`;
  - PUT without CSRF → 403; PUT unknown token / bad body → 400; PUT upserts
    (second PUT replaces, no duplicate row);
  - **A≠B**: A's PUT is invisible to B's GET (B gets default);
  - bad/empty `symbol` → 400.
- **Adapter restore-on-boot E2E** (dev-only, `test_market_e2e.py`): seed a
  `ChartLayout` for the logged-in user, `goto /market/`, assert the restored
  toggles/panes render (DOM-only); toggle an indicator and assert a debounced
  `PUT /market/api/layout` is observed.
- **Patch gate 100%**: every new Python line (model, view, urls) strictly
  covered; JS lives template-side (not in diff-cover) and is covered by E2E.
  `ruff` clean; `makemigrations --check` green; boundary + order scanner green.

## Affected Areas

- `web/trading/models.py` — add `ChartLayout(UserOwnedModel)`.
- `web/trading/migrations/0005_chartlayout.py` — additive migration (generated).
- `web/market/views.py` — add `api_layout` (GET/PUT).
- `web/market/urls.py` — add `market/api/layout`.
- `web/market/templates/market/chart.html` — CSRF meta; param inputs; toggle values.
- `web/market/templates/market/chart.js` — async boot/restore, debounced save,
  params collection, SMA/EMA token switch.
- `tests/web/test_owned_model_guard.py` — `OWNED_MODELS` + fixture.
- `tests/web/test_isolation.py` — ChartLayout A≠B scenarios.
- `tests/web/test_market_api.py` — endpoint GET/PUT/default/CSRF/A≠B.
- `tests/web/test_market_e2e.py` — restore-on-boot E2E.
- `openspec/specs/per-user-isolation/spec.md` — R14.2 model list delta (archive time).

## Approaches

1. **JSON layout in `trading`, GET/PUT endpoint in `market`, async boot (RECOMMENDED)**
   — reuse `UserOwnedModel` + existing migrations + guard scan; one JSON column
   matches the token registry; default-on-missing; debounced save. Pros: smallest
   diff, no new app, no new dep, R14-clean, forward-compatible (add `interval` to
   the unique key later). Cons: `market` endpoint reads a `trading` model
   (existing direction; ADR-worthy); `(user, symbol)` not per-interval.
   Effort: Medium.
2. **Granular columns** (`sma_bool`, `sma_len`, …) — Pros: typed, admin-friendly.
   Cons: a migration per new indicator, cannot model multi-series panes, more
   columns than the registry is stable around. Rejected (YAGNI).
3. **New `market` app model + `market/migrations/`** — Pros: domain-pure
   placement. Cons: two new files + a new migrations package for no functional
   gain; duplicates the ownership seam's home. Rejected for v1 (flag as ADR).
4. **localStorage only (no server)** — Pros: trivial. Cons: violates "per user"
   (R14) and does not survive device change; explicitly out of the issue's
   intent. Rejected.

## Recommendation

Approach 1. `ChartLayout(UserOwnedModel)` in `web/trading/models.py` with a single
JSON `indicators` field and unique `(user, symbol)`; a small `market/api/layout`
GET/PUT endpoint scoped by `for_user`; async boot in `chart.js` restores the
layout (syncing the panel DOM) and a debounced PUT saves on change; param inputs
added to the panel with SMA/EMA moved to the param-driven `sma`/`ema` tokens so
edits take effect. It extends the existing seam, keeps every invariant
(R14, CSP, no npm, read-only, single write path), and stays within the 400-line
review budget.

## Risks

- **Token-vocabulary mismatch** (SMA/EMA hard-coded 20). Mitigation: switch
  toggle/registry tokens to `sma`/`ema`; verified the E2E toggle tests key on
  `rsi`/`macd` only.
- **Guard blind spot**: forgetting to add `ChartLayout` to `OWNED_MODELS` leaves
  it unscanned. Mitigation: explicit task + negative-control fixture.
- **Async boot ordering**: layout fetch must resolve before `buildChart()`;
  a failed fetch must fall back to DOM defaults (never a blank chart).
- **Debounced PUT races with symbol switch**: a pending save for old symbol must
  be flushed/cancelled on switch. Mitigation: capture `symbol` in the payload;
  server upserts per symbol (no cross-symbol corruption).
- **JSON schema drift**: token/param names in the stored JSON may not match a
  future registry. Mitigation: validate tokens against `quotes.REGISTRY` on PUT;
  unknown tokens → 400.
- **A2 vs A3 scope creep**: drawing (A3/SMC) explicitly out; layout stores only
  indicator toggles + params.

## Open Questions (for spec/design)

1. Confirm unique **`(user, symbol)`** (recommended) vs `(user, symbol, interval)`.
2. Confirm `ChartLayout` lives in `web/trading/models.py` (recommended) vs a new
   `market` model.
3. Param inputs for **which** indicators in v1 (recommend: all param-capable —
   `sma`, `ema`, `rsi`, `bollinger`, `macd`, `stochastic`, `atr`)?
4. Save trigger: debounce delay, and save on every change vs an explicit "Save
   layout" button (recommend auto-save, debounced ~500 ms).
5. Should GET-on-missing return `exists:false` + default (recommended) or a 404?

## Ready for Proposal

YES — all questions answered with file references; the architecture is a direct
extension of the R14 ownership seam and the A1 indicator seam; the only pre-spec
decisions are the five open questions above.
