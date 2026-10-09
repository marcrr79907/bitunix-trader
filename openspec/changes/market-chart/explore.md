# Exploration: market-chart (Phase 4)

## Current State

- `web/` is a Django 5.2 project: `accounts` (auth/home/invites) + `trading`
  (global snapshots + owned models). Home page (`accounts/views.py:21-30`) is
  the auth-gating pattern: `home` redirects anonymous → login; protected views
  use `@login_required` + `@require_http_methods` (`accounts/views.py:33-34`).
  Root URLconf (`web/config/urls.py`) includes `accounts.urls` at `""`.
  `home.html:15` literally says "Market dashboard coming in the next phase" —
  this change replaces that stub.
- `src/client.py` has NO kline method (only `tickers`, `funding_rate_batch`,
  `positions`, `account`, `history_trades`, `history_orders`). The BitUnix REST
  kline endpoint is `GET /api/v1/futures/market/kline` — it fits `PUBLIC_PREFIX`
  (`src/client.py:19`) and the existing public `get()` path (`client.py:88-95`)
  with no signing.
- `src/indicators.py` is pure, index-aligned (`None` warm-up), stdlib-only —
  zips directly with candles. Enforced stdlib-only by `tests/test_boundary.py`
  `PURE_MODULES` tuple (`test_boundary.py:18`).
- NO CSP header exists anywhere (`base.py` MIDDLEWARE has no security-headers
  middleware; `prod.py` sets only HSTS/cookies). No inline `<script>` exists in
  any template today (`registration/base.html` is bare) — so a CSP adds risk
  only to new code, not existing pages.
- Tests: pytest-django with `DJANGO_SETTINGS_MODULE=config.settings.dev`
  (`pyproject.toml:20`); web tests live in `tests/web/` using `client` fixture,
  `@pytest.mark.django_db`, `force_login` (`test_ux.py:24-29`); network-free via
  `StubClient` doubles (`test_service_stubs.py:31`, `test_ingest.py:53`).
- CI (`.github/workflows/ci.yml`): L1 lint+tests+coverage, patch gate
  `diff-cover --fail-under=100` vs `origin/develop`, web gate 85%, L1
  core-isolation (imports `src/*.py` with Django absent, `ci.yml:72-103`), L1
  security (pip-audit + gitleaks), L2 docker build.

## Affected Areas

- `src/client.py` — add read-only `kline()` method (public endpoint, no auth).
- `web/market/` — NEW Django app: view + urls + template + JSON endpoint.
- `web/config/urls.py` — include `market.urls`.
- `web/config/settings/base.py` — add `"market"` to INSTALLED_APPS.
- `web/accounts/templates/accounts/home.html` — replace "coming next phase"
  stub with a link to `/market/`.
- `web/config/middleware.py` or settings — minimal CSP header (see Risks).
- `tests/web/test_market_api.py`, `tests/web/test_market_ux.py` — new suites.
- `tests/test_positions.py`-style unit tests for `kline()` mapping in `tests/`.
- `requirements-dev.txt` — add `pytest-playwright` (dev-only).
- `.github/workflows/ci.yml` — OPTIONAL: playwright E2E smoke job (see Risks).

## Architectural Decisions (APPROVED — validated with a live prototype + spikes, do NOT re-litigate)

| # | Decision |
|---|----------|
| A1 | Live candles: browser connects DIRECTLY to public BitUnix WS `wss://fapi.bitunix.com/public/` (no auth, `market_kline_<interval>` channels, 500ms push). Validated: 101 handshake with browser Origin, klines received in real Chromium. |
| A2 | Chart library: TradingView **Lightweight Charts v5.2.0** via CDN (revises earlier Chart.js decision). |
| A3 | History + indicators: Django JSON endpoint `/market/api/kline` reusing `src/client.py` (new read-only `kline()`) + `src/indicators.py` server-side. REST has NO CORS header — browser cannot call it directly (validated). |
| A4 | Candles are EPHEMERAL: no `Candle` model, no persistence, no migration. |
| A5 | Multi-user proxy (Django Channels) DEFERRED. |
| — | Overlays: single-source — `src/indicators.py` server-side; the forming candle renders WITHOUT overlay until it closes. NO indicator math duplicated in JS. |
| — | Layout: Variant A "chart-first" (large chart + side panel: pairs table + stats) — user-chosen from prototype. |
| — | Personal-first: single admin user; no multi-user features; `src.config.SYMBOLS`. |
| — | `pytest-playwright` in requirements-dev.txt (dev-only) for E2E smoke; Playwright MCP configured for orchestrator visual checks. |

