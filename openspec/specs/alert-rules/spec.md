# alert-rules Specification

## Purpose

Per-user, deterministic alert rules over the frozen SMC/indicator/price chain.
A pure, framework-free engine (`src/alert_rules.py`) evaluates a user `condition`
and reports the false→true **edge**; the worker records the fired bar in
`last_fired_at` and delivers a Telegram message via the `on_fired` sink. The
system evaluates, marks, and notifies — it never orders. New capability — no
prior spec.

**Frozen `AlertRule` shape** (field → role):

| Field | Role |
|-------|------|
| `user` | owner FK via `UserOwnedModel` (`CASCADE`) |
| `symbol`, `interval` | what to evaluate; `interval ∈ CANDLE_INTERVALS` |
| `condition` | JSON object (schema below) |
| `is_active` | Boolean; only active rules evaluate |
| `last_fired_at` | time of the fired **bar** (UTC); doubles as dedup key |
| `telegram_chat_id` | nullable per-rule Telegram destination; blank ⇒ `config.TELEGRAM_CHAT_ID` fallback |

No unique constraint (a collection, like `Drawing`); indexed on `(user, is_active)`.

## Requirements

### Requirement: R1 — Owned model and scoping

`AlertRule` MUST inherit `UserOwnedModel`, MUST be added to `OWNED_MODELS`, and
MUST NOT carry a unique constraint. `for_user(other).get(pk=rule.pk)` MUST raise
`DoesNotExist`. The migration MUST be additive.

#### Scenario: Cross-user read denied

- GIVEN an `AlertRule` owned by A
- WHEN `for_user(B).get(pk=rule.pk)` is called
- THEN it raises `DoesNotExist`

#### Scenario: Duplicate rules allowed

- GIVEN a user with an existing rule on `(symbol, interval)`
- WHEN a second rule with the same pair is created
- THEN it is persisted (no uniqueness violation)

### Requirement: R2 — Frozen `condition` schema

`condition` MUST be one JSON object with a discriminating `type`; exactly the
three schemas below are valid. Unknown `type`, unknown `op`, or a scalar-only
violation MUST evaluate to `False` (never raise). The schema MUST NOT change
without a new capability delta.

**`direction` is REQUIRED (clarifying note; W1).** For `smc_setup`, `direction`
MUST be present in the stored condition — there is no default. A missing or
unknown `direction` is a **configuration breach** and MUST raise `ValueError` at
parse time (`_parse_smc_setup`), NOT evaluate to `False`. This is the schema
contract; the frozen design prose that reads as if `direction` were optional with
a default is stale.

| `type` | Required keys | Constraint |
|--------|---------------|------------|
| `price` | `op` (`above\|below`), `level` (number) | strict compare on latest close |
| `indicator` | `name`, `params` (object, default `{}`), `op`, `level` | `name` scalar series only: `rsi\|sma\|ema\|atr\|vwap` |
| `smc_setup` | `direction` (`long\|short\|any`), `min_score` (int, default `MIN_CONFLUENCE`) | any matching `Setup` on latest bar |

Tuple indicators (`macd`, `bollinger`, `stochastic`) MUST be rejected as
unsupported in v1 (deferred to an additive sub-selector key).

#### Scenario: Unknown type is false

- GIVEN `condition={"type":"magic"}`
- WHEN the engine evaluates it
- THEN the result is `False` without raising

#### Scenario: Tuple indicator rejected

- GIVEN `condition={"type":"indicator","name":"macd",...}`
- WHEN the engine evaluates it
- THEN the result is `False` (no exception)

#### Scenario: Missing direction is a config breach

- GIVEN `condition={"type":"smc_setup"}` (no `direction`)
- WHEN the condition is parsed
- THEN `ValueError` is raised (never silently defaulted)

#### Scenario: Explicit direction is accepted

- GIVEN `condition={"type":"smc_setup","direction":"any"}`
- WHEN the condition is parsed
- THEN it parses and `direction` is `"any"`

### Requirement: R3 — Condition `matches` semantics

