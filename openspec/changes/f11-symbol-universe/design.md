# Design: f11-symbol-universe (issue #124, F11)

Four additive slices over existing seams. Normative contracts:
`specs/{symbol-catalog,market-watchlist,alert-rules,market-ingestion,market-chart}`.
No migration, dependency, CSP change, new bus event or store key.

## 1. `catalog.py` (new, A-S1)

```python
CATALOG_TTL_SECONDS = 60
_cache: tuple[float, tuple[str, ...]] | None = None   # (fetched_at, symbols)

def list_symbols(client=None, *, now=None) -> list[str]
def symbol_exists(symbol: str, *, client=None) -> bool
def reset_cache() -> None            # test seam
```

```python
def list_symbols(client=None, *, now=None):
    global _cache
    now = time.time() if now is None else now
    if _cache is not None and now - _cache[0] < CATALOG_TTL_SECONDS:
        return list(_cache[1])
    client = client or BitunixClient()
    symbols = tuple(sorted({t["symbol"] for t in client.tickers()}))
    _cache = (now, symbols)              # assigned only on success
    return list(symbols)
```

- **Failure rule (R2):** a raising `tickers()` propagates *before* the
  assignment, so `_cache` is never cleared, poisoned or replaced. A stale entry
  keeps serving the last good list; the alerts path does not degrade to "cold"
  on a blip.
- `now` injectable so TTL tests never sleep. Both exits `list(...)` so callers
  cannot mutate the cache.
- Cache stores the **projected tuple**, not the ticker payload (`client.py:118-120`
  returns full objects): hundreds of dicts → multi-MB response; projection is a
  few KB.
- Imports: stdlib + `src.client`/`src.config` only. No Django, no `trading`, no
  `market.views` (avoids the import cycle; `tests/test_boundary.py`).

## 2. Django glue

`views.py` is **600** lines over 6 concerns; `alerts.py` (182) is the shipped
precedent for a self-contained JSON resource (`urls.py:17-25`).

- **`api_symbols` inline in `views.py`**: 10-line GET with `api_kline`'s error
  map (`views.py:201-204`); no resource → no file.
- **New `web/market/watchlist.py`**: GET/POST/DELETE resource in the
  `/api/alerts` shape (`@login_required`, JSON body, scoped accessors).

```python
# urls.py
path("market/api/symbols", views.api_symbols, name="market_api_symbols"),
path("market/api/watchlist", watchlist.api_watchlist, name="market_api_watchlist"),
path("market/api/watchlist/<str:symbol>", watchlist.api_watchlist_detail,
     name="market_api_watchlist_detail"),
```

Allowlists: `MODULE_ALLOWLIST` += `symbol-search-core` (33→34);
`CONTROLLER_ALLOWLIST` += `symbol-picker` (17→18), asserted at
`test_market_ux.py:146,195,204`.

Watchlist semantics per verb:

| Verb | Behaviour |
|---|---|
| GET | `list(Watchlist.for_user(u).values_list("symbol", flat=True))`; empty → `{"symbols": SYMBOLS, "default": true}`, **no write** (R14.9); else sorted, false |
| POST | format → warm-miss → cap → `for_user(u).get_or_create(symbol=s, defaults={"user": u})` → 201 |
| DELETE | `for_user(u).filter(symbol=s).delete()` → 204 always |

Owner only from `request.user` (R14.8); CSRF via `CsrfViewMiddleware`.

## 3. Shared cap + format validator (`src/config.py`)

One literal `MAX_INGEST_SYMBOLS = 50`; `watchlist.py` imports it
`as MAX_WATCHLIST_SYMBOLS` — one value, both spec names, no drift. `src/` stays
framework-free (constants only; `config.py:47-49` already owns `SYMBOLS`).
`quotes.py` rejected: the cap is not a chart-payload concern.

`SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,24}$")` + `is_valid_symbol(value)`, one
definition for three call sites: watchlist POST (always 400 on malformed),
`alerts._pair_error` (format before any I/O), `worker.ingest_symbols` (defensive
filter on stored rows).

## 4. Alerts (`alerts.py:44-55`)

