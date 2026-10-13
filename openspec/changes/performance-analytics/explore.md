# Exploration: performance-analytics (issue #78, Fase E1 — roadmap close)

## Executive Summary

E1 is the **analytics + calibration** layer over data the project already owns:
`Trade` rows (per user) and the frozen `src/smc/` core. It asks "what works?" —
R-multiple, expectancy, profit factor, win rate, net PnL, equity curve and
drawdown, **broken down by SMC-setup kind / hour / symbol** — plus a
**calibration** view that crosses historical SMC signals against the user's real
trades.

The three decisions that shape everything:

1. **The SMC engine emits ONE unnamed setup** (direction + a 0..4 confluence
   score + the latest BOS/CHoCH anchor) — there is no catalogue of named "setup
   types". "Per setup type" therefore maps to `direction × confluence-score
   band × structure-event kind (bos|choch)`. E1 MUST define this vocabulary.
2. **`Trade` records fills, not round-trips.** Fields are `symbol, side, qty,
   price, fee, realized_pnl, ctime` — **no entry/stop/exit and no risk**. The
   journal already treats each fill row as one "trade". R-multiple is therefore
   **undefined** for a trade unless E1 derives risk from a matched SMC setup
   (`|entry − stop| × qty`). This is the core tension; the recommendation is to
   compute R **only** for setup-matched trades via the calibration join (no
   migration).
3. **`src/metrics.py` is pure and already frozen** (expectancy, profit_factor,
   r_multiple, equity_curve) but has **no drawdown, no win-rate/net, no
   grouping**. E1 MUST extend it (or add `src/analytics.py`) — never change the
   frozen behavior, never import Django/sqlite3/rich.

Analytics is CPU-light over a per-user trade list. Charts are best served
**server-rendered inline SVG** (no JS adapter, no npm, CSP-safe, Python
patch-covered) rather than a second CDN chart library. The existing
`Journal` screen already receives `equity_curve` but **never draws it** — E1
adds the visualization layer.

Total surface (pure math + calibration join + SVG render helper + a new screen
+ test batteries) lands **well over the 400-line budget → chained PRs (3
slices)**.

---

## 1. Existing metrics / journal (what E1 ADDS vs REUSES)

### 1.1 `src/metrics.py` (pure, stdlib, frozen by `trade-metrics` spec)

```python
expectancy(pnls: list[float]) -> float | None      # mean; None when empty
profit_factor(pnls: list[float]) -> float | None   # gp/gl; None when no losses
r_multiple(pnl: float, risk: float) -> float | None# pnl/risk; None when risk==0
equity_curve(pnls: list[float]) -> list[float]     # running sum; [] when empty
```

- Pure, timestamp-agnostic, **never raises**, **no I/O**, stdlib only
  (`statistics`). `tests/test_metrics.py` pins all four.
- **Boundary contract** (`test_boundary.py:PURE_MODULES`): metrics may import
  stdlib only — no `sqlite3`, no `src.journal`, no Django.
- **Missing for E1**: `max_drawdown`, `win_rate`, `net_pnl` (these live in
  `journal.metrics` today), and **any per-dimension grouping**.

### 1.2 `src/journal.py` (SQLite accounting + rich CLI)

- `metrics(rows)` → `{trades, wins, net_pnl, win_rate, per_symbol, best, worst}`.
  Takes dict rows `{symbol, realized_pnl, fee}`; **net = realized_pnl − fee**.
- `trade_row(raw)` maps a BitUnix history-trade JSON → dict (incl.
  `ctime = int(...)`).
- `sync()` / `report()` / `render_report()` are the CLI path (rich). **Not
  reusable in `src/analytics.py`** — importing `journal` would drag `sqlite3` and
  `rich` across the pure boundary. E1 either lives in `metrics.py` or a new
  `analytics.py` that imports **`src.metrics` only**.

### 1.3 Web surface today

- `web/trading/views.py:journal` reads `Trade.for_user(user)`, builds rows and
  the `net` sequence (`realized_pnl − fee`), and passes `journal_metrics(rows)`
  + `expectancy/profit_factor/equity_curve(nets)` to `trading/journal.html`.
- `trading/journal.html` renders: totals line, per_symbol **table**, best/worst.
  **`equity_curve` is passed but never rendered** — no chart exists.
- `positions-journal-ui` R2 **freezes** this reuse; R5 forbids new model
  fields/migrations and new runtime deps. E1 either amends that spec (a
  `Trade` field) or stays additive with a **new** analytics capability.

### 1.4 What E1 must ADD

| Capability | Status today | E1 |
|---|---|---|
| R-multiple | function exists, **no risk source** | derive risk from matched SMC setup |
| expectancy / PF / equity | exist, used by journal | reuse unchanged |
| win rate / net PnL | in `journal.metrics` (sqlite-shaped) | add pure `win_rate`/`net_pnl` to `src/metrics` |
| **max drawdown** | **absent** | add pure `max_drawdown` |
| **per-dimension breakdown** | **absent** | new grouping (setup/hour/symbol) |
| **calibration (signal × trade)** | **absent** | new pure join + scoring |
| **charts** | **absent** (equity passed, not drawn) | server-rendered inline SVG |
| analytics screen | only `/journal/` | new `/analytics/` route |

---

## 2. Trade data shape (the hard constraint)

### 2.1 `Trade` fields (`web/trading/models.py`, mirrors `journal.trade_row`)

```
trade_id      CharField(64)                 # exchange id; unique per (user, trade_id)
symbol        CharField(32)
side          CharField(8)  null            # "BUY"|"SELL" (upper-cased upstream)
qty           FloatField    null
price         FloatField    null            # FILL price, not entry
fee           FloatField    null
realized_pnl  FloatField    null            # realized PnL of THIS fill
ctime         BigIntegerField null          # epoch **milliseconds** (confirmed: 1700000000000 in test_private_sync)
```

**What exists for breakdowns:** `symbol` ✔, timestamp (`ctime`) ✔ (epoch
**ms**, UTC), `side` ✔, net PnL (`realized_pnl − fee`) ✔.
**What is missing:** setup kind ✘, entry/stop/exit ✘, per-trade risk ✘, R ✘.

### 2.2 R-multiple derivation (needs a risk denominator)

`r_multiple(pnl, risk)` exists but **no risk is stored**. Options:

| Option | Mechanics | Cost |
|---|---|---|
| **A. Join with SMC setup (recommended)** | At the trade's `ctime`, take the SMC `Setup` covering that bar → `risk = abs(entry − stop) × qty`; `R = net / risk`. Unmatched → `None`. | pure join, **no migration**, R only for matched trades |
| B. Add nullable `risk`/`setup` field on `Trade` | record risk at sync time | **migration**, changes `Trade`, needs the SMC setup known at sync (it isn't — sync is in the worker) |
| C. Group fills into round-trips | reconstruct open→close positions | **out of scope**, needs order/position logic E1 does not have |

**Recommend A.** It makes the calibration join the single source of risk and
keeps `Trade` immutable (no migration, no sync change). Option B is deferred.

### 2.3 "Setup kind" linkage (needed for per-setup analytics + calibration)

`Trade` does **not** record the SMC setup. The SMC `Setup` is
`(direction, entry, stop, take_profit, rr, score, index)` — **one record**, no
name. So "tipo de setup SMC" must be a **derived vocabulary**, e.g.:

```
setup_kind := f"{direction}:score{score}"      # e.g. "long:score4", "short:score3"
setup_kind := f"{direction}:{event_kind}"      # alt: "long:bos", "short:choch"
```

**Recommended linkage: a pure join at trade time** (no field). For each
`Trade`, compute the SMC chain over candles ending at `ctime` (warm-up window)
and take the setup whose anchor bar is the latest at/before the trade → gives
`direction, entry, stop, score` → risk → R and a `setup_kind` label. Trades
with no setup in their window are "unmatched".

> **Granularity caveat (key risk):** `Trade` rows are **fills**, so one
> round-trip may produce several rows (each with its own `realized_pnl`). The
> existing journal already counts each fill as a trade; E1 keeps that convention
> (status quo) and documents it. Reconstructing round-trips is **out of scope**.

---

## 3. Metrics design (propose — pure, stdlib, never raise)

Two homes (either works; recommend splitting to keep `metrics.py` frozen-small):

### 3.1 `src/metrics.py` — additive pure scalars (do not touch existing four)

```python
def max_drawdown(equity: list[float]) -> float | None:
    """Worst peak-to-trough decline of an equity curve; None when empty.
    Returns a non-positive number (e.g. -12.5) — the decline, not the ratio."""