## BitUnix API Facts (verified from docs)

- REST kline: `GET /api/v1/futures/market/kline?symbol=&interval=&limit=&startTime=&endTime=&type=`.
  limit default 100 max 200; intervals `1m 5m 15m 30m 1h 2h 4h 6h 8h 12h 1d 3d
  1w 1M`; `type` LAST_PRICE|MARK_PRICE; rate limit 10 req/s/ip. Response rows:
  `{open,high,low,close,time(ms),quoteVol,baseVol,type}`.
- WS public: `wss://fapi.bitunix.com/public/`; subscribe
  `{"op":"subscribe","args":[{"symbol":"BTCUSDT","ch":"market_kline_1min"}]}`;
  push every 500ms: `{ch, symbol, ts, data:{o,h,l,c,b,q}}`; snapshot after
  subscribe; interval switch REQUIRES unsubscribe first; max 5 msg/s, 300
  subs/connection.

## Key Findings (answers to the exploration questions)

### 1. Where the `/market/` view + templates + urls live

**New Django app `web/market/`** — the screaming-domain choice. Rationale:
- `trading` currently means "owned/global DB models" (models, ingest, no
  views, no urls.py at all). Adding views+templates there mixes two
  responsibilities.
- `accounts` is auth-domain only.
- `market` is a distinct user-facing capability (charts + live quotes); a
  separate app keeps the credential-scanner `REQUEST_PATH` tuple and
  INSTALLED_APPS additive.
- Per `core-domain-boundary` R9, `web/market` imports `src` (client,
  indicators, config) — same direction as `trading/ingest.py:15`.

Structure (mirrors `accounts` conventions):
```
web/market/
├── apps.py, __init__.py
├── views.py      # market_page (login_required), api_kline
├── urls.py       # app_name="market": "" → page, "api/kline" → JSON
└── templates/market/chart.html
```

Wiring:
- `web/config/urls.py`: `path("market/", include("market.urls"))` — wait, no:
  URLs must NOT be namespaced under "market/" prefix twice; follow accounts
  style: `path("", include("market.urls"))` with routes `path("market/", ...)`
  and `path("market/api/kline", ...)` inside `market/urls.py`. This matches
  how `accounts.urls` is included bare at `""` (`config/urls.py:13`).
- `base.py` INSTALLED_APPS += `"market"`.
- Home link: `home.html` gains `<li><a href="{% url 'market:page' %}">Market</a></li>`
  (or bare name if no app_name). NOTE: `accounts.urls` has NO app_name; the
  simplest consistent choice is **no app_name** in `market/urls.py` either,
  with names `market_page` / `market_api_kline`.

**Auth-gating pattern to follow** (`accounts/views.py`):
- Page view: `@login_required` + `@require_http_methods(["GET"])` (like
  `invite_create`, `views.py:33-34`). Anonymous → redirected to `/login/` by
  the decorator.
