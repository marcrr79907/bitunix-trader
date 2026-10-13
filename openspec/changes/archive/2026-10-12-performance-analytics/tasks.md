# Tasks: performance-analytics (issue #78, Fase E1 — roadmap close)

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

Chain: all slices base on tracker `feat/performance-analytics`; each later slice bases on the immediate previous slice branch; merge each to the tracker before branching the next. S1 pure core ~410 · S2 extraction + view ~380 · S3 SVG UI + E2E ~360.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1150 (core ~410, view ~380, UI/E2E ~360) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | S1 pure core → S2 extraction + view → S3 SVG UI + E2E |
| Delivery strategy | ask-on-risk (chain pre-chosen) |
| Chain strategy | feature-branch-chain |

### Suggested Work Units

| Unit | Goal | Likely PR | Base boundary |
|------|------|-----------|---------------|
| 1 | `metrics.py` +3 fns; NEW `src/analytics.py` (summarize/group_metrics/equity_and_drawdown/calibrate/equity_svg/bars_svg); `PURE_MODULES`; metrics/analytics/boundary tests | PR 1 | tracker |
| 2 | `get_smc_payload(before=…)`; `web/trading/analytics.py` seam; `analytics_view` + `/analytics/` route + nav + scoping tests | PR 2 | PR 1 branch |
| 3 | `trading/analytics.html` + `theme.css`; SVG/E2E tests; `/impeccable` audit | PR 3 | PR 2 branch |

## Guard/Edge Matrix

- [ ] `PURE_MODULES` (R12): `"analytics.py"` registered in `tests/test_boundary.py`; imports stdlib + `src.metrics` only (no sqlite3/rich/Django/requests) — `test_pure_modules_are_stdlib_only` green; `"metrics.py"` still registered (S1).
- [ ] R14 scoping (R14.5): `analytics_view` reads trades ONLY via `Trade.for_user(request.user)`; no `<OwnedModel>.objects.<verb>()` in request path — `test_owned_model_guard.py` stays green (S2).
- [ ] Join-only R (Q2): no `Trade` field, no migration; `risk=|entry−stop|×qty`; unmatched → `None`, rendered "—" (no divide-by-zero) (S1/S2).
- [ ] Determinism/no-clock (A5): sorted keys, `statistics.fmean`, hour caller-supplied `(ctime_ms//3_600_000)%24`; no `datetime`/`random`/I/O; same input → byte-identical output (S1).
- [ ] Never-raise (A1–A4): empty/malformed/`window_seconds<=0`/unknown `dimension` → empty buckets + `None` scalars, no raise; inputs not mutated (S1).
- [ ] Setup vocabulary (Q1): `setup_kind == f"{direction}:score{score}"`; `direction∈{long,short}`; `BUY→long`/`SELL→short` mapping in ONE pure helper; `None` key → `unmatched`/`unknown` (S1/S2).
- [ ] Nearest-match (Q7/Q5): same `symbol`+`direction`, nearest `|Δ|<=window_seconds`; `ctime//1000` before compare; ties → smaller `|Δ|` then earlier `time` (S1).
- [ ] SVG escaping/CSP (AS4): `xml.sax.saxutils.escape` on every label; SVG only via `|safe`; no inline `<script>`, no `on*=` handler; `Content-Security-Policy` unchanged; inline SVG is HTML, not script (S1/S3).
- [ ] No new dep: `requirements.txt` unchanged; no npm/build; no second chart lib; unpkg/LightweightCharts stays `/market/`-only (S2/S3).
- [ ] Read-only (AS6): no order verb/path, no exchange-client import; `test_no_order_surface.py` green; no schema field/migration; `/journal/` frozen (S2).
- [ ] Upstream degrade (AS5): seam swallows `BitunixError`/`RequestException` → empty signals, never 500; SMC math stays ONLY in `src/smc/` (S2).
- [ ] `before` additive (AS5): `get_smc_payload(client, symbol, interval, limit, *, before=None)`; omitted == today's newest-window payload (S2).

## Slice 1 — Pure core: metrics + analytics (base: tracker)

Dep: none (frozen `src/metrics.py` four fns, frozen `src/smc`). Rollback: delete `src/analytics.py` + `tests/test_analytics.py`; remove `"analytics.py"` from `PURE_MODULES`; drop `max_drawdown`/`win_rate`/`net_pnl` + their tests. No web, no JS.

