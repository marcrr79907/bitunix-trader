# Archive Report: alert-rules

**Archived**: 2026-10-12
**Verdict**: `pass_with_warnings` (0 blockers, 0 criticals) — 1 new capability (9 requirements / 16 scenarios) + 2 modified capabilities (`per-user-isolation` R14.2/R14.3/R14.4, `core-domain-boundary` R11)
**Delivery**: 3-slice Feature Branch Chain — PR #101 (model+guard) → #102 (pure engine) → #103 (worker wiring), each base on tracker `feat/alert-rules`; tracker merged to `develop` via PR #104
**Issue**: #76 (Fase D1)
**Verify**: `verify-report.md` — L1 717 passed / 23 deselected; L2 patch 100% (163 changed lines); L3 all requirements satisfied; read-only scanner clean; no new dependency

## What Shipped

Fase D1: the first trusted-zone (D) change. Users define per-user `AlertRule`s over
the frozen SMC/indicator/price chain; the worker evaluates them after sync and
records the false→true **edge** in `last_fired_at`. D1 evaluates and marks only —
it never sends and never orders. D2 (channels, UI) consumes D1's `on_fired` seam.
No user-visible behavior, no events table, no new dependency; inert until the
`run_once` step executes.

| Area | Delivered |
|------|-----------|
| Model | `web/trading/models.py`: `AlertRule(UserOwnedModel)` — `symbol`, `interval`, `condition` JSON, `is_active` (default True), `last_fired_at` (DateTimeField null); index `(user, is_active)`; **no unique constraint** (collection, like `Drawing`); additive migration `0007_alertrule`. |
| Engine | `src/alert_rules.py` (framework-free, joins `PURE_MODULES`): `parse_condition` (raises `ValueError` on structural breach), `matches` (total, never-raise), `edge_fired` (Option B — recompute over the latest two closed bars; `<2` bars → `False`). Condition types `price`/`indicator` (scalar series only)/`smc_setup`. Deterministic, no wall-clock, inputs not mutated. |
| Worker | `web/worker.py`: `run_alert_rules(on_fired_sink=None)` — unscoped `AlertRule.objects.filter(is_active=True)` (R14.4, only in `worker.py`), one candle window per `(symbol, interval)`, per-rule broad-`except` isolation, dedup by `last_fired_at`, `run_once` gains an isolated alert step after private sync. `ALERT_CANDLE_WINDOW=100`. |
| D2 seam | Module-level `on_fired(rule, detail)` (default logger stub); `detail = {"symbol","interval","edge_time","condition"}`. No events table. |
| Boundary/guard | `PURE_MODULES += "alert_rules.py"`; `OWNED_MODELS += AlertRule`; isolation + owned-model guard tests extended. |
| Tests | `tests/test_alert_rules.py` (engine edge battery), `tests/web/test_worker_alerts.py` (seeded-candle integration + isolation), extended `test_boundary.py`, `test_owned_model_guard.py`, `test_isolation.py`. |

## Verify Findings

Verdict `pass_with_warnings` (verify-report.md). L1: `pytest tests/` 717 passed / 23 deselected (baseline 650 after S1); `ruff check` + `ruff format --check` clean (122 files); `makemigrations --check --dry-run` no changes; `requirements.txt` vs develop empty diff; `src/alert_rules.py` imports stdlib + intra-package only. L2: `diff-cover --fail-under=100` → 100% (163 changed lines, 0 missing). L3: model/engine/worker conformance + adversarial probes all confirmed; the ONLY `AlertRule.objects` reference outside tests is in `web/worker.py` (R14.4 fence holds).

### Warnings carried (non-blocking)

- **W1 — `smc_setup` requires an explicit `direction`.** Apply followed spec R2 (explicit required key, raising `ValueError` on breach) over design prose (which said default `any`). Spec is authoritative; **design.md prose remains unreconciled** and should be corrected if the design is reused. Recorded, not a defect.
- **W2 — Slice 2 diff ~530 lines** (tests-dominated) sits above the 400-line review budget. Delivery strategy `ask-on-risk` accepted the chain; split the test battery if a reviewer objects.
- **W3 — `test_unexpected_rule_error_is_isolated` monkeypatches `alert_rules.edge_fired` by name.** Low coupling risk — `edge_fired` is the single engine entry point the worker calls.
- **W4 — `ALERT_CANDLE_WINDOW=100`** is a conservative constant (`>= RANGE_LOOKBACK(50) + swing warm-up + 2`); revisit only if a condition needs deeper context.
- **SUGGESTION — `tasks.md` checkboxes unmarked.** Apply left the boxes unmarked (orchestrator hard contract); engram `sdd/alert-rules/apply-progress` is the completion source, not `tasks.md`.