- JSON API view: same `@login_required` (the page's JS runs authenticated).
- No staff gate needed for the page (personal-first: single admin user; any
  authenticated user may view). If staff-only wanted: `request.user.is_staff`
  → `PermissionDenied` as in `views.py:36-37` — flag for user decision.

### 2. `kline()` client method — signature, mapping, placement, testing

Placement: under the `# --- public market endpoints ---` section of
`src/client.py` (after `funding_rate_batch`, `client.py:122-124`), alongside
its siblings.

Signature (deepest interface: mapping + normalizing inside the module):
```python
def kline(
    self,
    symbol: str,
    interval: str = "1m",
    limit: int = 100,
) -> list[dict]:
    """Public OHLC candles, newest LAST, unix-seconds `time`.

    Returns rows of {time: int(seconds), open, high, low, close: float}.
    Raises BitunixError on HTTP != 200 or API code != 0 (via _unwrap).
    """
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    rows = self.get(f"{PUBLIC_PREFIX}/kline", params)
    return [
        {
            "time": int(r["time"]) // 1000,      # ms -> unix seconds
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
        }
        for r in (rows or [])
    ]
```
- Mapping done ONCE at the boundary (same principle as `ingest.py:38`
  epoch-ms→UTC): `time` ms → unix seconds, numeric fields → `float`.
- No `startTime`/`endTime`/`type` params initially (YAGNI: limit-based history
  covers the chart; add when needed). Keep `type` defaulting to LAST_PRICE
  server-side (BitUnix default).
- Testing without sockets: same pattern as `tests/test_positions.py` /
  `tests/web/test_ingest.py` — a stub is NOT needed for the client itself;
  instead monkeypatch `requests.get` (or use a `StubClient` subclass) and
  assert the mapping:
  - GIVEN a fake response payload `{"code":0,"data":[{"time":1700000000000,
    "open":"50000.5","high":"51000","low":"49000","close":"50500"}, ...]}`
    WHEN `kline("BTCUSDT")` runs
    THEN returns `[{"time":1700000000000//1000, "open":50000.5, ...}]` with
    float types.
  - GIVEN API `code != 0` THEN raises `BitunixError` (via `_unwrap`).
  - GIVEN empty data THEN returns `[]` (never raises).
  Tests live in `tests/` (core, no Django): `tests/test_client_kline.py`.

### 3. `/market/api/kline` endpoint design

**Location**: `web/market/views.py`.

**Auth/CSRF**: `@login_required` + `@require_http_methods(["GET"])`. GET has
no CSRF exposure (CSRF protects unsafe methods only; `CsrfViewMiddleware` is
already in the stack, `base.py:89`). Session cookie auth means the browser
fetch from the page works with no extra headers. CORS: same-origin (Django
serves both page and endpoint) — no `django-cors-headers` needed.

**Response shape EXACTLY matching Lightweight Charts v5**:
```json
{
  "candles": [{"time": 1700000000, "open": 50000.5, "high": 51000.0,
               "low": 49000.0, "close": 50500.0}],
  "overlays": {
    "sma":    [{"time": 1700000140, "value": 50250.0}],
    "ema":    [{"time": 1700000140, "value": 50240.0}],
    "vwap":   [{"time": 1700000000, "value": 50100.0}],
    "rsi":    [],
    "atr":    [],
    "zscore": []
  }
}
```
- `candles`: sorted ascending by `time`, no duplicates (Lightweight Charts
  v5 THROWS "Value is null" otherwise — prototype gotcha). The REST API
  returns ascending rows; the view MUST defensively sort + dedupe by `time`
  before serializing.
- `overlays`: each overlay is a list of `{time, value}` with GAPS OMITTED —
  `None` warm-up positions from `src/indicators.py` are simply not emitted
  (series arrays must not contain `null` — prototype gotcha). Indicator math
  runs server-side via `src/indicators.py` — NO duplication in JS.
- Overlay windows: pick sensible defaults in design (e.g. sma=20, ema=50,
  rsi=14, atr=14) — design phase decision.
- RSI/ATR/zscore as line overlays on price scale are questionable
  (different scale); design must decide whether they ship in v1 payloads or
  only sma/ema/vwap. (Open question below.)

**Error handling**:
- Unknown/invalid symbol: BitUnix REST returns `code != 0` → `BitunixError` →
  view catches and returns `JsonResponse({"error": "..."}, status=400)` with a
  generic message (no internals leak). Given/When/Then covered.
- Empty kline list: return `{"candles": [], "overlays": {...empty}}` with 200
  (chart shows "no data" state) — an empty result is not an error.
- `limit` clamp: validate/clamp query param to `[1, 200]` server-side
  (BitUnix max 200); interval validated against the allowlist of 14 values —
  reject with 400 before hitting the API.
- Never 500 on upstream failure: catch `BitunixError` +
  `requests.RequestException` → 502 `{"error": "upstream"}`.

**Testing without network** (mirror `test_ingest.py` stub pattern):
- `StubClient` with `kline()` returning fixtures; monkeypatch the view's
  client factory (the view must ACCEPT a client, not create it — or import a
  module-level `_client()` helper that tests monkeypatch. Design decision:
  view calls `get_kline_payload(client, symbol, interval, limit)` in a
  separate module `web/market/quotes.py` — pure-ish seam, testable via stub
  client with NO monkeypatching, exactly like `fetch_market(client, symbols)`).
- Scenarios: happy path (shape, sort, dedupe), overlay gap omission,
  invalid interval → 400, limit clamp, unknown symbol → 400, upstream error →
  502, unauthenticated → 302 to login.

### 4. Frontend wiring (chart.html)

- **CDN script**: `<script src="https://unpkg.com/lightweight-charts@5.2.0/dist/lightweight-charts.standalone.production.js"></script>`
  (v5 standalone build; exposes global `LightweightCharts`). Pin exact version.
  v5 API differs from v4: `chart.addSeries(LightweightCharts.CandlestickSeries, {...})`
  instead of v4 `chart.addCandlestickSeries({...})`. The prototype validated
  v5.2.0 — encode the v5 call form and PIN 5.2.0.
- **WS client in page** (vanilla JS, ~80 lines):
  - Connect `wss://fapi.bitunix.com/public/`, subscribe
    `{"op":"subscribe","args":[{"symbol":SYM,"ch":"market_kline_<interval>"}]}`.
  - Forming candle: bucket `ts` to interval start (`Math.floor(ts / (intervalSec*1000)) * intervalSec`)
    → unix seconds; `series.update({...})` — updates in place instead of
    duplicating (gotcha: without bucketing, Lightweight Charts throws on
    duplicate/out-of-order time).
  - Closed candle: when the bucketed time advances past the last stored time,
    the previous candle is final. Fetch-on-interval-switch: on interval or
    symbol change → `unsubscribe` FIRST (BitUnix requirement), then subscribe,
    then re-fetch history from `/market/api/kline`.
  - Reconnect/backoff: on `close`/`error` → reconnect with exponential
    backoff (1s, 2s, 4s… cap 60s); resubscribe on open. Guard against storms:
    jitter + cap; page visibility change can pause (design decision).
  - Overlays: `createPriceLine`-free — overlays are LineSeries fed from
    `/market/api/kline` `overlays`; forming candle updates ONLY the
    candlestick series (overlay stays frozen until close — approved decision).
- **Interval switch ordering** (encode as a requirement): unsubscribe →
  subscribe → refetch. Never subscribe twice without unsubscribe (BitUnix
  rejects / duplicates pushes).
- **Stats panel**: side panel with pairs from `src.config.SYMBOLS` served into
  template context (or fetched); stats (last price, change) from WS pushes.

### 5. CSP (currently NO CSP exists)

Today: no `Content-Security-Policy` anywhere — `base.py` MIDDLEWARE has
SecurityMiddleware but no CSP config; `prod.py` sets HSTS/cookies only. No
inline `<script>` in any existing template.

**Decision — minimal CSP via settings-level header middleware**, not a
package: a ~15-line custom middleware `config/middleware.py` addition (or
`SecurityMiddleware`'s built-in? No — Django SecurityMiddleware has no CSP).
Options compared:
- Custom 15-line middleware setting the header on every response: full
  control, zero deps. RECOMMENDED.
- `django-csp` package: battle-tested but new runtime dependency for one
  header. Overkill (Ponytail: don't add a dep for a header).

Policy (single strict policy, all envs):
```
Content-Security-Policy:
  default-src 'self';
  script-src 'self' https://unpkg.com;
  style-src 'self' https://unpkg.com;
  connect-src 'self' wss://fapi.bitunix.com;
  img-src 'self' data:;
  frame-ancestors 'self'
```
- `connect-src wss://fapi.bitunix.com` authorizes the direct WS (A1).
- `script-src/style-src https://unpkg.com` authorizes the CDN.
- Risk of breaking `/healthz`: NONE for the response itself (healthz returns
  JSON, no resources), BUT the middleware short-circuits healthz in
  `HealthProbeHostMiddleware` (`middleware.py:27-29`) — if the CSP middleware
  sits AFTER it, healthz never gets the header (fine) and is unaffected. If
  CSP wraps ALL responses including healthz, also fine (a header on JSON is
  harmless). Either way, add a test asserting healthz still 200s.
- Risk of breaking admin: Django admin uses inline scripts AND inline event
  handlers (`onclick=`) → a strict CSP WITHOUT `'unsafe-inline'` BREAKS the
  admin UI. This is the #1 CSP risk. Mitigations (design must pick one):
  a) Add `'unsafe-inline'` (weakens CSP, pragmatic for personal-first).
  b) Path-conditional header: skip CSP (or add admin allowances) on
     `/admin/*`. RECOMMENDED — keep CSP strict for market pages, absent for
     admin, until admin is CSP-audited.
  c) Nonces via middleware — proper but heavier; defer.
