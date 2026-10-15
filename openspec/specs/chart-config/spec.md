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
`{token, params, style}`, `params` an object defaulting empty and `style` an
optional object) and `updated_at` (`auto_now`). `style`, when present, MUST be the
frozen shape `{color, lineWidth, precision}` with all three keys optional. No
owner-less rows MAY exist. The migration MUST be additive (no new model field, no
migration). (Previously: `indicators` entries carried only `{token, params}`.)

#### Scenario: Distinct intervals coexist

- GIVEN a layout for A `(BTCUSDT, 1m)`
- WHEN a row for A `(BTCUSDT, 1h)` is saved
- THEN both rows coexist

#### Scenario: Duplicate key rejected

- GIVEN a layout for `(A, BTCUSDT, 1m)`
- WHEN a second `(A, BTCUSDT, 1m)` is inserted
- THEN `IntegrityError` is raised

#### Scenario: JSON round-trip preserves style

- GIVEN `indicators=[{"token":"sma","params":{"sma_len":50},"style":{"color":"#ff0000","lineWidth":2,"precision":4}}]`
- WHEN saved and re-read
- THEN the nested list, params, and style are equal

#### Scenario: Additive migration

- GIVEN the change
- WHEN `makemigrations --check` runs
- THEN it passes (no pending model drift)

### Requirement: R2 — Layout API

`GET /market/api/layout?symbol=&interval=` MUST be login-required (anonymous →
302) and return the caller's layout for that key, or 200 with the DEFAULT set
when none exists (never 404). `PUT /market/api/layout` MUST be login-required and
CSRF-protected, and upsert the caller's layout for the payload's key (one row).
Every read/write MUST route through `ChartLayout.for_user(request.user)`.
Indicator `token`s MUST be validated against `quotes.REGISTRY`; an unknown token
or bad param → 400 before any write. `quotes.parse_layout_indicators` MUST
preserve and validate an optional `style`: unknown style keys, a non-`#rrggbb`
color, or out-of-range ints MUST raise `ValueError` → 400 before any write, and
a valid style MUST be stored verbatim (no defaults injected).
(Previously: the parser rebuilt each entry as `{"token", ["params"]}` and silently dropped any `style`.)

**Accept-and-ignore contract (clarifying note; W3/W4).** The parser validates
`params` keys against the **global** int/float param sets, not a token-scoped set.
Therefore an accepted `token` MAY carry a **cross-token param key** the token's
builder never reads (e.g. `{"token":"ema","params":{"sma_len":9}}`) and it MUST be
stored verbatim — no 400, the extra key is ignored at render time. A **legacy
token** still present in the server `REGISTRY` for kline back-compat
(`sma20`/`ema20`/`rsi14`) MUST also be accepted and stored verbatim; the JS adapter
knows only `sma`/`ema`/`rsi`, so it renders **degraded** — candles still render,
no indicator series (never blank). An **unknown param key** (outside the global
sets) MUST still raise `ValueError` → 400. Both tolerances are reachable only via a
hand-crafted `PUT` or a pre-A2 stored layout; no UI path emits either shape.

#### Scenario: GET with no layout returns default

- GIVEN A has no layout
- WHEN GET `?symbol=BTCUSDT&interval=1m`
- THEN 200 with the DEFAULT set and `exists:false`

#### Scenario: GET after PUT returns saved set

- GIVEN A PUT a layout with style
- WHEN GET the same symbol and interval
- THEN 200 with the saved set including style and `exists:true`

#### Scenario: PUT upserts one row

- GIVEN A PUTs twice for the same key
- WHEN rows are counted
- THEN exactly one row holds the latest indicators

#### Scenario: Invalid token → 400

- GIVEN PUT `indicators=[{"token":"notreal"}]`
- WHEN handled
- THEN 400 `{"error":"..."}` and no row is written

#### Scenario: Invalid style → 400 before write

- GIVEN PUT `indicators=[{"token":"sma","style":{"lineWidth":9}}]`
- WHEN handled
- THEN 400 `{"error":"..."}` and no row is written

#### Scenario: Unauthenticated → redirect

