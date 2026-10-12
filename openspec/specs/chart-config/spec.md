# chart-config Specification

## Purpose

Per-user persisted chart layout (issue #71, Fase A2): the indicator set and its
parameters are saved server-side and restored when the chart opens, so a user's
`/market/` view survives reloads and symbol switches. New capability — no prior
spec. Unique key `(user, symbol, interval)` (TradingView-style: one layout per
chart). Default set `[{token:"sma"},{token:"ema"},{token:"rsi"}]` (lengths 20).

## Requirements

### Requirement: R1 — Per-user layout persistence

`ChartLayout` MUST inherit `UserOwnedModel` (owner FK `on_delete=CASCADE` +
`for_user`) and persist one layout per `(user, symbol, interval)` via a
`UniqueConstraint`. It MUST carry `indicators` as a `JSONField` (list of
`{token, params}`, `params` an object defaulting empty) and `updated_at`
(`auto_now`). No owner-less rows MAY exist. The migration MUST be additive.

#### Scenario: Distinct intervals coexist

- GIVEN a layout for A `(BTCUSDT, 1m)`
- WHEN a row for A `(BTCUSDT, 1h)` is saved
- THEN both rows coexist

#### Scenario: Duplicate key rejected

- GIVEN a layout for `(A, BTCUSDT, 1m)`
- WHEN a second `(A, BTCUSDT, 1m)` is inserted
- THEN `IntegrityError` is raised

#### Scenario: JSON round-trip

- GIVEN `indicators=[{"token":"macd","params":{"macd_fast":12}}]`
- WHEN saved and re-read
- THEN the nested list and params are equal

### Requirement: R2 — Layout API

`GET /market/api/layout?symbol=&interval=` MUST be login-required (anonymous →
302) and return the caller's layout for that key, or 200 with the DEFAULT set
when none exists (never 404). `PUT /market/api/layout` MUST be login-required and
CSRF-protected, and upsert the caller's layout for the payload's key (one row).
Every read/write MUST route through `ChartLayout.for_user(request.user)`.
Indicator `token`s MUST be validated against `quotes.REGISTRY`; an unknown token
or bad param → 400 before any write.

#### Scenario: GET with no layout returns default

- GIVEN A has no layout
- WHEN GET `?symbol=BTCUSDT&interval=1m`
- THEN 200 with the DEFAULT set and `exists:false`

#### Scenario: GET after PUT returns saved set

- GIVEN A PUT a layout
- WHEN GET the same symbol and interval
- THEN 200 with the saved set and `exists:true`

#### Scenario: PUT upserts one row

- GIVEN A PUTs twice for the same key
- WHEN rows are counted
- THEN exactly one row holds the latest indicators

#### Scenario: Invalid token → 400

- GIVEN PUT `indicators=[{"token":"notreal"}]`
- WHEN handled
- THEN 400 `{"error":"..."}` and no row is written

#### Scenario: Unauthenticated → redirect

- GIVEN an anonymous session
- WHEN GET or PUT `/market/api/layout`
- THEN 302 to login

### Requirement: R3 — Per-user isolation (R14)

User B MUST NOT read or write A's layout (`A ≠ B`). The guard's `OWNED_MODELS`
set MUST include `ChartLayout`; request paths MUST NOT use unscoped queries on it.

#### Scenario: B cannot read A's layout

- GIVEN A's layout
- WHEN `for_user(B).get(pk=A.pk)` runs
- THEN `DoesNotExist`

#### Scenario: B's GET never leaks A's layout

- GIVEN A saved a non-default layout
- WHEN B GETs the same key
- THEN B receives the default set

#### Scenario: B's PUT does not touch A's row

- GIVEN A's layout
- WHEN B PUTs the same key
- THEN B gets its own row; A's row is unchanged

#### Scenario: Guard covers the new model

- GIVEN a fixture calling `ChartLayout.objects.all()`
- WHEN the guard scans it
- THEN `ChartLayout` is in `OWNED_MODELS` and the offender is reported

### Requirement: R4 — Restore on boot

The chart MUST restore the saved layout on open: asynchronously fetch the layout →
sync the toggle panel and parameter inputs → build the chart → connect the stream
→ fetch history. A failed fetch MUST fall back to the DOM defaults (never blank).
`switchTo(symbol, interval)` MUST load that chart's layout before history.

#### Scenario: Reload restores saved toggles

- GIVEN a saved layout with a non-default indicator active
- WHEN the page reloads
- THEN the panel reflects the saved toggles and the chart renders those series

#### Scenario: Fetch failure falls back

- GIVEN the layout fetch fails
- WHEN the page boots
- THEN the chart renders with the default DOM selection

#### Scenario: Switch loads target layout

- GIVEN charts with different layouts per key
- WHEN `switchTo` changes symbol or interval
- THEN that layout is applied before history loads

### Requirement: R5 — Save on change

Toggling an indicator or editing its parameters MUST debounce-save via `PUT`. The
payload MUST carry the current `symbol` and `interval` so a racing symbol switch
cannot mis-save. A failed save MUST be non-fatal to the in-session chart.

#### Scenario: Toggle triggers debounced PUT

- GIVEN an active chart
- WHEN an indicator toggle changes
- THEN one `PUT /market/api/layout` is observed after the debounce

#### Scenario: Payload pins the active chart

- GIVEN a pending debounced save
- WHEN `switchTo` changes the symbol first
- THEN the payload's symbol/interval are those captured at change time

### Requirement: R6 — Parameter editing and token vocabulary

SMA and EMA toggles MUST use the server's param-driven tokens `sma`/`ema` so their
lengths (`sma_len`/`ema_len`) are editable. Default length 20 MUST render
identically to the former `sma20`/`ema20`.

#### Scenario: Length edit takes effect

- GIVEN the SMA toggle on with `sma_len=50`
- WHEN history loads
- THEN the `sma` overlay uses a 50-period window

#### Scenario: Default matches prior rendering

- GIVEN default `sma_len=20`/`ema_len=20`
- WHEN history loads
- THEN the `sma`/`ema` overlays equal the former `sma20`/`ema20` values

### Requirement: R7 — CSP, design system, no new dependency

No inline `<script>` or event handler MAY be added; layout fetch/save MUST use
same-origin JS with the page CSRF token. The panel MUST inherit the design-system
shell/tokens. No npm/build MAY be added; `requirements.txt` MUST be unchanged and
`src/` MUST stay framework-free.

#### Scenario: CSP unchanged

- GIVEN the rendered market page
- WHEN the header is inspected
- THEN `Content-Security-Policy` equals the prior value (no `unsafe-inline`)

#### Scenario: No inline handler or new dependency

- GIVEN the templates and manifest
- WHEN scanned
- THEN no inline handler/`<script>` exists and no runtime dependency was added