```python
def _pair_error(symbol, interval):
    if not symbol: return "symbol required"
    if not is_valid_symbol(symbol): return "invalid symbol"   # no network
    try:
        known = catalog.symbol_exists(symbol)
    except (BitunixError, requests.RequestException):
        known = None                       # cold → fail open (R12)
    if known is False: return "invalid symbol"
    if not interval: return "interval required"
    if interval not in CANDLE_INTERVALS: return "invalid interval"
    return None
```

`symbol_exists` may raise on a cold fetch; the caller converts that to `None`.
It must never escape as a 500: the documented client failures are only
`BitunixError` (`client.py:25`) and `requests.RequestException` (`client.py:94`).
The watchlist POST uses the same warm/cold branch. Order preserved (symbol →
interval) so the existing 400 matrix keeps its assertions. GET (`alerts.py:105`)
shares the function: a warm miss is 400, never a silently empty list.

## 5. Worker ingestion

```python
# candles.py
def due_intervals(now: int, last_poll: Mapping[str, int] | None) -> tuple[str, ...]
```

Per-symbol `last_poll` map, values `{interval: epoch}`; missing key or `None` →
all intervals (restart burst, R8). Order = `CANDLE_INTERVALS`. Pure.

```python
# candles.py
def fetch_closed_candles(client, symbols, now=None, due=None) -> list[dict]:
    for symbol in symbols:
        intervals = CANDLE_INTERVALS if due is None else due.get(symbol, ())
        for interval in intervals:
            try: rows = client.kline(symbol, interval, 2)
            except (BitunixError, requests.RequestException) as exc:
                logger.warning(...); continue      # R7: peers continue
```

**One choice:** `fetch_closed_candles` gains a `due` map (not an `intervals`
tuple). Rationale: R8 says "only due intervals *per symbol*"; a uniform tuple
loses per-symbol state after one failure, and post-filtering keeps the full
request count (fails R9). `due=None` preserves today's all-intervals behaviour,
so `test_candles.py:83,95` and `test_worker_candles.py:87` stay untouched.

```python
# worker.py
_last_poll: dict[str, dict[str, int]] = {}      # module-level, one process
def reset_poll_state() -> None: _last_poll.clear()

def ingest_symbols() -> tuple[str, ...]:
    from trading.models import Watchlist
    symbols = list(config.SYMBOLS)                               # never starved
    seen = set(symbols)
    for symbol in (Watchlist.objects.values_list("symbol", flat=True)
                   .distinct().order_by("symbol")):             # R14.4 trust zone
        if len(symbols) >= MAX_INGEST_SYMBOLS: break
        if symbol not in seen and is_valid_symbol(symbol):
            symbols.append(symbol); seen.add(symbol)
    return tuple(symbols[:MAX_INGEST_SYMBOLS])
```