`matches(condition, ohlc, ...)` MUST return the boolean state at the latest
closed bar: `price` compares the latest close (strict) to `level`; `indicator`
computes the named scalar series and compares its latest value (strict) to
`level` (warm-up `None` ⇒ `False`); `smc_setup` runs the frozen chain and returns
`True` iff a `Setup` matches `direction` and `score >= min_score`. Short, empty,
or mismatched OHLC MUST return `False`.

#### Scenario: Price above level

- GIVEN latest close `101` and `{"type":"price","op":"above","level":100}`
- WHEN `matches` runs
- THEN it returns `True`

#### Scenario: Warm-up indicator

- GIVEN a window shorter than the indicator warm-up (latest value `None`)
- WHEN `matches` runs
- THEN it returns `False`

### Requirement: R4 — Edge detection (fire on false→true)

`evaluate(condition, ohlc, ...)` MUST compute the state at the latest closed bar
AND at the previous closed bar, and MUST return `fired = now AND NOT prev`. A
persistent `True` MUST NOT re-fire; a `False` MUST re-arm. The result MUST be
identical for identical OHLC regardless of worker cadence or restarts
(stateless — no persisted prior-state boolean).

#### Scenario: false→true fires

- GIVEN `prev=False` and `now=True`
- WHEN `evaluate` runs
- THEN `fired` is `True`

#### Scenario: true→true does not fire

- GIVEN `prev=True` and `now=True`
- WHEN `evaluate` runs
- THEN `fired` is `False`

#### Scenario: true→false does not fire

- GIVEN `prev=True` and `now=False`
- WHEN `evaluate` runs
- THEN `fired` is `False`

### Requirement: R5 — Dedup by fired bar time

On a fire the worker MUST stamp `last_fired_at` with the fired bar's open time
(UTC). A rule MUST NOT fire again for the same bar — a fire is allowed only when
the edge bar time is strictly greater than `last_fired_at`, or `last_fired_at`
is unset. Re-evaluating the same closed bar twice MUST yield at most one fire.

#### Scenario: Same bar twice — one fire

- GIVEN a rule that fired on bar `T` (so `last_fired_at == T`)
- WHEN the worker evaluates the same bar `T` again
- THEN no new fire occurs and `last_fired_at` stays `T`

#### Scenario: Restart does not re-fire

- GIVEN a persisted `last_fired_at == T` and a fresh worker process
- WHEN the worker evaluates bar `T`
- THEN no fire occurs

### Requirement: R6 — Determinism, purity, never-raise

`src/alert_rules.py` MUST be framework-free (registered in `PURE_MODULES`),
stdlib-only, and pure: same input ⇒ byte-identical `(state, fired)`. It MUST NOT
read a wall clock, use `random`, do I/O, or hold global mutable state; the only
timestamp in the system is the worker-supplied edge bar time. Short/empty/
malformed input MUST yield `False` and MUST NOT raise.

#### Scenario: Byte-identical output

- GIVEN the same OHLC window and condition
- WHEN evaluated twice
- THEN `(state, fired)` is identical

#### Scenario: Never raises on malformed input

- GIVEN an empty OHLC window
- WHEN the engine runs
- THEN it returns `False` without raising

**Edge-case matrix**

| Input / condition | Result |
|-------------------|--------|
| empty / short OHLC window | `False`, no fire |
| warm-up `None` indicator value | `False` |
| unknown `condition.type` / `op` | `False`, no raise |
| tuple indicator (`macd`/`bollinger`/`stochastic`) | `False` |
| prev `True`, now `True` | no fire |
| prev `True`, now `False` | no fire |
| prev `False`, now `True` | fire |
| same bar evaluated twice | one fire |
| restart after a fired bar | no re-fire |

### Requirement: R7 — Worker step contract

`run_once` MUST gain an isolated alert step calling `run_alert_rules()` inside a
broad `except Exception` (mirroring candles/private sync): an alert failure MUST
NOT degrade tick/private persistence or kill the loop. The step MUST read
`AlertRule.objects.filter(is_active=True)` **unscoped** in `web/worker.py`
(outside `REQUEST_PATH`, R14.4), evaluate each rule in its own `try/except` so a
failing rule is logged and skipped while peers continue, and only evaluate
intervals in `CANDLE_INTERVALS`.

