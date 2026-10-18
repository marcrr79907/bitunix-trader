# Design: f10-alerts-on-chart (issue #123, Fase F10)

## Technical Approach

The chart already speaks JSON to `/market/api/*` (`chart.js:28-34`), and the
alert stack already owns one validation engine and one model. F10 therefore adds
**one JSON transport** over the frozen model/engine (`web/market/alerts.py`), and
a **leaf controller** that consumes it (`controllers/alerts.js`), with all
mapping logic pushed into **two pure cores** so every JS module stays under the
300-line ceiling while `controllers/smc.js` (exactly 300, `test_module_size_guard.py:20-23`)
is left byte-untouched. The design is driven by line arithmetic, not taste: the
three new files are the only place new behaviour can live, because `main.js`
has 26 lines of headroom and `chart-host.js`/`chart-store.js` are frozen
surfaces (8-key seam, `test_market_e2e.py:2578-2586`; 11 store keys,
`chart-store.js:13-27`).

No migration, no dependency, no CSP change, no new bus event, no new store key.

## Architecture Decisions

| # | Decision | Choice | Alternatives rejected | Rationale |
|---|---|---|---|---|
| D1 | Server placement | New `web/market/alerts.py`, views imported into `urls.py` | a block in `market/views.py` (594 lines) | `views.py:1-6` already carries page + kline + smc + layout + preference + drawings; the alerts handler is a self-contained CRUD with its own validator. A separate module gives locality (one file to read for the whole contract) and mirrors the `quotes.py` helper-module precedent. Python has no ceiling guard (`test_module_size_guard.py:25` scans only JS), so this is a clarity call, not a forced one. |
| D2 | Transport | JSON `/market/api/alerts`, GET/POST + PUT/DELETE on `<id>`, mirroring `api_drawings` (`views.py:411-554`) | reuse the HTML form views (`trading/urls.py:13-17`) | The form returns `render`/`redirect` (`trading/views.py:205-258`); navigating away destroys store/bus/host (`main.js:52-68`). Not literally reusable — proven in `explore.md:32-56`. |
| D3 | Condition surface | `price` only, emitted by a pure core | indicator/smc_setup from the bell | `parse_condition` accepts three shapes (`alert_rules.py:101-119`); only `price` maps 1:1 to "this line" with zero warm-up and zero parameter surface. Deeper conditions stay `/rules/`. |
| D4 | Bell location | New leaf controller owns its crosshair subscription + hover `<button>` | F7 context-menu item as the primary affordance | The issue asks for a bell at the cursor; `context-menu.js:69-83` `ACTION` map is a shipped seam but right-click is not the requested discoverability, and a menu item would mutate `menuModel`'s frozen array contract (`context-menu-core.js:28-40`). A context-menu shortcut is a deferred additive slice, not v1. |
| D5 | Marker primitive | Own `createSeriesMarkers` handle in `alerts.js`, never `setData`/`update` | price lines for armed rules | Markers are not series data → #68 holds by construction (`smc.js:4-5,235-238`). Price lines would need per-rule primitives and a lifecycle for edits; markers are one array replace. Armed rules keep a marker at the newest bar (anchor rule §5); the tradeoff (an armed marker is not at the level) is stated in copy and in the a11y summary. |
| D6 | Fired-state freshness | Snapshot on `chart:built` + on switch; no polling | poll `/market/api/alerts` on a timer | `last_fired_at` is written only by the worker (`worker.py:178-183`); a poll would fight the single-session E2E server and add a request loop for a value that changes once per closed candle. Copy says "when the candle close goes above X", never "live". |
| D7 | Edit detection | Nearest `price` rule within 10 px of the cursor level opens the dialog pre-filled (PUT) | list picker / hit-test markers | Zoom-aware (px, not %) and needs no new DOM; a picker is more surface than the issue asks for. |
| D8 | Bell state storage | Controller closure | a `chart-store` key | `STORE_KEYS` is frozen at 11 (`chart-store.js:13-27`) and asserted; selection already lives in a closure (`drawing-interaction.js:55`). |
| D9 | Interval eligibility | Bell disabled + `aria-describedby` on intervals outside `CANDLE_INTERVALS`; API 400 | extend `CANDLE_INTERVALS` with `1m` | The worker skips non-`CANDLE_INTERVALS` (`worker.py:167-168`) and the form rejects them (`forms.py:25`), so a create there can never fire. Extending the engine is a separate change (`explore.md:243-246`). |

