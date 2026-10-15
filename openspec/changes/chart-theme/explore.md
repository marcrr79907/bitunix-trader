# Exploration: chart-theme (issue #148, DEBT-7 — P3)

> Read-only exploration. No code written. No execution ordered.

## Decision inside this document

The issue's open decision — **theme scope: chart canvas only, or chart + shell** — is
answered in §3 with a recommendation and the evidence behind it.

---

## 1. Current theming

### Token layer — `web/accounts/templates/registration/theme.css`

A single `:root` block (lines 3–10) declares the whole palette as CSS custom
properties, served same-origin as `text/css` by `accounts.views.theme_css`
(`web/accounts/views.py:98`) at route `theme.css` (`web/accounts/urls.py:17`):

```
--bg:#0e1117  --bg-2:#161b22  --surface:#1c2230  --border:#2a3240
--text:#e6edf3  --muted:#8b949e  --accent:#2962ff
--up:#26a69a  --dn:#ef5350
--fs-*  --sp-*  --r  --mono
```

**There is NO `prefers-color-scheme` handling and NO `data-theme` /
`[data-theme]` selector anywhere in the repo** (verified by grep across
`web/**` for `prefers-color-scheme`, `data-theme`, `matchMedia`, `theme`). The
shell is hardcoded dark. There is **no light token set** to switch to — one
would have to be authored.

`theme.css` has a `body:has(.market-layout){height:100dvh}` rule (line 22) and a
`@media (max-width:820px)` block (line 139) but no color-scheme media query.

### Shell vs canvas

- The **shell** (topbar, `.panel`, buttons, `dialog`, chips, legend) is themed
  entirely from the `:root` vars above — `background:var(--surface)`,
  `color:var(--text)`, borders `var(--border)`, up/down `var(--up)`/`var(--dn)`.
- The **chart canvas** is drawn by LightweightCharts v5, which knows nothing
  about CSS custom properties. Its colors come only from chart options.

### Where the mismatch (smc-overlay W1) comes from

`chart-host.js:158` constructs the chart as:

```js
chart = LightweightCharts.createChart(el, {
  autoSize: true,
  timeScale: { timeVisible: true },
});
```

No `layout`, no `grid`, no `crosshair` are passed. v5 then applies its **own
defaults** (confirmed against the v5.2.0 typings/defaults):

- `layout.background = { type: ColorType.Solid, color: '#FFFFFF' }` → **white canvas**
- `layout.textColor = '#191919'` → near-black axis text
- `grid.vertLines/horzLines.color = '#D6DCDE'`

