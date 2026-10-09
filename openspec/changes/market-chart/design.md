# Design: market-chart (Phase 4)

## Technical Approach

Three layers, one source of truth for indicator math:

    Browser (chart.html + chart.js)
      ├─ REST GET /market/api/kline ──▶ views.api_kline ──▶ quotes.get_kline_payload(client, …)
      │                                                    ├─ client.kline() ──▶ BitUnix REST (public)
      │                                                    └─ src/indicators.py (server-side)
      │                                  ◀── {candles, overlays}
      └─ WS wss://fapi.bitunix.com/public/  (direct, A1)
            subscribe market_kline_<ch> ──▶ 500ms pushes ──▶ bucket ts ──▶ series.update()

History + overlays come from Django (A3); live candles flow browser-direct (A1).
Overlays are computed only in `src/indicators.py` — the forming candle updates
the candlestick series alone; overlays catch up via a throttled REST refetch on
bucket advance. Candles are ephemeral (A4). Personal-first: `src.config.SYMBOLS`.

## Backend Design

### `src/client.py::kline()` (R3) — public section, after `funding_rate_batch`

```python
def kline(self, symbol: str, interval: str = "1m", limit: int = 100) -> list[dict]:
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    rows = self.get(f"{PUBLIC_PREFIX}/kline", params)  # unsigned public GET
    return [{"time": int(r["time"]) // 1000, "open": float(r["open"]),
             "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])}
            for r in (rows or [])]
```

Mapping done once at the seam (same principle as `ingest.py:38`): ms→unix-seconds
int, prices→float. Empty `data` → `[]`; HTTP/API failure → `BitunixError` via
`_unwrap`. No `startTime`/`endTime`/`type` (YAGNI). Raises nothing else.

### `web/market/` app (mirrors `accounts` conventions; no `app_name`, bare names)

```
web/market/
├── __init__.py, apps.py
├── views.py      # market_page, api_kline, chart_js — @login_required + GET-only
├── urls.py       # "market/", "market/api/kline", "market/chart.js"
├── quotes.py     # get_kline_payload(client, symbol, interval, limit) + INTERVALS
└── templates/market/chart.html, chart.js
```

`quotes.py` is the pure-ish seam (copy of the `fetch_market(client, symbols)`
pattern from `ingest.py:19` — accepts a stub-able client, no monkeypatching):

```python
INTERVALS = ("1m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d","3d","1w","1M")

def get_kline_payload(client, symbol, interval, limit) -> dict:
    candles = sorted({c["time"]: c for c in client.kline(symbol, interval, limit)}.values(),
                     key=lambda c: c["time"])          # dedupe (last wins) + ascending
    times  = [c["time"] for c in candles]
    closes = [c["close"] for c in candles]
    return {"candles": candles, "overlays": {
        "sma20": _zip(times, indicators.sma(closes, 20)),
        "ema20": _zip(times, indicators.ema(closes, 20)),
        "rsi14": _zip(times, indicators.rsi(closes, 14))}}

def _zip(times, values):   # gaps omitted — series arrays must never contain null
    return [{"time": t, "value": v} for t, v in zip(times, values) if v is not None]
```

`views.api_kline`: validate `interval` against `INTERVALS` (else 400), clamp
`limit` to `[1, 200]` (else 400), call `get_kline_payload(BitunixClient(), …)`.
`market_page` renders `chart.html` with `symbols=config.SYMBOLS`. `chart_js`
renders `chart.js` with `symbols` as JSON, `content_type="text/javascript"` —
serves the page's JS same-origin (see CSP decision (f): no static/collectstatic
infra exists in prod, and inline JS would force `'unsafe-inline'`).

### Exact JsonResponse shape (R2)

```json
{"candles": [{"time": 1700000000, "open": 50000.5, "high": 51000.0, "low": 49000.0, "close": 50500.0}],
 "overlays": {"sma20": [{"time": 1700000140, "value": 50250.0}],
              "ema20": [{"time": 1700000140, "value": 50240.0}],
              "rsi14": [{"time": 1700000140, "value": 61.2}]}}
```

**Deviation from the orchestrator's sketch, settled deliberately**: `rsi14` is a
`{time,value}` list, not a `<number|null>` scalar. Spec R3/R4 pin overlays as
uniform lists with gaps omitted; a scalar would fork the payload contract. The
side panel extracts `rsi14.at(-1)?.value` — presentation belongs to JS.