- Tests: assert header present + correct on `/market/` (authenticated), AND
  `healthz` still 200, AND admin pages still render (status 200 on admin
  login page).

### 6. pytest-playwright E2E smoke

- What it asserts (DOM, NOT image diff — the orchestrator's model cannot read
  images):
  1. `/market/` page loads authenticated: chart container div exists.
  2. `LightweightCharts` global is defined (JS-evaluated).
  3. Canvas element for the chart exists (`table` DOM inside container —
     Lightweight Charts renders canvases).
  4. **Against a mock/live-server-backed API**: the API endpoint returns 200
     JSON with `candles` key (tested separately via Django test client — no
     browser needed).
  5. Optional live-WS smoke: skip in CI (flaky, external dependency). The
     E2E smoke in CI asserts static wiring only: page renders, script tag
     present, container exists, no JS console errors on load (WS errors
     tolerated since external).
- Fixtures: `pytest-playwright` provides `page` fixture; auth via
  `page.context.add_cookies` after hitting login, or simpler: use Django
  `live_server` fixture (pytest-django) + force session cookie. Standard
  pattern: `live_server` + Django `client` login → extract `sessionid` cookie
  → `browser.new_context()` → `add_cookies`.
- Coexistence with pytest-django: pytest-playwright is a separate plugin;
  mark tests with `@pytest.mark.e2e` (custom marker registered in
  `pyproject.toml`) or rely on the `page` fixture. CRITICAL for CI: run the
  E2E tests in a SEPARATE pytest invocation with
  `--browser chromium --headed=false`, NOT in the main coverage run
  (playwright browsers install + timing pollutes L1; also headless chromium
  in CI needs `--with-deps` install step). CI: add optional/allow-fail job or
  keep E2E local-only (dev-only requirement) — decision flag.
  - Recommendation: mark `@pytest.mark.e2e`, `addopts = "-m 'not e2e'"` NOT
    set globally (would need edit), instead CI runs `python -m pytest -m "not
    e2e"` in L1 and E2E locally / optional CI job with browser install.
