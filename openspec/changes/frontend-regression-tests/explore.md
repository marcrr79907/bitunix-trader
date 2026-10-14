# Exploration: frontend-regression-tests (issues #143/#144/#145 — DEBT-2/3/4)

## Current State

F1 (chart-legend), F2 (chart-indicator-settings) and F3 (chart-shell) each shipped
green (`pass_with_warnings`, 0 blockers) but left a small set of scenarios that the
verify reports proved **only via throwaway session probes** — no committed regression
test guards them. This change commits those probes as tests. It is **test-only**: no
production code, no spec behavior change, no new runtime dependency, CSP unchanged.

Gate baseline today (from the three verify reports): `node --test "tests/js/**/*.test.js"`
→ **134 passed**; `pytest -m e2e -p no:randomly` → **52 passed**; Python unit 337;
ruff clean. All target scenarios are DOM/computed-style/source assertions — no image
diffs, no new seam key (the `window.marketChart` seam stays **8 keys**).

The architecture (F0, `docs/architecture/chart-modules.md`): layered ESM under
`web/market/templates/market/`. Pure cores import nothing; `chart-host.js` is the only
`LightweightCharts` construction surface; controllers are DI factories; `main.js` owns
`boot()`/`switchTo()` and the `gen` guard. R14 layer rule includes **"no module M
exceeds ~300 lines"**.

## Affected Areas