- [ ] 1.1 **RED** `tests/test_metrics.py` (R8/R9/R10): `max_drawdown([10,5,8,2])==-8.0`, monotonic `[1,2,3]→0.0`, `[]→None`; `win_rate([10,-5,5])≈66.666`, `[1,2]→100.0`, `[0,-1]→0.0`, `[]→None`; `net_pnl([10,-5,5])==10.0`, `[]→0.0`; no input mutation; frozen four unchanged. Acceptance: fails before 1.4.
- [ ] 1.2 **RED** `tests/test_analytics.py` (A1–A4): `summarize([10,-5,5])` exact dict (`trades=3,wins=2,win_rate≈66.67,net_pnl=10.0,expectancy≈3.33,profit_factor=3.0,max_drawdown=-5.0`); empty → zero/None; `group_metrics` sorted keys + `unmatched`/`unknown` + unknown dim → `{}` + `[]→{}`; `equity_and_drawdown([5,-2,3])` → `{[5,3,6], -2.0}`; `calibrate` nearest-in-window match / outside-window unmatched / direction mismatch / tie-break / zero-risk → `None` R / empty & `window_seconds=0` no-raise; no mutation; determinism (call twice). Acceptance: fails before 1.5.
- [ ] 1.3 **RED** `tests/test_analytics.py` SVG (A5/AS4): `equity_svg`/`bars_svg` deterministic byte-identical strings; empty → fixed empty-state SVG; label escaping asserted (`<&>` escaped); no raise. Acceptance: fails before 1.5.
- [ ] 1.4 **RED** `tests/test_boundary.py` (R12): `"analytics.py"` in `PURE_MODULES`; stdin-only check green; `"metrics.py"` still present. Acceptance: fails before 1.6.
- [ ] 1.5 **GREEN** `src/metrics.py`: add `max_drawdown`, `win_rate`, `net_pnl` (stdlib only; frozen four untouched). Acceptance: 1.1 green.
- [ ] 1.6 **GREEN** `src/analytics.py` (NEW): `summarize(pnls)`, `group_metrics(rows, dimension)`, `equity_and_drawdown(pnls)`, `calibrate(signals, trades, *, window_seconds)`, `equity_svg`, `bars_svg`; imports `src.metrics` + stdlib only; `saxutils.escape` labels; sorted/fmean/deterministic; never raise. Acceptance: 1.2/1.3 green.
- [ ] 1.7 **GREEN** `tests/test_boundary.py`: register `"analytics.py"`. Acceptance: 1.4 green.
- [ ] 1.8 **REFACTOR** ruff `check`+`format --check` clean. Acceptance: S1 green, patch 100%.

## Slice 2 — Historical signal extraction + `/analytics/` view (base: S1 branch)

Dep: S1 API (`src.analytics`). Rollback: revert `get_smc_payload(before=…)` to the frozen signature; delete `web/trading/analytics.py` + `analytics_view` + route + nav link + `tests/web/test_analytics.py` scoping cases.

- [ ] 2.1 **RED** `tests/web/test_analytics.py` (AS1/AS2/AS3/AS5): anon → 302; authed 200 HTML extending base; A≠B (B sees empty, no A symbols/data); no-trades → 200 empty state; grouped `setup`/`hour`/`symbol` buckets present with metric columns; calibration `matched`/`unmatched`/`by_setup` render, `None` R shows "—"; view/template duplicate no formula; `before` bounds and omitted == today. Acceptance: fails before 2.4.
- [ ] 2.2 **RED** `tests/web/test_isolation.py` / `test_owned_model_guard.py` (R14.5): analytics-style fixture calling `Trade.objects.all()` is flagged; real view scans clean. Acceptance: fails before 2.5.
- [ ] 2.3 **GREEN** `web/market/quotes.py` (AS5): `get_smc_payload(client, symbol, interval, limit, *, before=None)` passing `before` to `_fetch_window`; chain unchanged. Acceptance: 2.1 `before` cases green.
- [ ] 2.4 **GREEN** `web/trading/analytics.py` (NEW): `extract_signals(client, symbol, interval, bars, before)` — dedupe by `(symbol, bar=ctime//3_600_000)`, one `get_smc_payload(...)` per distinct bar, swallow `BitunixError`/`RequestException` → `[]`; row build `{net,hour,symbol,side,qty,ctime}` from `Trade.for_user`. Acceptance: 2.1 green.
- [ ] 2.5 **GREEN** `web/trading/views.py::analytics_view` (`@login_required`, GET-only): `Trade.for_user(request.user)` only; `group_metrics` per dim; `calibrate(rows, signals, window_seconds=3600)`; `equity_and_drawdown`; context `{groups, calibration, equity_svg, bars_svg, empty}`; upstream degrade → empty signals, never 500. Acceptance: 2.1/2.2 green.
- [ ] 2.6 **GREEN** `web/trading/urls.py`: `path("analytics/", views.analytics_view, name="analytics")`; `/journal/` route untouched. Acceptance: route resolves; AS1 green.
- [ ] 2.7 **GREEN** `web/accounts/templates/registration/base.html`: add **Analytics** nav link (mirrors existing links). Acceptance: 2.1 green.
- [ ] 2.8 **REFACTOR** ruff clean; confirm no `client` import in view (seam owns I/O); scanner clean. Acceptance: S2 green, patch 100%.

