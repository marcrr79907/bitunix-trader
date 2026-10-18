# chart-alerts Specification

## Purpose

Alert affordances on the `/market/` chart (issue #123, F10): a bell pinned to the
crosshair that creates or edits a `price` `AlertRule` in place, a keyboard entry
path from the empty-chart context menu, and armed/fired markers on the candle
series for the caller's rules on the active `(symbol, interval)`. This capability
is the UI over the frozen `alert-rules` engine (`src/alert_rules.py`) and the JSON
transport (`alert-rules` R10/R11); it never evaluates conditions or places orders.

Vocabulary comes from the frozen S4 precedence (`web/market/views.py:104-116`):
`fired` (any `last_fired_at`) > `armed` (any `is_active`) > `inactive` (rules
exist, none active) > `none`.

## Requirements

### Requirement: R1 — Bell at the crosshair

The chart MUST render a bell as a real `<button type="button">` inside `#chart`,
positioned at the crosshair point's price and offset horizontally by the measured
right price-scale width so it clears the crosshair price tag and the axis drag
strip. It MUST be hidden when the crosshair has no point (a deferred clear hides
it after the pointer leaves the bell), MUST carry an accessible name that includes
the seeded price, and MUST be reachable by keyboard with a visible focus state
(`:focus-visible`). It MUST NOT be created with an inline handler (CSP,
`design-system` R7).

Because the bell only exists once a pointer produces a crosshair point, a keyboard
user MUST also have a pointer-free entry: the empty-chart context menu (openable
with `Shift+F10` or the `ContextMenu` key) offers an **Add alert** item that opens
the same dialog seeded from the newest loaded candle's close. That action travels
an injected callback (the `onIndicatorSettings` precedent), not a new bus event.

#### Scenario: Bell follows the crosshair

- GIVEN a built chart with a crosshair over a candle at price 100
- WHEN the crosshair moves to price 105
- THEN `#chart-alert-bell` is visible and its accessible name contains 105

#### Scenario: Bell hides without a point

- GIVEN a visible bell
- WHEN the crosshair leaves the plot (`param.point` absent, mirroring `legend.js:190-196`)
- THEN the bell carries the `hidden` attribute and is not focusable

#### Scenario: Bell is keyboard reachable

- GIVEN a visible bell
- WHEN the user Tabs to it and activates it with Enter or Space
- THEN the condition dialog opens

#### Scenario: Keyboard path without a crosshair

- GIVEN an empty chart with no crosshair point
- WHEN the context menu is opened from the keyboard and "Add alert" is activated
- THEN the dialog opens seeded from the newest close, and no bus event was added

### Requirement: R2 — Condition dialog

Activating the bell (or the context-menu "Add alert" item) MUST open a native
`<dialog id="alert-dialog">` seeded with a price-only condition: `op` ∈
`{"above","below"}` (`_OPS`, `src/alert_rules.py:27`), `level` a numeric value > 0
seeded from the crosshair price (or the newest close for the keyboard path),
default `op` derived from the last close (`above` when the level is at/above it,
else `below`). Apply MUST persist through the JSON API — POST when no `price` rule
for the same pair is within 10 px of the level, PUT when one is. When a near rule
is the target, the dialog MUST name it (`#alert-cue`: "Updates the existing
<level> alert") so a silent edit is never silent. Cancel and `Escape` MUST write
nothing and MUST return focus to `#chart`. A failed Apply (client validation,
`400`, or network error) MUST re-open the dialog with the error visible, keep the
typed level, and focus the level input. A successful Apply MUST show a visible
confirmation in `#alert-confirm[role="status"]` naming the armed/updated level,
distinct from the `#alert-status` live summary. The dialog copy MUST NOT promise a
"cross": the engine fires on the closed-bar edge.

#### Scenario: Create from the bell

- GIVEN the crosshair at 100 and no nearby price rule
- WHEN the dialog is applied with `op=above, level=100`
- THEN one POST to `/market/api/alerts` carries `{type:"price",op:"above",level:100}` and a confirmation is announced

#### Scenario: Edit a nearby rule

- GIVEN an existing `price` rule whose level is within 10 px of the seeded price
- WHEN the dialog is applied
- THEN a PUT to `/market/api/alerts/<id>` is issued, the cue named that rule, and no second rule is created

#### Scenario: Cancel writes nothing

- GIVEN the dialog open with edited fields
- WHEN Cancel or `Escape` is used
- THEN no request is issued, the rule list is unchanged, and focus returns to `#chart`

#### Scenario: Invalid level is rejected client-side

- GIVEN a level input that is empty, non-numeric, or ≤ 0
- WHEN Apply is pressed
- THEN no request is issued and the dialog stays open with an error (mirrors `parse_condition`'s `_parse_price`)

#### Scenario: Failed Apply re-opens the dialog

- GIVEN a well-formed level and a server that answers `400` or a network error
- WHEN Apply completes
- THEN the dialog is re-opened with `{"error"}` visible, the typed level preserved, and the level input focused

### Requirement: R3 — Interval eligibility

A rule is interval-scoped and the worker skips intervals outside
`CANDLE_INTERVALS` (`web/trading/candles.py:19-30`, `web/worker.py:167-168`). On an
active interval outside `CANDLE_INTERVALS` (`1m`, `30m`, `3d`, `6h`, `8h`, `12h`)
the bell MUST be inert and MUST expose an accessible reason via
`aria-describedby="alert-interval-reason"`; it MUST stay focusable
(`aria-disabled="true"`, not the native `disabled` attribute, which would remove
it from the tab order and never announce the reason) and MUST skip the open
action. The JSON API MUST reject such a create with 400. The eligible set MUST
mirror the server's `CANDLE_INTERVALS` (`alert-ui-core.js` `EVALUABLE`), pinned by
a parity test.

#### Scenario: Bell is inert on a non-evaluable interval

- GIVEN the active interval is `1m` (or `3d`/`6h`/`8h`/`12h`)
- WHEN the page renders
- THEN the bell carries `aria-disabled="true"` and `aria-describedby` points at a reason naming the interval as non-evaluable

#### Scenario: API rejects a non-evaluable interval

- GIVEN a POST with `interval="1m"`
- WHEN the request is handled
- THEN it returns 400 and no rule is created (`alert-rules` R10)

#### Scenario: Enabled on an evaluable interval

- GIVEN the active interval is `1h`
- WHEN the chart renders
- THEN the bell is enabled and carries no `aria-describedby`

### Requirement: R4 — Armed and fired markers

Markers MUST render for the caller's rules on the active `(symbol, interval)` only,
via `createSeriesMarkers` on the candle series, owned by a separate handle from the
SMC primitive (`controllers/smc.js:235`). They MUST be (re)built on `chart:built`,
on `history:loaded`, on `candle:closed`, and on every symbol/interval switch, and
cleared before a switch. Armed and fired MUST differ by `shape` AND `text` AND
`position` (not color alone). Anchors: fired uses `last_fired_at` (epoch seconds),
armed uses the newest loaded candle time — a marker time that is not on the series
MUST be dropped, never fabricated. Missing `last_fired_at` on an armed rule MUST
NOT produce a fired marker. Armed rules sharing a level MUST collapse to ONE marker
per distinct level carrying its count (`A 100×3`). Marker colors MUST resolve the
shell tokens at render time (`--alert-armed` armed, `--dn` fired) with the pure
core's literals as a fallback, and a theme flip MUST repaint them.

#### Scenario: Markers on build

- GIVEN a user with 1 fired and 2 armed rules on `(BTCUSDT, 1h)`
- WHEN the chart builds
- THEN 3 markers render, the fired one at its `last_fired_at` and the armed ones at the newest candle time

#### Scenario: Switch clears and refetches

- GIVEN rendered markers on `(BTCUSDT, 1h)`
- WHEN the interval switches to `5m`
- THEN the previous markers are cleared, one GET for `(BTCUSDT, 5m)` is issued, and only its markers render

#### Scenario: Markers are not color-only

- GIVEN an armed and a fired marker
- WHEN the marker payload is inspected
- THEN each has a distinct `shape`, a distinct `text` ("A"/"F"), and a distinct `position`

#### Scenario: Off-series anchor is dropped

- GIVEN a fired rule whose `last_fired_at` is not a loaded candle time (or is non-finite)
- WHEN the marker list is computed
- THEN that rule produces no marker (never a synthetic data point, #68), and its fired state stays visible on `/signals/`

#### Scenario: Same-level armed rules collapse

- GIVEN three armed rules at the same level
- WHEN the marker list is computed
- THEN one marker is emitted for that level with the text `A <level>×3`

#### Scenario: Theme flip repaints

- GIVEN rendered markers under one theme
- WHEN the theme flips
- THEN the marker set is re-rendered with the new theme's `--alert-armed`/`--dn` colors

#### Scenario: Candle close re-anchors

- GIVEN armed markers on the newest candle
- WHEN a candle closes and a new one becomes newest
- THEN the armed markers re-anchor to the new candle time without a refetch

### Requirement: R5 — Frozen constraints

The capability MUST NOT add a `window.marketChart` key (8 frozen), a `STORE_KEYS`
entry (11 frozen), or a bus event; MUST leave `controllers/smc.js` byte-untouched;
MUST reuse the existing `chart:built`/`history:loaded`/`candle:closed` events; and
MUST write candles only through the existing host path (#68). All mapping must live
in pure cores (`alert-markers-core`, `alert-condition-core`, `alert-ui-core`) with
element/marker adapters (`alert-bell-view`, `alert-markers-view`) and one leaf
controller (`controllers/alerts`), every module ≤300 lines.

#### Scenario: Envelope unchanged

- GIVEN a booted chart with alerts active
- WHEN `window.marketChart` keys and `STORE_KEYS` are inspected
- THEN both counts are unchanged (8 and 11) and `smc.js` is byte-identical

#### Scenario: No new bus event

- GIVEN the alert layer attached
- WHEN `EVENTS` is inspected
- THEN it carries no `alert:*` member and `controllers/alerts.js` emits nothing
