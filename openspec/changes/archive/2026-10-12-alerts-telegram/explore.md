# Exploration: alerts-telegram (issue #77, Fase D2)

## Executive Summary

D2 is the **delivery + surface** half of the alert feature: it consumes the D1
`on_fired(rule, detail)` seam in `web/worker.py` to send a Telegram message
(trusted zone only), adds a `/signals/` screen that pairs the global SMC setups
(single-sourced from `get_smc_payload`) with each user's `AlertRule` state, and
adds a per-user config UI for `AlertRule` (create / edit / activate).

All three pieces are **additive** and reuse proven seams: the D1 sink, the C1
SMC chain, the `UserOwnedModel.for_user` contract, the `market/` same-origin
routes, and `src/alerts.send_telegram` (already framework-free). No new runtime
dependency, no migration beyond one nullable field for a per-user chat id
(proposal), no order path, CSP unchanged.

D2 is **well past the 400-line review budget** (delivery sink + a screen view +
template + CSS + a full CRUD form + three test batteries). Recommend a **3-slice
chained PR**.

---

## 1. D1 seam (how D2 plugs in)

### 1.1 Exact definitions (verified)

`web/worker.py`:

```python
ALERT_CANDLE_WINDOW = 100

def on_fired(rule, detail: dict) -> None:
    """D1 sink stub: log only. D2 re-binds this module seam (R8)."""
    logger.info("alert fired rule=%s user=%s symbol=%s", rule.pk, rule.user_id, rule.symbol)

def run_alert_rules(on_fired_sink=None) -> int:
    sink = on_fired_sink or on_fired          # line 136
    rules = list(AlertRule.objects.filter(is_active=True))   # unscoped (R14.4)
    ...
    rule.last_fired_at = datetime.fromtimestamp(edge_time, tz=UTC)
    rule.save(update_fields=["last_fired_at"])   # 158 — BEFORE the sink
    sink(rule, {
        "symbol": rule.symbol,
        "interval": rule.interval,
        "edge_time": edge_time,          # int, UNIX seconds of the fired BAR
        "condition": rule.condition,     # the raw condition dict
    })                                     # 159–167, INSIDE the per-rule try
    fired += 1
```

`run_once` calls `run_alert_rules()` **with no argument** (line 70), inside a
broad `except Exception` (lines 69–75). So the deployed path always uses the
**module-level `on_fired`**.

### 1.2 `detail` shape (frozen by `tests/web/test_worker_alerts.py`)

```python
{"symbol": str, "interval": str, "edge_time": int, "condition": dict}
```

No setup entry/SL/TP/R:R is carried — `detail` is derived from the rule, not
from the SMC chain. A Telegram message built from `detail` can name symbol /
interval / edge bar / condition; it CANNOT state entry/SL/TP without
recomputing the chain (see Q-MSG).

### 1.3 Dedup semantics (D2 MUST NOT double-send)

- `last_fired_at` stores the **fired bar's open time** (UTC).
- Fire is suppressed when `last_fired_at is not None and
  int(last_fired_at.timestamp()) >= edge_time`.
- The `alert_rules.edge_fired` engine is itself stateless (`now and not prev`
  over the last two closed bars), so re-running the same cycle is idempotent.
- **Consequence for D2**: the sink is invoked at most once per bar per rule.
  D2 must NOT add its own dedup — and must NOT send from anywhere except the
  sink (e.g. not from the `/signals/` view).

### 1.4 Where D2 plugs (recommended)

The lowest-diff, spec-blessed route is to **rewrite the module-level `on_fired`**
body to format and send the Telegram message. `run_alert_rules`'s signature,
`run_once`, and every existing D1 test stay untouched (`test_default_sink_handles_a_fire`
keeps exercising the default path). An alternative is to add a named
`telegram_sink(rule, detail)` and pass it from `run_once`; that touches `run_once`
and adds a function D1 tests do not know. **Recommend: rewrite `on_fired`.**

**Ordering gotcha (important)**: `last_fired_at` is saved **before** `sink(...)`,
and `sink` runs inside the per-rule `try/except`. If the sink raises, the rule is
already marked fired (no retry) and the count is not incremented. `send_telegram`
already swallows `RequestException` and returns `False`, so a Telegram outage
does **not** raise — but the sink SHOULD still be self-guarding (`try/except`
around the send) so delivery can never break the evaluation loop (R7 isolation).

