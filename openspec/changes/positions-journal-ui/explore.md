# Exploration: positions-journal-ui (Fase 6c, issue #58)

**Change**: `positions-journal-ui`
**Issue**: #58 (Fase 6c). Context: #57 (6b, merged), #56 (6a, done).
**Date**: 2026-10-10
**Mode**: investigation only. No code written.

## Executive Summary

Phase 6b already persists per-user `PositionSnapshot`, `AccountSnapshot`, and
`Trade` (`web/trading/models.py:147-207`), but the web has **no view for them** —
`/market/` is the only authenticated page and it shows global data only. This
change adds the two auth-gated pages the product promised: `/positions/` (latest
per-symbol snapshot per user, mirroring the CLI panel) and `/journal/` (win rate
+ net PnL per pair, reusing the pure `src/` math). The hard constraints are
already enforced by live scanners: every read MUST route through
`for_user(request.user)` (R14), and the request path MUST NOT touch `decrypt`
(R13). No new runtime dependency; HTMX ships from the CDN already allowlisted in
the CSP.

Three scan-critical facts verified:

1. **R14 guard** (`test_owned_model_guard.py:19-38`): `REQUEST_PATH` covers
   `config, accounts, trading, market`; `UNSCOPED_VERBS` flags only
   `<Model>.objects.<verb>()`. Chaining off the sanctioned accessor —
   `PositionSnapshot.for_user(user).order_by(...)` — is **not** flagged (the AST
   requires the receiver to be literally `.objects`). So views may freely chain
   `.order_by()/.values()/.exists()/[:1]` on a `for_user` queryset.
2. **Decrypt confinement** (`test_credentials_mechanism.py:20`): `trading/` is in
   the request path, so new views there MUST NOT import/call `credentials.decrypt`.
   They won't — they read only persisted rows (R13).
3. **CSP** (`web/config/middleware.py:27-32`): `script-src 'self' https://unpkg.com`
   and `connect-src 'self' …`. HTMX loads from unpkg → **no CSP edit needed**, and
   `hx-*` attributes do not require `unsafe-inline`.

## Current State (read, not guessed)

| Area | Fact | Source |
|---|---|---|
| Owned base | `UserOwnedModel` abstract: `user` FK CASCADE + `for_user(user)` | `web/trading/models.py:90-104` |
| Position model | `PositionSnapshot`: symbol, side, qty, avg_open, leverage Integer, liq_price, upnl, margin_rate, ts; unique `(user,symbol,ts)` | `web/trading/models.py:147-170` |
| Account model | `AccountSnapshot`: available, cross_upnl, ts; unique `(user,ts)` | `web/trading/models.py:173-183` |
| Trade model | `Trade`: trade_id, symbol, side, qty, price, fee, realized_pnl, ctime; unique `(user,trade_id)` | `web/trading/models.py:186-207` |
| Sync cadence | private sync runs **every worker cycle (~30s)**, one `ts` per cycle for all positions+account | `web/worker.py:59-97`, `web/trading/sync.py:132-143` |
| Position panel (CLI) | `liq_distance_pct(liq, mark)`, `margin_state(rate)` vs `config.MARGIN_WARN=0.5` | `src/monitor.py:142-179` |
| Journal panel (CLI) | pure `journal.metrics(rows)`: trades, wins, net_pnl, win_rate, per_symbol, best, worst | `src/journal.py:62-90` |
| Pure metrics (Phase 1) | `expectancy`, `profit_factor`, `r_multiple`, `equity_curve` (list in → number out) | `src/metrics.py:14-44` |
| View pattern | `@login_required` + `@require_http_methods(["GET"])`; render template | `web/market/views.py:25-28` |
| Same-origin JS | `chart_js` view serves `text/javascript` (no static infra) | `web/market/views.py:71-77`, `urls.py:12` |
| URL wiring | root includes `accounts.urls` + `market.urls`, bare names | `web/config/urls.py:10-15` |
| Home nav | links to `/market/` | `web/accounts/templates/accounts/home.html:15` |
| Base template | bare `<main>`, no CSS, no HTMX loaded anywhere | `registration/base.html` |
| Global mark source | `TickerSnapshot` (global, no owner): `last_price` per symbol | `web/trading/models.py:39-54` |
| Core boundary | `web/` MAY import `src/`; `web/trading/ingest.py` already does | `core-domain-boundary/spec.md`, `ingest.py:15` |

## Key Findings

1. **App placement — put the views in the existing `trading` app.**
   `web/trading/` owns the models and is already inside both scanners'
   `REQUEST_PATH`, so it needs **zero scanner changes** and no new app
   boilerplate (`apps.py`, `INSTALLED_APPS`, migrations dir). A new
   `web/portfolio/` app is unrequested abstraction; `market/` is chart-specific.
   This mirrors how `market/` pairs `quotes.py` (data) with `views.py` (HTTP).
   Cost: the trading app gains user-facing templates — the same seam market
   already has.

2. **Routes**: `web/trading/urls.py` (bare names, no `app_name`, mirroring
   market/accounts) with `/positions/` → `positions_page`, `/journal/` →
   `journal_page`; included from `web/config/urls.py`. Home links added next to
   Market.

3. **Latest-per-symbol is trivial — no window/subquery needed.** `sync_user`
   stamps **one shared `ts` per cycle** for all positions, so "latest per
   symbol" == "rows at the max ts". `qs = PositionSnapshot.for_user(user)`;
   `ts = qs.aggregate(Max("ts"))["m"]`; `rows = qs.filter(ts=ts)`. Portable to
   SQLite (tests) **and** Postgres — avoids `.distinct("symbol")`, which SQLite
   rejects. Header: `AccountSnapshot.for_user(user).order_by("-ts")[:1]`.

