# chart-theme Specification

## Purpose

User-global theme (light/dark/system) driving BOTH the LightweightCharts v5
canvas and the shell CSS from one source. New capability — no prior spec. Fixes
smc-overlay W1 (white canvas on dark chrome). Single-source: JS never computes
values; the theme is presentation only. No new dependency; CSP unchanged.

## Requirements

### Requirement: CT1 — `theme-core` contract

`theme-core.js` MUST be a pure core that imports no module and MUST export
`resolve(theme, prefersDark)` and `optionsFor(resolved)`. It MUST be
deterministic and MUST NOT throw for any input (unknown theme, missing boolean,
`null`/`undefined`). `resolve` MUST accept `theme ∈ {"light","dark","system"}`
and a boolean `prefersDark`, returning exactly `"light"` or `"dark"`. `optionsFor`
MUST accept a resolved value (`"light"`/`"dark"`) and return the v5 option object
`{layout, grid, crosshair, rightPriceScale, timeScale}` where
`layout.background` is `{type: <ColorType.Solid symbol>, color}` — never a flat
string or magic number. An unknown `resolved` MUST fall back to the dark option
set without throwing. The module MUST be served same-origin (added to
`MODULE_ALLOWLIST`).

#### Scenario: resolve passes explicit values through

- GIVEN `resolve("light", true)` / `resolve("dark", false)`
- WHEN called
- THEN each returns `"light"` / `"dark"` respectively

#### Scenario: system follows the media query

- GIVEN `resolve("system", true)` and `resolve("system", false)`
- WHEN called
- THEN the results are `"dark"` and `"light"` respectively

#### Scenario: Unknown theme degrades, never throws

- GIVEN `resolve("bogus", true)` and `resolve(null, undefined)`
- WHEN called
- THEN a valid `"light"`/`"dark"` is returned and no error is thrown

#### Scenario: optionsFor carries the v5 shape

- GIVEN `optionsFor("dark")`
- WHEN the result is inspected
- THEN `layout.background` is `{type: ColorType.Solid, color}` and `layout.textColor`, `grid.vertLines/horzLines.color`, `crosshair`, `rightPriceScale.borderColor`, `timeScale.borderColor` are present

#### Scenario: Core is pure and served

- GIVEN `theme-core`
- WHEN imports are inspected and it is requested under `/market/`
- THEN it imports nothing and is served 200 with a JS MIME type

### Requirement: CT2 — `data-theme` transport

One `data-theme` attribute on the document root (`<html>`) MUST be the single
source selecting the active theme for BOTH the CSS tokens and the chart options.
Its only valid values MUST be `"light"` and `"dark"` (the RESOLVED theme, not
`"system"`). Setting it MUST flip the shell to the matching token block AND the
applier MUST pass the same resolved value to the host; the two MUST never
disagree.

#### Scenario: Attribute drives both layers

- GIVEN the resolved theme is `"light"`
- WHEN the applier runs
- THEN `document.documentElement.dataset.theme === "light"` and the host's chart options are the light set

#### Scenario: Only resolved values are written

- GIVEN the stored preference is `"system"` with a light OS
- WHEN the applier runs
- THEN `data-theme` is `"light"` (never `"system"`)

### Requirement: CT3 — "Sistema" media-query behavior

When the stored preference is `"system"`, the theme MUST be resolved from
`window.matchMedia("(prefers-color-scheme: dark)").matches`. A `change` listener
on that media query MUST re-resolve and re-apply while the preference stays
`"system"`. When the preference is explicit (`"light"`/`"dark"`), the media query
MUST NOT override it.

#### Scenario: OS change re-applies

- GIVEN `theme="system"` on a light OS
- WHEN the OS switches to dark and the media query fires `change`
- THEN the resolved theme becomes `"dark"` and both layers re-apply

#### Scenario: Explicit theme ignores the OS

- GIVEN `theme="light"` on a dark OS
- WHEN the media query fires `change`
- THEN the resolved theme stays `"light"`

### Requirement: CT4 — v5 canvas theming

