# Design: frontend-regression-tests

## Technical Approach

Test-only. Commit the 10 session probes flagged `PARTIAL` in the F1/F2/F3 verify
reports into the existing suites. No production file, no new dependency, CSP/seam
unchanged (`window.marketChart` stays **8 keys**; the `LightweightCharts.createChart`
CDN global is wrapped in-page, not the seam). Every scenario gets an **exact**
assertion (`==`, never `>=1`) plus a RED-check. 3 slices, one per issue, chained.

## Scenario → Test Map

### S1 — #143 (F1 chart-legend)

| # | File · selector/API | Assertion | RED-check |
|---|---|---|---|
| a LC2 | `tests/js/legend-core.test.js`; `readFileSync(CORE_PATH)`, strip `//`+`/* */`, `/^\s*(import\|export\s+[^;]*\bfrom)\b/m` + `/require\(/` | `=== false` | add an `import` → RED |
| b LC4 | `test_market_e2e.py`; toggle `.indicator-toggle[value="bollinger"]`, then `#chart .chart-legend`, `.lg-ohlc`, `mouse.move` over `#chart canvas` | after 2nd `chart:built`: `.chart-legend` count `== 1`; `.lg-ohlc` contains `"H "` | unwire re-subscribe → no update → RED |
| c LC5 | `test_market_e2e.py`; `MutationObserver(attributeFilter:["aria-live"])`, 20× `mouse.move`, leave `(0,0)`, wait 400ms | transitions `<= 2`; final `== "polite"`; hover `== "off"` | remove debounce/off → spike → RED |
| d LC6 | `test_market_e2e.py`; `.chart-legend .lg-row`, `.lg-token` | rows `== 3`; `all_inner_texts() == ["SMA 20","EMA 20","RSI"]` | drop `rsi` default → `!=3` → RED |

LC2 strips comments because the header prose literally names EMA/RSI/ATR (R2).
LC6 closes the vacuous `>=1` at `test_legend_overlay...:1102`.

### S2 — #144 (F2 chart-indicator-settings)

| # | File · selector/API | Assertion | RED-check |
|---|---|---|---|
| W2 | `test_market_e2e.py`; wrap `LightweightCharts.createChart`→`window.__builds`; `_SETTINGS_GEAR`, `#is-color`, `#indicator-settings-dialog button[value="ok"]` | one Apply → `__builds === 1` | double-emit → `==2` → RED |
| W3 | `tests/js/legend-core.test.js`; comment-stripped `legend-core.js` **and** `controllers/legend.js` | no `styles`/`priceFormat` token | add a `styles` read → RED |
| W4 | `tests/web/test_module_size_guard.py` (NEW); `rglob("*.js")`, `splitlines()` | non-allowlisted `<= 300`; scanned `> 5` | 301-line module → RED |
| W5 | `tests/web/test_isolation.py`; `ChartLayout.objects.create(user_a, indicators=[{token:"sma",style:{...}}])`; `for_user(user_b)` | `count() == 0`; `.get(...)` raises `DoesNotExist` | drop scoping → RED |

W2 fallback (documented): count `/market/api/kline` GETs via `page.on("request")`.
W4: `CEILING=300`, `ALLOWLIST={"chart-host.js"}` with a comment naming DEBT-5/#146
and the 326-line high-water mark; every other module incl. `controllers/` must
comply; failure names file + line count (R7).

### S3 — #145 (F3 chart-shell)

| # | File · selector/API | Assertion | RED-check |
|---|---|---|---|
| W1 | `test_market_e2e.py`; `.interval-chip[data-interval="1m"]`, `keyboard.press`, `document.activeElement`, `#interval` | `ArrowRight`→active `==5m`; `Enter`→5m `aria-pressed=="true"`, 1m `"false"`, `#interval=="5m"`; `Space` on 15m→pressed | drop keydown → RED |
| W2 | `test_market_e2e.py`; `set_viewport_size`, `#chart .tv-lightweight-charts` vs `#chart` | `abs(rootH-chartH) <= 2`; `ready===true` | remove `autoSize` → detach → RED |
| W3 | `test_market_e2e.py` `@1280px`; `.panel-toggle`, `#panel`, `aria-label`, `getComputedStyle` | toggle not visible; `#panel` visible; chips group `role=="group"`+`aria-label=="Interval"`; toggle name `"Panel"`, `aria-expanded=="true"`; focused chip `outline-style != "none"` | drop `:focus-visible`/names → RED |