### Error contract (settles the 502-vs-500 question)

| Condition | Response |
|---|---|
| `interval` not in allowlist, `limit` outside `[1,200]`, non-int limit | 400 `{"error": "…"}` generic |
| Upstream rejects request (`BitunixError`, API `code != 0`, e.g. unknown symbol) | 400 `{"error": "…"}` generic (spec scenario pins this) |
| Network failure (`requests.RequestException`: timeout, conn refused) | 502 `{"error": "upstream"}` |
| Empty upstream list | 200, `{"candles": [], "overlays": {"sma20": [], "ema20": [], "rsi14": []}}` |

Never 500. Accepted edge (ponytail: rare, cosmetic): a BitUnix HTTP 5xx raises
`BitunixError` indistinguishable from an API-code rejection → 400. The 502 path
is what "upstream failure" means operationally (spec text is normative but had
no scenario — tasks.md must add the 502 test).

### Auth gating

`@login_required` + `@require_http_methods(["GET"])` on all three views
(`accounts/views.py:33-34` pattern). Anonymous → 302 `/login/`. No staff gate
(personal-first: single admin; any authenticated user may view). GET needs no
CSRF; same-origin fetch needs no CORS.

## Frontend Design

`chart.html` extends `registration/base.html`: `<div id="chart">` (Variant A
chart-first, ~480px), side panel (pairs buttons from `symbols`, RSI readout,
interval select), then the pinned CDN script and `{% url 'market_chart_js' %}`.
v5 init: `chart.addSeries(LightweightCharts.CandlestickSeries, {...})` +
`LineSeries` for sma20/ema20 (v4 `addCandlestickSeries` is gone). No build step.

### WS lifecycle contract (chart.js, testable pseudo-code)

```js
const WS_URL = "wss://fapi.bitunix.com/public/";
let ws, sub = null, retry = 0, fetchTimer = null;

const backoff = () => Math.min(1000 * 2 ** retry, 60000) * (0.5 + Math.random()); // cap 60s, jitter
const bucket  = (tsMs, sec) => Math.floor(tsMs / 1000 / sec) * sec;  // ms → interval-start unix s

function onPush(m) {                                   // {symbol, ts, data:{o,h,l,c}}
  const t = bucket(m.ts, INTERVAL_SEC[sub.interval]);  // FORMING-CANDLE BUCKETING
  candleSeries.update({time: t, open:+m.data.o, high:+m.data.h, low:+m.data.l, close:+m.data.c});
  if (lastTime && t > lastTime) scheduleRefetch();     // candle closed → overlays catch up
}                                                      // scheduleRefetch: debounce 2s, once per bucket

function connect() {
  ws = new WebSocket(WS_URL);
  ws.onopen    = () => { retry = 0; if (sub) sendSubscribe(sub); };  // resubscribe after reopen
  ws.onmessage = (e) => onPush(JSON.parse(e.data));
  ws.onclose   = () => { setTimeout(connect, backoff()); retry += 1; };
  ws.onerror   = () => ws.close();
}

function sendSubscribe(next) {                         // ORDERING GUARANTEE
  if (sub) ws.send(JSON.stringify({op: "unsubscribe", args: [chFor(sub)]})); // BEFORE subscribe
  sub = next;
  ws.send(JSON.stringify({op: "subscribe", args: [chFor(sub)]}));
}

function switchTo(symbol, interval) {                  // symbol/interval switch flow
  if (ws && ws.readyState === 1) sendSubscribe({symbol, interval});
  else sub = {symbol, interval};                       // pending; sent on open
  fetchHistory(symbol, interval);                      // REST redraw: setData + overlays
}
```

Invariants: unsubscribe strictly precedes subscribe on the same socket (BitUnix
requirement); `retry` resets on open; delay = 1s·2ⁿ capped 60s with ±50% jitter
(storm guard); one socket per page; `series.update()` only ever receives
ascending bucketed times (no duplicate-time throw). WS channel map
(`1m→market_kline_1min`, `1h→market_kline_60min`, …) verified live for 1min in
the spike; higher intervals get an apply-time live check.

## CSP Design

Custom ~12-line middleware in `web/config/middleware.py` (Django has no CSP
setting; `django-csp` is a new runtime dep for one header — rejected):

