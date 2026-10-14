# Tasks: frontend-regression-tests (issues #143/#144/#145 — DEBT-2/3/4)

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

**TEST-ONLY** — no production file, no `src/`, no seam key (frozen 8 keys), no new dep, CSP unchanged. Strict TDD (node --test + E2E). E2E is **dev-only** (deselected in CI via `addopts = "-m 'not e2e'"`). Anti-vacuity: every assertion is an **exact** count (`==`, never `>=1`) and has a **RED-check**.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~395 total (S1 ~125 · S2 ~150 · S3 ~120) |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR S1 → PR S2 → PR S3 |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

### Suggested Work Units (bases)

| Unit | Goal | PR | Base |
|------|------|----|------|
| S1 | #143 F1 legend regressions | PR 1 | tracker `feat/frontend-regression-tests` |
| S2 | #144 F2 settings regressions + size guard | PR 2 | S1 branch |
| S3 | #145 F3 shell regressions | PR 3 | S2 branch |

Merge each slice into the tracker before branching the next; only the tracker merges to main.

## Guard/Edge Matrix

- [ ] Vacuous `>=1` → **exact `==`** counts/labels (R1, S1d)
- [ ] Comment false-positive (R2) → strip `//`+`/* */` before token scan (S1a, S2W3)
- [ ] `aria-live` debounce flake (R3) → bounded `wait_for_function` + one 400ms settle, no long sleeps
- [ ] Frozen seam (R5) → wrap CDN `LightweightCharts.createChart` global, not the seam; assert `Object.keys(window.marketChart).length === 8`
- [ ] Size false-negative (R7) → `rglob` incl. `controllers/`, `splitlines()`, scanned count `> 5`
- [ ] New dep/CSP (R6) → stdlib only (`node:fs`/`node:url`, `pathlib`); no inline script/handler
- [ ] No `web/`/`src/` production line change; `requirements.txt` unchanged

## S1 — #143 (F1 chart-legend) · ~125 · base tracker

- [ ] 1.1 **RED** `tests/js/legend-core.test.js`: `readFileSync(legend-core.js)` via `fileURLToPath(import.meta.url)`; comment-strip; assert `^\s*(import|export\s+[^;]*\bfrom)\b/m` **false** + no `EMA|RSI|ATR|Math.pow` token. RED: add an `import` → fails (LC2).
- [ ] 1.2 **GREEN** 1.1 passes on current `legend-core.js` (118 lines); `node --test "tests/js/**/*.test.js"` green.
- [ ] 1.3 **RED** `test_market_e2e.py`: `seeded_5m_candles`; toggle `.indicator-toggle[value="bollinger"]` → 2nd `chart:built`; wait; `mouse.move` over `#chart canvas`; assert `.chart-legend` count **== 1** and `.lg-ohlc` contains `"H "`. RED: unwire re-subscribe → stale handler → no update (LC4).
- [ ] 1.4 **RED** same file: `MutationObserver` on `.chart-legend` (`attributeFilter:["aria-live"]`); 20× `mouse.move`, leave `(0,0)`, wait 400ms; assert transitions **<= 2**, hover `"off"`, final **== "polite"**. RED: remove debounce → spike (LC5).
- [ ] 1.5 **RED** same file: idle `.chart-legend .lg-row` count **== 3**; `all_inner_texts()` of `.lg-token` **== `["SMA 20","EMA 20","RSI"]`**. RED: drop `rsi` default → `!=3` (LC6).
- [ ] 1.6 **GREEN** assert `Object.keys(window.marketChart).length === 8`; `pytest -m e2e -p no:randomly` green; ruff clean.
- [ ] 1.7 **Rollback**: revert the LC2 block + 3 E2E. No production impact.

## S2 — #144 (F2 chart-indicator-settings) · ~150 · base S1

- [ ] 2.1 **RED** `tests/js/legend-core.test.js`: comment-stripped `legend-core.js` **and** `controllers/legend.js` contain **no** `styles`/`priceFormat` token. RED: add a `styles` read (W3).
- [ ] 2.2 **GREEN** 2.1 + full node suite green.
- [ ] 2.3 **RED** NEW `tests/web/test_module_size_guard.py` (pure fs, no fixtures): `rglob` `web/market/templates/market/**/*.js`, `len(read_text().splitlines())`; `CEILING = 300`; `ALLOWLIST = {"chart-host.js"}` (annotated: R14 "~300", DEBT-5/#146, 326-line high-water mark); assert non-allowlisted **<= 300**, scanned count **> 5**; failure names file + count. RED: synthetic 301-line module → fails (W4, R7).
- [ ] 2.4 **RED** `test_isolation.py`: A's `ChartLayout(indicators=[{"token":"sma","style":{...}}])`; assert `for_user(B).count() == 0` and `for_user(B).get(...)` raises `DoesNotExist`. RED: drop owner scoping → sees A (W5).
- [ ] 2.5 **RED** `test_market_e2e.py`: wrap global `LightweightCharts.createChart` → `window.__builds`; open `_SETTINGS_GEAR`, change color/width, apply `#indicator-settings-dialog button[value="ok"]`; assert **`window.__builds === 1`**. RED: double-emit → `==2` (W2). Fallback: count one `/market/api/kline` GET via `page.on("request")`.
- [ ] 2.6 **GREEN** `pytest tests/web -q` + `pytest -m e2e -p no:randomly` green; ruff clean.
- [ ] 2.7 **Rollback**: delete `test_module_size_guard.py`; revert W2/W3/W5.

## S3 — #145 (F3 chart-shell) · ~120 · base S2

- [ ] 3.1 **RED** `test_market_e2e.py` (inline `_active_element(page)`): focus `.interval-chip[data-interval="1m"]`; `ArrowRight` → active **== 5m**; `Enter` → 5m `aria-pressed=="true"`, 1m `"false"`, `#interval` value **== "5m"**; `Space` on 15m → pressed. RED: drop keydown (W1).
- [ ] 3.2 **RED** same file: load 1280×900, read `#chart` height; `set_viewport_size(640,800)`; assert `.tv-lightweight-charts` height tracks `#chart` (**abs <= 2**) and `ready === true`. RED: remove `autoSize` → detach (W2).
- [ ] 3.3 **RED** same file `@>820px`: `.panel-toggle` **not visible**; `#panel` + `#chart` visible; chips group `role=="group"` + `aria-label=="Interval"`; toggle name `"Panel"` + `aria-expanded=="true"`; focused chip `outline-style != "none"`. RED: drop `:focus-visible`/names (W3).
- [ ] 3.4 **GREEN** `pytest -m e2e -p no:randomly` green; seam still 8 keys; 0 page errors.
- [ ] 3.5 **Rollback**: revert the 3 E2E. No production impact.

## Phase 4 — Verification (per slice at its merge)

- [ ] 4.1 `node --test "tests/js/**/*.test.js"` + `pytest tests/web -q` + `pytest -m e2e -p no:randomly` green; `ruff check . && ruff format --check .` clean.
- [ ] 4.2 `git diff --stat` touches no `web/`/`src/` production line; `requirements.txt` unchanged; `window.marketChart` 8 keys.

Meets 10/10 scenarios · ~395 lines · 3 slices × 400 budget.