## Module Decomposition & Line Budget

### New files

| File | Est. lines | Exports / role |
|---|---|---|
| `web/market/alerts.py` | ~150 | `api_alerts` (GET/POST), `api_alert_detail` (PUT/DELETE), `_row`, `_read_body`, `_parse_pair`, `_parse_optional_fields` |
| `market/alert-markers-core.js` | ~62 | `COLORS`, `stateOf(rule)`, `markersFor(rules, anchorTime)` — pure, no imports |
| `market/alert-condition-core.js` | ~46 | `conditionFrom(fields)`, `levelFromInput(text)`, `opFor(level, lastClose)` — pure, no imports |
| `market/controllers/alerts.js` | ~218 | `createAlerts({store,bus,host,config})` → `{attach, refresh, clearForSwitch}` |

### Modified files

| File | Now | Δ | After | What changes |
|---|---|---|---|---|
| `web/market/urls.py` | 37 | +6 | 43 | 2 `path(...)` entries (4-6 lines incl. continuation) |
| `web/market/views.py` | 594 | +3 | 597 | `MODULE_ALLOWLIST:44` +2 cores, `CONTROLLER_ALLOWLIST:76` +`alerts` |
| `market/chart.js` | 37 | +1 | 38 | `urls.alerts: "/market/api/alerts"` |
| `market/main.js` | 274 | +6 | **280** | +1 import, +1 `const alerts = createAlerts(...)`, +1 `alerts.attach()` in `buildChart:120-142`, +1 `alerts.clearForSwitch()` in `switchTo:162-199`, +1 `alerts.refresh()` in the `switchTo` chain, +1 in `start():229-274` |
| `market/chart.html` | 154 | +14 | 168 | one `<dialog id="alert-dialog">` + 2 `modulepreload` lines (HTML, not ceiling-guarded) |
| `web/accounts/.../theme.css` | — | +12 | — | `.chart-alert-bell` + dialog rows |
| `tests/web/test_market_ux.py` | — | +4/−2 | — | asserts `==16` → `==17`, `:146,195`; preload names; `len(MODULE_ALLOWLIST)` unchanged assertions |
| `controllers/smc.js` | 300 | **0** | 300 | **BYTE-UNTOUCHED** |
| `chart-host.js` | 267 | **0** | 267 | untouched — `subscribeCrosshairMove:236` already exists |
| `chart-store.js` | 61 | **0** | 61 | untouched — no new key |
| `chart-bus.js` | 54 | **0** | 54 | untouched — no new event; reuses `chart:built`/`history:loaded` |

### Ceiling proof

`280 + 218 + 62 + 46 + 300 = 906` lines of JS across the touched surface, and the
maximum of any single module is `smc.js = 300`, unchanged. Every new module is
≤218 (82 lines of margin in the largest, `alerts.js`). The two live constraints:

- `main.js` ends at **280** (20 lines under). The +6 is one wire line per seam
  (`const`, `attach`, `refresh` ×2, `clearForSwitch`, `import`); no refactor is
  needed. If it ever creeps past 300, the extraction is `alerts.refresh()` and
  `clearForSwitch()` into an existing chain — not a new file.
- `smc.js` is exactly 300 with an empty guard allowlist, so markers **must** live
  in `alerts.js`. A regression test asserts `"alert"` never appears in the
  served `smc.js` source (see §9).

The guard scans `web/market/templates/market/**/*.js`
(`test_module_size_guard.py:24-30`), so `<dialog>` markup and CSS are exempt.

## Layer Compliance

