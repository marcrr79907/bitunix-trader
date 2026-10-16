# chart-indicator-settings Specification

## Purpose

Per-token-per-chart presentation settings (color, line width, precision) plus an
editable period, persisted additively on the layout and re-rendered through the
existing config-change `rebuild()` path. Give each active indicator a
TradingView-style gear opening an accessible dialog to edit its visual style.
Style is presentation-only and per `(user, symbol, interval)`; it never changes a
datum, so the "values come from the server" invariant holds. Values stay
server-side; only STYLE changes client-side. No new dependency, CSP strict,
`src/` untouched, no migration. Issue #115 (Fase F2).

## Requirements

### Requirement: F2.1 — Pure settings core contract

`indicator-settings-core.js` MUST be a pure, framework-free ESM core that imports
nothing (no DOM, no chart lib, network, or `REGISTRY`). It MUST export exactly
`FIELDS`, `TOKENS`, `validate`, `normalize`, and `defaultsFor`. It MUST be
deterministic and MUST NOT throw for any input. `FIELDS` MUST freeze the style
vocabulary: `color` (hex string), `lineWidth` (int 1..4), `precision` (int 0..8).
`TOKENS` MUST be the render vocabulary. `defaultsFor(registry, token)` MUST derive
the default color from the injected registry (the single color source) with fixed
width `1` and precision `2`; the core MUST NOT hardcode any color.

#### Scenario: Unknown token

- GIVEN `defaultsFor(REGISTRY, "notreal")`
- WHEN called
- THEN it returns a safe style (`lineWidth:1`, `precision:2`, neutral color) and never throws

#### Scenario: Core imports nothing

- GIVEN `indicator-settings-core.js` source
- WHEN inspected
- THEN it has no `import` statement and defines no indicator math

### Requirement: F2.2 — normalize (clamp, defaults, drop unknowns)

`normalize(token, raw, defaults)` MUST return the frozen style shape
`{color:"#rrggbb", lineWidth:1..4, precision:0..8}`. Omitted keys MUST fall back
to `defaults`; unknown keys MUST be dropped; out-of-range `lineWidth`/`precision`
MUST be clamped into range; a malformed/absent `color` MUST fall back to the
default. It MUST be total (never throw) for hostile or partial input.

#### Scenario: Happy path round-trip

- GIVEN `{color:"#ff0000", lineWidth:2, precision:4}`
- WHEN normalized
- THEN the same values are returned

#### Scenario: Clamping and unknown keys

- GIVEN `{lineWidth:99, precision:-3, foo:"bar"}`
- WHEN normalized
- THEN output is `{color:<default>, lineWidth:4, precision:0}` with `foo` dropped

#### Scenario: Malformed input never throws

- GIVEN `raw` is `null`, a string, or `{color:"red"}`
- WHEN normalized
- THEN a valid defaulted style is returned and no exception is raised

### Requirement: F2.3 — validate contract

`validate(token, raw)` MUST return `{ok: bool, errors: [...]}` (no clamping).
Out-of-range or malformed `lineWidth`, `precision`, `color`, an unknown token, or
an unknown key MUST yield `ok:false` with a descriptive error. It MUST NOT throw.

#### Scenario: Invalid values reported

- GIVEN `{color:"#zzz", lineWidth:9, precision:20}`
- WHEN validated
- THEN `ok:false` and `errors` names each offender

#### Scenario: Valid passes

- GIVEN `{color:"#2962ff", lineWidth:1, precision:2}`
- WHEN validated
- THEN `ok:true` and `errors` is empty

### Requirement: F2.4 — Style store slot

The chart store MUST gain a `styles` slot (`{token: style}`) that is a top-level
key, NOT nested under `params`. `STORE_KEYS` MUST include `styles`. A style change
MUST flow through `readState()` into `rebuild()` so re-render is the existing
config-change path. Styles MUST NOT enter `params` (which serializes into the
kline query). The store MUST ALSO gain an `indicatorVisible` slot (`{token: bool}`)
as a top-level key and `STORE_KEYS` MUST include it; it is the reactive source the
object tree reads and MUST NOT enter `params`.
(Previously: the store slot family was `styles` only; no visibility key.)

#### Scenario: Store vocabulary

- GIVEN `STORE_KEYS`
- WHEN inspected
- THEN it contains `styles` and `indicatorVisible`, and the store still holds no candle data

#### Scenario: No style leak into params

- GIVEN a saved style for `sma`
- WHEN the kline URL is built
- THEN no `color`/`lineWidth`/`precision` key appears in the query string

#### Scenario: No visibility leak into params

- GIVEN `indicatorVisible.sma20 = false`
- WHEN the kline URL is built
- THEN no `visible` key appears in the query string