#### Scenario: One bad rule does not break peers

- GIVEN two active rules where one raises during evaluation
- WHEN `run_alert_rules` runs
- THEN the failing rule is logged and the second rule is still evaluated

#### Scenario: Alert failure never kills the loop

- GIVEN `run_alert_rules` raises
- WHEN `run_once` runs
- THEN tick and private-sync persistence still complete and no exception escapes

#### Scenario: Unsupported interval skipped

- GIVEN a rule with `interval="1m"` (not in `CANDLE_INTERVALS`)
- WHEN the worker evaluates rules
- THEN that rule is skipped without error

### Requirement: R8 — `on_fired` Telegram delivery sink

A module-level `on_fired(rule, detail)` sink MUST be invoked once per fire. Its
body MUST format a **`detail`-only** message and send it via
`src.alerts.send_telegram(text, chat_id=...)`; the destination MUST be the rule's
`telegram_chat_id` or, when blank, `config.TELEGRAM_CHAT_ID`. The sink MUST be
self-guarded (`try/except`) so a delivery failure is logged and NEVER propagates
— it MUST NOT break the evaluation loop. The sink MUST NOT recompute SMC
(entry/SL/TP are out of the message), MUST NOT open an order path, and MUST NOT
add its own dedup. Delivery is **at-most-once**: the D1 stamp-before-send order
is preserved and a failed send MUST NOT be retried on the next cycle. The
Telegram token/secret MUST be read only in the worker trust zone (`src.alerts`
at call time), NEVER in the request path.

#### Scenario: Sink invoked on fire

- GIVEN a rule that fires
- WHEN the worker evaluates it
- THEN `on_fired` is called once with the rule and fire detail

#### Scenario: Message is detail-only

- GIVEN `detail = {"symbol","interval","edge_time","condition"}` and a destination
- WHEN the sink formats the message
- THEN it names symbol, interval, edge bar time, and condition, and carries no entry/SL/TP

#### Scenario: Telegram failure is isolated

- GIVEN `send_telegram` returns `False` (transport error)
- WHEN the sink runs
- THEN the failure is logged and the worker loop continues; no exception escapes

#### Scenario: Sink exception never breaks the loop

- GIVEN `send_telegram` raises an unexpected exception
- WHEN the sink runs
- THEN it is caught and logged inside `on_fired`; peers and later cycles continue

#### Scenario: At-most-once, no retry

- GIVEN a rule that fired on bar `T` and whose send failed
- WHEN the worker evaluates bar `T` again
- THEN `last_fired_at == T` and no re-send occurs

### Requirement: R8.2 — Per-user Telegram destination

`AlertRule` MUST gain a nullable `telegram_chat_id` (`CharField`, blank allowed,
nothing else changed) via an **additive** migration `0008`. It MUST be owned like
every other field (`for_user`), and MUST be the per-rule delivery destination
while blank falls back to `config.TELEGRAM_CHAT_ID`.

#### Scenario: Field is nullable and additive

- GIVEN existing `AlertRule` rows with no chat id
- WHEN migration `0008` applies
- THEN the column is added as nullable/blank without touching existing rules

#### Scenario: Blank falls back to env

- GIVEN a rule with `telegram_chat_id=""` and `TELEGRAM_CHAT_ID` set
- WHEN the sink resolves the destination
- THEN it sends to `TELEGRAM_CHAT_ID`

#### Scenario: Per-rule chat id wins

- GIVEN a rule with `telegram_chat_id="123"` and `TELEGRAM_CHAT_ID="999"`
- WHEN the sink resolves the destination
- THEN it sends to `123`

### Requirement: R9 — Read-only, no order

The system MUST NOT place, modify, or cancel orders, and this change MUST add no
execution path, no exchange-client import in the engine or sink, and no new
dependency. Rules MUST evaluate market data only; the sink MUST send messages only.

#### Scenario: Order scanner stays clean

- GIVEN the new sink and worker step
- WHEN the R11 order-surface scanner runs
- THEN no order-execution surface is reported