| Module | Layer | Allowed imports | DI |
|---|---|---|---|
| `alert-markers-core.js` | Pure core | none | — |
| `alert-condition-core.js` | Pure core | none | — |
| `controllers/alerts.js` | Controller (leaf) | `../alert-markers-core.js`, `../alert-condition-core.js` | `create({store, bus, host, config})` |
| `main.js` | Orchestrator | any controller | owns the instance |

`alerts.js` never imports `main.js`; it receives `store`/`bus`/`host`/`config`
exactly like `createSmc` (`smc.js:49`) and `createLegend` (`legend.js:70`). It
re-subscribes to the crosshair inside `bus.on("chart:built")` because `build()`
recreates the chart (`legend.js:207-212`, `chart-host.js:234-238`). Cores are
DOM-free and chart-lib-free, so they run under `node --test` with no stubs.

## The API Contract

### Routes (`web/market/urls.py`)

```
GET|POST    /market/api/alerts              -> alerts.api_alerts
PUT|DELETE  /market/api/alerts/<int:id>     -> alerts.api_alert_detail
```

Both are `@login_required` + `@require_http_methods` (`views.py:412-414`
pattern). CSRF is enforced by `CsrfViewMiddleware`: the page ships
`<meta name="csrf-token">` (`chart.html:5`) and the controller sends
`X-CSRFToken` (`drawings.js:12-15,144`).

### Row shape (single source, used by GET/POST/PUT)

```json
{
  "id": 12,
  "symbol": "BTCUSDT",
  "interval": "1h",
  "condition": {"type": "price", "op": "above", "level": 50000.0},
  "is_active": true,
  "last_fired_at": 1729220400,
  "telegram_chat_id": ""
}
```

`last_fired_at` is **epoch seconds** (`null` when never fired), matching every
other chart time (`Candle.time` is `BigIntegerField`, `models.py:68`) and the
boundary the worker writes (`worker.py:182` does `datetime.fromtimestamp(edge_time)`).
Serialization is `int(dt.timestamp())`; the round-trip is exact because the
worker's value came from an int epoch. `condition` is echoed **verbatim** as
stored (`parse_condition` already normalized it, `alert_rules.py:108-119`) — the
client never re-derives it.

### GET

`GET /market/api/alerts?symbol=BTCUSDT&interval=1h`

- Key is **symbol + interval** (a rule is interval-scoped, `models.py:292`; the
  worker groups by `(symbol, interval)`, `worker.py:170`). Unlike drawings, a
  missing `interval` is **not** ignorable.
- Response `200`: `{"symbol": "...", "interval": "...", "alerts": [row, ...]}`,
  empty list when there are none — never 404 (mirrors `views.py:429-431`).
- Owner scope: `AlertRule.for_user(request.user).filter(symbol=..., interval=...)`
  (`models.py:300-303`). `for_user` **filters, it does not inject** — every write
  passes `user=request.user` explicitly (comment precedent `views.py:472`).

### POST

```json
{"symbol": "BTCUSDT", "interval": "1h",
 "condition": {"type": "price", "op": "above", "level": 50000},
 "is_active": true, "telegram_chat_id": ""}
```

`201` with the row. `is_active` defaults `true`; `telegram_chat_id` defaults `""`.

### PUT (partial)

`{"condition"?: {...}, "is_active"?: bool, "telegram_chat_id"?: str}`

Absent fields keep stored values (mirrors `_put_drawing`, `views.py:516-554`).
`symbol`/`interval` are **immutable**: a differing value → `400
{"error": "symbol is immutable"}`; an equal value is accepted and ignored (the
stale-`interval` precedent, `views.py:442-444,;524-527`). Response `200` with the
row.

### DELETE

`204`, no body. Scoped fetch first → `404` on a foreign id.

### Validation order (MUST be this order, so errors are deterministic)

