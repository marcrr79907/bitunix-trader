# Exploration: chart-shell (issue #116, Fase F3 — Ola 1)

## Executive Summary

F3 is the "chart shell" pass: make the chart fill the viewport height, convert
the interval `<select>` into TradingView-style horizontal chips (`aria-pressed`,
keyboard), collapse the sidebar on small screens, and persist the chosen
interval. **All three concerns are CSS + template + small JS on top of the MERGED
F0/F1 layered ESM architecture** — no new module, no migration, no dependency,
no `src/` change.

Three load-bearing findings, all verified against the current tree:

1. **The 480px fixed height lives in `chart-host.js:124`** (`createChart(el, {height: 480, ...})`),
   NOT only in CSS. CSS `#chart{min-height:460px}` is a second floor. The v5
   `autoSize:true` option (ResizeObserver-backed, confirmed via Context7 v5 docs)
   makes the chart fill its container automatically — the minimal change is
   `autoSize:true` + CSS height on `#chart`. The container must have a real,
   resolved height or the chart collapses.

2. **The interval `<select id="interval">` is a hard E2E dependency.** 15
   `page.select_option("#interval", "5m")` calls in `test_market_e2e.py` drive the
   interval switch. Converting to chips MUST keep a `#interval`-targetable
   control OR the E2E edits are unavoidable — and R18 says E2E assertions MUST
   stay green with NO edits. **Recommended: keep the `<select>` (visually hidden,
   `#interval` preserved for E2E + no-JS fallback) AND add chips that drive it.**
   The chips emit the same `config:changed` command; `toolbar.js` also syncs the
   select value on chip click so `select_option` still works. This is the only
   approach that satisfies R18 without breaking the frozen E2E.

3. **`ChartLayout` already carries `interval` as part of its unique key
   `(user, symbol, interval)`** and `saveLayout` already PUTs `{symbol, interval,
   indicators}`. The layout is *per-interval*, so "persist the chosen interval"
   is a different thing: a **user-level "last interval" preference**, not a
   per-layout field. `quotes.py`/`views.py` have no such preference today.
   Minimal extension options are in §3 — the recommended one adds NO migration
   (a `user`-keyed row reusing the existing JSONField shape, or a new tiny
   model). This is the single open decision that could require a migration.

`chart.html` already preloads `legend-core` + `legend` (F1 merged). Frozen seams
(`window.marketChart` 8 keys, `window.SmcOverlayCore`) are untouched by F3.

---

## 1. Current shell / layout

### Template — `web/market/templates/market/chart.html`

```
<div class="market-layout">
  <section id="chart" aria-label="Candlestick chart"></section>   <!-- line 9 -->
  <aside class="panel"> … pairs / interval / indicators / smc / drawings … </aside>
</div>
```

- `#chart` is an empty `<section>`; the chart is attached by `chart-host.js`.
- Interval control (lines 18-34): `<h2>Interval</h2>` + `<select id="interval" aria-label="Interval">` with 14 `<option>`s `1m,5m,15m,30m,1h,2h,4h,6h,8h,12h,1d,3d,1w,1M`.
- Pairs (lines 13-17): `<nav class="pairs">` of `<button class="pair" data-symbol>`. E2E clicks `.pair[data-symbol="ETHUSDT"]`.
- The `<dialog id="text-dialog">` sits outside `.market-layout`.

### CSS — `web/accounts/templates/registration/theme.css`

| Selector | Rule | Role |
|---|---|---|
| `main` (line 37) | `max-width:1200px; margin:0 auto; padding:var(--sp-4)` | **The real height constraint**: the shell caps width at 1200px and pads. No height rule → `main` is content-height, so a percentage/dvh height on `#chart` has no ancestor chain to resolve against beyond the viewport. |
| `.market-layout` (line 51) | `display:grid; grid-template-columns:1fr 300px; gap:var(--sp-4)` | 2-col grid: chart + 300px sidebar. |
| `#chart` (line 53) | `min-height:460px; position:relative` | **A second floor** (460px), independent of the 480 in JS. |
| `.panel` (line 52) | surface + border + radius + padding | Sidebar. |
| `@media (max-width:820px)` (line 99) | `.market-layout{grid-template-columns:1fr}` | Sidebar already **reflows below** the chart at ≤820px — it does NOT collapse, it stacks. |
| `.panel:has(table)` (line 146) | `overflow-x:auto` | Precedent: wide content scrolls inside its panel. |

### What makes the chart fixed vs responsive