---

## 2. `src/alerts.py` — `send_telegram` (read fully)

```python
def send_telegram(text, token=None, chat_id=None) -> bool:
    token = token or config.TELEGRAM_TOKEN        # env, src/config.py:51
    chat_id = chat_id or config.TELEGRAM_CHAT_ID   # env, src/config.py:52
    if not (token and chat_id):
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text}, timeout=10)
        return r.ok
    except requests.RequestException as e:
        console.print(...); return False
```

Verified properties:

- **Framework-free**: imports `requests`, `rich.console`, `src.config` only — no
  Django. `src/` stays importable without Django (core-domain-boundary).
- **Explicit-args override**: `token`/`chat_id` args win; else env; else `False`.
- **Never raises** on transport failure (catches `RequestException`, returns
  `False`). Returns `r.ok` on success.
- **Current callers**: `src/monitor.py` (CLI `dispatch`) and indirectly
  `check_market`/`check_positions`. NOT imported by any request-path module — so
  importing it from `web/worker.py` does not leak the token into a scanned path.

**D2 call site** (worker-side sink):

```python
def on_fired(rule, detail: dict) -> None:
    from src.alerts import send_telegram   # lazy: keep import graph clean
    text = _format(rule, detail)
    chat = rule.telegram_chat_id or config.TELEGRAM_CHAT_ID
    try:
        send_telegram(text, chat_id=chat)
    except Exception as exc:   # ponytail: sink must never break the loop (R7)
        logger.warning("telegram send failed rule=%s: %s", rule.pk, exc)
```

`TELEGRAM_TOKEN` is read from env by `send_telegram` at call time; it MUST NOT
reach the request path. `config.TELEGRAM_CHAT_ID` is the **global fallback**
(the CLI monitor today sends one chat for the operator); the issue's R14
per-user intent needs a per-user destination (see §2.1).

### 2.1 Per-user chat id — recommendation

Today chat is a single **global env** value. R14 wants per-user isolation, so a
per-user chat id is the honest answer. Options:

| Option | Mechanism | Pros | Cons |
|--------|-----------|------|------|
| **A. Field on `AlertRule`** | add nullable `telegram_chat_id = CharField(blank=True)` | No new model; owned via `AlertRule.for_user`; one additive migration; per-rule granularity (a user may route different alerts to different chats) | Duplicated across a user's rules; the same user must set it per rule |
| **B. Field on `accounts.User`** | add `telegram_chat_id` to the custom `User` | One place per user; the config UI can live in a profile page | Modifies `accounts` (auth app) and its migration; a "profile" concept the product does not yet have |
| **C. Global env only** | keep `TELEGRAM_CHAT_ID` | Zero schema, zero UI | Every user's alerts go to ONE chat — violates R14 isolation; unusable multi-user |

**Recommend A**: the smallest per-user, owned, additive change. The CRUD form
(§4) already edits an `AlertRule`, so the chat id rides along with no new page.
Fallback to `config.TELEGRAM_CHAT_ID` when blank keeps the single-operator case
working. (Lock in design; tracked as Q-CHAT.)

---

## 3. `/signals/` screen

### 3.1 Placement

Issue offers "`/signals/` (or a section in market)". **Recommend a new route in
`market/urls.py`** (`path("signals/", views.signals_page, name="signals_page")`)
rendered by a `market/signals.html` template extending `registration/base.html`.
Rationale: it is SMC/market-derived data and lives beside the chart that already
owns the SMC chain; no new app, no new `config/urls.py` include. The
`topbar` nav gains a **Signals** link.

### 3.2 How it computes "active setups" (single-source)

Reuse the C1 seam exactly: `market.quotes.get_smc_payload(client, symbol,
interval, limit)` returns `{swings, structure, order_blocks, fvgs, range,
setups}` with **server-resolved `time`**; `setups[]` already carries
`{direction, time, entry, stop, take_profit, rr, score}`. The view therefore:

1. Determines the `(symbol, interval)` pairs to show — **bounded to the user's
   own `AlertRule` pairs** (`AlertRule.for_user(user)`), because that is the set
   the user cares about AND it bounds the compute (§7). (Open Q-SCOPE: also
   include `Watchlist` symbols × a default interval.)
2. For each pair, call `get_smc_payload` ONCE and take `payload["setups"]`.
3. Attach the user's `AlertRule` rows for that pair → an alert-state label.

`src/smc/signals.py` (`find_setups`) stays the sole home of setup math; the view
NEVER recomputes SMC. This preserves "the browser never recomputes" and matches
`api_smc`'s payload shape.

### 3.3 What "setups + alert state" means

- **Setup row** (global market data): direction, entry, stop, take_profit, rr,
  score, bar `time` — straight from `get_smc_payload`.
- **Alert state** (per user, from `AlertRule` + `last_fired_at`):
  - `inactive` — a matching rule exists but `is_active=False`;
  - `fired` — `last_fired_at` is set (and recent / equals the latest setup bar);
  - `armed` / `active` — an active rule exists but has not fired on the current
    bar.
- A pair with a setup but **no rule** shows the setup with a "no alert" state
  and a link to the config UI.

### 3.4 Render

Server-rendered Django table (positions.html is the precedent) using the design
tokens in `registration/theme.css` (`.panel`, `.num`, `--up`/`--dn`). **No JS
required** — the page is a GET snapshot, so it introduces no inline script and
does not touch CSP (market-chart R6/R12 stay green). Impeccable-audited via the
Playwright DOM/computed-style detector.

---

## 4. `AlertRule` config UI (CRUD, per user)

### 4.1 Pattern choice

Two precedents exist: `market/api_layout` / `api_drawings` (same-origin JSON +
CSRF + JS), and plain Django form views (`accounts/invite_create`). A
server-rendered **ModelForm view** is the lazy, CSP-safe choice for CRUD — no
hand-written JS, standard CSRF, `@login_required`. Recommend: a new
`web/trading/forms.py` (`AlertRuleForm`) + function views in `trading/views.py`
(`rules`, `rule_create`, `rule_edit`, `rule_toggle`/`rule_delete`) + routes in
`trading/urls.py` + a `trading/rules.html` template.

### 4.2 `for_user` scoping (R14)

