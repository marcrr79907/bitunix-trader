# Tasks: alerts-telegram (issue #77, Fase D2)

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

Chain: all slices base on tracker `feat/alerts-telegram`; each later slice bases on the immediate previous slice branch; merge each to the tracker before branching the next. S1 delivery ~210 · S2 `/signals/` ~260 · S3 CRUD ~380.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~850 (worker+migration ~60, screen ~120, CRUD ~180, tests ~490) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | S1 delivery → S2 `/signals/` → S3 CRUD |
| Delivery strategy | ask-on-risk (chain pre-chosen) |
| Chain strategy | feature-branch-chain |

### Suggested Work Units

| Unit | Goal | Likely PR | Base boundary |
|------|------|-----------|---------------|
| 1 | `on_fired` sink + `telegram_chat_id` + `0008` + worker/scanner tests | PR 1 | tracker |
| 2 | `signals_page` + route + `signals.html` + theme + nav + `test_signals.py` | PR 2 | PR 1 branch |
| 3 | `AlertRuleForm` + CRUD views/routes + `rules.html` + A≠B tests | PR 3 | PR 2 branch |

## Guard/Edge Matrix

- [ ] R15/S-scanner: `src.alerts`/`send_telegram`/`TELEGRAM_TOKEN`/`TELEGRAM_CHAT_ID` ONLY under `web/worker.py`; request path (`web/{trading,market,config,...}`, top-level `web/*.py`) clean; negative control flags a fixture (S1/S3).
- [ ] R14/for_user on EVERY queryset in `trading/views.py` (`rules`/`create`/`edit`/`toggle`/`delete`) and the screen; no unscoped `AlertRule.objects` in the request path — `test_owned_model_guard.py` stays green.
- [ ] Delivery isolation: `send_telegram` returns `False` OR raises → sink catches, logs, loop continues; `on_fired` never lets an exception escape (R7).
- [ ] At-most-once: D1 stamp-before-send preserved; sink adds NO dedup and NO retry; failed send not resent on the next cycle.
- [ ] Message is `detail`-only (`symbol`,`interval`,`edge_time`,`condition`) — no entry/SL/TP, no SMC recompute in the worker.
- [ ] Chat resolution: `rule.telegram_chat_id or config.TELEGRAM_CHAT_ID`; blank → env fallback.
- [ ] Single-source setups: view calls `get_smc_payload(BitunixClient(), symbol, interval, 200)` ONCE per pair; no `find_setups`/`src.smc` call in the view; upstream error → empty setups, never 500.
- [ ] Screen state: `fired`(last_fired_at set) > `armed`(active) > `inactive`(rule exists) > `none`; view MUST NOT write `last_fired_at` or call `send_telegram`.
- [ ] CSP/no-JS: `/signals/` and `rules.html` are GET/plain HTML, no inline script/handlers, no CSP relaxation.
- [ ] Form: `clean_condition`→`parse_condition` (ValueError→form error); `symbol ∈ SYMBOLS`, `interval ∈ CANDLE_INTERVALS`; anonymous → 302.
- [ ] Read-only/no-new-dep: no order verb/path, no `client` in CRUD; `requirements.txt` unchanged; `PURE_MODULES` untouched; `ruff check`+`format --check` green; patch 100%.

## Slice 1 — Telegram delivery (base: tracker)

Dep: none (D1 `on_fired` seam frozen). Rollback: restore the `on_fired` stub; drop migration `0008` (+ migration row) and the `telegram_chat_id` field; delete `test_worker_telegram.py` + scanner additions.

- [ ] 1.1 **RED** `tests/web/test_worker_telegram.py` (`@pytest.mark.django_db`, stub `src.alerts.send_telegram`): fire sends once with `rule.telegram_chat_id`; blank → `config.TELEGRAM_CHAT_ID`; `send_telegram` returns `False` → logged, no raise, loop continues; `send_telegram` raises → caught inside `on_fired`; at-most-once (stamped bar not resent). Acceptance: fails before 1.3.
- [ ] 1.2 **RED** `tests/web/test_telegram_boundary.py`: scanner flags `src.alerts`/`send_telegram`/token under `REQUEST_PATH` (negative control fixture) and MUST NOT flag `web/worker.py`. Acceptance: fails before 1.4.
- [ ] 1.3 **GREEN** `web/worker.py`: rewrite module-level `on_fired(rule, detail)` — lazy `from src.alerts import send_telegram`; format `detail`-only message; `chat = rule.telegram_chat_id or config.TELEGRAM_CHAT_ID`; `try: send_telegram(text, chat_id=chat) except Exception: logger.warning(...)`. Acceptance: 1.1 green.
- [ ] 1.4 **GREEN** `web/trading/models.py` + `web/trading/migrations/0008_alertrule_telegram.py`: `telegram_chat_id = CharField(max_length=64, blank=True, default="")`; additive `AddField`, `dependencies 0007_alertrule`. Acceptance: `migrate` clean; 1.2 green.
- [ ] 1.5 **REFACTOR** ruff clean. Acceptance: S1 green, patch 100%.