Unscoped `Watchlist.objects` is legal only here (`worker.py` is outside the
scanner's `REQUEST_PATH`, `test_owned_model_guard.py:20-21`). `run_loop` changes
one line (`worker.py:204`): `ingest_symbols() if symbols is None`.

`run_once` reads `candles._now_seconds()` (module import, so the `_freeze_now`
fixture still applies), builds
`due = {s: due_intervals(now, _last_poll.get(s)) for s in symbols}`, calls
`fetch_closed_candles(..., due=due)`, then stamps every attempted interval:
`_last_poll.setdefault(s, {}).update({iv: now for iv in due[s]})`. Stamping is
unconditional so an upstream outage does not multiply retries every 30 s; a
failed interval retries at the next bucket. On restart the map is empty → every
interval due once → 400-request burst absorbed by the cycle backoff
(`worker.py:215-220`), documented in R8.

**Failure-isolation contradiction resolved:** R7's scenario is normative and
`worker.py:56-59` catches only around the whole cycle, so one raise aborts
every peer. The design therefore puts the `try/except` *inside* the
symbol×interval loop; the outer catch remains as a belt for non-client bugs.

## 6. `symbol-search-core.js`

`export function filterSymbols(query, symbols, limit = 50) -> string[]`; no
imports, no DOM. Tier `0` exact | `1` prefix | `2` substring | `3` none; comparator
`tier asc, then a.localeCompare(b)` (stable tier sort); `.slice(0, limit)` after
the sort. Guards: non-array `symbols` → `[]`; non-string `query` → `""`;
empty/whitespace → `symbols.slice(0, limit)`; non-finite/≤0 `limit` → 50. Never
throws, never mutates.

## 7. `controllers/symbol-picker.js` (~145 lines, <300)

`createSymbolPicker({store, bus, config})`, leaf (imports only the core).

Markup in `chart.html` (replaces the pairs heading area; the nav survives):

```html
<div class="symbol-picker">
  <input id="symbol-search" type="search" role="combobox" aria-expanded="false"
         aria-controls="symbol-results" aria-autocomplete="list"
         aria-activedescendant="" autocomplete="off" placeholder="Search symbol">
  <ul id="symbol-results" role="listbox" hidden></ul>
  <p id="symbol-search-status" class="visually-hidden" aria-live="polite"></p>
</div>
<nav class="pairs" id="watchlist" aria-label="Watchlist">
  {% for symbol in symbols %}<button type="button" class="pair" data-symbol="{{ symbol }}">{{ symbol }}</button>{% endfor %}
</nav>
```

State: `catalog`, `results`, `active`, `followed: Set`, `open`. Machine: closed
(`aria-expanded=false`, `aria-activedescendant=""`) → input/`ArrowDown` opens at 0
→ `ArrowUp/Down` wrap → `Enter` selects → `Escape` closes and clears. Focus stays
in the input; the active option gets `aria-selected` + `scrollIntoView`.
`Alt+Enter` toggles follow; outside `mousedown` closes. On create: parallel
`GET /market/api/symbols` + `/api/watchlist`; failure degrades to `.pair`.

**No debounce:** filtering is local over an already-fetched array; `saveDelay`
(`chart.js:27`) is the server-PUT debounce — reusing it adds latency for nothing.
Selection emits the existing `bus.emit("config:changed", {symbol, interval:
store.get().interval})` (`main.js:201-205` owns the switch). Follow: `POST
config.urls.watchlist` `{symbol}` with `X-CSRFToken` from `chart.html:5`;
unfollow `DELETE .../<symbol>`; 2xx flips the row and announces.

## 8. `main.js`

**293/300.** One import + one `createSymbolPicker({ store, bus, config });` →
**+2 = 295**. No extraction needed; if a third line appears during apply, the
target is the late-bound context-menu callback block (already extracted in F10).

## 9. CSS (`theme.css`, tokens only, beside `.pairs` at `theme.css:139-140`)

```css
.symbol-picker{position:relative; margin:0 0 var(--sp-2)}
.symbol-picker input{width:100%; background:var(--surface); border:1px solid var(--border);
  color:var(--text); border-radius:var(--r); padding:var(--sp-2) var(--sp-3)}
.symbol-results{position:absolute; z-index:2; left:0; right:0; margin:var(--sp-1) 0 0;
  max-height:240px; overflow-y:auto; list-style:none; padding:var(--sp-1);
  background:var(--surface); border:1px solid var(--border); border-radius:var(--r)}
.symbol-results [role="option"]{display:flex; gap:var(--sp-2); align-items:center;
  padding:var(--sp-1) var(--sp-2); cursor:pointer}
.symbol-results [aria-selected="true"]{outline:2px solid var(--accent); outline-offset:-2px}
.watch-toggle{margin-left:auto; min-width:32px; min-height:32px;
  background:var(--surface); border:1px solid var(--border); color:var(--muted)}
.watch-toggle[aria-pressed="true"]{color:var(--accent); border-color:var(--accent)}
```

## 10. Test design

| File | Proves | Negative control |
|---|---|---|
| `tests/js/symbol-search-core.test.js` | tiers, alphabetical within tier, case, cap, empty, no-throw matrix | `"btc"` **drops** `ETHUSDT` (not a pass-through) |
| `tests/js/symbol-picker.test.js` (shim like `alerts-controller.test.js`) | wrap, Enter → one `config:changed`, Escape clears, Alt+Enter POST, label flip, outside close | no-match query leaves `aria-expanded=false` |
| `tests/web/test_market_catalog.py` | hit at `now=59` (0 client calls), expiry refetch, raise propagates *and* cache survives, projection, 302/405/502 | failed refetch then success returns the old list |
| `tests/web/test_market_watchlist.py` | 302/403, A≠B GET+DELETE, body-owner ignored, 201/dup/cap/unknown-warm/malformed/cold, DELETE×2, virtual default | 2 GETs leave 0 rows; B's DELETE leaves A's row |
| `tests/web/test_market_alerts_api.py` (extend) | warm accept/reject, cold accept, malformed both, `1m` 400 | catalog symbol outside `SYMBOLS` → 201 (was 400) |
| `tests/web/test_candles.py` (extend) | `due_intervals` table (same bucket/boundary/`None`), order, `due=` skip, per-symbol isolation | `due=None` still 8 calls/symbol |
| `tests/web/test_worker_ingest.py` (new) | union order/cap/dedupe, ingest budget over 2 cycles | bypass `due=` → 400 calls/cycle (>10 req/s), proving scheduling is the guard |
| `tests/web/test_market_ux.py` (extend) | 34/18 allowlists, combobox roles, no inline handler, size guard | unallowlisted name 404s |

Branches covered: catalog hit/expiry/raise; watchlist default/sorted/cap/
malformed/warm-miss/cold/dup/delete-miss; alert format/known/unknown/cold/
interval; `due_intervals` missing/same/rolled; `ingest_symbols` cap/dedupe/
invalid; JS open/close/move/select/follow/guards. Patch coverage 100% reachable.

## 11. Decisions & risks

| Decision | Choice | Alternative | Why |
|---|---|---|---|
| Catalog state | module tuple | class/DB table | smallest state for R2; a table duplicates exchange data |
| Watchlist module | new `watchlist.py` | grow `views.py` (600) | F10 precedent; keeps views navigable |
| Cap | one `MAX_INGEST_SYMBOLS` | two literals | spec says reuse; aliasing prevents drift |
| Scheduling | `due` map per symbol | uniform tuple; post-filter | only shape satisfying R8 *and* R9 |
| `last_poll` | in-memory dict | DB column | persists a ~40 s transient; new schema for nothing |
| Search | pure core, no debounce | controller/timer | local O(n); a timer adds latency and a test |

Risks: cold `tickers()` latency (60 s cache, 502, picker falls back to `.pair`);
restart burst (~40 s, accepted); follow button inside `role="option"`
(`tabindex="-1"`, `Alt+Enter`); allowlist count asserts move in the same commit;
E2E flake #149 (DOM + captured requests, never pixels).

## 12. Contradictions resolved (spec wins)

1. **R7 isolation vs `worker.py:56-59`** → in-loop `try/except` (§5).
2. **Two cap names** (`MAX_INGEST_SYMBOLS`, `MAX_WATCHLIST_SYMBOLS`) → one literal
   + import alias (§3).
3. **Watchlist POST cold is unspecified** (R14.10 covers warm/malformed) → same
   as R12: format-valid accepted when the catalog is unavailable; the worker's
   `is_valid_symbol` bounds the union.
4. **"Per-symbol" state vs "per-cycle due intervals"** → per-symbol map, only the
   due subset requested; stale entries after unwatch are harmless and capped.
5. **Explore says the nav becomes the watchlist; R20 requires `.pair`/`data-symbol`
   and an untouched `toolbar.js`** → nav stays server-rendered and static
   (initial-only); the picker is additive, because `toolbar.js:29-33` binds at
   create time and appended buttons would be dead.
6. **Frozen seams** → allowlist counts 33/17 intentionally change;
   `window.marketChart` (8 keys) and `STORE_KEYS` (11) do not.

Rollout: S1 catalog → S2 watchlist+alerts → S3 worker → S4 UI (S4 needs S1+S2).
Each slice reverts independently; reverting S4 restores the static nav.
