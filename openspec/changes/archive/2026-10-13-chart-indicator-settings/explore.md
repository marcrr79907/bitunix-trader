# Exploration: chart-indicator-settings (issue #115, Fase F2 — Ola 2)

## Executive Summary

F2 adds a per-indicator settings panel (TradingView-style): a gear button next to
each active indicator opens an accessible dialog to edit **color, line width,
period and precision**, persisted additively in `ChartLayout.indicators[].style`
(JSONField, no migration), and re-rendered through the existing config-change →
`rebuild()` path (#68 preserved).

The two load-bearing findings:

1. **The server WILL silently drop `style` today (HIGH).**
   `quotes.parse_layout_indicators` (quotes.py:281) rebuilds each entry as
   `entry = {"token": token}` and only copies `params`. Any `style` key the client
   PUTs is **discarded before the row is written**. Persistence therefore requires
   a Python change — the ONLY Python change in F2, and the only reason the
   diff-cover 100% gate applies. The `ChartLayout.indicators` JSONField itself is
   additive and needs **no migration**; the blocker is the validator, not the model.

2. **Style must be a new store slot, NOT folded into `params`.**
   `history.klineUrlFrom` (history.js:15-21) iterates `state.params[token]` and
   appends **every key** as a flat kline query param. Putting `color`/`lineWidth`
   under `params` would leak them into `/market/api/kline?...&color=%23f00`, which
   the server's `_parse_params` rejects (`ValueError` → 400). Style needs its own
   channel from store → host build.

There is **no existing gear, no indicator-settings core, and no style UI** — the
panel today is a `<fieldset class="indicators">` of checkboxes + two number inputs.
The `<dialog id="text-dialog">` used by drawings is the CSP-safe modal precedent to
reuse.

---

## 1. Registry + params today (verified against merged code)

### The render registry — `chart-host.js` (REGISTRY, lines 12-52)

| token | place | pane | series (key/type/color) |
|---|---|---|---|
| sma | overlay | — | sma/line/`#2962ff` |
| ema | overlay | — | ema/line/`#ff6d00` |
| bollinger | overlay | — | bollinger_upper/middle/lower — line/`#7e57c2` (×3) |
| vwap | overlay | — | vwap/line/`#26a69a` |
| rsi | pane | rsi | rsi/line/`#ab47bc` |
| macd | pane | macd | macd/line/`#2962ff`, signal/line/`#ff6d00`, histogram/histogram/`#26a69a` |
| stochastic | pane | stochastic | k/line/`#2962ff`, d/line/`#ff6d00` |
| atr | pane | atr | atr/line/`#ff6d00` |
| volume | pane | volume | volume/histogram/`#26a69a` |

Colors are **hardcoded literals** in the registry. `addSeries(token, paneIndex)`
(line 101) passes ONLY `{ color: s.color }` to `chart.addSeries(Ctor, {…}, idx)` —
no `lineWidth`, no `priceFormat`. `PANE_ORDER` (line 55) fixes pane indices.

`build(state)` (line 120) reads **only `state.indicators`** (array of tokens) to
decide which series exist. It never reads `params` or any style — so a user style
has nowhere to enter the host today; `build` must be given the style map (see §3).

### How `params` flow (params, not style)

```
chart.html .indicator-param inputs (sma_len, ema_len)   ← only these two exist
   → readParams()            controllers/indicators.js:11   → {sma:{sma_len:20}}
   → store.params            seeded in main.boot
   → readState()             (rebuild)                      → {indicators, params}
   → state.params            main.rebuild:94
   → klineUrlFrom()          history.js:15                  → ?sma_len=20&ema_len=20
   → quotes._parse_params/_validate_layout_params           server validation
```

- **Editable params today: only `sma_len` and `ema_len`.** These are the only
  `.indicator-param` inputs in `chart.html` (lines 39, 41). Every other indicator's
  period (`rsi_len`, `bb_len`, `macd_fast/slow/signal`, `stoch_k/d`, `atr_len`) is
  **fixed at the server default** — it exists in `_INT_PARAMS`/`_FLOAT_PARAMS`
  (quotes.py:79-91) and in the builder, but has **no DOM control**.
- The server vocabulary has 10 int params + `bb_std`; the client only surfaces 2.
  So "período editable" for rsi/macd/stochastic/atr/bollinger is **new UI surface**,
  not just a new persistence key.

### `ChartLayout.indicators` JSON today

```json
[{"token": "sma", "params": {"sma_len": 50}}, {"token": "macd"}]
```

- `ChartLayout` (models.py:210): `user`, `symbol`, `interval`, `indicators`
  (JSONField, default `list`), `updated_at`; unique `(user,symbol,interval)`.
- `buildIndicators(indicators, params)` (indicators.js:34) emits `{token}` plus
  `params` when present — no `style`.
- GET miss returns `DEFAULT_LAYOUT = [{"token":"sma"},{"token":"ema"},{"token":"rsi"}]`.

---

## 2. Style schema design (propose — `indicator-settings-core.js`)

Pure, framework-free ESM core (mirrors `legend-core.js`: no DOM, no chart lib, no
network, imports nothing). Unit-tested in Node with zero mocks.

**Layering note:** pure cores "may import nothing" (ADR). `chart-host.js` is a host
layer, so `indicator-settings-core.js` MUST NOT import `REGISTRY`. Defaults are
passed IN (from the host registry) to keep the core dependency-free.

### Proposed surface (freeze at design)

```js
// Per-token option schema. Fields describe type + clamp range; the token list is
// the render vocabulary. `lineWidth` is an integer 1..4 (LightweightCharts range);
// `color` is a #rrggbb string; `precision` is integer 0..8.
export const FIELDS = Object.freeze({
  color:     { type: "color" },
  lineWidth: { type: "int", min: 1, max: 4 },
  precision: { type: "int", min: 0, max: 8 },
});

// Which tokens accept which fields. Period (the existing params like sma_len) is
// carried in `params`, NOT in `style` (keeps the kline query clean, §1).
export const TOKENS = Object.freeze([...]);            // = REGISTRY keys

// raw (possibly hostile/partial) style + injected defaults -> normalized style.
// Unknown keys dropped; out-of-range clamped; missing -> default. Never throws.
export function normalize(token, raw, defaults) -> {color, lineWidth, precision}

// Validate only (no clamping) -> {ok: bool, errors:[...]}; used by tests/UI hints.
export function validate(token, raw) -> {ok, errors}

// Default style for a token from the host REGISTRY (color) + fixed width/precision.
export function defaultsFor(registry, token) -> {color, lineWidth, precision}
```

### Frozen `style` JSON shape (goes into `indicators[].style`)

```json
{ "color": "#2962ff", "lineWidth": 1, "precision": 2 }
```

- All three keys optional; omitted keys fall back to the registry default.
- `style` is **per-token per-chart** (lives on the layout entry) — see Q1.
- Period (`sma_len`, …) stays in `params`; the dialog may edit it, but it persists
  in `params`, not `style`.

### Precision semantics (propose)

`precision` sets the LightweightCharts series `priceFormat`
(`{ precision, minMove: 10^-precision }`) → controls axis + crosshair labels for
that series. It deliberately does NOT touch `legend-core.DECIMALS` (LC1 freezes
that static map); the legend can optionally prefer `store.styles[token].precision`
when present — a design decision (Q3).

---

## 3. Apply-style to the chart

**Where the style must thread:** `build(state)` is the only series-construction
site (`chart-host.js:120`). It must receive a **style map** keyed by token. Cheapest
options:

- **A (recommended): add a `styles` slot to the store.** `build` reads
  `state.styles[token]` with a REGISTRY fallback; `addSeries` uses
  `{color, lineWidth}` and `series.applyOptions({priceFormat})` for precision.
  `main.rebuild()` already spreads `readState()` into `state`, so the flow is the
  existing one. Cost: `STORE_KEYS` grows to 7 and `tests/js/chart-store.test.js`
  (asserts exactly 6 keys) must be updated — a 1-line test edit.
- **B: keep styles inside `params[token].style`.** Rejected — `klineUrlFrom` would
  serialize it into the kline query (§1), and `_validate_layout_params` rejects
  unknown keys → 400.

**`rebuild()` re-reads the style?** Yes, once the style map is in `state`:
`main.rebuild()` (main.js:91) calls `indicators.readState()` → `buildChart()` →
`host.build(state)`. A style edit therefore travels the same
`indicator:changed` → `rebuild()` path as a toggle/param change.

**#68 preserved:** style changes are config changes → `rebuild()` → full
`host.build()` + `history.fetchHistory()` (`setData` path). The live WS stream still
uses `update()` only; the E2E `setData` spy stays green. No live `applyOptions`
shortcut is needed (rebuild is the sanctioned path; see Q/precision-cost below).

**Cost note:** `build()` does `chart.remove()` + recreate; drawings/SMC re-attach
is already handled by `main.buildChart`. A style edit pays a full rebuild. That is
acceptable (same as today's toggle) but is the main perf concern if the dialog were
made live-preview — recommend apply-on-confirm (single rebuild per dialog submit).

---

## 4. UI

- **Gear attach point:** the panel `<fieldset class="indicators">` (`chart.html:37`)
  holds one `<label>` per indicator. Add a `<button type="button" class="indicator-settings"
  data-token="sma" aria-haspopup="dialog">` gear next to each toggle. It must be
  shown for active indicators (or always, disabled/greyed when off) — design choice.
- **Accessible dialog:** reuse the drawings `<dialog>` pattern
  (`chart.html:74-81` + `drawings.js:241` `showModal()`, close handling at 273). A
  single shared `<dialog id="indicator-settings-dialog">` with labelled inputs
  (`<input type="color">`, `<input type="number" min=1 max=4>` lineWidth,
  `<input type="number">` period, `<input type="number" min=0 max=8>` precision),
  populated per token on open. Close/cancel via `method="dialog"` buttons (the
  drawings precedent). Native `<input type=color>` satisfies the color picker with
  zero deps.
- **Wiring:** the settings controller (new leaf `controllers/indicator-settings.js`,
  `create({store, bus, config})`, never imports main) listens for gear clicks, writes
  the edited style into `store.styles[token]`, emits `indicator:changed` (→ rebuild)
  and calls the indicators controller's `saveLayout()` (or emits a save command) so
  the PUT carries the new style. Alternatively fold the gear + dialog into the
  existing `controllers/indicators.js` (already owns the panel DOM + saveLayout) to
  avoid a second controller and a second `readState` — see Q5/slice shape.
- **CSP/a11y:** no inline script/handler; dialog markup in `chart.html`, behaviour
  in JS. `aria-haspopup="dialog"`, labelled inputs, focus trapped by native
  `<dialog>`. Audit with `/impeccable` (DOM/computed-style via Playwright — the
  model cannot read images).

---

## 5. Persistence

- **Model: no migration needed.** `ChartLayout.indicators` is `models.JSONField`;
  `style` is just another key inside each list entry. `makemigrations --check` stays
  green. (Confirmed models.py:210-222, migration `0005_chartlayout.py`.)
- **CRITICAL server blocker:** `quotes.parse_layout_indicators` **drops `style`**
  (quotes.py:303 builds `entry = {"token": token}`; only `params` is conditionally
  copied). So the PUT returns/​persists a row WITHOUT the style. F2 MUST extend
  `parse_layout_indicators` to preserve+validate `style`, and add a
  `_validate_layout_style(token, style)` (whitelist keys `color`/`lineWidth`/
  `precision`; `color` a `#rrggbb` str; ints in range; unknown key → `ValueError`
  → 400). This mirrors `_validate_layout_params` and preserves the user shape
  verbatim (no defaults injected), keeping the existing "round-trips verbatim"
  contract.
- **Client path:** `saveLayout()` (indicators.js:102) PUTs
  `buildIndicators(state.indicators, state.params)` — must also carry
  `state.styles` (extend `buildIndicators` to emit `style` when present, or pass a
  3rd arg). `loadLayout()`/`applyLayout()` (indicators.js:57-97) must read
  `body.indicators[].style` into `state.styles` and into the dialog defaults.
- **Round-trip test precedent:** `test_isolation.py:161` proves the JSONField
  round-trips nested objects; `test_market_api.py:887-900` proves PUT→GET verbatim.
  A new test for `{token, params, style}` round-trip + a 400 on bad style is
  required (covers the new Python lines → 100% patch gate).

---

## 6. Open questions / decisions

| # | Question | Recommendation |
|---|---|---|
| Q1 | Style scope: per-token per-chart vs global per-token? | **Per-token per-chart** (lives on the layout entry, matches the issue's `indicators[].style` and the existing per-`(symbol,interval)` model). No new model/global. |
| Q2 | Precision meaning: legend decimals vs series axis/priceFormat? | Series `priceFormat` (axis+crosshair). Do NOT mutate `legend-core.DECIMALS` (LC1 frozen). Optionally let legend read `styles[token].precision` if present (design lock). |
| Q3 | Where do defaults live: REGISTRY vs settings-core? | Registry stays the color source (host layer); settings-core receives defaults via `defaultsFor(registry, token)` and stays dependency-free. ONE source of color (REGISTRY). |
| Q4 | Do periods (sma_len, rsi_len, …) move into the same dialog? | **Yes** — the issue lists "período". Persist periods in `params` (unchanged channel), style in `style`. This also surfaces rsi/macd/etc. periods for the first time. |
| Q5 | New `controllers/indicator-settings.js` vs extend `controllers/indicators.js`? | Extending `indicators.js` (already owns the panel DOM + `saveLayout` + `readState`) is lazier: no new allowlist entry, no second controller, no duplicated save path. Add the gear/dialog there unless size ceiling (~300 lines) is hit — it is currently 135 lines, so extension is safe. |
| Q6 | New store key `styles` vs a controller-local map? | New `styles` key (flows through `readState()`/`rebuild()` for free). Requires `STORE_KEYS` + `chart-store.test.js` (1-line) update. Controller-local map would need bespoke threading into `host.build`. |
| Q7 | Color picker: native `<input type=color>`? | Yes — zero deps, CSP-safe, accessible. |
| Q8 | Apply on confirm (one rebuild) vs live preview? | Apply on confirm — one rebuild per dialog submit keeps #68 and perf simple. |
| Q9 | lineWidth range? | 1..4 (LightweightCharts typical). Clamp in core + server validator. |

---

## 7. Risks

1. **Server drops `style` on save (HIGH).** `parse_layout_indicators` rebuilds the
   entry and discards unknown keys. Until extended, persistence silently fails.
   *Mitigation:* extend the parser + `_validate_layout_style` (quotes.py) with a
   round-trip test; this is the only Python change → **100% patch coverage**.
2. **Style leaking into the kline query (MED).** Any style key placed under
   `params` is appended to `/market/api/kline` by `klineUrlFrom` and rejected by
   `_parse_params`. *Mitigation:* dedicated `style`/`styles` slot, never `params`.
3. **`STORE_KEYS` is asserted frozen (MED).** `chart-store.test.js:70-78` asserts
   exactly 6 keys. Adding `styles` breaks it. *Mitigation:* deliberate 1-line test
   edit; R14's store-key list in the spec is a delta for this change.
4. **Rebuild cost (MED).** `build()` recreates the chart on every style change.
   *Mitigation:* apply-on-confirm (one rebuild), not live per-input.
5. **Single-source discipline (MED).** Colors/width/precision are presentation only;
   the invariant "values come from the server" (R14) holds because style never
   changes a datum. A test should assert `indicator-settings-core.js` imports nothing
   and computes no indicator math.
6. **Frozen seams (MED).** Do NOT add a `window.marketChart` key (8 frozen) or a new
   global. Assert the settings UI via its DOM. No new bus event needed
   (`indicator:changed` + `layout:loaded` suffice).
7. **Period UI expansion (LOW-MED).** Wiring rsi/macd/stochastic/atr/bollinger
   periods is new DOM + validation surface beyond colors/width. Scope it explicitly
   or defer non-sma/ema periods to keep the slice bounded.
8. **No-deps / CSP (LOW).** Native `<dialog>` + `<input type=color>` + theme.css; no
   inline, no npm. `requirements.txt` unchanged; `src/` untouched.
9. **E2E seam (LOW).** New behavior asserted via DOM (dialog open, `series.options()`
   color/width, PUT body carries style) without touching existing assertions.
10. **allowlist route (LOW).** If a NEW core `indicator-settings-core.js` is added,
    it MUST be in `MODULE_ALLOWLIST` (and `chart.html` preloaded) or the import
    404s. `test_import_graph_routes_resolve` derives and asserts it automatically.

---

## 8. Proposed PR shape + size

Scope: one pure core (`indicator-settings-core.js`), style threading through
`chart-store` + `chart-host`, dialog UI + gear (likely in `controllers/indicators.js`),
`quotes.py` style preservation+validation, allowlist + preloads, theme.css, node
tests + E2E + pytest.

Rough diff estimate:

| Area | Lines |
|---|---|
| `indicator-settings-core.js` | ~90 |
| `chart-host.js` (style in `addSeries`/`build`) | ~20 |
| `chart-store.js` (`styles` key) | ~4 |
| `controllers/indicators.js` (gear + dialog + style read/save) | ~120 |
| `chart.html` (gear buttons + dialog markup) | ~40 |
| `views.py` allowlist + `chart.html` preloads | ~6 |
| `theme.css` dialog/gear styles | ~20 |
| `quotes.py` (`parse_layout_indicators` + `_validate_layout_style`) | ~30 |
| `tests/js/indicator-settings-core.test.js` + store/host test edits | ~120 |
| `tests/web/test_market_api.py` (style round-trip/400) | ~40 |
| `tests/web/test_market_e2e.py` (dialog → style → PUT) | ~60 |
| **Total** | **~550** |

**400-line budget risk: High.** F2 spans core + host + store + UI + server
persistence + tests. Honest recommendation: **chained 2 slices** (feature branch
chain, PR #1 → tracker, PR #2 → PR #1).

- **Slice 1 — core + host/store style threading + server persistence.**
  `indicator-settings-core.js`, `chart-host` style-in-build, `chart-store.styles`,
  `quotes.py` `parse_layout_indicators`+`_validate_layout_style`, allowlist/preload,
  node tests + pytest style round-trip. ~330 lines; autonomous (node + pytest green,
  no browser change yet; colors still render from defaults).
- **Slice 2 — UI (gear + dialog) + E2E + /impeccable.**
  `controllers/indicators.js` gear/dialog/style wiring, `chart.html` markup,
  `theme.css`, E2E test. ~220 lines; depends on Slice 1's core + persistence.

Single PR (~550) is feasible only under `single-pr` / `size:exception`.

---

## Affected Areas

- **NEW** `web/market/templates/market/indicator-settings-core.js` — pure schema +
  validate/normalize.
- `web/market/templates/market/chart-host.js` — thread style into `addSeries`/`build`
  (color/lineWidth/priceFormat), REGISTRY stays the default source.
- `web/market/templates/market/chart-store.js` — add `styles` key.
- `web/market/templates/market/controllers/indicators.js` — gear + dialog + style
  read/save (or a new `controllers/indicator-settings.js` if size forces it).
- `web/market/templates/market/chart.html` — gear buttons + settings `<dialog>` +
  modulepreload.
- `web/market/views.py` — `MODULE_ALLOWLIST += "indicator-settings-core"` (and a
  controller entry if a new controller).
- `web/market/quotes.py` — preserve+validate `style` in `parse_layout_indicators`;
  new `_validate_layout_style`. **Only Python change → 100% patch coverage.**
- `web/accounts/templates/registration/theme.css` — dialog/gear styling.
- **NEW** `tests/js/indicator-settings-core.test.js`; edits to `chart-store.test.js`.
- `tests/web/test_market_api.py` — style round-trip + 400.
- `tests/web/test_market_e2e.py` — add dialog/style/PUT test (no edits to existing).
- Archive-time: `openspec/specs/chart-config/spec.md` (style persistence),
  `market-chart/spec.md` (store key + serving), and a new `chart-indicator-settings`
  domain.

No `src/` change, **no migration**, no model, no order surface, no new runtime
dependency, CSP unchanged, no new `window` global, `window.marketChart` stays 8 keys.

## Ready for Proposal

**YES.** All seams are verified against merged F0/F1 code: the REGISTRY and its
hardcoded colors, the params→store→kline→server flow, `build(state)` as the sole
series-construction site, the `rebuild()` config-change path (#68), the `<dialog>`
precedent, the frozen seams, the allowlist/serving pattern, and — decisively — the
`parse_layout_indicators` code that drops `style` (the one Python change required).
The design phase must lock Q1 (per-chart scope), Q2 (precision → priceFormat vs
legend), Q4/Q7 (period UI scope), Q6 (store `styles` key) and the 2-slice split.