- requirements-dev.txt: `pytest-playwright>=0.5` (pulls `pytest`,
  `playwright`). Dev-only — runtime `requirements.txt` UNTOUCHED (R7-style
  invariant from market-ingestion).

### 7. Requirements (R-numbers) this change introduces

New capability spec `market-chart` (kebab-case), R-numbers R1–R6 (fresh
numbering inside the capability, same as market-ingestion did):
- **R1 — Authenticated chart page** (`/market/`): login_required GET, renders
  chart-first layout (Variant A), links from home.
- **R2 — Kline history API** (`/market/api/kline`): login_required GET JSON;
  candles sorted/deduped ascending, `time` unix seconds; overlays with omitted
  gaps; invalid interval/symbol/limit → 4xx; upstream failure → 502; empty →
  200 empty payload.
- **R3 — Read-only kline client method** (`src/client.py::kline`): public
  endpoint, ms→s mapping, float normalization; tested without sockets.
- **R4 — Live WS candles** (browser-direct): subscribe/unsubscribe lifecycle,
  interval-switch ordering (unsubscribe first), forming-candle bucketing,
  reconnect with capped exponential backoff.
- **R5 — Minimal CSP**: strict policy for market pages (script/style CDN
  allowlist + wss connect-src); `/admin/*` and `/healthz` unaffected; no
  inline-script breakage on existing pages (there are none today).
