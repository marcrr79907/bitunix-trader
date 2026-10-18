# chart-alerts Specification

## Purpose

Alert affordances on the `/market/` chart (issue #123, F10): a bell pinned to the
crosshair that creates or edits a `price` `AlertRule` in place, and armed/fired
markers on the candle series for the caller's rules on the active
`(symbol, interval)`. This capability is the UI over the frozen `alert-rules`
engine (`src/alert_rules.py`) and the new JSON transport (`alert-rules` R10/R11);
it never evaluates conditions or places orders. New capability — no prior spec.

Vocabulary comes from the frozen S4 precedence (`web/market/views.py:104-116`):
`fired` (any `last_fired_at`) > `armed` (any `is_active`) > `inactive` (rules
exist, none active) > `none`.

## Requirements

### Requirement: R1 — Bell at the crosshair

The chart MUST render a bell as a real `<button type="button">` inside `#chart`,
positioned at the crosshair point's price. It MUST be hidden when the crosshair
has no point, MUST carry an accessible name that includes the seeded price, and
MUST be reachable by keyboard with a visible focus state. It MUST NOT be created
with an inline handler (CSP, `design-system` R7).

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

### Requirement: R2 — Condition dialog

Activating the bell MUST open a native `<dialog id="alert-dialog">` seeded with a
price-only condition: `op` ∈ `{"above","below"}` (`_OPS`, `src/alert_rules.py:27`),
`level` a numeric value > 0 seeded from the crosshair price, default `op` derived
from the last close (`above` when the level is above it, else `below`). Apply MUST
persist through the JSON API — POST when no `price` rule for the same pair is
within a small price epsilon of the level, PUT when one is. Cancel and `Escape`
MUST write nothing and MUST return focus to `#chart`. The dialog copy MUST NOT
promise a "cross": the engine fires on the closed-bar edge.

#### Scenario: Create from the bell

- GIVEN the crosshair at 100 and no nearby price rule
- WHEN the dialog is applied with `op=above, level=100`
- THEN one POST to `/market/api/alerts` carries `{type:"price",op:"above",level:100}` and a confirmation is announced

#### Scenario: Edit a nearby rule

- GIVEN an existing `price` rule whose level is within epsilon of the seeded price
- WHEN the dialog is applied
- THEN a PUT to `/market/api/alerts/<id>` is issued and no second rule is created

#### Scenario: Cancel writes nothing

- GIVEN the dialog open with edited fields
- WHEN Cancel or `Escape` is used
- THEN no request is issued, the rule list is unchanged, and focus returns to `#chart`

#### Scenario: Invalid level is rejected client-side

- GIVEN a level input that is empty, non-numeric, or ≤ 0
- WHEN Apply is pressed
- THEN no request is issued and the field shows an error (mirrors `parse_condition`'s `_parse_price`)

### Requirement: R3 — Interval eligibility

A rule is interval-scoped and the worker skips intervals outside
`CANDLE_INTERVALS` (`web/trading/candles.py:19-30`, `web/worker.py:167-168`). On an
active interval outside `CANDLE_INTERVALS` (`1m`, `3d`, `6h`, `8h`, `12h`) the bell
MUST be disabled and MUST expose an accessible reason via `aria-describedby`. The
JSON API MUST reject such a create with 400.

#### Scenario: Bell disabled on 1m

- GIVEN the active interval is `1m`
- WHEN the page renders
- THEN the bell is disabled and `aria-describedby` points at a reason naming the interval as non-evaluable

#### Scenario: API rejects a non-evaluable interval

- GIVEN a POST with `interval="1m"`
- WHEN the request is handled
- THEN it returns 400 and no rule is created (`alert-rules` R10)

#### Scenario: Enabled on an evaluable interval

- GIVEN the active interval is `1h`
- WHEN the chart renders
- THEN the bell is enabled

### Requirement: R4 — Armed and fired markers

Markers MUST render for the caller's rules on the active `(symbol, interval)` only,
via `createSeriesMarkers` on the candle series, owned by a separate handle from the
SMC primitive (`controllers/smc.js:235`). They MUST be (re)built on `chart:built`
and on every symbol/interval switch, and cleared before a switch. Armed and fired
MUST differ by `shape` AND `text` (not color alone). Anchors: fired uses
`last_fired_at` (epoch seconds), armed uses the newest loaded candle time — a
marker time that is not on the series MUST be dropped. Missing `last_fired_at` on
an armed rule MUST NOT produce a fired marker.

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
- THEN each has a distinct `shape` and a distinct `text` ("A"/"F")

#### Scenario: Off-series anchor is dropped

- GIVEN a fired rule whose `last_fired_at` is not a loaded candle time
- WHEN the marker list is computed
- THEN that rule produces no marker (never a synthetic data point, #68)

### Requirement: R5 — Frozen constraints

The capability MUST NOT add a `window.marketChart` key (8 frozen), a `STORE_KEYS`
entry (11 frozen), or a bus event; MUST leave `controllers/smc.js` byte-untouched;
and MUST write candles only through the existing host path (#68).

#### Scenario: Envelope unchanged

- GIVEN a booted chart with alerts active
- WHEN `window.marketChart` keys and `STORE_KEYS` are inspected
- THEN both counts are unchanged (8 and 11) and `smc.js` is byte-identical