## Slice 3 — SVG UI + E2E + `/impeccable` (base: S2 branch; final)

Dep: S2 view context (`equity_svg`/`bars_svg` strings, groups, calibration). Rollback: delete `trading/analytics.html`; revert `theme.css` analytics rules; drop E2E additions. `/journal/` untouched.

- [ ] 3.1 **RED** `tests/web/test_analytics.py` SVG/E2E (AS4): response contains inline `<svg role="img"`/`aria-label` or `<title>`; no `<script>`; no `on*=` handler; `Content-Security-Policy` equals prior value; labels escaped (no raw `<` from a symbol); A≠B E2E with a real trade set; SVG parses via `xml.etree`. Acceptance: fails before 3.2.
- [ ] 3.2 **GREEN** `web/trading/templates/trading/analytics.html` (NEW): extends base; server-rendered breakdown tables (`setup`/`hour`/`symbol`, `.panel`/`.num`/`--up`/`--dn`, tabular-nums); calibration block; `equity_svg`/`bars_svg` via `|safe`; empty states; no JS. Acceptance: 3.1 green.
- [ ] 3.3 **GREEN** `web/accounts/templates/registration/theme.css`: analytics/chart styles (SVG stroke via CSS classes, non-color state cues, tabular-nums). Acceptance: 3.1 green.
- [ ] 3.4 **E2E + `/impeccable`**: run the `/impeccable` audit on `/analytics/` (dark terminal aesthetic, aria labels, non-color cues); fix findings; record audit. Acceptance: audit applied; 3.1 green.
- [ ] 3.5 **REFACTOR** ruff clean; confirm CSP unchanged, `requirements.txt` unchanged. Acceptance: S3 green, patch 100%.

## Phase Verification (per slice + close)

- [ ] V.1 `python -m pytest` green; `diff-cover --fail-under=100` on changed lines.
- [ ] V.2 `ruff check . && ruff format --check .` green; `requirements.txt` unchanged; `test_no_order_surface.py` clean.
- [ ] V.3 `test_boundary.py` (analytics in `PURE_MODULES`) + `test_owned_model_guard.py` + `test_isolation.py` green; `/analytics/` CSP unchanged; `/journal/` frozen.

## Risks

- **R1** S2 consumes the S1 `src.analytics` API and S3 the S2 context — do not branch a child before its parent merges to the tracker.
- **R2** Two spec/contract naming deltas: design's `summarize(trades)`/`group_by` are superseded by spec + frozen contract (`summarize(pnls)`, `group_metrics`, plus `equity_and_drawdown` from A3). Implement per spec A1–A4.
- **R3** S1 ~410 lines near the budget edge; split the analytics test battery if the reviewer prefers.
- **R4** R is join-only — unmatched trades have no R; UI MUST show "—", never divide by zero.
- **R5** Trade = fill, not round-trip — per-fill win/R are approximations (Q3 documented; round-trips future).
- **R6** Signal-extraction cost O(distinct bars × chain) — deduped by bar; no cache v1 (`ponytail:` memoize later if measured slow).
- **R7** SVG `|safe` XSS — closed by `saxutils.escape` at the builder; asserted in 1.3/3.1.