So the canvas renders white while the surrounding chrome is `--bg:#0e1117`. That
is exactly W1 from `2026-10-12-smc-overlay/verify-report.md` ("the
LightweightCharts canvas renders white while the app chrome is dark"), listed
there as pre-existing and chart-wide. This change is the follow-up for that
warning.

SMC made this worse-adjacent: `controllers/smc.js:126` strokes the swing
connector `#616161` specifically for a **white** canvas ("6.2:1 on the white
chart canvas"). That choice assumes the canvas stays white — a light theme must
keep it, a dark theme must revisit it.

---

## 2. v5 theme options — exact shape and re-apply semantics

All names below are v5.2.0 (the pinned CDN build in `chart.html:113`,
`lightweight-charts@5.2.0`).

### Option shape (confirmed against v5 docs/defaults)

```js
createChart(el, {
  layout: {
    background: { type: LightweightCharts.ColorType.Solid, color: "#..." },
    textColor: "#...",
  },
  grid: {
    vertLines: { color: "#..." },
    horzLines: { color: "#..." },
  },
  crosshair: {
    vertLine: { color: "#...", labelBackgroundColor: "#..." },
    horzLine: { color: "#...", labelBackgroundColor: "#..." },
  },
  rightPriceScale: { borderColor: "#..." },
  timeScale:     { borderColor: "#..." },
});
```

- `layout.background` is an **object** `{ type, color }` in v4/v5 (the v3 flat
  `backgroundColor` string was removed). `type` uses the `ColorType` symbol
  (`ColorType.Solid`), not a magic number — same discipline the codebase already
  applies to `PriceScaleMode` in `chart-host.js:231`.
- `grid` controls only line colors/styles; `rightPriceScale.borderColor` and
  `timeScale.borderColor` draw the axis separators.
- The key `layout.textColor` is what the a11y requirement (≥4.5:1 axis text)
  targets; grid lines are decoration (WCAG 1.4.11 non-text floor 3:1).

### applyOptions vs create-only — why this matters here

`chart-host.js` has **one** `createChart` call. Its `build(state)` **destroys and
recreates** the chart on every rebuild (`if (chart) chart.remove();` line 157).
There is **no `chart.applyOptions`** call anywhere in `chart-host.js` today.

Consequences for theme:

- Because the chart is **recreated** on rebuild, theme colors passed into the
  `createChart` options survive every rebuild automatically — the new chart is
  born themed. No separate re-apply step is needed on rebuild **if** the theme is
  read inside `build()` from `state`.
- If theme must change **without** a rebuild (a live toggle), the host needs a
  **new `applyOptions` path** — `chart.applyOptions({ layout, grid, crosshair,
  rightPriceScale, timeScale })` — mirroring `setScaleMode`
  (`chart-host.js:237`) which already does `priceScale("right").applyOptions` as
  an option-only change with no `setData` (#68 held).
- `applyOptions` exists on the chart object and accepts all five option groups
  above. **Design note:** a theme toggle that only swaps colors is a strong
  candidate for an option-only `applyOptions` (mirroring the `scale:changed`
  precedent) — it avoids a full rebuild + refetch. But a *shell* theme flip also
  needs the CSS tokens to change, and candle sub-pane separator colors, so the
  simplest coherent approach is discussed in §3/§8.

The one v5 gotcha to carry into design: `applyOptions` treats `undefined` as
"not specified" (no reset). Pass full values, not `undefined` keys.

---

## 3. Scope decision — chart-only vs chart + shell

### Option A — chart canvas only

Change `chart-host.js` `build()` (and series colors) so the canvas matches the
existing dark chrome. Add a theme selector (light/dark/system) that only drives
chart options.

- Pros: smallest diff; touches one host file + persistence; no CSS authoring; no
  risk to other screens (the shell is untouched, so Signals/Rules/Analytics are
  unaffected).
- Cons: violates the issue's stated criterion **"canvas y chrome coherentes"**.
  A user who picks "Claro" gets an *inverted* page: a light chart floating on a
  dark shell — W1 in reverse. The dark chrome and light canvas are precisely the
  bug; A relocates it rather than fixing it. Also: the drawing text color
  `#e6edf3` (`drawing-core.js:22`) is the dark `--text`; on a light canvas it is
  **invisible** (≈1.1:1), so "Claro" would ship broken drawings.

### Option B — chart + shell (coherent) — RECOMMENDED

Flip the whole surface together via a `data-theme` attribute on `<html>`/`<body>`
that selects between the dark `:root` tokens and an authored light token set;
the chart host reads the resolved theme and paints the canvas from the same
palette values.

- Pros: satisfies "canvas y chrome coherentes"; the toggle has a *visible*
  meaning across the whole market page; one theme model (a `data-theme` on the
  root) drives both CSS and the chart; the resolved theme is a single value both
  layers read.
- Cons: larger diff — requires authoring a light token set in `theme.css`
  (~15 vars) plus a `[data-theme="light"]` selector; the *shell* flips on every
  page that inherits the tokens (Market, Signals, Rules, Analytics), so the light
  set must be verified against all of them, not just the chart.
- Mitigation for the breadth: scope the `data-theme` attribute to the **market
  page root** if a global shell flip is out of scope — but the issue explicitly
  recommends "chart + shell coherentes", so the global flip is the intended
  reading. Note the shell currently has **no** light mode; this is net-new CSS.

### Recommendation

**Option B (chart + shell)**, because:
1. The requirement says "canvas y chrome coherentes" and the issue's own
   recommendation is "chart + shell coherentes".
2. Option A ships a *worse* light mode (light canvas on dark chrome) and breaks
   drawing text; the theme must therefore own the shell anyway to be usable.
3. The `data-theme`-on-root pattern is the smallest coherent mechanism: one
   attribute selects the token block, and the chart host reads the *same* resolved
   value. No duplicated color maps.

The `prefers-color-scheme` a11y motive (WCAG 1.4.11 for drawing text, but also
the general "System" expectation) only works cleanly when the shell participates,
which again points at B.

---

## 4. "Sistema" mode

- Detection: `window.matchMedia("(prefers-color-scheme: dark)")` → `.matches`.
- Live changes: `mq.addEventListener("change", handler)` (modern API; the legacy
  `addListener` is unnecessary) re-resolves the theme while `theme === "system"`.
- Mapping: a **pure core** `resolve(theme, prefersDark) → "light" | "dark"`,
  where `theme` is the stored preference (`"light" | "dark" | "system"`) and
  `prefersDark` is a boolean. `"system"` → `prefersDark ? "dark" : "light"`;
  explicit values pass through. Never throws; unknown → treat as `"system"` (or
  `"dark"`, the current default). This mirrors the repo's "pure core at the
  center" rule (`chart-types-core.js`, `legend-core.js`, `drawing-core.js`).
- Where it lives: a **new pure core `theme-core.js`** (imports nothing), plus a
  thin applier. See §8 for the applier's home.

`theme-core.js` must be added to `views.MODULE_ALLOWLIST` (and a
`modulepreload` in `chart.html`) or its served import 404s
(`test_market_ux.py::test_import_graph_routes_resolve` enforces this).

---

## 5. Persistence

- `ChartPreference` (`web/trading/models.py:295`) already exists, is a
  `UserOwnedModel` with a `OneToOneField` user, and carries `last_interval`,
  `scale_mode`, `chart_type`. Adding a third preference field is the exact
  pattern chart-scales used.
- New field: `theme = models.CharField(max_length=16, default="system")`,
  validated against a server vocabulary `THEMES = ("light", "dark", "system")`
  in `quotes.py` (mirroring `SCALE_MODES`/`CHART_TYPES`).
- Migration **`0011`** is `AddField`-only with a default → **additive, no data
  migration, no risk**. This is identical to `0010_chartpreference_scale_type`
  (`AddField` x2, both defaulted). `makemigrations --check` must stay green.
- API: `/market/api/preference` (`views.py:289`) GET body (`_preference_body`,
  line 315) gains `"theme"`; `_put_preference` (line 324) gains a
  `if "theme" in body: validate against THEMES else 400` branch. Partial-body
  semantics already exist and are tested; adding one key is mechanical.
  The GET default-when-absent body (lines 304–311) and the PUT nothing-to-apply
  branch (lines 353–360) also gain `"theme": "system"`.

---

## 6. Series colors

Today's color sources and whether they need a light variant:

| Source | Colors | Light-canvas concern |
|---|---|---|
| Candle up/down | **Not set** — v5 `CandlestickSeries` defaults (`upColor #26a69a`, `downColor #ef5350`, wick/border darker variants). Host calls `addSeries(Ctor)` with no options (`chart-host-candles.js:26`). | Defaults already equal `--up`/`--dn`. On a light canvas they read acceptably, but v5's wick/border defaults should be re-checked for the ≥3:1 non-text floor. |
| Indicator REGISTRY | `chart-host.js:16–54`: `#2962ff`, `#ff6d00`, `#7e57c2`, `#26a69a`, `#ab47bc` | Mid-tone hues; generally legible on both canvases, but `#7e57c2`/`#ab47bc` on white are borderline for thin 1px lines. Re-evaluate, don't necessarily fork. |
| SMC overlay | `smc-overlay-core.js:23–28`: `swings {#ef5350,#26a69a}`, `structure {#2962ff,#ff6d00}`, `order_blocks`/`fvg`/`setups` reuse up/down, `range #7e57c2` | Same mid-tones; the swing connector `#616161` (`controllers/smc.js:126`) was tuned **for white** and must stay for light but change for dark. |
| Drawings | `drawing-core.js:18–22`: `hline #2962ff`, `trendline #ff6d00`, `fib #7e57c2`, `rect #26a69a`, **`text #e6edf3`** | `text` is the **dark-theme `--text`** — invisible on light. This MUST become theme-aware. |
| Candle legend | `legend-core.js` / `.chart-legend` — uses CSS vars (`.lg-chg.up{color:var(--up)}`) | Follows the shell automatically once tokens flip. |

Assessment: series line colors are broadly acceptable on both canvases, but:
1. **Drawing text `#e6edf3` is a hard bug on light** — must follow the theme.
2. **Swing connector `#616161` is tuned for white** — needs a per-theme value.
3. Candle wick/border defaults should be re-checked for light contrast.

The lightest coherent approach (see §8): keep the **numeric series colors
theme-independent** where they pass contrast, and make only the **surface/text
options** (`layout.background`, `layout.textColor`, `grid`, `crosshair`,
`rightPriceScale/timeScale.borderColor`) theme-driven. Fork only the two
explicitly-tuned colors (drawing text, swing connector) when a light token is
required. Avoid maintaining two full palettes if one passes — evidence should
drive it (contrast check in §7).

---

## 7. Tests

Mirroring the chart-scales test pyramid:

- **`theme-core.js` pure (node --test, `tests/js/theme-core.test.js`)**:
  `resolve("light", true)==="light"`, `resolve("dark", false)==="dark"`,
  `resolve("system", true)==="dark"`, `resolve("system", false)==="light"`,
  unknown → fallback, never throws. This is the red→green core.
- **Host test (`tests/js/chart-host.test.js`)**: extend the existing
  `withChartStub` (it already stubs `createChart`/`document`/`window`) to assert
  the chart options passed to `createChart` carry the theme's `layout.background`
  / `layout.textColor` for a dark build, and an option-only
  `chart.applyOptions(...)` path for a live toggle. The stub currently captures
  no `createChart` args — capture them.
- **Python pref round-trip (`tests/web/test_market_api.py`)**: GET default body
  gains `theme:"system"`; PUT `{theme:"light"}` round-trips; PUT
  `{theme:"bogus"}` → 400 and writes nothing; partial PUT applies only `theme`.
  These mirror the existing `scale_mode`/`chart_type` cases (lines ~2045–2089).
- **E2E (`tests/web/test_market_e2e.py`)**: toggle → the canvas background
  changes (read `chart.options().layout.background.color` via
  `window.marketChart.chart`) and/or `document.documentElement.dataset.theme`
  flips; reload → the persisted theme is restored; "Sistema" follows
  `page.emulate_media(color_scheme=...)`. Use DOM/evaluate assertions, never
  image diffs (repo rule).
- **a11y contrast check**: assert the resolved axis `textColor` vs
  `layout.background.color` meets ≥4.5:1 for both themes (a small pure helper or
  a fixed-pair assertion). This is the issue's explicit a11y criterion.
- **`/impeccable`**: run the frontend audit skill on the market page after
  implementation — it is listed as a criterion ("UI auditada").

DB/boot: Rust note — boot must read `theme` in `loadPreference()`
(`main.js:189`) with a `"system"` fallback, and apply it **before the first
build** (so the canvas is never born white), reusing the existing preference
sequencing.

---

## 8. Open questions / decisions

1. **Scope** — chart-only vs chart+shell. **Recommend chart+shell** (§3), matching
   the issue's criterion and recommendation. This is THE decision to ratify.
2. **`theme-core.js` home** — a new pure core (mirrors `chart-types-core.js`) is
   the clean choice. The **applier** (which sets `document.documentElement.dataset.theme`,
   reads `matchMedia`, and calls the host) could be: (a) a new small controller
   `controllers/theme.js`, or (b) folded into the existing `toolbar` controller
   (which already owns the F8 selects) or `main`. Given the size ceiling and the
   "no new controller unless needed" precedent (chart-scales R26 kept controls in
   `toolbar`), **prefer the toolbar controller + a pure `theme-core`**, with
   `main` wiring the boot apply — avoid a new controller unless the shell-flip
   logic justifies one.
3. **"Sistema" storage** — store `"system"` and resolve at load **and** on
   `matchMedia` change. Confirmed as the right model.
4. **Light token set** — **none exists**; it must be authored (~15 vars) in
   `theme.css` under `[data-theme="light"]`. This is the largest net-new CSS.
5. **Does the shell support light today?** No — hardcoded dark only. A global
   flip means the light set must be validated on every shell page
   (Market/Signals/Rules/Analytics), not just the chart.
6. **Chart theme transport** — pass the resolved theme into `build(state)` via the
   store (`state.theme`), so a rebuild is born themed; a **live** toggle uses an
   option-only `chart.applyOptions` (mirroring `setScaleMode`) to avoid a
   rebuild+refetch, unless a rebuild is acceptable and simpler. Decide in design.
7. **Candle/series color forking** — decide per §6 whether to fork series colors
   or keep them theme-independent (recommended: keep, fork only drawing text +
   swing connector).

---

## 9. Risks

- **v5 option shape drift**: `layout.background` must be `{type: ColorType.Solid,
  color}`, not a flat string (v3 style); v5 defaults confirm white. Using a magic
  number for `ColorType` would repeat the `PriceScaleMode` mistake. Verify against
  the pinned 5.2.0 build.
- **Contrast failures on light**: `drawing text #e6edf3` is near-invisible on
  white; swing connector `#616161` is white-tuned; thin mid-tone indicator lines
  may miss the non-text floor. A light theme without re-checking these ships
  broken. The a11y test in §7 is the guard.
- **Frozen seam**: `window.marketChart` MUST stay exactly **8 keys**
  (`tests/web/test_market_e2e.py::test_shell_keeps_seam_at_eight_keys`). The theme
  MUST NOT be added to the seam — it belongs in the store (`state.theme`) and/or
  `data-theme` on the DOM. `window.SmcOverlayCore` untouched.
- **Migration additivity**: `0011` must be `AddField`-only with a default
  (`makemigrations --check` green). No data migration.
- **Module size ceiling**: `chart-host.js` is **286/300 lines** and
  `tests/web/test_module_size_guard.py` enforces `CEILING = 300` with an **empty**
  allowlist. Adding theme option blocks inline risks breaching it. Mitigation:
  build the theme option object in a **pure `theme-core.js`** (e.g.
  `optionsFor(theme)`) and spread it into `createChart`, keeping the host thin —
  the same reason `chart-host-candles.js` was extracted (DEBT-5/#146).
- **Served-module registration**: `theme-core.js` MUST be added to
  `MODULE_ALLOWLIST` + `modulepreload`, or the import 404s and the chart blanks
  (`test_import_graph_routes_resolve`, `test_module_allowlist_routes_serve_javascript`).
  The `CONTROLLER_ALLOWLIST` count (`== 7`) is asserted in
  `test_market_ux.py:119` — adding a theme controller would require updating that
  assertion (another reason to avoid a new controller).
- **CSP / no deps**: no inline script/handler; `matchMedia` and DOM writes are
  same-origin ESM. `requirements.txt` and CSP unchanged.
- **Patch 100%**: placeholder-free patch — every new line must be covered by a
  committed test (the guards above), including 400 paths and the "system"
  fallback.
- **E2E env flake (WS, DEBT-8)**: the WS E2E is known-flaky under load
  (`2026-10-12-smc-overlay` W4). Theme E2E should avoid coupling to the WS path;
  run `-p no:randomly` on an idle machine as the prior report advises.
- **Shell breadth of a global flip**: if Option B flips the shell globally, the
  light set must be checked on pages beyond Market (signals tables, rules forms,
  analytics SVG) — the analytics SVG theming (`theme.css:178+`) is CSS-driven and
  should follow, but must be re-verified.

---

## 10. Proposed PR shape + size

The work spans: theme core + host options + shell light tokens + persistence
(model/migration/API) + toolbar control + boot wiring + a11y + tests + E2E +
`/impeccable`. That is plausibly **>400 changed lines** once the light token set
is authored, so a single PR is at risk of breaching the review budget
(400 lines, `sdd-phase-common.md` §E).

**Recommendation — 2 chained slices (Feature Branch Chain):**

- **Slice 1 — theme engine + chart canvas (no persistence shell flip yet):**
  `theme-core.js` (pure `resolve` + `optionsFor`), `chart-host.js` consumes
  `state.theme` in `build()` + a live `applyOptions` path, `MODULE_ALLOWLIST` +
  `modulepreload`, node tests (`theme-core`, host options), a host test for the
  option shape. Small, self-contained, verifiable.
- **Slice 2 — persistence + shell coherence + UI + a11y + E2E:**
  `ChartPreference.theme` + migration `0011`, `/market/api/preference` gains
  `theme` (+400), the toolbar theme control, `theme.css` light token set +
  `[data-theme]`, `document.documentElement.dataset.theme` applier + `matchMedia`,
  boot restore, Python round-trip tests, E2E toggle/reload/system, contrast
  check, `/impeccable`.

Honest forecast: **chained PRs recommended: Yes**; **400-line budget risk:
Medium** (Slice 2 alone may approach it if the light token set and E2E grow).
The orchestrator's `delivery_strategy` should carry this into `sdd-tasks`.

---

## Ready for Proposal

Yes. The scope decision (§3, recommend chart+shell) is the one item to ratify
before design. All other decisions have a default. No blockers; no code was
modified.
