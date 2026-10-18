# Exploration: f10-alerts-on-chart

Issue #123, Fase F10. Branch `develop` @ `b12c0df`. Read-only: no code changed,
no branch created. Builds on F0/F1 (market chart) + the D1/D2 alert stack.

## 1. Problem framing

Two deliverables on the existing `/market/` chart:

1. **Bell at the crosshair** — a bell affordance pinned to the crosshair point
   that opens a small condition dialog seeded with the price under the cursor,
   and persists an `AlertRule` (create; edit an existing one when the cursor is
   near its level).
2. **Alert markers** — `createSeriesMarkers` markers on the candle series for the
   caller's rules on the active `(symbol, interval)`, visually distinguishing
   **active/armed** from **fired**.

**What "reuse the D1/D2 engine and the existing CRUD" really means.** It means
reuse the **engine** (`src/alert_rules.py`) and the **model**
(`AlertRule` + `for_user`). It does NOT mean reuse the CRUD *transport*: that
CRUD is Django HTML form views (`web/trading/urls.py:13-17` →
`web/trading/views.py:205-258`), and the chart is an ESM app that only speaks
JSON to `/market/api/*` (`chart.js:28-34`). Navigating the browser away from the
chart to a form page would destroy the chart state and contradicts the
"create at the crosshair, in place" UX. A JSON alert endpoint is therefore
required. See §2.

State vocabulary is already frozen by S4 (`openspec/specs/signals-screen/spec.md:68-74`,
implemented in `web/market/views.py:104-116`):
`fired` (any `last_fired_at`) > `armed` (any `is_active`) > `inactive` (rules
exist, none active) > `none`. `last_fired_at` doubles as the dedup key
(`trading/models.py:295`, written only by the worker at `web/worker.py:178-183`).

## 2. The API gap (KEY FINDING — confirmed)

**There is no JSON API for alert rules.** Verified exhaustively:

| Evidence | Result |
|---|---|
| `web/market/urls.py:9-37` | routes: `kline`, `smc`, `layout`, `preference`, `drawings`, `drawings/<id>`, `chart.js`, module/controller JS. **No alerts route.** |
| `web/trading/urls.py:13-17` | `rules/`, `rules/new/`, `rules/<pk>/edit/`, `rules/<pk>/toggle/`, `rules/<pk>/delete/` — all HTML views returning `render(...)` or `redirect(...)` (`web/trading/views.py:205-258`) |
| `grep "api/alerts\|api_alert"` over `web/ tests/ openspec/` | zero hits |
| `web/market/views.py:18` | `AlertRule` is already imported in the market views (used by `signals_page` only) |

So the issue's "reusa el CRUD existente" is **not literally achievable**. What
IS reusable: `parse_condition` (single-source validation, already imported by the
form at `trading/forms.py:15,31-37`), the `AlertRule` model + `for_user`
(`trading/models.py:277-304`, `:102-104`), `_rule_state` precedence
(`market/views.py:104-116`), and the drawings JSON CRUD **shape** as a template
(`market/views.py:411-554`).

### Minimal proposed endpoint (mirrors `api_drawings`)

```
GET    /market/api/alerts?symbol=BTCUSDT&interval=1h   -> list for_user
POST   /market/api/alerts                              -> create (201)
PUT    /market/api/alerts/<id>                         -> partial update
DELETE /market/api/alerts/<id>                         -> delete (204)
```

- GET: `@login_required`, `require_http_methods(["GET","POST"])`; keys on
  `symbol` **and** `interval` (unlike drawings, a rule is interval-scoped —
  `AlertRule.interval` is part of the evaluation key, `models.py:292`). Missing
  `symbol` → 400 (mirror `views.py:425-427`); unknown `interval` → 400.
- Response rows: `{id, symbol, interval, condition, is_active, last_fired_at,
  telegram_chat_id}` — `last_fired_at` is the fired marker's `time` and the
  only server-computed state input. Ship it as an ISO-8601 string or epoch
  seconds; **recommend epoch seconds** to match every other chart time value
  (`market/quotes.py:619`, `Candle.time` is a `BigIntegerField`,
  `models.py:68`). Convert via `int(dt.timestamp())`.