```python
CSP_POLICY = ("default-src 'self'; script-src 'self' https://unpkg.com; "
              "style-src 'self' 'unsafe-inline' https://unpkg.com; "
              "connect-src 'self' wss://fapi.bitunix.com; img-src 'self' data:")
CSP_EXEMPT = ("/admin/",)

class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith(CSP_EXEMPT):
            response.headers.setdefault("Content-Security-Policy", CSP_POLICY)
        return response
```

Placed **last** in `MIDDLEWARE`. `HealthProbeHostMiddleware` short-circuits
`/healthz` first, so healthz never reaches it (naturally unaffected). `/admin/*`
is exempt: Django admin uses inline handlers and would break under a strict
`script-src`. What could break, enumerated: **admin** → exempted; **healthz** →
skipped by ordering (regression test: still 200); **login/home/invites** → no
inline scripts, strict CSP safe (form-action falls back to `default-src 'self'`,
same-origin posts fine); **chart.js** → same-origin under `'self'`; **unpkg CDN
down** → chart missing, page loads; **gunicorn/Railway** → plain WSGI header,
unaffected; **style attributes** on the chart page → covered by `'unsafe-inline'`
in `style-src` only (script-src stays strict — no unsafe-inline). Regression
tests pin: CSP present on `/market/` (authenticated), CSP **absent** on admin
login, healthz 200.

## Testing Strategy

Strict TDD (`python -m pytest`), RED-GREEN-REFACTOR per `config.yaml`.

| Layer | What | How |
|-------|------|-----|
| Unit (`tests/test_client_kline.py`) | URL/params (no signing), ms→s + float mapping, `BitunixError`, empty→`[]` | monkeypatch `requests.get`; core, no Django |
| Integration (`tests/web/test_market_api.py`) | payload shape/sort/dedupe/gap-omission/sma count N−w+1; endpoint 200/400-interval/400-reject/502/302/limit-clamp | stub client via `quotes.get_kline_payload` (no monkeypatch); view errors via monkeypatched `market.views.BitunixClient` |
| Integration (`tests/web/test_market_ux.py`) | page 200 + chart container; home link; anonymous 302; CSP present/absent matrix; healthz 200 | `client` fixture + `force_login` (`test_ux.py` pattern) |
| E2E (`tests/web/test_market_e2e.py`, dev-only) | `LightweightCharts` global defined, canvas exists, no console errors on load (WS errors tolerated) | `live_server` + session cookie + `page`; DOM-only, no image diffs |

**E2E marking**: `e2e` marker registered in `pyproject.toml`;
`addopts = "-q -m 'not e2e'"` (CLI `-m e2e` overrides it locally). **CI runs
dev-only E2E = no CI job, `ci.yml` stays unchanged** — the addopts deselect
makes CI's existing invocation safe. Local run: `pip install pytest-playwright`
(via requirements-dev) → `playwright install chromium` once → `python -m pytest
-m e2e`. Justification: browser download (~120MB) + install step + flake risk
inside L1's 15-min timeout buys near-zero assurance — the smoke asserts wiring
integration tests already cover, and live WS is an external dependency.
Revisit (optional CI job) if page JS grows real logic.

**Honest coverage note**: `chart.js` is a rendered template — diff-cover measures
Python only, so the WS/JS lines are invisible to the patch gate. E2E is the JS
verification layer; keep JS minimal (~120 lines) and never move business math
into it.

## Architecture Decisions

| # | Decision | Choice | Alternatives | Rationale |
|---|----------|--------|--------------|-----------|
| a | Chart lib | Lightweight Charts v5.2.0 CDN-pinned | Chart.js + financial plugin (memory decision — revised) | Purpose-built OHLC + time axis, ~45KB, v5 `addSeries` prototype-validated; Chart.js fights financial time axes |
| b | Live transport | Browser-direct public WS (A1) | Django Channels proxy (A5) | Zero new infra (no redis/channels layer); public data needs no auth; A5 deferred — re-litigating it costs deployment complexity for one user |
| c | Candle storage | Ephemeral, no model/migration (A4) | `Candle` model + persistence | REST history + WS live make storage speculative; avoids market-ingestion's 11,520-rows/day unbounded growth; rollback = delete branch |
| d | CSP mechanism | Path-conditional custom middleware, last in stack | Global strict header; `django-csp`; nonces | Admin breaks under strict CSP (inline handlers) — exemption is 1 prefix check; package = new runtime dep for one header; nonces deferred until admin CSP audit |
| e | Indicator math | Server-side only (`src/indicators.py` via `quotes.py`) | Duplicated JS math | Single source of truth; `indicators.py` is stdlib-only and suite-tested; JS math = two truths + untested code. Cost: overlay lags until refetch (accepted, approved) |
| f | Page JS delivery | Served same-origin via `chart_js` view | Inline `<script>` in template | No static/collectstatic infra exists in prod (Dockerfile has none); inline JS forces `script-src 'unsafe-inline'`, defeating the CSP this change adds. Cost: one 4-line view |
| g | Overlay set v1 | sma20 + ema20 lines on price scale; rsi14 as list (side panel shows last) | RSI/ATR panes; vwap | Only MA lines share the price scale; RSI-on-price-scale is wrong; side-panel scalar satisfies RSI read w/o a pane; panes deferred (proposal) |