def win_rate(pnls: list[float]) -> float | None:
    """wins/total*100; None when empty (mirrors journal.metrics semantics:
    a win is net > 0)."""

def net_pnl(pnls: list[float]) -> float:
    """Sum of realized net PnL; 0.0 when empty."""
```

### 3.2 `src/analytics.py` — NEW pure module (groups + calibration)

Imports **only** `src.metrics` (+ stdlib). No sqlite3/rich/Django/requests.

```python
def summarize(pnls: list[float]) -> dict:
    """One bucket's stats. Keys/stability frozen:
    {"trades": int, "wins": int, "win_rate": float | None, "net_pnl": float,
     "expectancy": float | None, "profit_factor": float | None,
     "max_drawdown": float | None}"""

def group_metrics(rows: list[dict], dimension: str) -> dict[str, dict]:
    """Group net PnLs by dimension and summarize each bucket.
    `dimension` ∈ {"setup", "hour", "symbol"}; each row is
    {"net": float, "setup": str|None, "hour": int|None, "symbol": str}.
    Rows whose dimension key is None are bucketed under "unmatched"/"unknown".
    Deterministic order: keys sorted. Empty rows -> {}."""

def equity_and_drawdown(pnls: list[float]) -> dict:
    """{"equity": list[float], "max_drawdown": float | None} — one call, no
    re-traverse."""

