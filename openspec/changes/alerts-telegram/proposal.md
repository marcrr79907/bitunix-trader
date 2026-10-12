# Proposal: alerts-telegram (Fase D2, issue #77)

## Intent

D2 is the **delivery + surface** half of the alert feature. It consumes D1's
`on_fired(rule, detail)` seam to send a Telegram message (trusted zone only),
adds a server-rendered `/signals/` screen pairing global SMC setups with each
user's `AlertRule` state, and adds a per-user `AlertRule` config UI. All three
pieces are additive and reuse proven seams. The system still **never orders**.

## Why Now

D1 froze the `on_fired` sink, `src/alerts.send_telegram`, `get_smc_payload`, and
the `for_user` contract. D2 is the named next D change and closes the alert
loop; delaying it leaves fired rules silent and unroutable per user.

## Scope

### In Scope
- Worker sink: rewrite module-level `on_fired` to format + send via
  `send_telegram`, self-guarded (`try/except`) so a send can never break the loop.
- Per-user destination: nullable `AlertRule.telegram_chat_id` (additive
  migration), env `TELEGRAM_CHAT_ID` fallback; rides the existing CRUD form.
- `/signals/` screen in `market/urls.py`: server-rendered table, pairs = the
  user's own `AlertRule` pairs, setups single-sourced from `get_smc_payload`,
  alert state from `last_fired_at`; no JS, no pagination.
- `AlertRule` CRUD: server-rendered `AlertRuleForm`, `for_user` everywhere,
  condition validated via `parse_condition`.

### Out of Scope
- **Email / push channels** and any non-Telegram transport (future).
- **Order automation — forbidden, ever.**
- General alert-history/events table (D1 `last_fired_at` is the only state).
- Retry / at-least-once delivery (v1 is at-most-once).
- New runtime deps, npm/build, CSP relaxation, `src/smc/` or chart-JS changes.

## Capabilities

### New Capabilities
- `alerts-telegram`: Telegram delivery sink, per-user chat destination, `/signals/`
  screen, and `AlertRule` config UI.

### Modified Capabilities
- `alert-rules`: R8 `on_fired` stub → Telegram delivery; `AlertRule` gains
  `telegram_chat_id`.
- `market-chart`: new `/signals/` GET route (read-only screen).
- `security-invariants`: Telegram token confined to the worker (no request-path
  import of `src.alerts`).

## Approach

- **Seam**: rewrite the module-level `on_fired` body (not `run_once`) — lowest
  diff; all D1 tests stay green.
- **Chat id (Q-CHAT)**: nullable `AlertRule.telegram_chat_id` + env fallback
  (additive migration `0008`).
- **Message (Q-MSG)**: `detail`-only — name symbol/interval/edge bar/condition;
  no worker-side SMC recompute.
- **Screen**: `/signals/` server-rendered, pairs bounded to the user's rules,
  setups from the frozen `get_smc_payload`; state active/armed/fired/inactive.
- **CRUD**: `AlertRuleForm` (server-rendered, not JSON+JS), validated via
  `parse_condition`; `interval ∈ CANDLE_INTERVALS`, `symbol ∈ SYMBOLS`.
- **Retry (Q-RETRY)**: none in v1; stamp-before-send = at-most-once (documented).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/worker.py` | Modified | `on_fired` → Telegram sink |
| `web/trading/models.py` | Modified | `+telegram_chat_id` |
| `web/trading/migrations/0008_alertrule_telegram.py` | New | additive |
| `web/trading/forms.py` | New | `AlertRuleForm` |
| `web/trading/views.py`, `urls.py` | Modified | rules CRUD |
| `web/trading/templates/trading/rules.html` | New | CRUD UI |
| `web/market/views.py`, `urls.py` | Modified | `signals_page` |
| `web/market/templates/market/signals.html` | New | screen |
| `web/accounts/templates/registration/theme.css`, `base.html` | Modified | styles + nav |
| `tests/web/test_worker_telegram.py`, `test_signals.py`, `test_alert_rule_crud.py`, `test_isolation.py` | New/Modified | batteries |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Telegram token leaks into request path | Med | `src.alerts` worker-only; test asserts no import under the request-path apps |
| R14 CRUD scoping miss | Med | all access via `for_user`; A≠B tests; guard stays green |
| Telegram failure breaks eval loop | Med | `send_telegram` returns `False`; sink self-guards (R7) |
| At-most-once drops a failed send | Low | documented; keep D1 ordering (no reorder) |
| Screen SMC compute cost | Med | bounded to user pairs + fixed `limit`; DB-first window |
| Sender untestable (network) | Med | stub `send_telegram` / inject sink (D1 `Recorder`) |
| Patch 100% coverage | Med | per-view batteries incl. fallback + error branches |

## Rollback Plan

Pure additive; revert in reverse: restore the `on_fired` stub; delete the
`/signals/` view + template + route + nav link; delete the CRUD form/views/
template/routes; delete `migrations/0008` (and migration row) + revert the
`telegram_chat_id` field. Safe because nothing writes to an order path.

## Read-Only Boundary

The system MUST NOT place, modify, or cancel orders. D2 adds no execution path,
no exchange-client import, no new dependency; the sink sends messages only.
R11 scanner stays clean; CSP is untouched (`/signals/` and CRUD are plain
server-rendered HTML, no inline script).

## Dependencies

- D1 `on_fired` fired seam (frozen).
- C1 `market.quotes.get_smc_payload` (frozen) — sole SMC source.
- `src/alerts.send_telegram` and `src/alert_rules.parse_condition` (existing).

## Delivery (Chained PRs — Feature Branch Chain)

Base = `feat/alerts-telegram` tracker; each child targets the previous slice.
`400-line budget risk: High` (~850 lines). 3 slices:

1. **Slice 1 — Telegram delivery** (~210): `on_fired` rewrite + `telegram_chat_id`
   + migration. Rollback = revert sink + drop migration.
2. **Slice 2 — `/signals/` screen** (~260): view + template + tokens + nav.
   Independent of slices 1 & 3.
3. **Slice 3 — AlertRule CRUD** (~380): form + views + template + routes.

- Decision needed before apply: Yes · Chained PRs recommended: Yes · budget risk: High

## Success Criteria

- [ ] `on_fired` sends via `send_telegram`; a send failure is logged and the loop
      continues; blank `telegram_chat_id` falls back to env.
- [ ] No request-path module imports `src.alerts` or references the token.
- [ ] `/signals/` renders setups from `get_smc_payload` + per-user alert state;
      anonymous → 302; no JS; CSP unchanged.
- [ ] CRUD scoped via `for_user` (A≠B → 404); invalid condition → form error.
- [ ] At-most-once documented (stamp-before-send, no retry).
- [ ] No new dependency; `pytest` green; patch 100%; `ruff` clean.