The chart MUST be created with the theme's option set applied at construction:
`layout.background = {type: ColorType.Solid, color}`, `layout.textColor`, `grid`
line colors, `crosshair`, and `rightPriceScale`/`timeScale` border colors. Axis
text (`layout.textColor`) MUST meet ≥4.5:1 contrast against
`layout.background.color` in BOTH themes. Series/indicator hues MAY stay
theme-independent; the drawing text and the SMC swing connector MUST be
theme-aware (never the dark text color on a light canvas).

#### Scenario: Born themed

- GIVEN `state.theme="dark"`
- WHEN `build(state)` runs
- THEN the created chart's `layout.background.color` is the dark color and `layout.textColor` matches it

#### Scenario: Contrast holds both ways

- GIVEN the light and dark option sets
- WHEN `textColor` vs `background.color` is measured
- THEN the contrast ratio is ≥4.5:1 in both

#### Scenario: Drawing text is theme-aware

- GIVEN a light resolved theme
- WHEN drawings render
- THEN the drawing text color is the light text token (never `#e6edf3`)

### Requirement: CT5 — Live toggle is option-only

A live theme change (no symbol/interval change) MUST be applied via
`chart.applyOptions({layout, grid, crosshair, rightPriceScale, timeScale})` —
option-only, mirroring `setScaleMode` (#68): no `setData`, no `update`, no
rebuild, no `fetchHistory`. A theme change that coincides with a rebuild MUST
instead be born applied via `state.theme` (no separate re-apply needed).
`applyOptions` MUST pass full values, never `undefined` keys.

#### Scenario: Live toggle writes no data

- GIVEN a built chart
- WHEN the user switches theme live
- THEN `chart.applyOptions` runs with the theme groups and neither `setData` nor `update` is called

#### Scenario: Rebuild is born themed

- GIVEN `state.theme="light"`
- WHEN a chart-type change rebuilds
- THEN the new chart is created with the light option set

### Requirement: CT6 — Persistence contract

`ChartPreference.theme` MUST persist user-global and `/market/api/preference`
MUST carry `theme` end-to-end (see `chart-config` delta). Boot MUST read `theme`
before the first build; a failed/empty fetch MUST fall back to `"system"` without
blocking boot. A theme change MUST debounce-PUT only the `theme` key; a failed
save MUST be non-fatal.

#### Scenario: Round-trip restores the theme

- GIVEN a saved `theme="dark"`
- WHEN the page reloads
- THEN the chart boots dark and both layers reflect it

#### Scenario: Fetch failure falls back to system

- GIVEN the preference fetch fails
- WHEN the page boots
- THEN the theme resolves from the OS (`"system"`) and boot is not blocked

### Requirement: CT7 — Boundary, seam, no dependency

No `src/` change, no new runtime dependency, CSP unchanged. `window.marketChart`
MUST keep exactly its 8 frozen keys — `theme` MUST NOT be added to it; the theme
lives in the store (`state.theme`) and/or `data-theme`. `window.SmcOverlayCore`
MUST be untouched.

#### Scenario: Seam stays 8 keys

- GIVEN a booted chart
- WHEN `window.marketChart` is read
- THEN exactly 8 keys exist and no theme key was added

#### Scenario: No dependency or CSP change

- GIVEN the change
- WHEN the manifest, `src/`, and the CSP header are inspected
- THEN no dep was added, `src/` is untouched, and the CSP equals the prior value

## Edge-Case Matrix

| Case | Input | Expected |
|------|-------|----------|
| System → dark OS | `theme="system"`, prefersDark `true` | resolved `"dark"` |
| System → light OS | `theme="system"`, prefersDark `false` | resolved `"light"` |
| Media change | OS flips while `theme="system"` | re-resolve + re-apply both layers |
| Explicit vs OS | `theme="light"` on dark OS | stays `"light"` |
| Invalid stored theme | `theme="bogus"` from API/DB | `resolve` → `"system"` behavior, no throw |
| Toggle live | theme change, no config change | option-only `applyOptions`, no `setData` |
| Toggle + rebuild | theme + chart-type change | born themed via `state.theme` |
| Contrast | both themes | axis text vs background ≥4.5:1 |
| A≠B | B reads/writes | B gets own `"system"` default, A untouched |