def calibrate(
    signals: list[dict],          # SMC setups resolved at/near trade times
    trades: list[dict],           # {"net": float, "side": str, "ctime": int, "qty": float}
    *,
    window_seconds: int,
) -> dict:
    """Pure join of historical SMC signals with real trades.
    A trade MATCHES the most recent signal with the same symbol whose
    |trade.ctime - signal.time| <= window_seconds and direction == side's
    direction (BUY->long, SELL->short). Output (frozen):
    {
      "matched":   summarize(nets of matched trades),
      "unmatched": summarize(nets of unmatched trades),
      "by_setup":  {setup_kind: summarize(nets)},      # only matched
      "r_by_setup":{setup_kind: float | None},         # mean R (needs risk)
    }
    Never raises; no signals/trades -> empty buckets with None scalars."""
```

**Determinism / never-raise rules** (mirror `src/smc` and `src/metrics`):
- Pure; no `datetime.now`; `hour` is supplied by the caller (see §7 Q4).
- Mismatched/empty input → empty dict / None scalars, never raise.
- No global state, no mutation of inputs.
- `src/analytics.py` added to `test_boundary.py:PURE_MODULES`.

---

## 4. Calibration (cross historical SMC signals vs real trades)

**Question it answers:** "which setups perform?" — the win rate / expectancy of
trades that matched an SMC setup vs those that did not, grouped by
`setup_kind`.

**Two halves:**

1. **Signal extraction (I/O, web/worker zone — NOT pure).** The frozen
   `market.quotes.get_smc_payload(client, symbol, interval, limit)` only
   computes over the **newest** window (no `before`). To get *historical*
   signals aligned to trade times, E1 MUST compute the chain over candles
   ending at each trade's bar. Recommended seam: a helper in `web/` that,
   per `(symbol, interval)` found in the user's trades, fetches the DB-first
   window (**`_db_rows` + `client.kline`**, reusing the existing merged
   ascending seam) with `before = trade_ctime_seconds + 1`, runs the frozen
   `src/smc` chain (same call order as `get_smc_payload`), and yields
   `{symbol, time, direction, entry, stop, score, event_kind}` records.
   Alternative: extend `get_smc_payload` with a `before` arg (pure seam reuse) —
   **preferred**, but touches a frozen signature (add keyword-only `before=None`).
2. **Scoring (pure — `analytics.calibrate`, §3.2).** Join by
   `(symbol, direction, |Δtime| <= window_seconds)` and score.

**Output:** `{matched, unmatched, by_setup, r_by_setup}` (§3.2). This is the
"which setups perform" answer, and it is the **only source of risk** for
R-multiple (§2.2).

**Cost note:** one chain run per trade is O(trades × chain). For a per-user
history this is small; if it grows, dedupe by distinct bar and cache the
window (ponytail: no cache in v1; add keyed-by-bar memoization later).

---

## 5. UI (where it lives, how charts render without new deps)

### 5.1 Route

**New `/analytics/` screen in the `trading` app** (mirrors `journal`): GET-only,
`@login_required`, `Trade.for_user(user)` only, `src/` math delegated (never
reimplemented in view/JS). Add a nav link in `base.html`. Rationale: the issue
asks for **breakdowns + calibration + charts**, a distinct surface from the
plain `/journal/` totals; keeping `/journal/` frozen honors
`positions-journal-ui` R2.

### 5.2 Charts — **server-rendered inline SVG (recommended)**

- **No CSP-safe client chart lib for a simple equity line.** The only
  CDN script allowed is `https://unpkg.com` (`middleware.CSP_POLICY`), used for
  **LightweightCharts** on `/market/`. Reusing it here would mean a full JS
  adapter (untestable in Python, needs a `node --test` suite + E2E) for what is
  a polyline + bars.
