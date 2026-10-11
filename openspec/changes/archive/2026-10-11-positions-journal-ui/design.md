# Design: positions-journal-ui (issue #58, Fase 6c)

## Technical Approach

Two auth-gated GET views in the existing `web/trading/` app (owns the models; already
inside both scanners' REQUEST_PATH → zero scanner/app changes), reusing pure `src/`
math with no reimplementation. Server-rendered templates inherit the design-system
shell (Fase 5.5). Reads route exclusively through `for_user(request.user)` (R14).

## Views (`web/trading/views.py`, NEW)

```python
POSITION_FIELDS = ("symbol","side","qty","avg_open","leverage","liq_price",
                   "upnl","margin_rate")

@login_required
@require_http_methods(["GET"])
def positions(request):
    user = request.user
    latest = PositionSnapshot.for_user(user).aggregate(ts=Max("ts"))["ts"]
    rows = PositionSnapshot.for_user(user).filter(ts=latest) if latest else []
    # mark per symbol from the latest global TickerSnapshot
    marks = {t.symbol: t.last_price for t in _latest_tickers(s for s in ...)}
    panel = [ _position_view(r, marks.get(r.symbol)) for r in rows ]
    acct = AccountSnapshot.for_user(user).order_by("-ts").first()
    return render(request, "trading/positions.html", {"rows": panel, "account": acct})

@login_required
@require_http_methods(["GET"])
def journal(request):
    user = request.user
    rows = [{"symbol": t.symbol, "fee": t.fee or 0.0, "realized_pnl": t.realized_pnl or 0.0}
            for t in Trade.for_user(user)]
    nets = [r["realized_pnl"] - r["fee"] for r in rows]
    metrics = journal_metrics(rows)            # src.journal.metrics (win_rate/net_pnl/per_symbol/best/worst)
    extra = {"expectancy": expectancy(nets),
             "profit_factor": profit_factor(nets),
             "equity_curve": equity_curve(nets)}
    return render(request, "trading/journal.html", {"metrics": metrics, **extra, "empty": not rows})
```

- **Latest per symbol**: `sync_user` stamps one shared `ts` per cycle → `Max("ts")` then `filter(ts=latest)`. Portable (no `.distinct("symbol")`, which SQLite rejects).
- **Mark**: latest global `TickerSnapshot.last_price` per symbol; `None` → "—".
- **`_position_view`**: `distance = liq_distance_pct(liq_price, mark)`, `state = margin_state(margin_rate)` (reused from `src.monitor`). No arithmetic duplicated.
- **Journal**: `src.journal.metrics(rows)` + `src.metrics.{expectancy,profit_factor,equity_curve}` over the net sequence. Zero metric math in the view/JS.

## URLs (`web/trading/urls.py`, NEW) + include

```python
urlpatterns = [
    path("positions/", views.positions, name="positions"),
    path("journal/", views.journal, name="journal"),
]
```
`web/config/urls.py`: add `path("", include("trading.urls"))`.

## Templates (`web/trading/templates/trading/{positions,journal}.html`)

Extend `registration/base.html` (design-system shell). `positions.html`: account
header (`available`, `cross_upnl`) + table (symbol, side, qty, avg, lev, liq,
distance, margin state, uPnL) with `.num` cells; empty state panel when no rows.
`journal.html`: metric cards (win rate, net PnL, expectancy, profit factor) +
per-symbol table + a small equity sparkline (optional; text list is fine).
`home.html`: both nav entries already exist in the shell; add in-content links too.

## Nav

The design-system shell already links `/positions/` and `/journal/` (href
placeholders). Once these routes exist they resolve — no shell change needed.

## CSP / HTMX

No CSP relaxation. Full-page render is sufficient (worker updates ~30s); HTMX is
NOT required for 6c — keep it lazy (no HTMX dependency). If added later it uses the
allowed unpkg CDN.

## Testing Strategy (Strict TDD)

`tests/web/test_positions.py`, `tests/web/test_journal.py`:
- Anonymous → 302 for both.
- Latest-per-symbol only (two ts cycles).
- Distance/state from `src.monitor`; missing mark → "—".
- Empty state (no rows) for both.
- **A≠B**: user B sees empty states + none of A's symbols.
- Journal known fixture → win_rate 66.67%, net 10.0, expectancy 3.333, PF 3.0, equity [10,5,10].
- Scanners (R14.3 guard + credential) stay green; no decrypt in views.
- Home links both pages. Patch gate 100%.

## ADRs

- **(a) Views in `trading/` not a new app**: models live there; already scanned; mirror `market/` split.
- **(b) Max-ts latest-per-symbol**: shared cycle ts; portable, avoids SQLite `.distinct(on=...)`.
- **(c) Reuse `src.monitor`/`src.journal`/`src.metrics`**: single source; no reimplementation.
- **(d) No HTMX**: full-page render is enough for a 30s-cadence personal dashboard; add later if polling hurts.

## Boundary Note

`src/` unchanged/framework-free; `requirements.txt` unchanged; no migration; no order
surface; no secrets/decrypt in request path; R14 via `for_user`.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `web/trading/views.py` | New | `positions`, `journal` views |
| `web/trading/urls.py` | New | 2 routes |
| `web/config/urls.py` | Modify | include `trading.urls` |
| `web/trading/templates/trading/positions.html` | New | positions page |
| `web/trading/templates/trading/journal.html` | New | journal page |
| `web/accounts/templates/accounts/home.html` | Modify | in-content links |
| `tests/web/test_positions.py`, `tests/web/test_journal.py` | New | TDD suites |

## Task Breakdown Hint

~350–500 lines → 400-line budget risk **Medium**. Single PR (one cohesive page pair,
shares the read seam); no chaining.

## Open Questions

None blocking.