- **R6 — E2E smoke (dev-only)**: DOM-assertion Playwright smoke, excluded from
  the coverage L1 run, `pytest-playwright` dev-only, runtime deps unchanged.

Constraints carried (not new R-numbers, but MUST-hold): R9 core boundary
(`web/market` MAY import `src`, `src` stays framework-free — `kline()` uses
only `requests`), R11 read-only (kline is a GET market endpoint — the order
scanner's read-path list must NOT match `/market/kline`; verified: scanner
forbids `/trade/place_order`, `/tpsl/`, `/account/change_*` — none match),
R12 no secrets, patch gate 100% on changed lines, web gate 85%.

### 8. Scope boundaries

**In**: new `market` app (page + API + template), `kline()` client method,
WS wiring in page, CSP middleware + tests, playwright smoke (dev),
INSTALLED_APPS + urls + home link, tests.
**Out**: Django Channels/multi-user WS proxy (A5 deferred), Candle model /
persistence / migrations (A4), indicator math in JS (single-source
server-side), `startTime`/`endTime`/`type` kline params (YAGNI until needed),
alerts on chart, RSI/ATR separate panes (maybe only payload-ready), retouching
`scheduler`/`worker`, multi-symbol simultaneous WS streams (single-pair chart;
pairs table switches the chart).

## Approaches (for the record — architecture was pre-approved via prototype)

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| A. Browser-direct WS + Django JSON history (APPROVED A1-A4) | No Channels infra; REST has no CORS so Django endpoint is forced anyway; ephemerality keeps DB clean; prototype-validated | WS logic in page JS; CSP needed; two data paths (REST+WS) | Medium |
| B. Django Channels WS proxy | Single data path; server-side reconnect | New infra (redis channels layer), deployment complexity, re-litigates A5 | High |
| C. Polling REST from Django view | Simplest | 10 req/s/ip limit shared; no real-time; latency | Low |

## Risks

- **CSP breaks Django admin** (inline handlers) — HIGH impact, MED likelihood.
  Mitigation: path-conditional CSP (skip on `/admin/*`) + regression tests for
  admin login page + healthz.
- **WS reconnect storm** (all tabs reconnecting on BitUnix blip) — MED/MED.
  Mitigation: capped exponential backoff + jitter; single connection per page;
  personal-first single user makes storm unlikely.
- **v5 vs v4 CDN API differences** (`addSeries` vs `addCandlestickSeries`) —
  MED/LOW: pin `lightweight-charts@5.2.0` exactly; encode v5 call form in
  design + E2E smoke asserts the global loads.
- **Interval switch ordering** (subscribe-without-unsubscribe duplicates
  pushes / BitUnix rejects) — MED/LOW: encode ordering requirement R4 +
  JS lifecycle guard.
- **Symbol not found on REST** (`code != 0`) — LOW: 400 with generic error,
  test covered.
- **Data gaps when worker hasn't run**: irrelevant for kline (REST history
  comes live from BitUnix, NOT from `TickerSnapshot` tables). Document that
  the pairs-table stats COULD later use snapshots, but v1 uses WS/REST only.
- **`time` type mismatch** (Lightweight Charts wants UNIX seconds; accepts
  number; business-day string also accepted) — LOW: single mapping point in
  `kline()` + endpoint dedupe/sort, E2E asserts no console errors.
- **Playwright in CI** (browser install weight, flakiness) — LOW: dev-only +
  separate invocation; CI job optional/allowed to fail, or local-only.
- **patch gate 100% on JS** — the inline page JS is inside an HTML template;
  diff-cover measures Python only by default (`coverage xml`), so template
  JS lines don't count. Flag: keep JS minimal and validated by E2E smoke
  instead of coverage.

## Ready for Proposal

YES — all exploration questions answered with file references; architecture
pre-approved (A1–A5); scope boundaries explicit; the only open decisions for
spec/design are listed in the proposal's Open Questions (CSP admin strategy,
overlay set for v1, E2E in CI or local-only, staff-gate on market page).
