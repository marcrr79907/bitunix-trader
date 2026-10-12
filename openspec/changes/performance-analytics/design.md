# Design: performance-analytics (Fase E1, issue #78)

## Technical Approach

Additive analytics layer over frozen seams. `src/metrics.py` gains three pure
scalars (`max_drawdown`, `win_rate`, `net_pnl`); a NEW pure `src/analytics.py`
holds grouping, the per-bucket record, the calibration join and a pure SVG
builder. A web seam extracts historical SMC setups via
`get_smc_payload(..., before=None)`; a read-only `/analytics/` view renders
breakdowns + calibration + inline SVG (no JS, CSP untouched, no new dep, no
migration).

    Trade.for_user ─→ row dicts {net,hour,symbol,setups,…}
      ├─→ analytics.group_by/summarize ─→ per-dimension records ─→ SVG/table
      └─→ web seam: get_smc_payload(before=bar+1)/pair ─→ signals
            └─→ analytics.calibrate(trades, signals, window_seconds=3600)
                  ─→ {matched, unmatched, by_setup, r_by_setup}   (R = join-only)

## Architecture Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Metrics home (Q10) | Scalars in `src/metrics.py`; groups+calibration in NEW `src/analytics.py` | Keeps the frozen `metrics.py` small; analytics imports `src.metrics` only |
| Setup vocabulary (Q1) | `setup_kind = f"{direction}:score{score}"` (e.g. `long:score4`) | SMC emits one unnamed `Setup`; the derived label is the only stable key |
| R source (Q2) | join-only, `risk = abs(entry-stop)*qty`, `R = r_multiple(net, risk)`; unmatched → `None` | `Trade` stores no risk; no migration/sync change |
| Granularity (Q3) | one fill = one trade (journal status quo) | Round-trip reconstruction is out of scope; documented |
| Hour (Q4) | UTC, `hour = (ctime//3_600_000) % 24`, caller-supplied | Pure fns stay tz-free/deterministic; no `datetime.now` |
| ctime unit (Q5) | epoch **ms**; `trade_time = ctime // 1000` before compare | Matches candle `time` (s) and `test_private_sync` |
| Match rule (Q7) | same `symbol`+`direction` (BUY→long, SELL→short), nearest signal with `|Δt|<=window_seconds`; ties → earliest signal | One signal scored once; deterministic |
| Charts (Q6) | pure Python inline SVG (`equity_svg`, `bars_svg`) | No CDN lib, no npm, patch-covered, CSP unchanged |
| Signal seam (Q12) | `get_smc_payload(client, symbol, interval, limit, *, before=None)` | Reuses the frozen chain; additive keyword-only |
| SVG escaping | `xml.sax.saxutils.escape` on labels (stdlib) | SVG inserted `\|safe`; escape is the XSS guard |

## Interfaces / Contracts (FROZEN)

```python
# src/metrics.py — additive; the frozen four are untouched
def max_drawdown(equity: list[float]) -> float | None   # worst peak→trough, <=0.0; None when empty
def win_rate(pnls: list[float]) -> float | None          # wins/total*100 (win = p>0); None when empty
def net_pnl(pnls: list[float]) -> float                  # sum(pnls); 0.0 when empty
```

```python
# src/analytics.py — NEW; imports only src.metrics + stdlib; never raises
def summarize(trades: list[dict]) -> dict
# {"trades":int,"wins":int,"win_rate":float|None,"net_pnl":float,
#  "expectancy":float|None,"profit_factor":float|None,"max_drawdown":float|None}
# `trades` are records carrying "net": float; empty -> all-zero/None bucket.

def group_by(trades: list[dict], dimension: str) -> dict[str, list[dict]]
# dimension ∈ {"setup","hour","symbol"}; keys sorted; a None key buckets under
# "unmatched" (setup) / "unknown" (hour). Empty rows -> {}.

def calibrate(trades: list[dict], signals: list[dict], *, window_seconds: int) -> dict
# trade  : {"net":float,"side":str,"ctime":int,"qty":float,"symbol":str}
# signal : {"symbol":str,"time":int,"direction":str,"entry":float,"stop":float,"score":int}
# -> {"matched":summarize(...),"unmatched":summarize(...),
#     "by_setup":{kind:summarize(...)},"r_by_setup":{kind:float|None}}
# R = r_multiple(net, abs(entry-stop)*qty); r_by_setup = fmean of non-None R.

def equity_svg(points: list[float], *, width: int, height: int) -> str
def bars_svg(bars: list[dict], *, width: int, height: int) -> str
# bars: [{"label":str,"value":float}]. Deterministic strings; stdlib only;
# labels escaped with xml.sax.saxutils.escape; empty -> fixed empty-state SVG.
```

```python
# web/market/quotes.py — additive keyword-only
def get_smc_payload(client, symbol, interval, limit, *, before: int | None = None) -> dict
# passes `before` to _fetch_window; chain behavior unchanged.
```