Every read/write routes through `AlertRule.for_user(request.user)` — list,
edit, delete. A miss (including another user's pk) → 404, never leak existence.
`AlertRule` is already in `OWNED_MODELS` and `REQUEST_PATH` includes `web/trading`,
so an accidental unscoped query fails `test_owned_model_guard.py`. The create
path passes `user=request.user` explicitly (`for_user` filters, it does not
inject the owner — same A2 gotcha noted in `_post_drawing`).

### 4.3 Condition validation (reuse `parse_condition`)

`src/alert_rules.py::parse_condition(condition)` is the only function that raises
(`ValueError`) on a structural breach and returns the normalized dict. The form
MUST build the `condition` dict from structured fields and validate it via
`parse_condition` in `clean()` (write-time validation, mapped to a form error).
The three schemas:

| type | required | notes |
|------|----------|-------|
| `price` | `op` (above/below), `level` (number) | latest close |
| `indicator` | `name` ∈ {rsi,sma,ema,atr,vwap}, `op`, `level`, optional `params` | scalar only; tuple indicators rejected |
| `smc_setup` | `direction` (long/short/any), `min_score` (int, default `MIN_CONFLUENCE`) | latest bar |

UI shape (open Q-UI): a **structured form** (type select + per-type widgets)
gives a clean Impeccable audit; a **raw JSON textarea** validated by
`parse_condition` is smaller but poor UX. Recommend structured widgets for the
three types, falling back to `parse_condition` for the authoritative check.

`interval` MUST be constrained to `CANDLE_INTERVALS` (`5m,15m,1h,2h,4h,1d,1w,1M`
— note `1m` is NOT persisted and can never fire) and `symbol` to `config.SYMBOLS`.

---

## 5. Worker Telegram wiring (summary of the change)

- Rewrite module-level `on_fired(rule, detail)` → format message → call
  `src.alerts.send_telegram(text, chat_id=...)`, wrapped in `try/except` so a
  send failure is logged and the loop continues (R7 isolation).
- Token/chat read only inside the worker (`send_telegram` reads env); no
  request-path module imports `src.alerts`.
- Failure isolation: `send_telegram` returns `False` (never raises) on transport
  error; the sink guard covers any other exception.
- Testability: inject a stub sender (`monkeypatch.setattr(src.alerts,
  "send_telegram", recorder)`) or inject a `Recorder` sink through
  `run_alert_rules(on_fired_sink=...)` — the D1 tests already prove this seam.
- **At-most-once**: because `last_fired_at` is stamped before the send, a failed
  send is NOT retried on the next cycle. Acceptable for v1; document it. (Q-RETRY
  if retries are wanted — would need reordering, a D1-owned decision.)

---

## 6. Open questions / decisions to lock

| # | Question | Recommendation |
|---|----------|----------------|
| Q-CHAT | Chat-id source: env global, per-`AlertRule` field, or `User` field? | **Per-`AlertRule` nullable field** + env fallback (§2.1) |
| Q-MSG | Message content: `detail` only, or recompute entry/SL/TP? | **`detail` only** — no chain recompute in the worker (YAGNI); name symbol/interval/edge/condition |
| Q-ONE | One message per fire per rule? | **Yes** — one `sendMessage` per sink call |
| Q-ROUTE | `/signals/` vs `/market/signals/`? | **`/signals/`** in `market/urls.py` (top-level, mirrors `/positions/`, `/journal/`) |
| Q-SCOPE | Which pairs does the screen scan? | **User's `AlertRule` pairs only** (bounds compute); optionally + watchlist symbols |
| Q-INACT | Show inactive rules' state too? | **Yes** — needed for "disparada/activa" contrast; a cheap list read |
| Q-WINDOW | Pagination/window for setups? | **No pagination**; cap pairs and use a fixed `limit` (e.g. 200, the `api_smc` default) |
| Q-UI | Config UI: full CRUD or minimal (create + activate)? | **Create + edit + delete + toggle** (a ModelForm gives all four cheaply); structured condition widgets |
| Q-RETRY | Retry a failed Telegram send? | **No** for v1 (at-most-once); document. Add later if needed |
| Q-SCREENCOMPUTE | Call upstream in the screen, or DB-only? | **Reuse `get_smc_payload`** (single source); accept degraded/DB-first behavior, bounded pair set |

---

## 7. Risks

- **Secret leak in the request path**: `TELEGRAM_TOKEN` MUST stay worker-only.
  *Mitigation*: `src.alerts` is imported solely by `worker.py` (and the CLI
  `monitor.py`); the credential/order scanners do not see `worker.py`. A test
  SHOULD assert no `src.alerts` / token reference under `web/trading`,
  `web/market`, `web/accounts`, `web/config`.
- **R14 isolation for the CRUD**: an unscoped `AlertRule.objects.*` in the new
  form/views fails `test_owned_model_guard.py`. *Mitigation*: route everything
  through `for_user`; add A≠B tests mirroring `test_isolation.py`.
- **Telegram failure isolation**: a send error must not break the evaluation
  loop (R7). *Mitigation*: `send_telegram` returns `False` on transport error;
  wrap the sink call in `try/except`.
- **At-most-once semantics**: stamp-before-send means a failed send is lost.
  *Mitigation*: document; keep D1 ordering.
- **Screen SMC compute cost**: N pairs × full chain per page load. *Mitigation*:
  bound to the user's rule pairs and a fixed `limit`; reuse the DB-first
  `_fetch_window` so repeated loads hit the DB, not upstream.
- **Testability of the sender**: network in tests. *Mitigation*: stub
  `send_telegram` / inject a sink; mirror `test_worker_alerts.py`'s `Recorder`.
- **Patch 100% coverage**: every branch — price/indicator/smc_setup form
  validation, invalid condition → form error, anonymous → 302, A≠B on
  list/edit/delete, fired vs armed state, sink send success/failure, blank chat
  fallback. *Mitigation*: per-view batteries mirroring `test_market_api.py` +
  `test_isolation.py`.

---

## 8. Proposed PR shape + size (honest estimate)

| Slice | Contents | Impl | Tests | Total |
|-------|----------|------|-------|-------|
| 1 — Telegram delivery | `web/worker.py` `on_fired` rewrite; `AlertRule.telegram_chat_id` field + migration; `config` fallback | ~60 | ~150 | ~210 |
| 2 — `/signals/` screen | `market/views.py` `signals_page`, `market/urls.py` route, `market/signals.html`, `theme.css` rows, `topbar` link | ~120 | ~140 | ~260 |
| 3 — AlertRule CRUD | `trading/forms.py`, `trading/views.py` (rules/create/edit/delete/toggle), `trading/urls.py`, `trading/rules.html` | ~180 | ~200 | ~380 |
| **Total** | | **~360** | **~490** | **~850** |

**~850 changed lines — well past the 400-line review budget. `400-line budget
risk: High`.** D2 is three independent deliverables (delivery sink, screen,
config UI), each with its own test battery.

### Recommended: CHAINED PRs (3 slices, Feature Branch Chain)

Base = a `feat/alerts-telegram` tracker branch; each child targets the previous.

1. **Slice 1 — Telegram delivery** (`~210`): the worker sink rewrite + the
   per-rule chat-id field/migration. Autonomous; rollback = revert `on_fired` +
   drop migration.
2. **Slice 2 — `/signals/` screen** (`~260`): view + template + tokens + nav.
   Depends only on the frozen C1 SMC payload; independent of slices 1 & 3
   (the screen reads `AlertRule` state, not the sink).
3. **Slice 3 — AlertRule CRUD** (`~380`): form + views + template + routes.
   Consumes the slice-1 field (edits the chat id) and the `parse_condition`
   validator.

A 2-slice alternative (delivery+CRUD | screen) puts ~590 lines in one PR — worse.
**Recommend the 3-slice chain.**

### Out of scope (fence)

- Email / push channels (future) — Telegram only.
- Order automation — forbidden, ever.
- A general-purpose alert-history/event table — YAGNI (D1's `last_fired_at` is
  the only state).
- New runtime dependencies, npm/build, CSP relaxation.

---

## Affected Areas

- **EDIT**: `web/worker.py` — rewrite `on_fired` into the Telegram sink.
- **EDIT**: `web/trading/models.py` — `AlertRule.telegram_chat_id` (nullable);
  **NEW** migration `web/trading/migrations/0008_alertrule_telegram.py`.
- **NEW**: `web/trading/forms.py` — `AlertRuleForm` (validates via
  `parse_condition`).
- **EDIT**: `web/trading/views.py`, `web/trading/urls.py` — CRUD views/routes.
- **NEW**: `web/trading/templates/trading/rules.html`.
- **EDIT**: `web/market/views.py`, `web/market/urls.py` — `signals_page`.
- **NEW**: `web/market/templates/market/signals.html`.
- **EDIT**: `web/accounts/templates/registration/theme.css` — screen table styles.
- **EDIT**: `web/accounts/templates/registration/base.html` — nav link.
- **NEW/EDIT**: tests — `tests/web/test_worker_telegram.py`,
  `tests/web/test_signals.py`, `tests/web/test_alert_rule_crud.py`,
  `tests/web/test_isolation.py` (`AlertRule` A≠B).
- **EDIT**: `src/config.py` (already has `TELEGRAM_*`) — no change expected.
- **ARCHIVE-TIME**: new `openspec/specs/alerts-telegram/spec.md` (or a delta on
  `alert-rules`); a `market-chart` delta for `/signals/`; `per-user-isolation`
  unchanged (`AlertRule` already listed).

No change to `src/smc/`, `src/indicators.py`, `src/alert_rules.py`, or the
chart JS.

## Ready for Proposal

**YES** — every piece is a direct extension of a proven seam (the D1 `on_fired`
sink, `src.alerts.send_telegram`, the C1 `get_smc_payload`, the `for_user`
contract, and the `market/`/`trading/` route+template patterns). No new runtime
dependency, no order path, additive migration. The spec MUST lock: the chat-id
source (Q-CHAT, recommend per-rule field), the message content (Q-MSG, recommend
`detail`-only), the screen route (Q-ROUTE) and scope (Q-SCOPE), the config-UI
shape (Q-UI), and the at-most-once delivery semantics (Q-RETRY).