- **Fixed by JS**: `chart-host.js:123-126` — `LightweightCharts.createChart(el, {height: 480, timeScale:{timeVisible:true}})`.
  This is the authoritative fixed height; the chart canvas is 480px tall
  regardless of CSS.
- **Fixed by CSS**: `#chart{min-height:460px}` floors the container, so even
  before JS runs the box reserves 460px.
- **Not responsive**: no `height:100%`/`dvh`, no `ResizeObserver`, no `autoSize`.
  Grep confirms zero `autoSize`/`resize` usage in `market/`.

**Conclusion:** height is fixed in TWO places (JS `480`, CSS `460`). Making it
fill the viewport requires touching both, and giving `#chart` a resolvable
height (either an explicit `calc(100dvh - topbar - padding)` or an ancestor
`height:100%` chain).

---

## 2. Interval chips

### How the select is wired today

- **DOM → command**: `controllers/toolbar.js:14-16`:
  ```js
  document.getElementById("interval").addEventListener("change", function (e) {
    bus.emit("config:changed", { symbol: state.symbol, interval: e.target.value });
  });
  ```
- **Command → orchestration**: `main.js:129` — `bus.on("config:changed", p => switchTo(p.symbol, p.interval))`.
- **`switchTo`** bumps `gen`, sets `state.interval`, clears drawings/SMC, re-subscribes the stream, loads that key's layout → build → drawings → SMC → history. **The store `interval` + `switchTo` contract + the `config:changed` bus event are the frozen contract chips must preserve.**
- The `<select>` is a **leaf DOM element** owned by `toolbar.js`. No other module reads `#interval`.

### Converting to chips while preserving the contract

The cleanest conversion that **does not break the 15 E2E `select_option` calls**:

