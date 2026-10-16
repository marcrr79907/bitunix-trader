# chart-indicator-add Specification

## Purpose

Restores the lost ability to ADD an indicator (issue #176, F5 slice S5). The
pre-F5 checkbox `fieldset` (`chart.html:46-68`) let a user tick any token; the
Object Tree replaced it active-only (sibling `chart-object-tree` R1: "the
registry's inactive tokens MUST NOT be listed"). This capability is the
counterpart ADD control — TradingView-style — that lists the REGISTRY's INACTIVE
tokens, leaving the tree itself active-only. It does NOT contradict R1: the tree
lists membership; the add affordance lists registry-minus-membership. Adding is
a legitimate REBUILD (`indicator:changed` → `setData` path, #68), DISTINCT from
`hide` (`indicator:visibility`, option-only). No new bus event, no new store key,
no new dependency, `src/` untouched. New capability — no prior spec.

## Requirements

### Requirement: R1 — Add affordance lists registry-minus-active

The Indicators group of the Object Tree MUST expose a native `<button
type="button">` add control (accessible name, e.g. "Add indicator") that is
keyboard-operable (focusable + Enter/Space activation). When activated it MUST
list ONLY the REGISTRY tokens NOT present in `state.indicators` (the active
membership). No candidate MAY duplicate an active token. The affordance and its
items MUST live in `controllers/object-tree.js` (or a small leaf helper) and MUST
NOT import `main`.

#### Scenario: Lists only inactive tokens

- GIVEN a layout with active `{sma, ema, rsi}` and a 9-token REGISTRY
- WHEN the add affordance is activated
- THEN it lists exactly `bollinger, vwap, macd, stochastic, atr, volume` (no active token)

#### Scenario: Keyboard-operable

- GIVEN focus on the add button
- WHEN `Enter` (or `Space`) is pressed
- THEN the inactive list opens; each item is reachable and activatable by keyboard

### Requirement: R2 — Add action rebuilds and persists membership

Choosing an inactive token MUST append it: `store.set({indicators:[...active,
token]})`, then `bus.emit("indicator:changed")` (the rebuild/`setData` path,
permitted here), then persist membership via the existing debounced
`saveLayout` PUT (`indicators.js:141-160`). After the rebuild the added token
MUST render as its registry pane/overlay series (`chart-registry-core.js`,
`REGISTRY[token].place`/`series`) and its history MUST be refetched with it
(the exact positive refetch assertion #177 flagged as lost).

#### Scenario: Adding a pane indicator renders and refetches

- GIVEN active `{sma, ema, rsi}` (no `macd`)
- WHEN `macd` is added
- THEN `indicators` becomes `[sma, ema, rsi, macd]`, `indicator:changed` is emitted exactly once, a MACD pane series is created, and history is refetched including the new series

#### Scenario: Adding an overlay indicator renders

- GIVEN active `{sma, ema, rsi}` (no `vwap`)
- WHEN `vwap` is added
- THEN a `vwap` overlay series renders and a debounced partial `PUT` is observed persisting the new membership

### Requirement: R3 — add-vs-hide boundary (#68)

`add` and `hide` MUST coexist as DISTINCT paths: adding uses the rebuild/`setData`
path (`indicator:changed` → main `rebuild`, `main.js:185`); hiding uses the
option-only path (`indicator:visibility` → `host.setSeriesVisible`,
`main.js:200-204`) with no rebuild or refetch. Adding a token and hiding an
already-active token MUST be independently reachable and MUST NOT be conflated.

#### Scenario: Add rebuilds while hide stays option-only

- GIVEN an active indicator and an inactive one
- WHEN the inactive token is added, and separately an active token's eye is hidden
- THEN the add triggers `indicator:changed`/`setData`; the hide triggers only `indicator:visibility`/`applyOptions` with no `setData`

### Requirement: R4 — No new bus event

Adding MUST reuse the existing `indicator:changed` event. `EVENTS` MUST NOT gain
any key beyond the existing set plus the F5 `indicator:visibility` and
`scale:changed` (`chart-bus.js:8-20`) — no add-specific event MAY be introduced.

#### Scenario: Event vocabulary unchanged

- GIVEN the shipped `chart-bus.js`
- WHEN `EVENTS` is inspected
- THEN it contains exactly its existing keys plus `indicatorVisibility`; no `indicator:add` key exists

### Requirement: R5 — Invariants (seam, size, CSP, deps)

`window.marketChart` MUST stay exactly 8 keys (`main.js:51-60`); `STORE_KEYS`
MUST stay 11 (`chart-store.js:13-27`, no new key). The add code MUST keep every
module ≤300 lines (empty allowlist, `test_module_size_guard.py`). No inline
`<script>`/handler MAY be added (icons are JS-built SVG strings,
`tool-icons-core.js`); CSP and `requirements.txt` MUST be unchanged; `src/` MUST
be untouched.

#### Scenario: Seam and store frozen

- GIVEN the delivered change
- WHEN the contract checks run
- THEN `window.marketChart` has exactly 8 keys and `STORE_KEYS.length === 11`

#### Scenario: Size and CSP

- GIVEN the delivered `object-tree.js`
- WHEN the size guard and CSP check run
- THEN it is ≤300 lines, no inline script/handler exists, and CSP equals the prior value

### Requirement: R6 — Empty state when all tokens active

When every REGISTRY token is already active, the add affordance MUST show no
candidate items and MUST present a defined disabled/empty state (button
`aria-disabled="true"` / disabled, or an explicit empty message) — it MUST NOT
offer a duplicate.

#### Scenario: All active disables the add

- GIVEN all 9 registry tokens are active
- WHEN the add affordance is activated
- THEN no candidate item is listed and the control reports `aria-disabled="true"` (or shows an empty-state message)

### Requirement: R7 — Persistence round-trip

A reload with the added token present in the saved layout MUST show it active in
the Object Tree and rendered as its pane/overlay series. The layout entry carries
the added token (and its optional `style`/`visible`) exactly as the existing
`buildIndicators` payload shape emits (`indicators.js:60-68`).

#### Scenario: Reload restores the added indicator

- GIVEN a `macd` added and the debounced `PUT` completed
- WHEN the page reloads for the same `(symbol, interval)`
- THEN the tree lists `macd` as active and a MACD pane series renders