- POST body: `{symbol, interval, condition, is_active?, telegram_chat_id?}`.
  Validate `interval ∈ CANDLE_INTERVALS`, `symbol ∈ SYMBOLS` (parity with
  `AlertRuleForm`, `trading/forms.py:24-25`), then
  `condition = parse_condition(body["condition"])` and map `ValueError` → 400 —
  exactly the form's `clean_condition` contract (`forms.py:31-37`). Owner is set
  explicitly (`user=request.user`) because `for_user` filters, it does not
  inject (comment at `market/views.py:472`; spec C2).
- PUT: partial, `for_user(request.user).filter(pk=id).first()` → 404 on miss
  (mirror `views.py:507-509`); accept `condition` re-validated via
  `parse_condition`, and `is_active` as a REAL bool (reject int/str, mirroring
  `parse_drawing`'s bool rule at `quotes.py:429`). `symbol`/`interval`
  immutable per rule (recommend rejecting a differing value, mirroring the
  drawings' `kind is immutable` at `views.py:526-527`) — the bell seeds a new
  rule for a different pair instead.
- DELETE: same scoped fetch → 204.
- CSRF: the page already ships `<meta name="csrf-token">`
  (`chart.html:5`) and the controllers send `X-CSRFToken`
  (`controllers/drawings.js:12-15,144`); the endpoint gets it for free from
  `CsrfViewMiddleware` (a POST without the header → 403, mirroring
  `test_drawings_post_requires_csrf`, `test_market_api.py:1390`).

**Sizing: this is the bulk of the server work.** ~120–160 lines in
`web/market/views.py` (or a new `web/market/alerts_api.py` — see §6 ceiling
pressure) + 3 URL lines + tests. Note `market/views.py` is already **594 lines**
— there is **no 300-line guard on Python** (`test_module_size_guard.py` scans
only `web/market/templates/market/**/*.js`, `:25`), but keeping the alert
handler in a small module is the cleaner split and mirrors the `quotes.py`
helper pattern.

## 3. Codebase map — exact touch points

### Server

| File | Change |
|---|---|
| `web/market/urls.py:9-37` | +3 routes: `market/api/alerts`, `market/api/alerts/<int:id>` |
| new `web/market/alerts.py` (or views block) | GET/POST/PUT/DELETE handlers, `parse_condition` + pair validation, `for_user` scoping |
| `web/market/views.py:44-95` | add the new JS modules to `MODULE_ALLOWLIST` / `CONTROLLER_ALLOWLIST` (16/28 today; both counts are asserted by tests) |
| `web/market/templates/market/chart.js:28-34` | `urls.alerts = "/market/api/alerts"` |

### Chart client

| File | Change |
|---|---|
| new `web/market/templates/market/alert-markers-core.js` | pure: `rules → marker[]` (+ `stateOf(rule)`), no DOM/chart imports |
| new `web/market/templates/market/alert-condition-core.js` | pure: dialog fields → a `price` condition dict; decimal/edge guards |
| new `web/market/templates/market/controllers/alerts.js` | fetch list + POST/PUT; crosshair → bell DOM position; `createSeriesMarkers` (re)creation; dialog wiring |
| `web/market/templates/market/chart-host.js:231-241` | **no change needed** — `subscribeClick`/`subscribeCrosshairMove` already exist; consumers re-subscribe on `chart:built` (see `controllers/legend.js:207-212` precedent) |
| `web/market/templates/market/main.js:59-68,121-142,162-199` | create the controller (`const alerts = createAlerts({store,bus,host,config})`), call `alerts.attach()`/`alerts.refresh()` in `buildChart`, `alerts.clearForSwitch()` in `switchTo` |
| `web/market/templates/market/chart.html:71-104` | + one `<dialog id="alert-dialog">` (native, CSP-safe, mirrors `#drawing-settings-dialog`) |
| `web/accounts/templates/registration/theme.css:253-261` | + `.chart-alert-bell` styles next to `.chart-context-menu` |

Marker precedent: `controllers/smc.js:235-238` (create), `:270,285`
(`setMarkers` re-render), `:225-228` (`detach`). The pure mapper precedent:
`smc-overlay-core.js:217-230` (`setupMarkers`).

### Tests to mirror

| Test | Pattern |
|---|---|
| `tests/js/smc-overlay-core.test.js:243-282` | pure `→ marker[]` assertions (deep-equal array) |
| `tests/js/chart-host.test.js:10-19` | crosshair/click surface exists + null-guarded |
| `tests/web/test_market_api.py:1243-1640` | full drawings CRUD matrix: auth 302, CSRF 403, 400 validation, isolation A≠B, partial PUT |
| `tests/web/test_market_ux.py:127-262` | allowlist route serving + import-graph resolution + no-inline-script |
| `tests/web/test_market_e2e.py:2578-2587` | seam-key count assertion (will fail if a 9th key is added) |
| `tests/web/test_alert_rule_crud.py` | HTML CRUD contract (must keep passing untouched) |
| `tests/test_alert_rules.py` | engine parity for the condition the bell emits |

## 4. The condition model (what the bell may create)

`parse_condition` accepts exactly three shapes (`src/alert_rules.py:101-119`,
frozen by `openspec/specs/alert-rules/spec.md` R2):

| `type` | Required keys | Constraint |
|---|---|---|
| `price` | `op ∈ {above, below}`, `level: number` | strict compare on latest **close** (`alert_rules.py:45-52,159-165`) |
| `indicator` | `name ∈ {rsi,sma,ema,atr,vwap}`, `params` (default `{}`), `op`, `level` | scalar only; `params` key names per `_SCALAR_PARAMS` (`:32-38,55-88`) |
| `smc_setup` | `direction ∈ {long,short,any}` (REQUIRED), `min_score: int` | `min_score` defaults `MIN_CONFLUENCE` (`:91-98`) |

**Recommended minimal UX:** the bell creates a `price` condition only —
`{type:"price", op:"above"|"below", level:<crosshair price>}`. That is the one
shape that maps 1:1 to "alert when price crosses *this line*", needs no
indicator warm-up, and has zero parameter surface. `above`/`below` is chosen by
a two-item `radio`/`select` in the dialog (default: `above` if the seeded level
is above the last close, else `below`). Deeper conditions remain the `/rules/`
page's job; a "More options →" link is optional.

**Important semantic gotcha (must be surfaced in the dialog copy).** The engine
is an **edge/state detector**, not a cross detector: `matches` is
`close > level` (`alert_rules.py:159-165`) and the worker fires on
`now && !prev` between the last two closed bars (`:203-216`,
`worker.py:175-183`). So `op:"above", level:100` fires *once*, on the first
closed bar whose close is above 100, not every time price crosses 100. The
dialog copy should say "fires when the candle close goes above 100" rather than
"crosses". This is a real UX/spec mismatch worth an explicit scenario.

**Interval validation gap (real constraint).** `CANDLE_INTERVALS` is
`tuple(INTERVAL_SECONDS)` = `5m, 15m, 30m, 1h, 2h, 4h, 1d, 1w, 1M`
(`web/trading/candles.py:19-30`) — it **excludes `1m`**, while the chart boots on
`1m` (`main.js:40`) and the toolbar exposes 14 intervals incl. `1m`, `3d`, `6h`,
`8h`, `12h` (`chart.html:21-34`, `market/quotes.py:38-53`). The form constrains
`interval` to `CANDLE_INTERVALS` (`forms.py:25`), so **a bell on 1m/3d/6h/8h/12h
cannot create a valid rule today**. The JSON endpoint MUST return the same 400,
and the bell must be disabled (with an accessible explanation) on those
intervals, or the UI will offer a create that can never succeed. This is a
first-class acceptance detail, not an edge case.

## 5. Design options + recommendation

### (a) Where the bell lives — new controller vs context-menu item

| Option | Pros | Cons |
|---|---|---|
| **A1. `controllers/alerts.js` owning its own crosshair + bell** | One module, one concern; markers + bell + dialog in one place; no change to F7 | One more `CONTROLLER_ALLOWLIST` entry (16→17) and more code |
| A2. F7 context menu gains "Add alert here" | Zero new DOM affordance; reuses `context-menu-core.menuModel` + `context-menu.js` action map | The issue explicitly asks for a **bell at the crosshair**; right-click is not the requested discoverability; pollutes the frozen `menuModel` contract (`context-menu-core.js:28-40`) and its tests |

**Recommend A1**, with the bell as a *hover-only* absolutely-positioned
`<button>` inside `#chart` (`position:relative`, `theme.css:94`) — the same
technique the legend overlay uses (`theme.css:118-121`). A **context-menu item is
still worth adding as a secondary path** ("Add alert at <price>") because it is
the keyboard/right-click route and needs no pointer hover; it reuses the
existing `ACTION` map (`context-menu.js:69-83`) — but only after A1 exists, as
an additive slice. Keep `menuModel` untouched if possible (a new item changes
its array contract and `context-menu-core.test.js`).

### (b) Markers mechanism

`createSeriesMarkers(series, markers)` is the v5 primitive and the exact SMC
precedent (`controllers/smc.js:235-238`). Markers are **not** series data, so
`#68` is satisfied by construction (`smc.js:4-5`). Marker `time` MUST match an
existing data point (LightweightCharts v5 rule), so a rule whose level is not on
a bar needs an anchor time: use `last_fired_at` for fired rules and, for armed
rules, the **last visible/loaded candle time** (the rule has no time of its own).
That is honest: an armed rule's marker means "level armed", pinned at the newest
bar.

**Recommend** a separate `createSeriesMarkers` handle owned by `alerts.js`
(not shared with SMC's handle — two independent primitives on one series is
fine; each is created with its own array). Use `shape` + `text`, not just
`color`: `arrowDown`/`"A"`-text for armed, `arrowUp`/`"F"` for fired, or an
`circle` + `text:"!"`. Must not be color-only (a11y).

### (c) Create-in-place vs open the rules page

Create in place via the dialog. Opening `/rules/new/` would discard chart state
(store/bus/host are page-scoped, `main.js:32-68`) and cannot be seeded with the
crosshair price without a query-param extension to the HTML form. **Recommend in
place.**

### (d) Bell "edit" behavior

The issue says create *or edit*. Minimal honest version: the bell always offers
**create** for the current pair at the crosshair price; if a `price` rule for the
same pair already sits within N pixels/ticks of the seeded level, the dialog opens
pre-filled in **edit** mode (PUT). Anything else (arbitrary rule selection) would
need hit-testing rule markers, which is more surface than the issue needs.

## 6. Pure-core split (CRITICAL for the ceiling)

Current ceilings (verified this session, `wc -l`, guard at
`tests/web/test_module_size_guard.py:20-23`, `CEILING=300`, `ALLOWLIST` empty):

```
smc.js=300      drawing-interaction.js=291   drawing-tools-core.js=284
drawing-interaction-core.js=285              main.js=274
chart-host.js=267   object-tree.js=263   smc-overlay-core.js=253
context-menu.js=208   drawing-primitive.js=196   chart-store.js=61   chart-bus.js=54
```

**`controllers/smc.js` is EXACTLY at 300 — zero headroom. Do not touch it.**
Markers for alerts must live in the new controller, never in `smc.js`.

| New module | Responsibility | Est. lines |
|---|---|---|
| `alert-markers-core.js` | `stateOf(rule)` (`fired`/`armed`/`inactive`), `markerFor(rule, anchorTime)`, `markersFor(rules, anchorTime)` → `{time, position, color, shape, text}[]`; pure, no imports | ~50 |
| `alert-condition-core.js` | `conditionFrom({op, level})` → `{type:"price",op,level}` + `levelFromInput(str)` (decimal parse, reject NaN/≤0) + `opFor(level, lastClose)` | ~40 |
| `controllers/alerts.js` | fetch/CRUD, crosshair→bell placement, dialog, `createSeriesMarkers` lifecycle, `clearForSwitch` | ~170 |

Ceiling proof: all three are new files, all well under 300. Existing modules
grow only additively and stay under the ceiling:

- `main.js` 274 → **~281** (+import, +`createAlerts(...)`, +`attach/refresh`
  in `buildChart`, +`clearForSwitch` in `switchTo`). 19 lines of headroom.
- `chart-host.js` **unchanged** (267).
- `chart-store.js` **unchanged** (61) — no new store key (§8).
- `chart-bus.js` **unchanged** (54) — reuse `chart:built` / `config:changed`;
  if a dedicated event is needed, add ONE `EVENTS` entry but that breaks
  `chart-bus.test.js:52-65` semantics tests only if they enumerate; they assert
  specific names, not an exact set. Cheapest: **no new event** (the controller
  reacts to `chart:built` + its own fetches).
- `chart.html` +1 `<dialog>`; `theme.css` +bell styles.
- `views.py` allowlists: `MODULE_ALLOWLIST` 28 → **30** (two cores),
  `CONTROLLER_ALLOWLIST` 16 → **17** (`alerts`). **The `== 16` assertions at
  `test_market_ux.py:146,195` MUST be updated** — that is an expected edit, and
  the same happened in F6/F9 (`test_market_ux.py:159-195`).

## 7. a11y + CSP

- **Bell**: a real `<button type="button" class="chart-alert-bell">` with
  `aria-label="Create alert at <price>"`; rendered only while the crosshair has
  a point (`param.point` present, mirroring `legend.js:190-196`); hidden
  (`hidden` attr, not `display:none` only) when the crosshair leaves. Keyboard:
  the bell is focusable, but the primary keyboard route is the context-menu item
  (§5a) because a hover-only control is unreachable by keyboard otherwise.
- **Dialog**: native `<dialog>` + `<form method="dialog">` (the pattern used
  three times already, `chart.html:71-104`); `showModal()` traps focus and
  returns focus to the invoking element on close — matching F7's
  `close(returnFocus)` (`context-menu.js:52-59`). Announce the created state via
  an `aria-live="polite"` node (mirror `#position-readout`, `chart.html:65`).
- **Markers are canvas** — invisible to assistive tech by definition. So the
  state must ALSO exist in the DOM: an `aria-live` summary
  ("3 alerts: 1 fired, 2 armed") and/or rows in the existing object tree/panel.
  Never rely on marker shape/color alone; a shape *and* a text label ("A"/"F")
  is the canvas-side non-color cue.
- **CSP**: no inline script/handler (`CSP_POLICY` has no `unsafe-inline` for
  scripts, `web/config/middleware.py:29-33`). The bell is built with
  `createElement` + `setAttribute` (mirror `context-menu.js:113-139`); inline
  `node.style.*` writes are already the established pattern and are allowed
  (`style-src 'unsafe-inline'`, `context-menu.js:143-150`). No new dependency.

## 8. Risk list

| # | Risk | Sev | Evidence / mitigation |
|---|---|---|---|
| R1 | **`smc.js` is exactly 300** — any edit overflows | **High** | `wc -l` = 300; guard `test_module_size_guard.py:20-23` (ALLOWLIST empty). New controller owns markers; `smc.js` byte-untouched. |
| R2 | **`window.marketChart` frozen 8 keys** | High | `main.js:59-68`; asserted `test_market_e2e.py:2578-2586`. Do NOT add a key — test via captured network + DOM + `aria-live`. |
| R3 | **`STORE_KEYS` frozen 11** | High | `chart-store.js:13-27`; `chart-store.test.js:75-89`. Alert selection/dialog state lives in the controller closure, never the store (precedent: selection at `drawing-interaction.js:55`). |
| R4 | **#68** — no `setData`/`update` from a controller | High | Markers go through `createSeriesMarkers` (`smc.js:235`); the `time` must exist on the series, so anchors come from `host.getCandles()` / `last_fired_at`, never a synthetic data point. |
| R5 | **No JSON API** — the bulk of the work, and the issue's premise is wrong | High | §2. Scope it as its own slice with the full CRUD matrix. |
| R6 | **Condition parity** — the bell must emit only `parse_condition`-valid shapes or every create 400s | High | Validate server-side with the SAME function the form uses (`forms.py:15,31-37`); client core emits the exact `{type:"price",op,level}`. |
| R7 | **`1m`/`3d`/`6h`/`8h`/`12h` cannot hold rules** | Med | `candles.py:19-30` vs `quotes.py:38-53`/`chart.html:21-34`. Disable the bell + explain, or the UI advertises an impossible create. |
| R8 | **Fired-state timing** — `last_fired_at` is written by the worker, not the request path | Med | `worker.py:178-183`. The chart shows a snapshot; it goes stale until the next list fetch. Recommend refetch on `chart:built` + on interval/symbol switch; do not poll. Copy must not promise live firing. |
| R9 | **Marker anchor time** — a marker whose `time` is not on the series is dropped by LWC v5 | Med | Verified in the LWC v5 docs (markers require an existing data point). Anchor armed rules at the newest candle time; fired rules at `last_fired_at`. |
| R10 | **Allowlist counts are asserted** (`== 16`) | Med | `test_market_ux.py:146,195`. Update deliberately (16→17, 28→30) + the import-graph test (`:226-262`) covers the new imports for free. |
| R11 | **Patch coverage 100%** | High | `patch-coverage-gate` R1, `.github/workflows/ci.yml:70`. Every new Python branch (400s, 404, CSRF, isolation) needs a test — mirror the drawings matrix, which is exhaustive. |
| R12 | **E2E class-C flake (#149)** | Med | Dev-only, `-m e2e -p no:randomly` on an idle machine (`README.md:60-61`). Assert DOM + captured requests, never pixels; readiness-gate on `window.marketChart.ready`. |
| R13 | **R14 `for_user`** | Med | Same discipline as `api_drawings` (`views.py:429,473,507`); `AlertRule` isolation already proven (`test_isolation.py:330-338`). |
| R14 | **Worker/fired parity** — a rule created by the bell must be one the worker can evaluate | Med | Worker skips intervals outside `CANDLE_INTERVALS` (`worker.py:167-168`) — same set the endpoint validates. Reusing the frozen engine is what makes this safe. |
| R15 | **Dialog + bell DOM inside `#chart`** must not eat chart input | Low | `pointer-events` rules like the legend (`theme.css:118-121`); the bell is the only interactive child and it is small. |

## 9. Open questions (real forks)

1. **Edit semantics** — does the bell offer edit of an *existing* rule (needs a
   proximity rule + which rule wins) or is create-only acceptable for v1 with
   edit deferred to `/rules/`? *(Recommend: create-only + "edit nearby price
   rule" when within a small price epsilon.)*
2. **Bell discoverability** — hover-only bell (issue's literal ask) vs bell +
   context-menu item. *(Recommend both, but land the bell first; the context
   menu item is a second slice.)*
3. **Armed-marker semantics** — is an armed rule's marker meaningful at the
   newest candle, or should armed rules render as a **price line**
   (`series.createPriceLine({price: level, title})`) instead, with markers
   reserved for `fired`? A price line at `condition.level` is arguably a much
   better fit for a `price` rule than a marker. *(Recommend: price line for
   `price`-type armed/fired rules + marker for the fired event. This changes the
   primitive, not the API.)*
4. **List scope** — GET by `(symbol, interval)` only, or `symbol`-wide with a
   client-side interval filter? A rule is interval-scoped for evaluation, so
   filtering to the active interval avoids showing markers for rules that will
   never fire on this chart. *(Recommend `(symbol, interval)`.)*
5. **`1m` rule support** — extend `CANDLE_INTERVALS` to include `1m` (worker
   change, new evaluation cadence, out of F10 scope) or disable the bell there?
   *(Recommend disable + a link to `/rules/`; extending the engine is a separate
   change.)*

## Prioritized brief for the next phase (sdd-propose)

- **Intent**: bell at the crosshair creates a `price` `AlertRule` in place, and
  the chart shows rule state (armed/fired) via a v5 markers primitive, all
  `for_user`-scoped and read-only.
- **In scope**: new JSON CRUD `/market/api/alerts` (GET/POST/PUT/DELETE)
  reusing `parse_condition` + `AlertRule.for_user`; new
  `alert-markers-core.js`, `alert-condition-core.js`, `controllers/alerts.js`;
  1 `<dialog>`; bell CSS; allowlist + preload entries; node + API + UX + E2E
  tests.
- **Out of scope**: orders (HARD), `src/` engine changes, new deps, CSP
  relaxation, `STORE_KEYS`/seam changes, extending `CANDLE_INTERVALS` to `1m`,
  worker/polling changes for live fired state.
- **Delivery**: comfortably >400 lines → chained PRs. Suggested slices:
  S1 = API + tests (server only); S2 = pure cores + node tests; S3 = controller
  + dialog + bell + markers + allowlists + E2E. Each slice independently
  verifiable; S3 depends on S1+S2.

### Ready for Proposal
**Yes.** The premise correction (no JSON API) is proven with file:line, the
condition vocabulary is enumerated with the edge-vs-cross semantic gotcha and
the `1m` interval gap called out, every touched module is sized against the
300-line ceiling (including `smc.js` at exactly 300), and the four real forks
are isolated in §9.

**Status**: success
**Summary**: Explored F10 against the D1/D2 alert stack and the F0/F1 chart; proved there is no JSON alert API (so the issue's "reuse the CRUD" is wrong), sized a drawings-style `/market/api/alerts`, mapped the bell/marker/client touch points with file:line, and proved the pure-core split keeps every module ≤300 including `smc.js` at exactly 300.
**Artifacts**: `openspec/changes/f10-alerts-on-chart/explore.md`
**Next**: sdd-propose
**Risks**: 300-line ceiling (`smc.js`=300 untouched), 8-key seam, 11 `STORE_KEYS`, #68, `1m` interval gap, condition parity with `parse_condition`.