## Slice 2 — `/signals/` screen (base: S1 branch)

Dep: frozen `market.quotes.get_smc_payload` only (no code from S1/S3). Rollback: delete `signals_page` view + `signals.html` + route + nav link + `test_signals.py`.

- [ ] 2.1 **RED** `tests/web/test_signals.py`: anonymous → 302; authed 200 HTML extending base; only caller's `for_user` `AlertRule` pairs (A≠B); no rules → 200 empty; setups == `get_smc_payload(...)["setups"]`; states `fired`/`armed`/`inactive`/`none`; no `send_telegram`/`last_fired_at` write; no pagination. Acceptance: fails before 2.3.
- [ ] 2.2 **GREEN** `web/market/urls.py`: `path("signals/", views.signals_page, name="signals_page")` (market-chart R13). Acceptance: route resolves.
- [ ] 2.3 **GREEN** `web/market/views.py::signals_page` (`@login_required`, GET-only): pairs from `AlertRule.for_user(request.user)`; per pair ONE `get_smc_payload(BitunixClient(), symbol, interval, 200)`, `except`→empty listings; attach state; context `{"groups":[{"symbol","interval","setups","state"}]}`. Acceptance: 2.1 green.
- [ ] 2.4 **GREEN** `web/market/templates/market/signals.html` (extends base, server-rendered table, `.panel`/`.num`/`--up`/`--dn`) + `web/accounts/templates/registration/theme.css` rows + `base.html` **Signals** nav link. Acceptance: 2.1 green.
- [ ] 2.5 **REFACTOR** ruff clean. Acceptance: S2 green, patch 100%.

## Slice 3 — AlertRule CRUD (base: S2 branch; final)

Dep: S1 field (`telegram_chat_id`) + `src.alert_rules.parse_condition`. Rollback: delete `forms.py`, CRUD views/routes, `rules.html`, `test_alert_rule_crud.py`.

- [ ] 3.1 **RED** `tests/web/test_alert_rule_crud.py`: anon → 302; create sets `user=request.user`; invalid condition → form error, no row; `interval="1m"`/bad symbol rejected; normalized condition persisted; edit updates; toggle flips `is_active` without send; A≠B on list/edit/toggle/delete → 404. Acceptance: fails before 3.3.
- [ ] 3.2 **RED** `tests/web/test_isolation.py`: extend `AlertRule` A≠B coverage for the CRUD surface (edit/toggle/delete scope). Acceptance: fails before 3.3.
- [ ] 3.3 **GREEN** `web/trading/forms.py`: `AlertRuleForm` (ModelForm: symbol, interval, condition, telegram_chat_id, is_active); `clean_condition`→`parse_condition` mapping `ValueError`; `clean()` bounds `SYMBOLS`/`CANDLE_INTERVALS`. Acceptance: 3.1 green.
- [ ] 3.4 **GREEN** `web/trading/views.py` + `urls.py`: `rules`/`rule_create`/`rule_edit`/`rule_toggle`/`rule_delete`, all `@login_required`, every queryset `AlertRule.for_user(request.user)`, miss/other-user → 404, create `user=request.user`; routes in `trading/urls.py`. Acceptance: 3.1/3.2 green.
- [ ] 3.5 **GREEN** `web/trading/templates/trading/rules.html`: server-rendered form + list + toggle/delete, CSRF, no inline script. Acceptance: 3.1 green.
- [ ] 3.6 **REFACTOR** ruff clean; confirm no `client`/order path; scanner still clean. Acceptance: S3 green, patch 100%.

## Phase Verification (per slice + close)

- [ ] V.1 `python -m pytest` green; `diff-cover --fail-under=100` on changed lines.
- [ ] V.2 `ruff check . && ruff format --check .` green; `requirements.txt` unchanged; `test_no_order_surface.py` clean.
- [ ] V.3 R15 scanner + owned-model guard + isolation green; `/signals/` CSP unchanged.

## Risks

- **R1** S3 consumes the S1 field — do not branch before S1 merges to the tracker; S2 is independent.
- **R2** S3 alone ~380 lines near the budget edge; split its test battery if the reviewer prefers.
- **R3** Token leak — `src.alerts` worker-only; scanner negative control guards it.
- **R4** R14 scoping — CRUD/screen must stay `for_user`; guard test enforces.
- **R5** At-most-once — send-failure is lost by design (D1 order); documented, no reorder.
- **R6** Screen SMC cost — bounded to user pairs + fixed `limit=200`; upstream errors degrade, never 500.