## Data Flow (view)

    analytics_view(user)
      rows  = [ {net, hour, symbol, setups:None} for t in Trade.for_user(user) ]
      by_sym = group rows by symbol
      for symbol: signals += web.analytics.extract_signals(client, symbol, bars)
      groups = {dim: {k: summarize(v) for k,v in group_by(rows,dim).items()}}
      cal    = calibrate(rows, signals, window_seconds=3600)
      svgs   = equity_svg(equity_curve(nets)) + bars_svg(win_rate bars)
      render("trading/analytics.html", {...})   # SVG strings via |safe (escaped labels)

**Cost bound (Q9):** one SMC chain pass per distinct trade bar. The seam
dedupes by `(symbol, bar = ctime//3_600_000)` so N fills on one bar cost ONE
call; no cache in v1 (ponytail: keyed-by-bar memoization only if measured slow).
Upstream `BitunixError`/`RequestException` degrade to no signals, never 500.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/metrics.py` | Modify | `max_drawdown`/`win_rate`/`net_pnl` (frozen four untouched) |
| `src/analytics.py` | Create | pure `summarize`/`group_by`/`calibrate`/`equity_svg`/`bars_svg` |
| `tests/test_metrics.py` | Modify | battery for the three scalars |
| `tests/test_analytics.py` | Create | groups, calibration, exact SVG strings |
| `tests/test_boundary.py` | Modify | register `analytics.py` in `PURE_MODULES` |
| `web/market/quotes.py` | Modify | `get_smc_payload(*, before=None)` |
| `web/trading/analytics.py` | Create | signal extraction seam (I/O; dedupe by bar) |
| `web/trading/views.py` | Modify | `analytics_view` (`@login_required`, GET) |
| `web/trading/urls.py` | Modify | `/analytics/` route |
| `web/trading/templates/trading/analytics.html` | Create | breakdowns + calibration + inline SVG |
| `web/accounts/templates/registration/base.html` | Modify | nav link |
| `web/accounts/templates/registration/theme.css` | Modify | analytics/chart styles |
| `tests/web/test_analytics.py` | Create | view, per-user, charts present, A≠B |

SVG is built server-side; only `equity_svg`/`bars_svg` output is marked
`|safe`. Every user-derived label passes `saxutils.escape` first, so no
attribute/text can break out — the `|safe` XSS risk is closed at the builder.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit (metrics) | drawdown `[10,5,10]→-5.0`, monotonic `→0.0`; win_rate `66.66…`; net `0.0`; empty→`None`/`0.0` | `tests/test_metrics.py` |
| Unit (analytics) | group keys sorted + `unmatched`/`unknown`; calibrate match/unmatched/`by_setup`/`r_by_setup`; risk formula; empty→empty buckets, no raise; exact `equity_svg`/`bars_svg` strings; label escaping | `tests/test_analytics.py` |
| Boundary | `analytics.py` stdlib-only | `tests/test_boundary.py` |
| View | anon→302; per-user `Trade.for_user`; breakdown + calibration + `<svg` present; well-formed (parses via `xml.etree`); A≠B; no inline script/handler | `tests/web/test_analytics.py` |
| E2E | `/analytics/` renders with a real trade set; CSP header unchanged | `tests/web/test_analytics.py` |

`strict_tdd: true`; patch 100%; `ruff` clean; no new dependency.

## Guard / Edge Matrix

| Guard / Edge | Handling |
|---|---|
| `PURE_MODULES` | `analytics.py` registered; imports `src.metrics` + stdlib only (no sqlite3/rich/Django/requests) |
| R14 isolation | view reads `Trade.for_user(user)` only; `test_owned_model_guard` green |
| Join-only R | no `Trade` field/migration; unmatched → `None`, rendered "—" |
| Determinism / no clock | sorted keys, `statistics.fmean`, hour supplied by caller; no `datetime.now` |
| SVG escaping / CSP | `saxutils.escape` labels; inline SVG is HTML; no inline script/handler; CSP unchanged |
| No new dep | `requirements.txt` untouched; no npm/build |
| Read-only | no order verb, no exchange-client import; `test_no_order_surface` green |
| Upstream failure | seam swallows `BitunixError`/`RequestException` → empty signals, never 500 |

## Migration / Rollout

No migration, no model change, no flag. Pure additive; `/journal/` untouched.

## Delivery — Chained 3 slices (Feature Branch Chain, base = tracker)

`400-line budget risk: High` (~1150 lines). `Decision needed before apply: Yes` ·
`Chained PRs recommended: Yes`.

| Slice | Content | ~Lines | Depends on | Rollback boundary |
|-------|---------|--------|-----------|-------------------|
| 1 — pure core | `metrics.py` +3 fns; NEW `src/analytics.py`; `test_boundary`; `test_metrics`/`test_analytics` | ~410 | — | delete `analytics.py` + tests, drop fns, unregister |
| 2 — extraction + view | `get_smc_payload(before=…)`; `web/trading/analytics.py`; `analytics_view` + route + nav + scoping tests | ~380 | slice 1 API; frozen `get_smc_payload` | delete view/route/nav/seam; revert `before` |
| 3 — SVG UI + E2E | `analytics.html` + `theme.css`; E2E + `/impeccable` audit | ~360 | slice 2 context | delete template/CSS; revert E2E |

Each child PR targets the previous slice; rebase if a child diff shows prior
slices. Slice 1 is autonomous (no web, no JS).

## Open Questions

None blocking. Explore Q1–Q12 locked here and by the delta spec.
