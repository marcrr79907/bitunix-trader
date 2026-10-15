# Delta for chart-config

Issue #147 (DEBT-6, W3/W4) — **clarifying delta only**: records the accept-and-ignore
contract that `parse_layout_indicators` already implements. No production behavior
change, no new 400, no `quotes.py` edit.

## MODIFIED Requirements

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