4. **Distance/margin math is reusable as-is.** `src/monitor.py` is
   framework-free and already imported by `web/trading/ingest.py:15`, so the
   view can `from src.monitor import liq_distance_pct, margin_state` (rich is a
   declared dep, already in the web process). The mark price is **not** persisted
   in `PositionSnapshot` — use the latest global `TickerSnapshot.last_price` for
   the symbol; `None` when absent → render "—".

5. **Journal: the issue's "reuse `src/metrics.py`" is under-specified.**
   `src/metrics.py` has `expectancy`/`profit_factor`/`r_multiple`/`equity_curve`
   but **no win_rate and no per-symbol PnL**; the pure `src/journal.py::metrics(rows)`
   (list-in/dict-out, no I/O) has exactly win_rate/net_pnl/per_symbol/best/worst
   and matches the CLI. **Decision for spec/design**: single-source = reuse the
   existing pure functions, never reimplement in the view — `metrics.expectancy`
   + `metrics.profit_factor` (+ `metrics.equity_curve` for a running-PnL series)
   **and** `journal.metrics(rows)` for the report dict. If one module is mandated,
   add `win_rate`/`per_symbol` to `metrics.py`. Do NOT duplicate the math in the
   view or JS.

6. **HTMX is optional and lazy-compatible.** The worker updates every ~30s and
   this is personal-first, so a full-page render is enough. If auto-refresh is
   wanted, HTMX from `https://unpkg.com` is **already CSP-allowed** (no CSP
   change, no build, no runtime dep) and `hx-*` attributes need no
   `unsafe-inline`; a single `hx-get="/positions/" hx-trigger="every 30s"
   hx-select="#positions-table" hx-target="#positions-table"` needs no fragment
   view. The laziest alternative is `<meta http-equiv="refresh" content="30">`
   (zero JS). Recommend HTMX (issue asks for it) but keep it to one attribute
   set; surface the meta-refresh option to design.

7. **R14 is enforced by construction**: all reads use `for_user(request.user)`;
   the guard stays green because no `<Model>.objects.<verb>()` is written in the
   views. A≠B is proven by seeding rows for `user_a` and asserting `user_b` sees
   none.

8. **Empty state**: a user whose credentials have not synced yet (or who has no
   active credential) has zero snapshot rows — render a friendly "no data yet"
   panel, never an error and never another user's rows.

## Approaches (app placement)

1. **Views in `web/trading/` (recommended)** — Pros: models colocated, already
   scanned, no new app/config/migration, matches `market/` pattern. Cons: trading
   app grows a user-facing surface. Effort: Low.
2. **New `web/portfolio/` app** — Pros: clean separation. Cons: app boilerplate,
   `INSTALLED_APPS` edit, new scanner path to keep aligned; unrequested
   abstraction. Effort: Medium.
3. **Views in `web/market/`** — Pros: reuses chart app's view/template shell.
   Cons: market is chart-specific; mixes concerns. Effort: Low-Med.

## Recommendation

Add `web/trading/views.py`, `web/trading/urls.py`, and
`web/trading/templates/trading/{positions,journal}.html`; wire `/positions/` and
`/journal/` in the root URLconf; link both from `home.html`. Read everything via
`for_user(request.user)`; compute the position table with the max-ts query and
`src.monitor` helpers, the mark price from the latest global `TickerSnapshot`,
and the journal report from the pure `src/` functions (no reimplementation).
Ship server-rendered HTML; add HTMX (unpkg, already CSP-allowed) only for a
single `every 30s` refresh. Auth-gate with `@login_required` +
`@require_http_methods(["GET"])`. No secrets, no new runtime dependency.

## Affected Areas

- `web/trading/views.py` — new: `positions_page`, `journal_page` (New).
- `web/trading/urls.py` — new: two GET routes (New).
- `web/trading/templates/trading/positions.html` — new (New).
- `web/trading/templates/trading/journal.html` — new (New).
- `web/config/urls.py` — include `trading.urls` (Modified).
- `web/accounts/templates/accounts/home.html` — two nav links (Modified).
- `registration/base.html` — optional shared shell/CSS (Modified, Impeccable).
- `tests/web/test_positions_ui.py`, `test_journal_ui.py` — new (New).
- `tests/web/test_ux.py` — home-links assertion (Modified).
- `src/` — **unchanged** (R10); reused only.

## Risks & Open Questions

- **Metrics single-source ambiguity** (Med): `metrics.py` vs `journal.metrics`.
  Mitigation: spec MUST name one source; recommend reuse of both pure functions
  with zero reimplementation.
- **Mark price absent from snapshots** (Low): distance depends on the global
  `TickerSnapshot`; empty → `None`/“—”.
- **`distinct("symbol")` not portable** (Low): avoided via max-ts query.
- **HTMX vs plain vs meta-refresh** (Low): decide in design; HTMX is CSP-ready.
- **Snapshot freshness** (Low): the page shows the worker's last cycle, not live;
  label the `ts` so the user knows.
- **Trading app grows templates** (Low): acceptable; mirrors `market/`.

## Ready for Proposal

Yes — placement, routes, query strategy, reuse points, CSP/HTMX facts, R14
enforcement, test matrix, and risks are all grounded in read code.
