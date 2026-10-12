# Delta for security-invariants

D2 adds a Telegram delivery channel. This delta adds one scanner-testable
invariant confining the Telegram transport to the worker trust zone. R11–R14 are
unchanged and MUST be preserved.

## ADDED Requirements

### Requirement: R15 — Telegram secret confined to the worker

`src.alerts` (and therefore the Telegram token/chat secret) MUST be imported and
called ONLY from the worker trust zone (`web/worker.py` and the `src/monitor.py`
CLI). Request-serving code under `web/trading/`, `web/market/`, and `web/`
(top-level request modules) MUST NOT import `src.alerts`, reference
`send_telegram`, or read `TELEGRAM_TOKEN`/`TELEGRAM_CHAT_ID`. A scanner MUST flag
any such occurrence as an offender and MUST NOT flag `web/worker.py`.

#### Scenario: Request path is clean

- GIVEN `web/trading/`, `web/market/`, and top-level `web/` request modules
- WHEN scanned for `src.alerts`, `send_telegram`, or the Telegram token
- THEN no offender is reported

#### Scenario: Worker is allowed

- GIVEN `web/worker.py` importing and calling `src.alerts.send_telegram`
- WHEN the scanner runs
- THEN it is not reported as an offender

#### Scenario: Scanner catches a leak (negative control)

- GIVEN a fixture under the request path calling `src.alerts.send_telegram`
- WHEN the scanner runs
- THEN the fixture is reported as an offender

### Requirement: R16 — Telegram delivery adds no execution surface

The Telegram sink and the `/signals/` screen and the `AlertRule` config UI MUST
NOT place, modify, or cancel orders and MUST NOT add an execution path, an
exchange-client import, or a new runtime dependency. The system remains read-only.

#### Scenario: Order scanner stays clean

- GIVEN the D2 sink, screen, and CRUD code
- WHEN the R11 order-surface scanner runs
- THEN no order-execution surface is reported

#### Scenario: No new runtime dependency

- GIVEN the D2 change
- WHEN the dependency guard runs
- THEN `requirements.txt` is unchanged and the guard passes on the current tree
