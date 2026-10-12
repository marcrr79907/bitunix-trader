# Archive Report: alerts-telegram

**Archived**: 2026-10-12
**Verdict**: `pass_with_warnings` (0 blockers, 0 criticals) — 2 new capabilities (`signals-screen` 5 req / 11 scenarios, `alert-rule-config` 4 req / 10 scenarios) + 3 modified capabilities (`alert-rules` R8 rewritten + R8.2 added, `security-invariants` R15/R16 added, `market-chart` R13 added)
**Delivery**: 3-slice Feature Branch Chain — PR #105 (Telegram delivery) → #106 (`/signals/` screen) → #107 (AlertRule CRUD), each base on tracker `feat/alerts-telegram`; tracker merged to `develop` via PR #108
**Issue**: #77 (Fase D2)
**Verify**: `verify-report.md` — L1 full suite green (60 focused web tests); L2 patch 100% (110 changed lines); L3 all requirements satisfied; R15 scanner + owned-model guard + isolation green; no new dependency

## What Shipped

Fase D2: the delivery + surface half of the alert feature. D1 froze the
`on_fired(rule, detail)` seam, `src.alerts.send_telegram`, `get_smc_payload`, and
the `for_user` contract; D2 consumes them. It sends a Telegram message per fire
(worker trust zone only), adds a server-rendered `/signals/` screen pairing
global SMC setups with each user's own `AlertRule` state, and adds a per-user
`AlertRule` CRUD UI. All three are additive and reuse proven seams. The system
still **never orders**. No new runtime dependency; no `src/smc/` or chart-JS
change; CSP untouched.

| Area | Delivered |
|------|-----------|
| Worker sink | `web/worker.py`: module-level `on_fired(rule, detail)` rewritten to format a **detail-only** message (`{symbol, interval, edge_time, condition}` — no SMC recompute) and send via lazy `from src.alerts import send_telegram`; chat = `rule.telegram_chat_id or config.TELEGRAM_CHAT_ID`; self-guarded `try/except` so a send can never break the eval loop (R7). Delivery is **at-most-once** (D1 stamp-before-send preserved). |
| Model | `web/trading/models.py`: `AlertRule.telegram_chat_id = CharField(max_length=64, blank=True, default="")`; owned via `for_user`; no unique constraint; additive migration `0008_alertrule_telegram`. |
| Screen | `web/market/views.py::signals_page` + `market/urls.py` route (`name="signals_page"`) + `market/templates/market/signals.html` + `base.html` Signals nav link + `theme.css` rows. GET-only `@login_required`; pairs = caller's own `AlertRule.for_user` pairs; setups single-sourced from `get_smc_payload(BitunixClient(), symbol, interval, 200)`; state `fired`/`armed`/`inactive`/`none`; server-rendered, no JS, no pagination. |
| CRUD | `web/trading/forms.py::AlertRuleForm` (`symbol`/`interval`/`condition`/`telegram_chat_id`/`is_active`; `clean_condition` → `parse_condition`; bounds `SYMBOLS`/`CANDLE_INTERVALS`) + `views.py`/`urls.py` (`rules`/`rule_create`/`rule_edit`/`rule_toggle`/`rule_delete`, every queryset `AlertRule.for_user(request.user)`) + `templates/trading/rules.html`. Cross-user → 404. |
| Tests | `tests/web/test_worker_telegram.py`, `test_telegram_boundary.py` (R15 scanner + negative control), `test_signals.py`, `test_alert_rule_crud.py`; extended `test_isolation.py`, `test_owned_model_guard.py`. |

## Verify Findings

Verdict `pass_with_warnings` (verify-report.md). L1: `python -m pytest tests/`
green (60 focused web tests green); `ruff check .` + `ruff format --check .` clean
(128 files); `makemigrations --check --dry-run` no changes; `requirements.txt` vs
develop empty diff; `src/` untouched. L2: `diff-cover --fail-under=100` → 100%
(110 changed lines, 0 missing: `web/worker.py`,
`web/trading/{models,forms,views}.py`, `web/market/views.py`). L3: delivery sink,
model field, screen, CRUD, and R15 all confirmed with independent adversarial
probes (model round-trip; sink one-call-per-fire with stub; request-path scanner;
real-browser render of `/signals/` and `/rules/`; A≠B → 404; anonymous → 302).

### Warnings carried (non-blocking)

- **W1 — Slice 3 diff ~552 lines** (tests-dominated) sits above the 400-line
  review budget. The CRUD + scanner test battery. Delivery strategy `ask-on-risk`
  accepted the chain; split the test file if a reviewer objects.
- **W2 — R15 scanner deferred from Slice 1 to Slice 3.** Intent held throughout,
  but the invariant had no test until Slice 3. Now covered with negative controls.
- **W3 — at-most-once drops a failed send** (documented): a Telegram failure is
  NOT retried; D1 owns ordering/dedup. Intentional v1 tradeoff, no reorder.
- **W4 — `/signals/` SMC compute cost** is live per GET, bounded to the user's
  rule pairs + fixed `limit=200` (DB-first window). Upstream errors degrade to
  empty setups, never 500.