- GIVEN an anonymous session
- WHEN GET or PUT `/market/api/layout`
- THEN 302 to login

#### Scenario: Parser is the sole drop point

- GIVEN a PUT entry carrying `style`
- WHEN `parse_layout_indicators` runs
- THEN the returned entry retains the validated `style` (not dropped)

#### Scenario: Cross-token param key accepted and stored verbatim

- GIVEN PUT `indicators=[{"token":"ema","params":{"sma_len":9}}]`
- WHEN `parse_layout_indicators` runs
- THEN it succeeds (no 400) and the entry is stored with `sma_len` verbatim
- AND the `ema` builder reads `ema_len` only, ignoring the extra key

#### Scenario: Legacy token accepted, renders degraded

- GIVEN PUT `indicators=[{"token":"sma20"}]`
- WHEN `parse_layout_indicators` runs
- THEN it succeeds (no 400) and `sma20` is stored verbatim
- AND the JS adapter matches no toggle, so candles render with no indicator series

#### Scenario: Unknown param key still → 400

- GIVEN PUT `indicators=[{"token":"ema","params":{"bogus_key":1}}]`
- WHEN handled
- THEN 400 `{"error":"..."}` and no row is written

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

Toggling an indicator, editing its parameters, or confirming a style MUST
debounce-save via `PUT`. The payload MUST carry the current `symbol` and
`interval` so a racing symbol switch cannot mis-save, and each entry MUST carry
its `style` when one is set. A failed save MUST be non-fatal to the in-session
chart.
(Previously: only toggles/params triggered the save; no style was emitted.)

#### Scenario: Toggle triggers debounced PUT

- GIVEN an active chart
- WHEN an indicator toggle changes
- THEN one `PUT /market/api/layout` is observed after the debounce

#### Scenario: Payload pins the active chart

- GIVEN a pending debounced save
- WHEN `switchTo` changes the symbol first
- THEN the payload's symbol/interval are those captured at change time

#### Scenario: Style is included in the payload

- GIVEN an active style for `sma`
- WHEN a save fires
- THEN the PUT body's `sma` entry contains its `style`
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

### Requirement: R8 — User-global interval preference model

`ChartPreference` MUST inherit `UserOwnedModel` (owner FK `on_delete=CASCADE` +
`for_user`), with a `OneToOneField` to the user (exactly one row per user), a
`last_interval` `CharField(max_length=8)` validated against `quotes.INTERVALS`, a
`scale_mode` `CharField(max_length=16, default="linear")` validated against
`SCALE_MODES`, and a `chart_type` `CharField(max_length=16, default="candles")`
validated against `CHART_TYPES`. It MUST NOT reuse or overload `ChartLayout` (a
preference is user-global, not per-chart). The migration `0010` MUST be additive
(`makemigrations --check` green).
(Previously: the model carried only `last_interval`, migration `0009`.)

#### Scenario: One row per user

- GIVEN A saved a preference
- WHEN A saves again
- THEN exactly one row holds the latest values

#### Scenario: Additive migration 0010

- GIVEN the change
- WHEN `makemigrations --check` runs
- THEN it passes and `0010` adds only the two columns with defaults

#### Scenario: Field round-trip

- GIVEN `last_interval="4h"`, `scale_mode="log"`, `chart_type="area"`
- WHEN saved and re-read
- THEN each value equals its saved value and no owner-less row exists

### Requirement: R9 — Preference API

`GET /market/api/preference` MUST be login-required (anonymous → 302) and return
the caller's preference as `{interval, scale_mode, chart_type, exists}`, or
`{interval:"1m", scale_mode:"linear", chart_type:"candles", exists:false}` when
none exists (never 404). `PUT /market/api/preference` MUST be login-required and
CSRF-protected and MUST accept a PARTIAL body: only the keys present are applied.
Each present field MUST be validated before any write — `interval` against
`quotes.INTERVALS`, `scale_mode` against `SCALE_MODES`, `chart_type` against
`CHART_TYPES` (invalid → 400 with no row touched, one 400 per bad field). The PUT
MUST upsert through `ChartPreference.for_user(request.user)`, apply only the
supplied fields, and return the saved preference. The route MUST stay registered
in `market/urls.py` without altering existing routes.
(Previously: the body required `interval` and wrote only `last_interval`.)