- **Recommended:** a **pure Python SVG builder** (e.g.
  `src/analytics.py:svg_polyline(...)` or a small `web/trading/svg.py` helper
  that is pure) returning an SVG string embedded in the template via
  `|safe`. Deterministic, patch-covered by pytest, no npm/build, CSP untouched
  (inline **SVG markup** is HTML, not script). The repo already avoids SVG
  today (`grep svg` → none), so this is new but self-contained.
- **Charts to render:** equity curve (line), drawdown (the curve's under-water
  region or a bar), per-dimension win-rate/expectancy bars. Optionally reuse
  the design tokens (`--up/--dn/--accent`) via CSS classes on SVG elements.
- **`/impeccable` audit** applies to the new screen (dark terminal aesthetic,
  `aria` labels on the SVG, tabular-nums, non-color state cues) per the issue.

### 5.3 Confirmed available today

- `lightweight-charts@5.2.0` from unpkg **is** loaded on `/market/` only; the
  journal/analytics pages load **no JS**. E1 should stay JS-free (server-rendered).
- No static files / no `collectstatic` in prod — CSS/JS are served by Django
  views (`theme_css`, `chart_js`). SVG inline in the template sidesteps all of it.

---

## 6. Scoping (R14)

- Analytics view: `Trade.for_user(request.user)` **only**; all reads scoped.
- Any signal-extraction helper reads **candles** (`Candle`, global market data)
  but trades are joined in Python **after** scoping to the caller — no owned
  model accessed unscoped.
- No new owned model, **no migration** (recommended A path). If a
  nullable `Trade.setup_kind` is later chosen, it is an additive migration and
  must route through `for_user` everywhere.
- `test_owned_model_guard` MUST stay green (no `<OwnedModel>.objects.<verb>`).
- `src/analytics.py` added to `PURE_MODULES`; `src/` stays framework-free.

---

## 7. Open questions / decisions the spec MUST lock