## Boundary Note

- `src/` stays framework-free: `kline()` uses only `requests` — `core-isolation`
  CI + `tests/test_boundary.py` green.
- `web/market` imports `src.{client,indicators,config}` — the R9-permitted
  direction (`ingest.py:15` precedent). No reverse import.
- `kline()` is a **public read-only GET**: `/api/v1/futures/market/kline`
  matches no `FORBIDDEN_PATHS` fragment and no `ORDER_VERBS` verb
  (`test_no_order_surface.py:19-68` — verified); scanner stays green.
- Credential scanner completeness: `REQUEST_PATH` (`test_credentials_mechanism.py:20`)
  gains `WEB / "market"` — every request-serving app stays scanned (R13.2 spirit).
- Worker/scheduler untouched. No user-owned data (ephemeral, global quotes).

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/client.py` | Modify | Add `kline()` under public market endpoints |
| `web/market/` (`__init__.py`, `apps.py`, `views.py`, `urls.py`, `quotes.py`) | Create | New app: page, JSON endpoint, JS view, payload seam |
| `web/market/templates/market/chart.html` | Create | Chart-first page (Variant A), CDN script tag |
| `web/market/templates/market/chart.js` | Create | WS client + chart init (~120 lines, v5 API) |
| `web/config/urls.py` | Modify | `include("market.urls")` |
| `web/config/settings/base.py` | Modify | `INSTALLED_APPS += "market"`; CSP middleware last |
| `web/config/middleware.py` | Modify | `ContentSecurityPolicyMiddleware` |
| `web/accounts/templates/accounts/home.html` | Modify | Replace stub text with `/market/` link |
| `tests/test_client_kline.py` | Create | kline mapping + error suites |
| `tests/web/test_market_api.py` | Create | Payload + endpoint + error contract suites |
| `tests/web/test_market_ux.py` | Create | Page, home link, CSP matrix suites |
| `tests/web/test_market_e2e.py` | Create | Dev-only Playwright smoke (`@pytest.mark.e2e`) |
| `tests/web/test_credentials_mechanism.py` | Modify | `REQUEST_PATH += web/market` |
| `pyproject.toml` | Modify | `e2e` marker; `addopts = "-q -m 'not e2e'"` |
| `requirements-dev.txt` | Modify | `pytest-playwright>=0.5` (dev-only) |
| `.github/workflows/ci.yml`, `requirements.txt`, `web/worker.py`, `web/scheduler.py` | Unchanged | addopts deselects e2e; runtime deps untouched; worker out of scope |

## Task Breakdown Hint

~600–800 changed lines vs 400 budget → **High risk → chained PRs** (orchestrator
confirms with user per ask-on-risk):

- **PR1 — backend (autonomous)**: `kline()` + `quotes.py` + `views.py`/`urls.py`
  + INSTALLED_APPS + `test_client_kline.py` + `test_market_api.py` (~300 lines).
  Verifies headless (no browser). Clean start/finish/rollback; endpoint fully
  usable via curl.
- **PR2 — frontend (targets PR1 branch)**: `chart.html` + `chart.js` + CSP
  middleware + home link + e2e marker/`requirements-dev.txt` + UX/E2E suites +
  `REQUEST_PATH` fix (~350 lines). Verifies in browser.

## Open Questions

- [ ] WS channel names for >30m intervals (e.g. `1h` → `market_kline_60min`?) —
      only `1min` was live-verified in the spike; apply-time live check.
- [ ] Spec gap: 502 upstream-failure is normative (R2/R3 text) but has no
      Given/When/Then scenario — `tasks.md` must add the test (spec text already
      requires the behavior).