- **Add** a chip group (`<div class="interval-chips" role="group" aria-label="Interval">` of `<button type="button" class="interval-chip" data-interval="5m" aria-pressed="false">5m</button>`) in `chart.html`, rendered from the same 14-interval source.
- **Keep** the `<select id="interval">` in the DOM, visually hidden (`.visually-hidden` utility or `hidden` attribute won't work for `select_option` — Playwright needs it actionable; use a visually-hidden CSS class that keeps it in the accessibility/action tree). **This is a decision to lock in design** — see §5 Q2.
- `toolbar.js` gains a chip listener that: emits the SAME `config:changed` command, sets `aria-pressed` on the clicked chip / clears siblings, and **syncs `select.value`** so a later `select_option` stays coherent.
- `toolbar.js` (or a tiny sync) also reflects a select-driven change onto the chips (`aria-pressed`) — bidirectional, both paths emit one command.
- Keyboard: chips are `<button>` → natively focusable/activatable. `:focus-visible` already themed globally (theme.css:20-22). Optional roving tabindex/arrow keys is enhancement, not required for a11y baseline.

### Where the chip set should live

The 14 intervals exist in **three** places already:
- `chart.html` `<option>`s (template),
- `quotes.INTERVALS` (Python tuple — server validation source of truth),
- `chart.js CONFIG.channels` keys (JS, WS channel map).

**Recommendation:** the interval set stays **template-driven** (mirrors the
existing `<option>` list; no new config plumbing, no `CONFIG.intervals` export).
The server already rejects unknown intervals (`api_kline`/`api_layout`/`api_drawings`
all check `interval in INTERVALS`). Adding `CONFIG.intervals` would be a 4th copy
for no gain. *(Ponytail rung 2: reuse the existing template list.)*

---

## 3. Persist the chosen interval

### The existing layout-persistence pattern

- **`ChartLayout`** (`trading/models.py:210-230`): `UserOwnedModel`, unique
  `(user, symbol, interval)`, `indicators` JSONField, `updated_at`. One layout
  **per chart** — it does **not** store a "last interval"; `interval` is the
  key, not a value.
- **API** (`views.py:207-281`): `GET ?symbol=&interval=` returns that key's
  layout (default on miss, `exists:false`); `PUT {symbol,interval,indicators}`
  upserts via `for_user`. **No field for a user-level preference.**
- **JS** (`controllers/indicators.js:102-119`): `saveLayout` debounce-PUTs
  `{symbol, interval, indicators}`. It is called from `main.rebuild()`
  (indicator toggle path) — **NOT** from `switchTo`. So an interval change today
  does **not** trigger a save by itself.
- **`quotes.py`**: `INTERVALS`, `DEFAULT_LAYOUT` — the payload/layout shapes.
  **No interval-preference shape exists.**

### Does layout already carry `interval`?

Yes, but only as the **unique-key column** (which chart the layout belongs to),
not as "the interval the user last had selected". Restoring a user's **last
chosen interval** is a distinct, user-global preference (independent of symbol).

### Minimal extension options

| Option | Shape | Migration? | Notes |
|---|---|---|---|
| **A. New tiny model** `ChartPreference(user OneToOne, last_interval CharField(8))` + `GET/PUT /market/api/preference` | New table, `for_user` scope | **YES** (additive migration `0009_…`) | Cleanest intent; mirrors `ChartLayout` ownership. Costs one migration + endpoint + isolation test. |
| **B. Reuse `ChartLayout` with a sentinel symbol** (e.g. `symbol=""` or `"*"` meaning "global default") holding `interval=last` | No schema change | **NO** | Hacky: overloads a per-chart table; `symbol` is non-empty-validated in the API, so `symbol=""` currently 400s. Would need a carve-out → smells. |
| **C. Store the preference in the layout row for the *boot* key only** | No schema change | **NO** but conceptually wrong | The boot key is `(symbols[0], "1m")`; saving "last interval" there conflates two meanings. Reject. |
| **D. Reuse the layout endpoint with a new `defaults` field** on the `(user,symbol,interval)` row | Additive JSONField or reuse `indicators` sibling | Needs a model change → migration | Cross-cutting; per-key not per-user. Reject for a user-global pref. |

**Recommendation: Option A** — a small `ChartPreference` model (per-user,
OneToOne) + a `GET/PUT /market/api/preference` endpoint, mirroring the
`ChartLayout` ownership/validation idiom. It is the honest model for "user-global
last interval"; it is one additive migration (the ONLY migration F3 would add)
and one small endpoint. **Boot reads it and sets the initial interval before the
first `switchTo`.** The issue explicitly says "reusa el patrón de layout" — A
reuses the *pattern* (UserOwnedModel + GET/PUT + for_user) without overloading
the layout table.

*(If the team insists on zero migrations, Option B is the only no-migration
path, but it is a design smell and should be an explicit, documented exception —
flag it in design, do not default to it.)*

### Where the initial interval is decided

`main.js:33-34` hardcodes `interval: "1m"` in the boot store. F3 must replace
this with the persisted preference (fetched before `start()`), defaulting to
`"1m"` on any failure (never blank) — same resilience stance as `loadLayout`.

---

## 4. Full-height + responsive

### Chart fills the viewport height (v5-correct)

- **v5 option: `autoSize: true`** (confirmed, Context7 `/tradingview/lightweight-charts`
  v5.2.0). It installs a `ResizeObserver` on the container and calls `resize()`
  with the container's `contentRect` on every resize. With `autoSize` enabled,
  `chart.resize(w,h)` is ignored (a warning is logged) — so `height:480` in the
  create options becomes dead weight and should be removed.
- **Requirement:** the container must have a **resolved height**; v5's fallback
  uses `getBoundingClientRect()` when `height===0`, but a zero-height flex/grid
  child still yields 0 → collapsed chart. So `#chart` needs an explicit height.
- **Recommended CSS:** give `main` the viewport-height context and size `#chart`:
  ```css
  main{ min-height: calc(100dvh - var(--topbar-h)); }        /* topbar is content-height today */
  .market-layout{ height: 100%; }                              /* grid stretches */
  #chart{ height: calc(100dvh - 140px); min-height: 460px; }  /* 140 ≈ topbar+padding; tune */
  ```
  `dvh` (not `vh`) avoids mobile browser-chrome jump. The exact offset must be
  verified in the browser (topbar height is not tokenised today) — a
  `--topbar-h` token or a flex column on `body` are the two clean options.
- **JS change:** `chart-host.js:123-126` → drop `height:480`, add `autoSize:true`
  (keep `timeScale:{timeVisible:true}`). This is the "one host method/option"
  surface, consistent with R14 (host owns the chart construction).

### Sidebar collapse (≤820px)

- Today the sidebar **reflows below** the chart (`grid-template-columns:1fr`),
  not collapses. The issue asks for a **collapsible sidebar on small screens**
  (accessible toggle).
- Minimal, no-deps, CSP-safe mechanism: a **`<button type="button" class="panel-toggle" aria-expanded aria-controls="panel">`**
  in the template + a CSS class on `.market-layout` (e.g. `.panel-collapsed`)
  driving `display`/`grid-template-columns`. Toggle logic is 3 lines in
  `toolbar.js` (or a tiny dedicated handler). No checkbox-hack (less accessible),
  no JS framework.
- **Desktop behaviour:** either always show the panel (toggle hidden ≥821px via
  media query) or allow collapse at all widths. Recommended: toggle visible only
  ≤820px; desktop unchanged (least regression surface). Design to lock this.

---

## 5. Open questions / decisions (lock in design)

| # | Question | Recommendation |
|---|---|---|
| Q1 | Chip set source: template vs `CONFIG.intervals`. | **Template** (same 14 `<option>`s). Server already validates via `quotes.INTERVALS`. Avoid a 4th copy. |
| Q2 | How to keep the E2E `select_option("#interval", …)` green. | Keep `<select id="interval">` in the DOM (visually hidden but action-able) + chips drive it and it drives chips. **Only path satisfying R18 with zero E2E edits.** Verify `select_option` works on a visually-hidden (`clip`/`position:absolute`) select — if not, keep it 1px/near-invisible rather than `display:none`. |
| Q3 | Interval persistence location. | **New `ChartPreference` (UserOwned, OneToOne) + GET/PUT /market/api/preference**, one additive migration. Reuses the layout pattern, honest model. Option B (no migration) only if explicitly accepted as an exception. |
| Q4 | Sidebar collapse mechanism. | `<button aria-expanded aria-controls>` + a CSS class; 3-line JS in `toolbar.js`. Visible only ≤820px. No checkbox hack. |
| Q5 | `#chart` height vs v5 `height`/`autoSize`. | `autoSize:true` + REMOVE `height:480`; `#chart` gets an explicit `dvh`-based height. Do NOT leave both a fixed option and `autoSize`. |
| Q6 | 375px behaviour. | No `overflow-x`: verify via Playwright at 375px (`/impeccable` + DOM/computed-style, model cannot read images). Chips must wrap (`flex-wrap`) not overflow. `main{padding}` + 300px sidebar already collapse at 820 → at 375 the grid is 1-col; the chips row is the overflow risk. |
| Q7 | Does an interval change need a save? | Yes for persistence: a chip/select change must PUT the preference (debounced, like `saveLayout`). `switchTo` today does NOT save — F3 adds a preference save on interval change. |
| Q8 | `main{max-width:1200px}` interaction. | The chart fills width up to 1200px; full-*viewport*-width is out of scope (the issue says fill the viewport *height*). Keep `max-width`. |

---

## 6. Risks

1. **E2E breakage (HIGH).** 15 `select_option("#interval", …)` calls are the
   contract. Removing the `<select>` fails all of them. *Mitigation:* keep the
   select in the DOM (Q2), chips drive it. Any other approach = E2E edits =
   R18 violation.
2. **v5 height/autoSize (MED-HIGH).** Setting both `height:480` and `autoSize`
   or a zero-height container → collapsed/half chart. *Mitigation:* remove the
   option, give `#chart` a resolved height, verify canvas bounding box in
   Playwright.
3. **Frozen seams (MED).** Do NOT add a 9th `window.marketChart` key or touch
   `window.SmcOverlayCore`. Interval state already lives in the store; chips
   write nothing new to the seam. *Mitigation:* assert `Object.keys(...).length === 8`
   in the new E2E (the legend E2E already does this).
4. **No-deps / CSP (LOW).** Chips are template buttons + theme.css + existing
   ESM. No inline handler, no new script. *Mitigation:* existing
   `test_market_page_has_no_inline_script_or_handler` + CSP tests stay green.
5. **Migration (MED — only if Option A).** Additive `ChartPreference` migration
   must be additive; `makemigrations --check` must pass; the owned-model guard
   (`OWNED_MODELS`) must include it. If zero-migration is mandatory, escalate
   Option B in design.
6. **Patch coverage (MED).** `diff-cover --fail-under=100` is Python-only; JS is
   invisible. New Python (preference endpoint/model) needs 100% patch coverage;
   JS safety net is `node --test` + E2E. *Mitigation:* add endpoint tests to
   `test_market_api.py` and one E2E for chips/height/collapse.
7. **`main.js` boot ordering (MED).** Reading the preference before `start()`
   adds an async step ahead of the layout fetch; a slow/failed preference fetch
   must default to `"1m"` and never block boot. Keep the `gen` guard intact.
8. **Topbar offset drift (LOW).** `calc(100dvh - 140px)` is a magic number; if
   the topbar wraps (mobile nav), the offset is wrong. *Mitigation:* prefer a
   flex-column `body` or a `--topbar-h` measured value over a hardcoded px.

---

## 7. Proposed PR shape + size

F3 touches: `chart.html` (chips + toggle button + keep select), `theme.css`
(height/`dvh`, chip styles, collapse, 375px), `chart-host.js` (autoSize),
`toolbar.js` (chip listeners + collapse toggle), possibly `main.js` (boot pref +
save), and — if Option A — `models.py` + migration + `views.py`/`urls.py`
(preference endpoint) + `test_market_api.py` + `test_market_e2e.py`.

Rough diff estimate:

| Area | Lines |
|---|---|
| `chart.html` (chips, toggle, hidden select) | ~30 |
| `theme.css` (height/dvh, chips, collapse, 375px) | ~40 |
| `chart-host.js` (autoSize) | ~2 |
| `toolbar.js` (chips + collapse) | ~35 |
| `main.js` (boot pref + interval save) | ~15 |
| `models.py` + migration (Option A) | ~25 |
| `views.py`/`urls.py` (preference endpoint) | ~40 |
| `tests/web/test_market_api.py` (endpoint) | ~60 |
| `tests/web/test_market_e2e.py` (chips/height/collapse, add-only) | ~60 |
| `tests/js` (if a pure helper emerges) | ~0-30 |
| **Total** | **~310-370** |

**400-line budget risk: Medium.** Honest split:

- **Single PR is plausible (~310-370)** if Option A's endpoint is kept tight and
  no new JS pure-core is introduced. The CSS+template+chips part alone is ~120
  lines — small and cohesive.
- **Chained 2 slices (recommended when the preference endpoint is included):**
  1. **Slice 1 — shell (CSS + template + chips + collapse + autoSize).** No
     migration. Chips drive the existing select/`config:changed`; height +
     responsive + a11y. ~150 lines, autonomous, E2E for chips/height/collapse.
  2. **Slice 2 — interval persistence.** `ChartPreference` + migration +
     `/market/api/preference` + `main.js` boot read/save + API tests. ~160 lines,
     independently reversible.

Recommendation to the orchestrator: **chained 2-slice** unless the delivery
strategy resolves to `single-pr`. Slice 1 delivers the user-visible shell
(issue title) with zero migration; Slice 2 adds persistence as a clean,
reversible increment. This also isolates the one risky artifact (the migration)
into its own reviewable PR.

---

## Affected Areas

- `web/market/templates/market/chart.html` — chips group + hidden `<select>` retained + panel toggle button.
- `web/accounts/templates/registration/theme.css` — `#chart` `dvh` height, `.interval-chips`/`.interval-chip[aria-pressed]`, `.panel-collapsed`, 375px/`flex-wrap`, focus/aria states.
- `web/market/templates/market/chart-host.js` — `height:480` → `autoSize:true` (remove fixed height).
- `web/market/templates/market/controllers/toolbar.js` — chip click → `config:changed` + `aria-pressed` + select sync; panel-toggle handler.
- `web/market/templates/market/main.js` — boot reads persisted interval (default `"1m"`); interval-change save path (Slice 2).
- `web/trading/models.py` + `web/trading/migrations/0009_*` — `ChartPreference` (Slice 2, additive).
- `web/market/views.py` + `web/market/urls.py` — `/market/api/preference` GET/PUT (Slice 2), mirroring `api_layout`.
- `tests/web/test_market_api.py` — preference endpoint contract (Slice 2).
- `tests/web/test_market_e2e.py` — ADD-ONLY: chips aria-pressed + click switches interval; `#chart` fills height; 375px no overflow; panel toggle; seam stays 8 keys.

No `src/` change. No order surface. No new runtime dependency. CSP unchanged.
`window.marketChart` stays 8 keys; `window.SmcOverlayCore` untouched. The only
migration is the additive `ChartPreference` (Slice 2, Option A).

---

## Ready for Proposal

**YES.** The fixed-height sites (JS `480` + CSS `460`) are confirmed; the v5
`autoSize` option is verified against v5.2.0 docs; the interval-select wiring and
its 15 E2E dependencies are mapped; the layout persistence pattern
(`ChartLayout` + `api_layout` + `saveLayout`) is understood and the gap
("user-global last interval" ≠ per-chart layout) is named with a concrete
recommendation. The design phase MUST lock: **Q2** (keep `<select>` for R18 — the
critical path), **Q3** (preference location + whether the migration is
acceptable), **Q4** (collapse mechanism scope), and **Q1/Q5** (chip source,
autoSize). The one true fork is Q3 (new model + migration vs a no-migration
exception); everything else is CSS/template/small JS.