| # | Question | Recommendation (freeze) |
|---|---|---|
| Q1 | **Setup-kind vocabulary** | `f"{direction}:score{score}"` (e.g. `long:score4`) as the canonical `setup_kind`; keep `event_kind` (bos/choch) + `direction` as secondary dimensions. |
| Q2 | **R-multiple source** | Only via the calibration join (`risk = abs(entry−stop) × qty`); unmatched trades → `R = None`. **No migration.** |
| Q3 | **Trade granularity** | Each `Trade` fill = one trade (status quo, matches the journal). Round-trip reconstruction is out of scope; documented. |
| Q4 | **Hour dimension timezone** | **UTC** hour (`(ctime_ms // 3_600_000) % 24`); caller supplies `hour` so the pure function stays deterministic/tz-free. |
| Q5 | **`ctime` unit** | epoch **milliseconds** (confirmed by `test_private_sync`); divide by 1000 before comparing to candle `time` (seconds). |
| Q6 | **Chart technology** | Server-rendered **inline SVG** (pure Python builder); **no** second CDN chart lib, no npm, no JS adapter. |
| Q7 | **Calibration match rule** | Same `symbol` + same `direction` + nearest signal with `|Δtime| <= window_seconds`; `window_seconds` default = one interval span (e.g. 3600). Match is scored once (nearest), not many. |
| Q8 | **Calibration output shape** | `{matched, unmatched, by_setup, r_by_setup}` (§3.2). |
| Q9 | **Caching / precompute** | Compute on request (per-user trade list is small); **no cache** in v1. Add keyed-by-bar memoization only if measured slow. |
| Q10 | **Metrics home** | Add `max_drawdown`/`win_rate`/`net_pnl` to `src/metrics.py`; put groups + calibration in **new** `src/analytics.py`. |
| Q11 | **Screen location** | New `/analytics/` in `trading`; leave `/journal/` frozen. |
| Q12 | **Signal extraction seam** | Extend `get_smc_payload` with keyword-only `before=None` (preferred, reuses the frozen chain) OR a `web/` helper; the pure chain stays the sole SMC math home. |

---

## 8. Risks

- **Trade granularity (highest, semantic).** `Trade` = fill, not round-trip;
  per-fill "R" and "win rate" are approximations. *Mitigation:* document Q3;
  calibrate by matching each fill to its SMC setup; round-trips are future work.
- **No stored risk → R is join-only.** Trades without a matched signal have no
  R. *Mitigation:* explicit `None` (never raise), surfaced as "—" in the UI.
- **Historical signal extraction cost.** One SMC chain pass per trade/bar.
  *Mitigation:* dedupe by `(symbol, bar)`; no cache v1, memoize later (Q9).
- **`src/` framework-free.** `analytics.py` MUST NOT import `sqlite3`, `rich`,
  `journal`, Django, or `requests`. *Mitigation:* `test_boundary.PURE_MODULES`.
- **Per-user isolation (R14).** All trade reads via `for_user`;
  `test_owned_model_guard` green. *Mitigation:* scoped view + scanner.
- **Charts without deps/CSP.** A JS chart lib would need a JS adapter (outside
  the Python patch gate) and E2E. *Mitigation:* server-rendered SVG (pure,
  patch-covered); CSP unchanged (no inline script).
- **Patch coverage 100%.** Every changed Python line needs a test —
  `diff-cover --fail-under=100`. *Mitigation:* all math pure and unit-tested;
  SVG builder deterministic and asserted on a fixture.
- **Determinism.** Floating point + dict ordering. *Mitigation:* sorted keys,
  `statistics.fmean`, no `datetime.now` in pure functions.
- **Spec surface.** This touches `src/metrics.py`, a new module, tables/specs.
  If SMC `Setup.direction` is `"long"|"short"` and `side` is `"BUY"|"SELL"`, the
  mapping MUST live in one place (a pure helper) to avoid drift.

---

## 9. Proposed PR shape + rough size

| File | Impl | Tests | Total |
|---|---|---|---|
| `src/metrics.py` (`max_drawdown`/`win_rate`/`net_pnl`) | ~35 | — | ~35 |
| `src/analytics.py` (NEW: summarize/group/calibrate/equity) | ~150 | — | ~150 |
| `tests/test_analytics.py` + `tests/test_metrics.py` additions | — | ~220 | ~220 |
| `tests/test_boundary.py` (`analytics.py` into PURE_MODULES) | ~2 | — | ~2 |
| `web/market/quotes.py` (`before` kwarg on `get_smc_payload`) or helper | ~30 | — | ~30 |
| `web/trading/analytics.py` (signal extraction + row build, web seam) | ~90 | — | ~90 |
| `web/trading/views.py` + `urls.py` (`analytics_view`) | ~50 | — | ~50 |
| `web/trading/templates/trading/analytics.html` (SVG + tables) | ~120 | — | ~120 |
| `web/trading/svg.py` (pure SVG builder) + `theme.css` | ~90 | — | ~90 |
| `web/accounts/templates/registration/base.html` (nav link) | ~3 | — | ~3 |
| `tests/web/test_analytics.py` (view, scoping, fixtures, CSP) | — | ~240 | ~240 |
| `tests/web/test_market_ux.py`/E2E + `/impeccable` audit | — | ~120 | ~120 |

