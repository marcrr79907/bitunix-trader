# Delta for alert-rules

D2 consumes the D1 `on_fired(rule, detail)` sink (R8) to deliver Telegram
messages and adds a per-user destination field. Evaluation semantics (R1–R7,
R9) are unchanged.

## ADDED Requirements

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

## MODIFIED Requirements

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

### Requirement: R9 — Read-only, no order

The system MUST NOT place, modify, or cancel orders, and this change MUST add no
execution path, no exchange-client import in the engine or sink, and no new
dependency. Rules MUST evaluate market data only; the sink MUST send messages only.

#### Scenario: Order scanner stays clean

- GIVEN the new sink and worker step
- WHEN the R11 order-surface scanner runs
- THEN no order-execution surface is reported