- `tests/js/legend-core.test.js` — add the LC2 source-purity assert (issue #143 a) and the LC1 style-independence assert (#144 W3).
- `tests/js/chart-controllers.test.js` — (optional) legend-ignores-style unit assert.
- `tests/web/test_market_e2e.py` — 3 legend E2E (#143 b/c/d), 1 rebuild-count E2E (#144 W2), 3 shell E2E (#145 W1/W2/W3). Reuses every fixture already in the file.
- `tests/web/test_module_size_guard.py` — **new** R14 size ceiling guard (#144 W4).
- `tests/web/test_isolation.py` — extend for style A≠B (#144 W5).
- `openspec/specs/{chart-legend,chart-indicator-settings,chart-shell,market-chart}/spec.md` — verification-method wording only (the specs already contain the scenarios; the delta records "now covered by a committed test").
- No production file is touched. No change to `web/market/templates/**`, `views.py`, `quotes.py`, `theme.css`, `requirements.txt`, or CSP.

## Scenario → Exact Test Map

### Issue #143 — DEBT-2 (F1 chart-legend): 4 probe-only scenarios

| # | Scenario (verify warning) | File | Mechanism / assertion |
|---|---|---|---|
| a | **LC2** "no indicator math / imports nothing" (W1) | `tests/js/legend-core.test.js` (add) | `readFileSync` of `legend-core.js` (path via `fileURLToPath(import.meta.url)`), assert `^\s*(import\|export\s+[^;]*\bfrom)\b/m` is `false` — copy the exact pattern in `tests/js/indicator-settings-core.test.js:143-146`. Optional second regex on **comment-stripped** source for `EMA\|RSI\|ATR\|Math.pow` (see risk R2). |
| b | **LC4** re-subscribe across rebuilds — no stale handler (W2) | `tests/web/test_market_e2e.py` (add) | Boot → 5m seeded → wait `#chart .chart-legend` present. Force a **second** `chart:built` (toggle an indicator checkbox `.indicator-toggle`, e.g. `bollinger`). Wait for the rebuilt chart, move the mouse over `#chart canvas` (same pattern as `test_legend_overlay_shows_ohlc_and_updates_on_crosshair:1106-1116`), assert `.lg-ohlc` textContent contains `"H "` and `aria-live == "off"` → the handler re-bound to the new chart. Assert `.chart-legend` count `== 1` (no duplicate overlay). |
| c | **LC5** idle summary announced once, not per mousemove (W2) | `tests/web/test_market_e2e.py` (add) | Inject a `MutationObserver` on `.chart-legend` with `attributeFilter:["aria-live"]` via `page.evaluate`, counting transitions. Drive ~20 rapid `page.mouse.move` across the canvas, then leave (`page.mouse.move(0,0)`), wait 400ms (debounce is 300ms). Assert transitions `<= 2` and final `aria-live == "polite"`; assert that during hover it is `"off"` (never flips per move). |
| d | **LC6** all active series appear in the legend (W2) | `tests/web/test_market_e2e.py` (add) | Default actives = `sma`, `ema`, `rsi` (chart.html checked). Wait idle rows. Assert `.chart-legend .lg-row` count `== 3` (exact, not `>=1`) and `all_inner_texts()` of `.lg-token` == `["SMA 20","EMA 20","RSI"]` (overlays first, then pane). |

### Issue #144 — DEBT-3 (F2 chart-indicator-settings): W2/W3/W4/W5

| # | Scenario (verify warning) | File | Mechanism / assertion |
|---|---|---|---|
| W2 | One rebuild per `style` change (#68, W2) | `tests/web/test_market_e2e.py` (add) | After `_wait_ready`, wrap the global: `page.evaluate("() => { const c = LightweightCharts.createChart; window.__builds = 0; LightweightCharts.createChart = (...a) => { window.__builds++; return c(...a); }; }")`. Open the sma gear (`_SETTINGS_GEAR`), change color/width, apply (`#indicator-settings-dialog button[value=ok]`), wait for the series to change, then assert `window.__builds === 1`. Fallback mechanism (no global mutation): count kline GET requests via `page.on("request", ...)` — one rebuild → one `fetchHistory()` → one `/market/api/kline` GET. |
| W3 | Legend output unchanged when `styles.sma.precision` differs (W3) | `tests/js/legend-core.test.js` (add) | Source purity: assert `legend-core.js` **and** `controllers/legend.js` contain no `styles`/`priceFormat` token (grep already confirms zero today). Behavioural alternative (optional): E2E — set sma precision 6, apply, assert the `.lg-row` sma value still has exactly 2 decimals (DECIMALS.sma=2), proving the legend ignores style precision. |
| W4 | R14 module-size ceiling guard (W4) | `tests/web/test_module_size_guard.py` (**new**) | Pure Python (no Django client needed): `Path(.../"web/market/templates/market").rglob("*.js")`, per file `len(path.read_text().splitlines())`, assert `<= CEILING`. **Decision required — see Open Q3.** `chart-host.js` is **326 lines** today, so a literal `CEILING=300` FAILS at commit time. Recommend `CEILING=350` (drift guard, comment naming R14 "~300" + chart-host 326 as the current high-water mark) so it is test-only and passes. |
| W5 | `style` A≠B — B never sees A's style (W5) | `tests/web/test_isolation.py` (extend) | Create A's `ChartLayout` with `indicators=[{"token":"sma","style":{"color":"#ff0000","lineWidth":3,"precision":4}}]`; assert `ChartLayout.for_user(user_b).count() == 0` and `ChartLayout.for_user(user_b).get(...)` raises `DoesNotExist` (so B can never read the row that carries the style). See Open Q4: the *stronger* API-level form lives in `tests/web/test_market_api.py::test_layout_isolation_b_get_never_sees_a` (B GET returns default with no `style` key). |

### Issue #145 — DEBT-4 (F3 chart-shell): W1/W2/W3

| # | Scenario (verify warning) | File | Mechanism / assertion |
|---|---|---|---|
| W1 | Keyboard: Enter/Space/arrows + `aria-pressed` (W1) | `tests/web/test_market_e2e.py` (add) | Focus `.interval-chip[data-interval="1m"]`; `page.keyboard.press("ArrowRight")` → `document.activeElement` is the `5m` chip (via `page.evaluate`); `press("Enter")` → 5m chip `aria-pressed=="true"`, 1m `"false"`, `#interval` input_value `"5m"`. Repeat `press("Space")` on `15m` → 15m pressed. |
| W2 | `#chart` follows container resize (autoSize) (W2) | `tests/web/test_market_e2e.py` (add) | Load at 1280×900, wait root fills `#chart` (same wait as `test_chart_fills_height_and_canvas_tracks_container:1190-1197`). Read `#chart` height. `page.set_viewport_size({"width":640,"height":800})`, wait for `.tv-lightweight-charts` height to track `#chart` (abs `<= 2`) and stay `ready === true` (no re-boot). |
| W3 | Desktop >820px: toggle hidden, layout unchanged; focus/names (W3) | `tests/web/test_market_e2e.py` (add) | At 1280 (or 821)px: assert `.panel-toggle` **not visible**, `#panel` visible, `#chart` visible. Accessible names: `.interval-chips` has `role="group"` + `aria-label="Interval"`; `.panel-toggle` accessible name "Panel", `aria-expanded=="true"`; chips carry `aria-pressed`. Focus outline: focus a chip, assert computed `outline-style != "none"` (global `:focus-visible`). |

## Test-Only Scope Proof

Every scenario above is expressible with the **existing** test seams and fixtures:

- `window.marketChart` (8 keys: `chart`, `candleSeries`, `panes`, `ready`, `drawings`, `smc`, `smcCounts`, `smcToggles`) exposes the chart, candle series and panes needed for W2/W3/E2E.
- The v5 public API `window.marketChart.chart.panes()[i].getSeries().options()` (already used by `_pane0_series`) covers any style read-back.
- `LightweightCharts.createChart` is a **global** (CDN) that `chart-host.js:169` calls — wrapping it in `page.evaluate` counts builds **without touching the seam** or adding a 9th key.
- The bus is **not** exposed and does not need to be: rebuild counting uses the `createChart` wrapper (or the kline GET), not a new seam.

**Prod change needed: NO** — with one caveat. The **only** scenario that could force a production edit is **W4** if a literal `~300`-line ceiling is enforced: `chart-host.js` is **326 lines** (and was already flagged `W1` open in `archive/2026-10-13-chart-scales`: it was 322 then, 326 now). A strict 300 guard would fail today and would require a **prod refactor of chart-host.js** — explicitly out of scope for a test-only change. Recommended minimal non-behavioral resolution: set the guard at 350 with a documented comment (no prod edit). No other scenario needs a hook; no new global/seam/dependency.

## Shared Fixtures / Helpers

Already exist and should be **reused unswooped** (all in `tests/web/test_market_e2e.py`):

- `browser_page` (yields `(page, base_url)`, session cookie injected) — every E2E.
- `seeded_5m_candles` / `seeded_eth_5m_candles` — deterministic varied 5m data (legend + shell E2E).
- `e2e_user`, `saved_layout`, `per_interval_layouts`, `saved_interval_preference` — only if a test needs a persist path (not required here).
- `_wait_ready(page)`, `_poll(page, fn)`, `_dialog_open(page)`, `_pane0_series(page)`, `_SETTINGS_GEAR` — reuse verbatim.
- `route_web_socket("wss://fapi.bitunix.com/**", handler)` pattern (installed **before** `goto`) — reusable if a legend test wants deterministic pushes (not required for #143 b–d).
- `tests/js` pattern: `readFileSync` + `fileURLToPath(import.meta.url)` (as in `indicator-settings-core.test.js`).
- `tests/web/test_isolation.py` fixtures `user_a` / `user_b` (conftest).

**New needed:** one tiny helper `_active_element(page)` (or inline `page.evaluate`) for keyboard assertions; one **new** standalone file `tests/web/test_module_size_guard.py` (no fixtures). Nothing else.

## Key Decisions (proposed)

1. **Rebuild counting (W2):** wrap `window.LightweightCharts.createChart` in-page with a counter; assert `=== 1` after one style change. Zero production change, no seam key. Kline-GET count is the fallback if the wrapper proves brittle.
2. **Legend-does-not-read-styles (W3):** commit the **source-grep** purity assert (cheap, precise, matches the existing core-purity precedent) rather than a slow E2E; optionally add the E2E behavioural form.
3. **Re-subscription trigger (#143 b):** force the second `chart:built` via an **indicator toggle** (keeps the seeded 5m data populated so hover is assertable) instead of an interval switch (no seeded target interval). Same lifecycle path (`buildChart()` → `chart:built`).
4. **Size guard (W4):** `CEILING=350` drift guard, documented, test-only — **unless** the team wants literal `~300`, which forces the chart-host refactor (prod).
5. **W5 location:** follow the issue (`test_isolation.py`, model-level) and optionally mirror the stronger API-level assert in `test_market_api.py`.

## Open Questions / Decisions

1. **Q1 — #143 b trigger:** indicator-toggle rebuild (recommended, keeps data) vs interval switch. If interval switch is mandatory, a second seeded interval fixture is needed.
2. **Q2 — W3 mechanism:** source-grep only, or source-grep + E2E behavioural? (Recommend source-grep only; E2E is slower and adds little.)
3. **Q3 — W4 ceiling value (blocking decision):** literal `300` (fails → requires chart-host prod refactor) vs `350` drift guard (test-only). Recommend 350.
4. **Q4 — W5 location:** `test_isolation.py` (model, as the issue names) vs `test_market_api.py` (API, stronger). Recommend doing the issue's model test **and** a one-assert API extension.
5. **Q5 — #143 c exactness:** MutationObserver transition count (probe method, `<=2`) vs simple attribute-state assertions (`"off"` while hovering, `"polite"` after leave+debounce). Recommend the state assertions (deterministic, no counting flake).

## Risks

- **R1 — Vacuous passes.** `.lg-row count >= 1` (the current E2E) passes even if series are missing. New tests MUST assert **exact** counts/labels (issue #143 d).
- **R2 — Comment false positive.** `legend-core.js` header comments literally mention `EMA/RSI/ATR`, so a naive formula denylist regex matches prose. Check **imports only**, or strip `//` comments before the token scan.
- **R3 — Flakiness.** `aria-live` debounce is 300ms; use `wait_for_function`/bounded waits, never fixed long sleeps; keep `-p no:randomly` for E2E; the size guard is pure filesystem (no flake).
- **R4 — Volatile selectors.** All target selectors (`.interval-chip[data-interval]`, `.chart-legend`, `#indicator-settings-dialog`, `.panel-toggle`, `.tv-lightweight-charts`) are already used by passing tests — low risk. Avoid asserting CSS class names for state (use `aria-pressed`/`aria-expanded`).
- **R5 — Frozen 8-key seam.** No test may add a 9th `window.marketChart` key; the `createChart` wrapper stays on the global, not the seam. Assert `Object.keys(window.marketChart).length === 8` where relevant.
- **R6 — No-deps / CSP.** Only `node:fs`/`node:url` (stdlib) and `pathlib`/`ast`-style Python; no new runtime dep; no CSP/inline-script change. A server-side grep test (like `test_market_page_has_no_inline_script_or_handler`) already guards inline handlers.
- **R7 — W4 false-negative.** `rglob("*.js")` must include `controllers/` and use `splitlines()` (not a trailing-newline-sensitive `count("\n")`). Guard should name the offending file + line count in the failure message.
- **R8 — E2E is dev-only** (deselected in CI via `addopts = "-m 'not e2e'"`). These regressions are only run locally / on the dev machine — accepted status quo for the JS/template layer (same as F0/F1/F2/F3).

## Proposed PR Shape

Test-only, ~370–420 insertions (bulk = E2E). Given the review budget (400 lines) and the
user's "granularity por fase" for the issues, recommend **3 slices, one per issue**, chained
behind a tracker branch (`feat/frontend-regression-tests`):

- **Slice 1 (#143, F1 legend):** `tests/js/legend-core.test.js` (+~25) + 3 E2E (~+100) ≈ 125 lines.
- **Slice 2 (#144, F2 settings):** node purity/keyE2E (~+45) + `test_module_size_guard.py` (~+35) + E2E rebuild-count (~+45) + isolation extend (~+25) ≈ 150 lines.
- **Slice 3 (#145, F3 shell):** 3 E2E (~+120) ≈ 120 lines.

A single PR (~400) is acceptable if it lands at/under budget; the 3-slice split maps 1:1 to
the issues and each slice is independently reviewable and revertible. **Recommend 3 slices.**

## Ready for Proposal

**Yes.** All 10 scenarios are mapped to concrete files, selectors and mechanisms validated
against the current code; no production change is required (except the W4 ceiling decision).
One blocking-ish decision is Q3 (ceiling value 300 vs 350) — recommend 350 to keep it test-only.