### Requirement: F2.5 — Host apply contract

`host.build(state)` MUST read `state.styles[token]` per series, falling back to
the registry default when absent, and MUST apply `color`/`lineWidth` at series
construction and `precision` as the series `priceFormat`
(`{precision, minMove: 10^-precision}`). A style change MUST travel
`indicator:changed` → `rebuild()` (the `setData` path); the live WS `update()`
path MUST remain the sole writer for candles (#68). Precision MUST NOT mutate the
legend `DECIMALS` map. The host MUST expose `setSeriesVisible(token, bool)`,
applying `series.applyOptions({visible})` on the active series for that token
(option-only; no `setData`/`update`, mirroring `setTheme`); when
`state.indicatorVisible[token]` is `false` at build time the series MUST still be
built and immediately set hidden via the same option-only path (no rebuild). The
one-rebuild invariant MUST now be proven by a committed E2E
(`tests/web/test_market_e2e.py`) that wraps the CDN global
`LightweightCharts.createChart` in-page as a counter (NOT a `window.marketChart`
key) and asserts `=== 1` builds after one confirmed style change; the legend
style-independence MUST be proven by committed source assertions in
`tests/js/legend-core.test.js` that `legend-core.js` and `controllers/legend.js`
contain no `styles`/`priceFormat` token.
(Previously: the host had no visibility method; hidden-at-build was undefined.)

#### Scenario: Series reflects style

- GIVEN `styles.sma = {color:"#ff0000", lineWidth:3, precision:5}`
- WHEN the chart builds
- THEN the `sma` series `options()` have that color/lineWidth and priceFormat precision 5

#### Scenario: Missing style uses registry default

- GIVEN no `styles` entry for `ema`
- WHEN the chart builds
- THEN the `ema` series uses the registry color, width 1

#### Scenario: setSeriesVisible is option-only

- GIVEN a built chart with a hidden token
- WHEN `setSeriesVisible("sma20", true)` runs
- THEN the series option `visible` becomes true and neither `setData` nor `update` is called

#### Scenario: Hidden at build stays option-only

- GIVEN `state.indicatorVisible.sma20 === false`
- WHEN `build(state)` runs
- THEN the `sma20` series is constructed and set hidden via `applyOptions` with no rebuild after boot

#### Scenario: One rebuild per style change (#68 intact)

- GIVEN an active chart with the `createChart` counter installed
- WHEN a style is confirmed
- THEN exactly one `rebuild()` runs on the `setData` path, `createChart` is called exactly once, and no live-path full `setData` occurs

#### Scenario: Legend output ignores style precision

- GIVEN `legend-core.js` and `controllers/legend.js` sources
- WHEN `tests/js/legend-core.test.js` scans them
- THEN neither contains a `styles`/`priceFormat` read — the legend cannot be affected by a per-indicator style precision

### Requirement: F2.6 — Gear and settings dialog

Each active indicator MUST render a `<button type="button" class="indicator-settings"
data-token aria-haspopup="dialog">` gear. Activating it MUST open a single shared
accessible `<dialog id="indicator-settings-dialog">` populated for that token,
with labelled controls for color (`<input type="color">`), line width
(`<input type="number" min=1 max=4>`), period (number) and precision
(`<input type="number" min=0 max=8>`). Submit MUST apply the style to
`store.styles[token]`, persist period in `params`, and close; cancel MUST make no
change. There MUST be NO inline script/handler (CSP unchanged).

#### Scenario: Gear opens the dialog for its token

- GIVEN active `sma` with a stored style
- WHEN its gear is activated
- THEN the dialog opens pre-filled from `styles.sma` and `params.sma`

#### Scenario: Confirm applies once

- GIVEN the dialog open for `sma`
- WHEN submitted with a valid style
- THEN `store.styles.sma` updates, one rebuild occurs, and the dialog closes

#### Scenario: Cancel makes no change

- GIVEN the dialog open
- WHEN cancelled
- THEN `store.styles` and `params` are unchanged and no rebuild occurs

#### Scenario: Empty required fields block submit

- GIVEN a cleared/invalid control
- WHEN submit is attempted
- THEN the dialog stays open and no invalid value is persisted

### Requirement: F2.7 — Persistence round-trip and style validation

The client PUT payload MUST carry each indicator's optional `style` AND optional
`visible` alongside `token`/`params`. The server MUST preserve and validate both
verbatim (see the `chart-config` delta): `PUT` with `style`/`visible` → `GET`
returns them; an invalid style MUST yield 400 before any write; a non-boolean
`visible` MUST yield 400 before any write. `parse_layout_indicators` MUST accept
and coerce `visible` (absent = true) and MUST preserve it on read; NO migration is
required (the `indicators` JSON column is open-ended, `models.py:217-221`).
(Previously: only `style` round-tripped; `visible` did not exist.)

#### Scenario: Round-trip verbatim

- GIVEN PUT `indicators=[{token:"sma",params:{sma_len:50},style:{color:"#ff0000",lineWidth:2,precision:4},visible:false}]`
- WHEN GET the same key
- THEN the returned entry carries that exact `style` and `visible:false`

#### Scenario: Absent visible defaults to true

- GIVEN PUT `indicators=[{token:"sma"}]` (no `visible`)
- WHEN GET the same key
- THEN the entry is treated as visible (absent or `true`)

#### Scenario: Bad style or non-bool visible → 400, no write

- GIVEN PUT with `style:{lineWidth:9}` (out of range) or `visible:"yes"`
- WHEN handled
- THEN 400 `{"error":"..."}` and the stored layout is unchanged

### Requirement: F2.8 — Accessibility, CSP, no new dependency

The dialog MUST be keyboard-operable (native `<dialog>` focus trapping; Escape
closes), every input MUST have an accessible name, and the gear MUST have a
visible focus state. No inline `<script>`/handler and no new runtime dependency
MAY be added; the market CSP and `requirements.txt` MUST be unchanged. At 375px
the dialog and gear MUST not cause horizontal overflow.

#### Scenario: Keyboard operable

- GIVEN focus on a gear
- WHEN Enter is pressed, then Escape in the dialog
- THEN the dialog opens and closes with focus returning to the gear

#### Scenario: CSP and manifest unchanged

- GIVEN the rendered `/market/` page and manifest
- WHEN inspected
- THEN the CSP equals the prior value, no inline script/handler exists, and no runtime dependency was added

### Requirement: F2.9 — Scope and isolation

Style MUST be scoped per chart, i.e. per `(user, symbol, interval)` — NOT
global-per-token, NOT cross-chart. User B MUST NOT read or write A's style
(inherited from the layout isolation contract). The A≠B scenario MUST now be
proven by committed assertions in `tests/web/test_isolation.py`: A's `ChartLayout`
carrying an indicator `style` yields `ChartLayout.for_user(B).count() == 0` and
`for_user(B).get(...)` raises `DoesNotExist`, so B can never read the row that
carries the style.
(Previously: style isolation was proven only by a session probe.)

#### Scenario: A ≠ B

- GIVEN A saved a layout with a styled indicator for `BTCUSDT,1m`
- WHEN `tests/web/test_isolation.py` evaluates `for_user(B)`
- THEN B's queryset is empty and `get` raises `DoesNotExist` — B never sees A's style

### Requirement: F2.10 — Module-size ceiling guard (R14)

A committed guard `tests/web/test_module_size_guard.py` MUST enforce the R14
layer rule that no module exceeds ~300 lines. It MUST define `CEILING = 300` and
scan every `web/market/templates/market/**/*.js` file (including `controllers/`)
via `Path.rglob("*.js")` with `len(path.read_text().splitlines())`. It MUST carry
an **explicit allowlist** exempting `chart-host.js` (326 lines), annotated with a
comment referencing R14 "~300" and DEBT-5 (#146) as the tracked refactor. The
guard MUST FAIL for any **other** module exceeding `CEILING`, naming the offending
file and its line count. It is pure filesystem (no Django client, no network) and
adds no dependency.

#### Scenario: Current tree passes with the documented exception

- GIVEN the current modules, WHEN the guard runs
- THEN it passes and `chart-host.js` is exempted by the annotated allowlist (DEBT-5 / #146)

#### Scenario: A synthetic over-ceiling module fails the guard (negative control)

- GIVEN any module other than `chart-host.js` with more than `CEILING` lines
- WHEN the guard runs
- THEN it fails and the failure names that file and its line count

## Edge-Case Matrix

| Case | Input | Expected |
|---|---|---|
| Unknown token | `normalize("notreal",…)` | defaulted style, no throw |
| Bad color | `color:"red"` | fall back to default |
| lineWidth out of range | `99` / `0` | clamp to `4` / `1` |
| precision out of range | `20` / `-3` | clamp to `8` / `0` |
| Unknown key | `{foo:1}` | dropped |
| Style on inactive indicator | token not in `indicators` | stored, ignored at render; no error |
| Malformed stored style | `indicators[].style` bad shape | PUT 400; GET returns default |
| A ≠ B | other user same key | registry default |

## Non-Applicable Domains

- **technical-indicators**: N/A — no indicator math changes; period edits reuse existing server params.
- **core-domain-boundary**: N/A — served template/JS/CSS only; `src/` untouched.
- **chart-shell**: N/A — no shell/chip/sidebar change.
