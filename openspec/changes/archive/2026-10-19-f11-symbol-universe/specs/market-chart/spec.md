# Delta for market-chart

Issue #124 (F11): the chart's pair navigation is a static server-rendered
`<nav class="pairs">` over `config.SYMBOLS` (`chart.html:14-18`), wired by
`controllers/toolbar.js:29-33`. This ADDS R19 (symbol search + watchlist UI) and
R20 (selector and inventory compatibility). R1–R18 stay in force: the ESM layer
rules, the frozen store vocabulary, the 8-key `window.marketChart` seam, the
single-write-path rule (#68), the boot/switch ordering and the CSP contract are
unchanged.

## ADDED Requirements

### Requirement: R19 — Symbol search and watchlist affordance

The chart page MUST offer a search over the exchange-wide catalog
(`symbol-catalog` R3) and a per-user watchlist affordance
(`market-watchlist` R14.8–R14.10).

The search MUST be driven by a pure, framework-free, DOM-free core
`symbol-search-core.js` exporting `filterSymbols(query, symbols, limit)`:
case-insensitive; empty/whitespace query returns all symbols (capped); otherwise
results are ranked **exact match → prefix match → substring match**, then
alphabetically within a tier; the returned length MUST NEVER exceed `limit`
(default 50); a non-matching query MUST return an empty array; the function MUST
NOT throw for any input (non-array, null, non-string query).

The picker MUST live in a NEW leaf controller
`controllers/symbol-picker.js` (factory `create({store, bus, config})`, imports
host/store/bus/cores but NEVER `main`). Selecting a result MUST emit the EXISTING
`config:changed` bus command (`{symbol, interval}`) — no new bus event, no new
store key, no new write path. Follow/unfollow MUST call the watchlist API and
reflect the new state without a page reload.

The picker MUST be an accessible combobox: the input carries `role="combobox"`,
`aria-expanded`, `aria-controls`, `aria-autocomplete="list"` and
`aria-activedescendant`; results render in a `role="listbox"` with one
`role="option"` per result; `ArrowDown`/`ArrowUp` move the active option
(wrapping), `Enter` selects it, `Escape` closes the listbox and clears the active
option. Focus MUST stay in the input (combobox pattern, not roving tabindex). A
result-count change MUST be announced through a polite live region.

#### Scenario: Prefix outranks substring

- GIVEN a catalog containing `BTCUSDT`, `WBTCUSDT` and `ETHUSDT`
- WHEN `filterSymbols("btc", symbols, 50)` runs
- THEN `BTCUSDT` precedes `WBTCUSDT` and `ETHUSDT` is absent

#### Scenario: Empty query returns a capped list

- GIVEN a catalog of 300 symbols
- WHEN `filterSymbols("", symbols, 50)` runs
- THEN exactly 50 symbols are returned

#### Scenario: Case and malformed input never throw

- GIVEN `filterSymbols("BtC", symbols, 50)` and `filterSymbols(null, null, 50)`
- WHEN called
- THEN the first matches case-insensitively and the second returns an array (no throw)

#### Scenario: No match is empty

- GIVEN a catalog without `ZZZ`
- WHEN `filterSymbols("zzz", symbols, 50)` runs
- THEN the result is `[]`

#### Scenario: Selecting a result switches the chart

- GIVEN the picker is open with `DOGEUSDT` in the results
- WHEN the user presses `Enter` on it
- THEN one `config:changed` command with `{symbol: "DOGEUSDT", interval: <current>}` is emitted

#### Scenario: Follow persists without a reload

- GIVEN `DOGEUSDT` is not in the caller's watchlist
- WHEN the user follows it from a result row
- THEN one `POST /market/api/watchlist` is issued and the row reflects the followed state

#### Scenario: Keyboard-only operation

- GIVEN focus in the picker input
- WHEN `ArrowDown`, `ArrowDown`, `Enter` are pressed
- THEN the second result is selected and the listbox closes

### Requirement: R20 — Selector and inventory compatibility

The watchlist section MUST keep rendering symbol buttons carrying
`class="pair"` and `data-symbol="<SYMBOL>"`, and MUST remain inside an element
with `class="pairs"`. `controllers/toolbar.js` MUST NOT be rewritten for this
change: its `.pair` delegation (`toolbar.js:29-33`) and the three existing E2E
selectors (`test_market_e2e.py:1908, :2007, :2176`) MUST keep working unchanged.

The new modules MUST be registered in the serving allowlists
(`views.MODULE_ALLOWLIST` gains `symbol-search-core`;
`views.CONTROLLER_ALLOWLIST` gains `symbol-picker`) and documented in
`docs/architecture/chart-modules.md`. No module MAY exceed the ~300-line ceiling.
`window.marketChart` MUST keep exactly its 8 keys and `STORE_KEYS` its 11 entries.
No inline `<script>` or inline event handler MAY be added, and the market CSP
MUST be unchanged.

#### Scenario: Pair selectors survive

- GIVEN the rendered market page
- WHEN the watchlist markup is inspected
- THEN `.pairs .pair[data-symbol]` still matches one element per listed symbol

#### Scenario: Toolbar delegation is untouched

- GIVEN `controllers/toolbar.js`
- WHEN the change is applied
- THEN its `.pair` click delegation and byte content are unchanged

#### Scenario: New modules are served and allowlisted

- GIVEN `GET /market/symbol-search-core.js` and `GET /market/controllers/symbol-picker.js`
- WHEN fetched
- THEN both are 200 `text/javascript` and both names appear in their allowlists

#### Scenario: Frozen seams hold

- GIVEN the browser build
- WHEN `window.marketChart` and the store vocabulary are inspected
- THEN they carry exactly 8 and 11 keys respectively

#### Scenario: CSP unchanged

- GIVEN the rendered market page
- WHEN the response header and templates are inspected
- THEN `Content-Security-Policy` equals the prior value and no inline handler exists

#### Scenario: Ceiling holds

- GIVEN every module under `web/market/templates/market/`
- WHEN `tests/web/test_module_size_guard.py` runs
- THEN no module exceeds 300 lines and the allowlist stays empty