- **SUGGESTION — `tasks.md` checkboxes unmarked.** Apply left the boxes unmarked
  (orchestrator hard contract); engram `sdd/alerts-telegram/apply-progress` is the
  completion source, not `tasks.md`.

## Requirement Outcomes

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| alert-rules | R8 `on_fired` Telegram delivery sink (MODIFIED) | ✅ detail-only message; chat-id/env resolution; self-guarded; at-most-once; token worker-only |
| alert-rules | R8.2 Per-user Telegram destination (ADDED) | ✅ nullable additive `telegram_chat_id` (migration `0008`); `for_user`-owned; env fallback |
| alert-rules | R1–R7, R9 (preserved) | ✅ evaluation semantics unchanged; R9 wording extended to "engine or sink" + "sink MUST send messages only" |
| signals-screen (new) | S1 Route and auth | ✅ GET-only `signals` route in `market/urls.py`; `login_required`; anonymous → 302; server-rendered |
| signals-screen (new) | S2 Per-user pair scoping | ✅ pairs from `AlertRule.for_user`; no-rules → empty page, never error |
| signals-screen (new) | S3 Single-sourced setups | ✅ one `get_smc_payload` call per pair; setups match frozen payload; no SMC recompute in the view |
| signals-screen (new) | S4 Alert-state rendering | ✅ `fired`/`armed`/`inactive`/`none`; no send and no `last_fired_at` write from the view |
| signals-screen (new) | S5 CSP unchanged, server-rendered | ✅ no inline script; CSP unchanged; single GET snapshot, no pagination |
| alert-rule-config (new) | C1 Server-rendered form view | ✅ `AlertRuleForm` CRUD; `login_required`; anonymous → 302; CSRF; no inline script |
| alert-rule-config (new) | C2 Per-user scoping (`for_user`) | ✅ every read/write via `for_user`; cross-user → 404; owner set explicitly on create |
| alert-rule-config (new) | C3 Condition validated via `parse_condition` | ✅ `clean_condition` maps `ValueError` to form error; symbol/interval bounded; normalized dict persisted |
| alert-rule-config (new) | C4 Activate / toggle and edit | ✅ edit + `is_active` toggle via `for_user`; no evaluate/send on toggle |
| security-invariants | R15 Telegram secret confined to the worker (ADDED) | ✅ `src.alerts`/`send_telegram`/token only in `web/worker.py`; scanner + negative control |
| security-invariants | R16 Telegram delivery adds no execution surface (ADDED) | ✅ order scanner clean; `requirements.txt` unchanged |
| security-invariants | R11–R14 (preserved) | ✅ untouched |
| market-chart | R13 `/signals/` route registered (ADDED) | ✅ GET-only route; existing market routes unchanged; CSP/boundary unchanged |
| market-chart | R1–R12 (preserved) | ✅ untouched |

## Gates

`pytest` full suite green (60 focused web tests); `ruff check` + `ruff format
--check` clean (128 files); `makemigrations --check --dry-run` no changes;
`diff-cover` patch gate 100% (110 changed lines, 0 missing); `requirements.txt`
unchanged; boundary + owned-model guard + isolation green; R15 scanner + order
scanner clean.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| signals-screen | Created | New capability — S1–S5 (11 scenarios) copied verbatim from the change spec |
| alert-rule-config | Created | New capability — C1–C4 (10 scenarios) copied verbatim from the change spec |
| alert-rules | Updated | R8 replaced (D2 seam → Telegram delivery sink, +4 scenarios); R8.2 added (+3 scenarios); R9 reworded (sink included); Purpose/`AlertRule` table refreshed with `telegram_chat_id`; R1–R7 preserved untouched |
| security-invariants | Updated | R15 added (+3 scenarios); R16 added (+2 scenarios); R11–R14 preserved untouched |
| market-chart | Updated | R13 added (+2 scenarios); R1–R12 preserved untouched |

## Carry-forward

- None blocking.
- W1: Slice 3 size above the budget stays an accepted chain decision; split its
  test battery only if a reviewer objects.
- W2: R15 scanner now lives in S3's battery; the invariant is covered with
  negative controls.
- W3: at-most-once send-failure loss is by design (D1 ordering); no retry.
- W4: `/signals/` per-GET compute is bounded to the user's pairs + `limit=200`.
- Frozen seams consumed by D2 (do not change without a new capability delta):
  D1 `on_fired(rule, detail)` with `detail={"symbol","interval","edge_time","condition"}`;
  C1 `market.quotes.get_smc_payload`; `src.alerts.send_telegram`;
  `src.alert_rules.parse_condition`.
- **Topology note**: all three slice PRs (#105/#106/#107) base on tracker
  `feat/alerts-telegram`; the tracker merged to `develop` via PR #108. The feature
  chain is a Feature Branch Chain — child diffs must not show prior slices.

## SDD Cycle Complete

Planned (explore/proposal/design/tasks) → implemented (3-slice chain PRs
#105/#106/#107 → tracker #108 merged to `develop`) → verified
(`pass_with_warnings`; no CRITICAL/BLOCKER) → archived.

Traceability: `openspec/changes/archive/2026-10-12-alerts-telegram/` (explore,
proposal, design, specs, tasks, verify-report); engram
`sdd/alerts-telegram/{archive-report,proposal,spec,design,tasks,verify-report}`.
