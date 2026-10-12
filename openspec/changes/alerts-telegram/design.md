# Design: alerts-telegram (Fase D2, issue #77)

## Technical Approach

Additive consumers of frozen seams: (1) rewrite module-level `on_fired(rule,
detail)` in `web/worker.py` to format + send via `src.alerts.send_telegram`
(D1's `run_alert_rules`/`run_once`/`detail` untouched); (2) `AlertRule.telegram_chat_id`
nullable + additive migration `0008`; (3) `/signals/` server-rendered view pairing
each user's rule pairs with single-sourced `get_smc_payload` setups; (4) `AlertRule`
CRUD via ModelForm. No order path, no new dep, CSP untouched.

    run_alert_rules ─(fire: last_fired_at stamped first)─→ on_fired(rule, detail)
        → send_telegram(text, chat_id=rule.chat or env)      (try/except → log)
    /signals/ ─→ for_user ─→ get_smc_payload/pair ─→ setups + state
    CRUD ─→ AlertRuleForm.clean_condition ─→ parse_condition ─→ for_user write

## Architecture Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D1 | Sink seam | Rewrite `on_fired` body (not `run_once`) | Lowest diff; D1 tests stay green |
| D2 | Chat resolution | `rule.telegram_chat_id or config.TELEGRAM_CHAT_ID` | Per-rule override + operator fallback (R8.2) |
| D3 | Message | `detail`-only, no SMC recompute | Worker has no chain; R8 forbids entry/SL/TP |
| D4 | Semantics | At-most-once (D1 stamps before sink); no retry | Frozen D1 order |
| D5 | Field | `CharField(max_length=64, blank=True, default="")` | Additive; no unique, `for_user` unchanged |
| D6 | Screen source | Reuse `get_smc_payload`; pairs = `for_user` | Single-source SMC; bounds compute (S2/S3) |
| D7 | CRUD shape | Server-rendered `ModelForm` (not JSON+JS) | CSP-safe; mirrors `invite_create` |
| D8 | Condition validation | `clean_condition` → `parse_condition` | Engine owns schema; map `ValueError`→error |

## Interfaces / Contracts (FROZEN)

```python
# web/worker.py — module-level default sink; self-guarded
def on_fired(rule, detail: dict) -> None:
    # lazy `from src.alerts import send_telegram`
    # chat = rule.telegram_chat_id or config.TELEGRAM_CHAT_ID
    # send_telegram(text, chat_id=chat) in try/except Exception -> logger.warning
```

Frozen message (one per fire): `"🚨 Alert {symbol} {interval}\nCondition:
{json.dumps(condition, sort_keys=True, separators=(',',':'))}\nBar:
{datetime.fromtimestamp(edge_time, tz=UTC).isoformat()}"`.

`/signals/` context: `{"groups": [{"symbol","interval","setups":[...],"state": str}]}`.

`AlertRuleForm` (`web/trading/forms.py`, NEW): ModelForm fields symbol, interval,
condition(JSON), telegram_chat_id, is_active; `clean_condition` returns
`parse_condition(...)`; `clean()` bounds symbol ∈ `SYMBOLS`, interval ∈ `CANDLE_INTERVALS`.

State rule: `fired` if any matching rule `last_fired_at is not None`; else `armed`
if any `is_active`; else `inactive` if a rule exists; else `none`. View MUST NOT
write `last_fired_at` or call `send_telegram` (S4). Each pair calls
`get_smc_payload(BitunixClient(), symbol, interval, 200)` once; upstream errors
degrade to empty setups, never 500. CRUD views `rules`/`rule_create`/`rule_edit`/
`rule_toggle`/`rule_delete`: all `@login_required`, every queryset
`AlertRule.for_user(request.user)`; miss or other-user pk → 404; create sets `user=request.user`.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `web/worker.py` | Modify | `on_fired` → Telegram sink |
| `web/trading/models.py` | Modify | `+ telegram_chat_id` |
| `web/trading/migrations/0008_alertrule_telegram.py` | Create | additive `AddField` |
| `web/trading/forms.py` | Create | `AlertRuleForm` |
| `web/trading/{views,urls}.py` | Modify | rules CRUD + routes |
| `web/trading/templates/trading/rules.html` | Create | CRUD/list UI |
| `web/market/{views,urls}.py` | Modify | `signals_page` + route |
| `web/market/templates/market/signals.html` | Create | screen |
| `web/accounts/templates/registration/{base.html,theme.css}` | Modify | nav + styles |
| `tests/web/{test_worker_alerts,test_signals,test_alert_rule_crud,test_telegram_boundary}.py` | Modify/Create | batteries + scanner |

## Testing Strategy

| Layer | Approach |
|-------|----------|
| Unit | extend `test_worker_alerts.py`: format, chat fallback, `send_telegram` `False`/raises → logged, at-most-once |
| View | new `test_signals.py`: anon→302, per-user pairs, setups == payload, states, no send/write |
| Form/View | new `test_alert_rule_crud.py`: validation, bounds, A≠B→404, CRUD |
| Boundary | new `test_telegram_boundary.py`: no `src.alerts` under `REQUEST_PATH` |

`strict_tdd: true`; patch 100%; `ruff` clean.

## Guard / Edge Matrix

| Guard / Edge | Handling |
|--------------|----------|
| Telegram token | `src.alerts` imported only in `web/worker.py`; scanner enforces |
| R14 `for_user` | every CRUD query scoped; no `AlertRule.objects` in request path |
| Telegram isolation | `send_telegram` returns `False`; sink `try/except` (R7) |
| At-most-once | D1 stamp-before-send preserved; sink adds no dedup |
| Single-source setups | `get_smc_payload` only; view never recomputes SMC |
| CSP / no new dep / `src/` | plain HTML, no inline script; `PURE_MODULES` untouched |
| Read-only | no order/execution/`client` in sink or CRUD |

## Migration / Rollout

Additive `0008` (nullable/blank, no backfill, no constraint); inert until the sink runs.

## Delivery — Chained 3 slices (Feature Branch Chain, base = tracker)

`400-line budget risk: High` (~850 lines). `Decision needed before apply: Yes` ·
`Chained PRs recommended: Yes`.

| Slice | Content | ~Lines | Depends on | Rollback boundary |
|-------|---------|--------|-----------|-------------------|
| 1 — Telegram delivery | `on_fired` rewrite + `telegram_chat_id` + `0008` + sink tests + scanner | ~210 | — | revert `on_fired` + drop migration |
| 2 — `/signals/` screen | view + template + tokens + nav + `test_signals.py` | ~260 | frozen `get_smc_payload` | delete view/template/route/nav |
| 3 — CRUD | `forms.py` + views + template + routes + tests | ~380 | slice 1 field + `parse_condition` | delete form/views/template/routes |

Slice 2 is independent of 1 & 3 (reads rule state, not the sink). Each child PR
targets the previous slice; rebase if a child diff shows prior slices.

## Open Questions

None blocking. Q-CHAT/Q-MSG/Q-ROUTE/Q-SCOPE/Q-UI/Q-RETRY/Q-ONE locked by the specs.