#### Scenario: GET default when no preference

- GIVEN A has no preference
- WHEN GET `/market/api/preference`
- THEN 200 `{interval:"1m", scale_mode:"linear", chart_type:"candles", exists:false}` (no 404)

#### Scenario: Partial PUT applies only present keys

- GIVEN A has `{interval:"1h", scale_mode:"log", chart_type:"area"}`
- WHEN PUT `{chart_type:"line"}`
- THEN 200 and the row is `{interval:"1h", scale_mode:"log", chart_type:"line"}`

#### Scenario: Invalid scale_mode → 400

- GIVEN PUT `{scale_mode:"bogus"}`
- WHEN handled
- THEN 400 `{"error":"..."}` and no row is written

#### Scenario: Invalid chart_type → 400

- GIVEN PUT `{chart_type:"notreal"}`
- WHEN handled
- THEN 400 `{"error":"..."}` and no row is written

#### Scenario: Invalid interval → 400

- GIVEN PUT `{interval:"7m"}`
- WHEN handled
- THEN 400 `{"error":"..."}` and no row is written

#### Scenario: Unauthenticated → redirect

- GIVEN an anonymous session
- WHEN GET or PUT `/market/api/preference`
- THEN 302 to login

### Requirement: R10 — Boot restore and save on change

Boot MUST asynchronously fetch the preference BEFORE `start()` and apply the
saved interval as the initial chart interval; a failed or empty fetch MUST fall
back to `"1m"` and MUST NOT block boot (the `gen` guard stays intact). An
interval change (chip or select) MUST debounce-PUT the preference, mirroring
`saveLayout`; a failed save MUST be non-fatal to the in-session chart.

#### Scenario: Persisted interval restores on reload

- GIVEN A previously saved `last_interval="1h"`
- WHEN the page reloads on `/market/`
- THEN the initial chart interval is `1h` and the active chip reflects it

#### Scenario: Fetch failure defaults to 1m

- GIVEN the preference fetch fails at boot
- WHEN the page boots
- THEN the chart renders with interval `1m` (never blank) and boot is not blocked

#### Scenario: Change persists

- GIVEN an active chart on `1m`
- WHEN the interval changes to `5m`
- THEN one debounced `PUT /market/api/preference` with `{interval:"5m"}` is observed

### Requirement: R11 — Per-user isolation (R14) and CSP

Both GET and PUT MUST route through `ChartPreference.for_user(request.user)`
(A ≠ B isolation); request path code MUST NOT use unscoped queries. No inline
`<script>`/handler MAY be added; the market CSP and `requirements.txt` MUST be
unchanged.

#### Scenario: B never sees A's preference

- GIVEN A saved `last_interval="4h"`
- WHEN B GETs the preference
- THEN B receives `{interval:"1m", exists:false}`

#### Scenario: B's PUT does not touch A's row

- GIVEN A's preference
- WHEN B PUTs a preference
- THEN B gets its own row and A's row is unchanged

#### Scenario: CSP unchanged

- GIVEN the rendered market page
- WHEN the header is inspected
- THEN the CSP equals the prior value and no inline script exists

### Requirement: R12 — Preference isolation and CSP for the new fields

Both new fields (`scale_mode`, `chart_type`) MUST route through
`ChartPreference.for_user(request.user)` (A ≠ B isolation); request path code MUST
NOT use unscoped queries. No inline `<script>`/handler MAY be added; the market CSP
and `requirements.txt` MUST be unchanged.

#### Scenario: B never sees A's scale/type

- GIVEN A saved `scale_mode="percentage"` and `chart_type="heikin-ashi"`
- WHEN B GETs the preference
- THEN B receives `linear`/`candles` with `exists:false`

#### Scenario: B's PUT does not touch A's row

- GIVEN A's preference
- WHEN B PUTs `{scale_mode:"log"}`
- THEN B gets its own row and A's row is unchanged

#### Scenario: CSP unchanged

- GIVEN the rendered market page
- WHEN the header is inspected
- THEN the CSP equals the prior value and no inline script exists