## Architecture Decisions

| Decision | Option A | Option B | Choice + rationale |
|---|---|---|---|
| Rebuild count (W2) | wrap CDN global | 9th seam key | **A** — no prod edit; seam frozen |
| Legend purity (W3) | comment-aware grep | E2E behavioural | **A** — cheap, matches core precedent |
| 2nd `chart:built` (#143b) | indicator toggle | interval switch | **toggle** — same lifecycle, keeps seeded data |
| Size ceiling (W4) | `300`+allowlist | `350` drift | **300+allowlist** — blocks other growth, exempts #146 |
| W5 locus | `test_isolation.py` | `test_market_api.py` | **model** — matches issue; API form covered |

## Harness Reuse

`browser_page` → all 7 E2E. `seeded_5m_candles` → S1b–d, S2W2, S3W1–3.
`_wait_ready`/`_poll` → S2W2, S3W1. `_SETTINGS_GEAR`/`_dialog_open`/`_pane0_series`
→ S2W2. `user_a`/`user_b` → S2W5. `readFileSync`+`fileURLToPath(import.meta.url)`
→ S1a, S2W3. NEW inline `_active_element(page)` → S3W1. `route_web_socket`
available, unused (no live push needed).

## File Changes

| File | Action | Slice | Description |
|---|---|---|---|
| `tests/js/legend-core.test.js` | Modify | S1,S2 | LC2 purity (S1); W3 grep (S2) |
| `tests/web/test_market_e2e.py` | Modify | S1,S2,S3 | 7 E2E appended; no existing assertion edited |
| `tests/web/test_module_size_guard.py` | Create | S2 | R14 ceiling guard (W4) |
| `tests/web/test_isolation.py` | Modify | S2 | style A≠B (W5) |
| `openspec/specs/{...}/spec.md` | Delta at archive | — | verification-method wording only |

No production file touched.

## Delivery — 3 Slices (tracker `feat/frontend-regression-tests`)

| Slice | Issue | Files | ~Lines | Rollback |
|---|---|---|---|---|
| S1 | #143 | `legend-core.test.js`+LC2, `test_market_e2e.py` (3 E2E) | ~125 | revert the 3 E2E + LC2 block |
| S2 | #144 | `legend-core.test.js`+W3, `test_module_size_guard.py` (new), `test_isolation.py` W5, `test_market_e2e.py` W2 | ~150 | delete new guard; revert W2/W3/W5 |
| S3 | #145 | `test_market_e2e.py` (3 E2E) | ~120 | revert the 3 E2E |

**Guard/Edge Matrix**: vacuous `>=1` → exact `==`; comment false-positive (R2) →
strip comments; flake/debounce (R3) → bounded `wait_for_function` + one 400ms
settle; seam growth (R5) → wrap CDN global; size false-negative (R7) → `rglob`
incl. `controllers/`, `splitlines()`, scanned-file count `> 5`; new dep/CSP (R6)
→ stdlib only. Child PRs base on the previous slice (Feature Branch Chain).

`Decision needed before apply: No` · `Chained PRs: Yes` · `400-line budget risk: Low`.

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit (JS) | LC2, W3 | `node --test "tests/js/**/*.test.js"` |
| Unit (py, fs) | W4, W5 | `pytest tests/web -q` |
| E2E (dev-only) | LC4/LC5/LC6, W2, shell W1/W2/W3 | `pytest -m e2e -p no:randomly` |

## Migration / Rollout

No migration. E2E deselected by default (`addopts = "-m 'not e2e'"`); CI runs
node + py unit. Rollback = revert the slice; zero production impact.