| Step | Check | Failure |
|---|---|---|
| 0 | body parses as JSON and is an object | `400 {"error":"invalid JSON"}` / `{"error":"invalid body"}` |
| 1 | `symbol` present and non-empty | `400 {"error":"symbol required"}` |
| 2 | `symbol ∈ SYMBOLS` (parity with `forms.py:24`) | `400 {"error":"invalid symbol"}` |
| 3 | `interval` present | `400 {"error":"interval required"}` |
| 4 | `interval ∈ CANDLE_INTERVALS` (`candles.py:30`) | `400 {"error":"invalid interval"}` |
| 5 | `condition = parse_condition(body["condition"])` | `400 {"error": str(exc)}` (the engine's own message) |
| 6 | `is_active` is a **real** bool (`True` is an `int`; `quotes.py:445-453` discipline) | `400 {"error":"is_active must be a boolean"}` |
| 7 | `telegram_chat_id` is a `str`, length ≤ 64 | `400 {"error":"invalid telegram_chat_id"}` |
| 8 | write | — |

Steps 1-5 run **before any write** (the `views.py:458-469` discipline), so a
failed request never leaves a row behind. Step 5 is the parity guarantee: the
bell cannot persist a shape the evaluator would reject, because the server
re-validates with the same function the HTML form uses (`forms.py:31-37`).

Interval uses `CANDLE_INTERVALS` (8 values, `candles.py:30`) rather than
`INTERVALS` (14, `quotes.py:38-53`): a rule outside the persisted set is skipped
by the worker (`worker.py:167-168`) and would be a permanent no-op.

### Status matrix

| Case | Status |
|---|---|
| Anonymous GET/POST/PUT/DELETE | `302` → `/login/` |
| POST/PUT/DELETE without `X-CSRFToken` | `403` |
| GET missing `symbol` | `400` |
| GET missing/unknown `interval` | `400` |
| GET known pair, no rows | `200 {"alerts": []}` |
| GET another user's pair | `200 {"alerts": []}` (never leaks) |
| POST invalid JSON / non-object | `400` |
| POST unknown `symbol` / unknown `interval` | `400` |
| POST invalid `condition` | `400`, no row |
| POST non-bool `is_active` | `400`, no row |
| PUT id not owned / missing | `404` |
| PUT differing `symbol` or `interval` | `400`, row untouched |
| PUT invalid `condition` | `400`, row untouched |
| DELETE id not owned / missing | `404` |

## Data Flow

**(a) Crosshair move → bell placement**

```
chart mouse move
  └─▶ host.subscribeCrosshairMove(onMove)            [chart-host.js:236]
        onMove(param):
          param.point ? place bell at {x,y} : hide bell (hidden attr)
          level = host.getCandleSeries().coordinateToPrice(param.point.y)
          eligible = CANDLE_INTERVALS_SET.has(state.interval)
          bell.setAttribute("aria-label", "Create alert at " + fmt(level))
          bell.disabled = !eligible; aria-describedby=reason when disabled
```
`state.interval` is read from the store (`chart-store.js`), so a switch needs no
listener. The bell is absolutely positioned inside `#chart`
(`theme.css:94,118-121` legend precedent) and clamped to the container.

**(b) Bell click → dialog → Apply → refetch**

```
bell.click
  └─▶ seed = {price, op: Core.opFor(price, lastClose), ruleId?}
        ruleId = nearest price-rule whose |priceToCoordinate(level) - param.point.y| <= 10
        dialog.showModal()  (native focus trap; returns focus to the bell)
  form submit value=ok
  └─▶ level = Core.levelFromInput(input.value); cond = Core.conditionFrom({op, level})
        cond === null  -> inline error, dialog stays open, no request
        cond !== null  -> POST /market/api/alerts  (or PUT .../<ruleId>)
             body {symbol, interval, condition, is_active:true}
             on 2xx  -> alerts = refetch(); render markers; aria-live announce
             on 400  -> inline error text from {"error"}
             on 302  -> window.location.assign("/login/")  (session expired)
```
The dialog is `<form method="dialog">` (three precedents, `chart.html:71-104`),
so no inline handler and no `preventDefault`-driven markup change.

**(c) Markers: rules → core → primitive**

```
refresh():
  fetch(config.urls.alerts + "?symbol=" + enc(sym) + "&interval=" + enc(iv))
    └─▶ rules = body.alerts
        anchorTime = last candle time from host.getCandles()   [chart-host.js:175]
        list = Core.markersFor(rules, anchorTime)              [pure]
        if (!markers) markers = LightweightCharts.createSeriesMarkers(series, list)
        else markers.setMarkers(list)                          [smc.js:270 precedent]
        summary.textContent = "N alerts: F fired, A armed"     [aria-live]
```

**(d) Symbol / interval switch → refetch + clear**

```
main.switchTo(symbol, interval)                          [main.js:162]
  └─▶ alerts.clearForSwitch()
        markers.detach(); markers = null; rules = []; summary = ""
        bell hidden; dialog closed if open
      ...buildChart() → host.build() → bus.emit("chart:built")
  └─▶ bus.on("chart:built") → host.subscribeCrosshairMove(onMove); alerts.refresh()
```
Reusing `chart:built` avoids a ninth seam key and a new bus event. `alerts.refresh()`
is also called once in `start()` after `drawings.refreshDrawings()` so the first
paint has markers.

## Pure Core Interfaces

### `alert-markers-core.js`

```js
export const COLORS = { armed: "#2962ff", fired: "#ef5350" };

// Per-rule projection of the frozen S4 precedence (market/views.py:104-116).
// Frozen S4 precedence: fired (last_fired_at) > armed (is_active) > inactive.
export function stateOf(rule) {}          // -> "fired" | "armed" | "inactive"

export function markersFor(rules, anchorTime) {} // -> marker[]
```

Rules:

- `stateOf`: `last_fired_at != null` → `"fired"`; else `is_active === true` →
  `"armed"`; else `"inactive"`. Never throws; a non-object rule → `"inactive"`.
  Folding `stateOf` over a pair's rules reproduces `_rule_state`
  (`views.py:104-116`) with the same precedence, which is why the pair badge on
  `/signals/` and the chart markers agree.
- Marker anchor: **fired** → `rule.last_fired_at` (already epoch seconds from the
  API); **armed** → `anchorTime` (the newest loaded candle, because LWC v5 drops
  a marker whose `time` is not a data point); **inactive** → no marker.
- Degrade: `anchorTime` missing/non-finite → `[]`. A fired `last_fired_at` that
  is not a finite number → fall back to `anchorTime` (still render, never drop a
  rule silently). `rules` not an array → `[]`. Never mutates the input.
- Emitted marker (shape **and** text, never colour alone):

```js
{ time: 1729220400, position: "aboveBar", color: "#ef5350",
  shape: "arrowDown", text: "F 50000" }        // fired
{ time: 1729220400, position: "belowBar", color: "#2962ff",
  shape: "circle",   text: "A 50000" }         // armed
```

`text` carries the level, so shape+text distinguish state without colour
(a11y/design-system R6/R7). `position` differs too (`aboveBar` vs `belowBar`),
which survives colour-blind palettes and greyscale.

### `alert-condition-core.js`

```js
export function conditionFrom(fields) {}      // {op, level} -> {type:"price",op,level} | null
export function levelFromInput(text) {}       // string -> number | null
export function opFor(level, lastClose) {}    // number, number -> "above" | "below"
```

- `levelFromInput`: `String(text).trim()`; accept `,` as a decimal separator
  (replaced with `.`); `Number(...)`; reject empty, `NaN`, `!isFinite`, `<= 0`
  (a non-positive price is not a price). Returns `null`, never throws.
- `conditionFrom`: `op` must be exactly `"above"` or `"below"`; `level` must pass
  the same finite/positive test; returns a **fresh** object, never mutates input.
  `null` is the controller's "do not POST" signal.
- `opFor`: `lastClose` finite and `level < lastClose` → `"below"`, otherwise
  `"above"` (default above when the reference is unknown).
- These three names are the whole surface; the server still re-validates through
  `parse_condition`, so a core bug can only produce a `400`, never a bad row.

## Server Design

`web/market/alerts.py`:

| Symbol | Role |
|---|---|
| `api_alerts(request)` | `@login_required` + GET/POST |
| `api_alert_detail(request, id)` | `@login_required` + PUT/DELETE; scoped fetch first |
| `_row(rule) -> dict` | the one row serializer (`last_fired_at` → int/None) |
| `_read_body(request)` | `json.loads(request.body or b"{}")`; raises a `_BadBody` mapped to 400 |
| `_parse_pair(body)` | symbol → `SYMBOLS`, interval → `CANDLE_INTERVALS` |
| `_parse_optional(body, *, default)` | real-bool `is_active` + bounded `telegram_chat_id` |

Reuse, not reimplementation:

- `parse_condition` from `src.alert_rules` (the single engine, `alert_rules.py:108`)
- `CANDLE_INTERVALS` from `trading.candles:30`
- `SYMBOLS` from `src.config` (the `forms.py:24` source)
- `AlertRule.for_user` (`models.py:300-303`)
- the real-bool discipline from `quotes.py:445-453` (not the function — it is
  private and drawing-specific; the two-line check is local)

`_row` is the only serializer, so GET, POST and PUT can never drift. The HTML
form and the JSON endpoint are consistent by construction: both bound on
`SYMBOLS`/`CANDLE_INTERVALS` and both normalize through `parse_condition`; the
worker consumes the same fields (`worker.py:162-183`) and its writes are the only
source of `last_fired_at`.

Patch-coverage matrix (every new Python branch gets a test, mirroring the
drawings matrix at `test_market_api.py:1243-1640`):

| Branch | Test |
|---|---|
| anon GET / POST / PUT / DELETE | 4 × `302` |
| no-CSRF POST / PUT / DELETE | 3 × `403` |
| GET missing symbol / missing interval / bad interval | 3 × `400` |
| GET empty → `[]`, not 404 | 1 |
| GET other user's pair → `[]` | 1 |
| POST invalid JSON / non-object | 2 × `400` |
| POST bad symbol / bad interval | 2 × `400` |
| POST bad condition (3 shapes) | 3 × `400` + `count()==0` |
| POST non-bool `is_active` / bad `telegram_chat_id` | 2 × `400` |
| POST valid → `201` + GET round-trip | 1 |
| PUT partial `condition` / `is_active` | 2 |
| PUT immutable symbol / interval | 2 × `400`, row unchanged |
| PUT miss / foreign id | 2 × `404`, A unchanged |
| PUT invalid condition | `400`, row unchanged |
| DELETE own → `204`; miss; foreign | 3 |
| `last_fired_at` null and int serialization | 2 |

## a11y + CSP

- **Bell** is a real `<button type="button" class="chart-alert-bell">` built with
  `createElement` + `setAttribute` (`context-menu.js:113-139` precedent), with
  `aria-label="Create alert at <price>"`, `hidden` when the crosshair has no
  point, and `disabled` + `aria-describedby="alert-interval-reason"` on
  non-evaluable intervals. It is focusable; the visible reason text
  (`#alert-interval-reason`, `visually-hidden`) says why.
- **Dialog**: native `<dialog id="alert-dialog" aria-label="Price alert">` with
  `<form method="dialog">`. `showModal()` traps focus and restores it to the
  invoking element on close — the same contract F7 documented
  (`context-menu.js:52-59`). Close order: cancel → focus back to the bell;
  after a successful create → focus back to the bell, announcement via the
  summary node.
- **Markers are canvas**, invisible to assistive tech. State therefore also
  exists in the DOM: `#alert-summary` (`aria-live="polite"`) announces
  "N alerts: F fired, A armed" after each refresh. Marker shape + text ("A"/"F"
  + level) is the canvas-side non-colour cue; `position` differs too.
- **CSP**: no inline script and no inline handler — the page test
  (`test_market_ux.py:265-272`) already enforces this, and the dialog is static
  markup. Inline `node.style.*` writes are allowed (`style-src 'unsafe-inline'`,
  `middleware.py:29-33`) and are the established bell-positioning mechanism.

## Risks & Mitigations

| Risk | L | Mitigation |
|---|---|---|
| `smc.js` at exactly 300 | High | new controller owns markers; regression test asserts `"alert"` absent from served `smc.js` |
| 8-key seam / 11 store keys | High | no new key/event; state in the closure; E2E asserts 8 |
| #68 single write path | High | `createSeriesMarkers` only; anchors from `getCandles()`/`last_fired_at`, never synthetic bars |
| Condition parity | High | server re-validates with `parse_condition`; a core bug yields 400, never a bad row |
| `for_user` isolation | High | every query scoped; A≠B tests for GET/PUT/DELETE |
| Patch coverage 100% | High | the matrix above; nothing else in `alerts.py` |
| Marker dropped by LWC (time not a data point) | Med | armed anchored at the newest candle; fired at `last_fired_at`; degrade to `anchorTime` |
| Fired-state staleness | Med | snapshot only; refetch on build/switch; copy avoids "live"/"crosses" |
| Interval guard regression | Med | bell disabled + reason; API 400; E2E asserts disabled on `1m` |
| Allowlist counts asserted (`==16`) | Med | deliberately update to 17/30 in the same commit as the allowlist change |
| E2E flake (#149) | Med | DOM + captured requests only, no pixels; `window.marketChart.ready` gate |

## Test Strategy

| Layer | File | Assertions |
|---|---|---|
| Node | `tests/js/alert-markers-core.test.js` | `stateOf` precedence incl. `inactive`; fired anchor = `last_fired_at`; armed anchor = `anchorTime`; inactive omitted; null/garbage → `[]`/fallback; deep-equal marker arrays (mirror `smc-overlay-core.test.js:243-282`) |
| Node | `tests/js/alert-condition-core.test.js` | `levelFromInput` rejects `""`, `"abc"`, `0`, `-1`, `Infinity`, accepts `"50000,5"`; `conditionFrom` op whitelist + fresh object; `opFor` above/below boundary + unknown close |
| Pytest | `tests/web/test_market_alerts_api.py` | the full matrix above |
| Pytest | `tests/test_alert_rules.py` (add case) | a bell-shaped `{type:"price",op:"above",level:X}` is accepted by `parse_condition` and has an edge (`edge_fired`) |
| Pytest | `tests/web/test_market_ux.py` | allowlist counts 17/30, 2 new module preloads, dialog present, no inline handler (existing), `smc.js` contains no `alert` token |
| Pytest | `tests/web/test_alert_rule_crud.py` | **unchanged**, must stay green (HTML CRUD untouched) |
| E2E | `tests/web/test_market_alert_e2e.py` | create via bell → captured `POST /market/api/alerts` body shape + `aria-live` summary; switch interval → captured GET with the new interval; bell disabled on `1m`; 8-key seam still holds |

No pixel assertions. Grep-style tests for "no inline", "no alert in smc.js" are
cheap invariants that fail loudly if the layering drifts.

## Delivery & Rollback (chained PRs, Feature Branch Chain)

Base tracker `feat/f10-alerts-on-chart`; >400 changed lines → three slices, each
independently revertible (no migration, no dependency, no CSP change):

| Slice | Content | Rollback |
|---|---|---|
| **S1** (API) | `alerts.py`, 2 URL entries, API tests | revert module + routes; `AlertRule` rows on `/rules/` unaffected |
| **S2** (cores) | `alert-markers-core.js`, `alert-condition-core.js`, node tests | delete 2 files + 2 allowlist names; nothing imports them yet |
| **S3** (chart) | `controllers/alerts.js`, `<dialog>`, bell CSS, `chart.js` url, `main.js` wiring, allowlist `alerts`, E2E | revert controller/dialog/CSS/wiring; S1's data remains valid and readable from `/rules/` |

S3 depends on S1 + S2. Each slice leaves the repo green: S1 and S2 are additive
and dead until S3 wires them.

## Open Question Carried Into Spec

The engine is an **edge** detector, not a cross detector: `matches` is
`close > level` (`alert_rules.py:159-165`) and the worker fires on
`now && !prev` (`worker.py:178-183`). Dialog copy MUST read "fires when the
candle close goes above 100", never "crosses". The spec delta should pin this as
a scenario so the copy cannot drift.