## Requirement Outcomes

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| alert-rules (new) | R1 owned model and scoping | ✅ `UserOwnedModel`, in `OWNED_MODELS`, no unique constraint, additive migration, cross-user `DoesNotExist` |
| alert-rules (new) | R2 frozen `condition` schema | ✅ three types; unknown type/op ⇒ `False`; tuple indicators rejected (W1: explicit `direction` per spec) |
| alert-rules (new) | R3 `matches` semantics | ✅ strict compare; warm-up `None` ⇒ `False`; short/empty/mismatched ⇒ `False` |
| alert-rules (new) | R4 edge detection (false→true) | ✅ Option B over latest two closed bars; `fired = now AND NOT prev`; stateless |
| alert-rules (new) | R5 dedup by fired bar time | ✅ `last_fired_at` stamped with edge bar; same bar twice = one fire; restart no re-fire |
| alert-rules (new) | R6 determinism, purity, never-raise | ✅ framework-free, stdlib-only, no clock/random/I-O; byte-identical output |
| alert-rules (new) | R7 worker step contract | ✅ isolated broad-`except` step; unscoped read in `worker.py`; per-rule isolation; non-`CANDLE_INTERVALS` skipped |
| alert-rules (new) | R8 `on_fired` D2 seam | ✅ invoked once per fire; logger stub; no events table; no order path |
| alert-rules (new) | R9 read-only, no order | ✅ no order verb/import; no new dependency; R11 scanner clean |
| per-user-isolation | R14.2 cross-user read denied | ✅ `AlertRule` added to delivered list + new scenario |
| per-user-isolation | R14.3 unscoped-query guard | ✅ `AlertRule` added to `OWNED_MODELS` + new flagged-query scenario |
| per-user-isolation | R14.4 worker trusted-zone exception | ✅ credentials + alert rules unscoped; scanner does not apply to `worker.py` + new scenario |
| core-domain-boundary | R11 smc package joins inventory | ✅ `alert_rules.py` registered in `PURE_MODULES` + stdlib-only/Django-free scenarios |

## Gates

`pytest tests/` 717 passed / 23 deselected; `ruff check` + `ruff format --check` clean (122 files); `diff-cover` patch gate 100% (163 changed lines, 0 missing); `requirements.txt` unchanged; boundary + owned-model guard + isolation green; order scanner clean.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| alert-rules | Created | New capability — R1–R9 (16 scenarios) copied verbatim from the change spec |
| per-user-isolation | Updated | R14.2 modified (+`AlertRule`, +1 scenario); R14.3 modified (+`AlertRule`, +1 scenario); R14.4 modified (+alert rules + scanner-exemption clause, +1 scenario); R14.1 preserved untouched |
| core-domain-boundary | Updated | R11 modified (inventory + `PURE_MODULES` gains `alert_rules.py`, +3 scenarios); R9/R10 preserved untouched |

## Carry-forward

- None blocking.
- W1: canonical `alert-rules` R2 carries the authoritative explicit-`direction` rule; **design.md prose is stale** and unreconciled — fix only if the design is reused.
- W2: Slice 2 size above the budget stays an accepted chain decision; split tests only if a reviewer objects.
- W3: monkeypatch-by-name coupling stays as-is (single entry point).
- W4: `ALERT_CANDLE_WINDOW=100` stays conservative unless a condition needs deeper context.
- Frozen seams D2/next changes consume: `AlertRule` shape, `src/alert_rules.py` (`parse_condition`/`matches`/`edge_fired`), `on_fired(rule, detail)` with `detail={"symbol","interval","edge_time","condition"}` — do not change without a new capability delta.
- **Topology note**: all three slice PRs (#101/#102/#103) base on tracker `feat/alert-rules`; the tracker merged to `develop` via PR #104. The feature chain is a Feature Branch Chain — child diffs must not show prior slices.

## SDD Cycle Complete

Planned (explore/proposal/design/tasks) → implemented (3-slice chain PRs #101/#102/#103 → tracker #104 merged to `develop`) → verified (`pass_with_warnings`; no CRITICAL/BLOCKER) → archived.

Traceability: `openspec/changes/archive/2026-10-12-alert-rules/` (explore, proposal, design, specs, tasks, verify-report); engram `sdd/alert-rules/{archive-report,proposal,spec,design,tasks,verify-report}`.