**Total ≈ 1150 changed lines → 400-line budget risk: HIGH.** Chained PRs
recommended.

### Recommended: CHAINED PRs, 3 slices

1. **Slice 1 — pure metrics + analytics core (Python, patch-100).**
   `max_drawdown`/`win_rate`/`net_pnl` in `src/metrics.py`; new
   `src/analytics.py` (`summarize`, `group_metrics`, `equity_and_drawdown`,
   `calibrate`); `test_boundary` update; `tests/test_metrics.py` +
   `tests/test_analytics.py`. Autonomous, no web, no JS. ~**410 lines**.
2. **Slice 2 — signal extraction + `/analytics/` view (Python).**
   `get_smc_payload(before=...)` or a web helper; the web seam that builds
   per-dimension rows and the calibration input from `Trade.for_user`; the
   `analytics` view + route + nav link + scoping/fixture tests. ~**380 lines**.
3. **Slice 3 — UI (SVG charts) + E2E + `/impeccable` audit.**
   Pure SVG builder + template + CSS; E2E (seam/DOM, no image diffs) and the
   `/impeccable` audit. ~**360 lines**.

2-slice alternative folds 3 into 2 (~740 lines, one heavier review).
**Recommend 3 slices** — same shape as C1/D2, each autonomous with its own
verification and trivial rollback.

### Out of scope (fence)

- ML / prediction (issue: future). Order execution (**never**).
- Round-trip reconstruction from fills (future). Any new runtime dependency,
  npm/build step, or second chart library. Caching/precompute (v1 on-request).
- Persisting `setup_kind`/risk on `Trade` (deferred, would need a migration).
- Changing the frozen `src/metrics.py` four functions or `journal.metrics()`.

---

## Affected Areas

- `src/metrics.py` — add `max_drawdown`, `win_rate`, `net_pnl` (additive; frozen four untouched).
- **NEW** `src/analytics.py` — pure groups + calibration + equity/drawdown.
- **NEW** `tests/test_analytics.py`, `tests/test_metrics.py` additions.
- `tests/test_boundary.py` — register `analytics.py` in `PURE_MODULES`.
- `web/market/quotes.py` — `get_smc_payload(..., before=None)` (or a shared seam) for historical signals.
- **NEW** `web/trading/analytics.py` — signal extraction + row/dimension build (web seam, I/O).
- `web/trading/views.py` + `web/trading/urls.py` — `analytics` view + `/analytics/` route.
- **NEW** `web/trading/templates/trading/analytics.html` — breakdowns + calibration + SVG charts.
- **NEW** `web/trading/svg.py` — pure server-side SVG builder.
- `web/accounts/templates/registration/theme.css` — analytics/chart styles.
- `web/accounts/templates/registration/base.html` — nav link.
- **NEW** `tests/web/test_analytics.py`; `tests/web/test_market_ux.py`/`test_market_e2e.py` additions.
- **ARCHIVE-TIME** — new `openspec/specs/performance-analytics/spec.md`; possibly a delta to `trade-metrics`.

No `src/` framework import, no migration, no order surface, no new dependency.

## Ready for Proposal

**YES** — the math layer (`src/metrics`), the SMC chain, and the per-user
`Trade` seam all exist and are frozen; E1 is an additive analytics + calibration
capability plus a new read-only screen. The spec MUST lock: the **setup-kind
vocabulary** (Q1), the **R-multiple source** (Q2, join-only, no migration), the
**fill granularity** (Q3), the **hour timezone** (Q4), the **chart technology**
(Q6, inline SVG), and the **calibration match rule + output shape** (Q7/Q8).
