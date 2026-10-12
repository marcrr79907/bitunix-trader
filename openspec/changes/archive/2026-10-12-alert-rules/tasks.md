# Tasks: alert-rules (issue #76, Fase D1)

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

Chain: all slices base on tracker `feat/alert-rules`; each later slice bases on the immediate previous slice branch; merge each to the tracker before branching the next. S1 model+guard ~200 · S2 pure engine ~410 · S3 worker wiring ~220.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~830 (src ~160, tests ~550, model+migration ~60, worker ~60) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | S1 model+guard → S2 pure engine → S3 worker wiring |
| Delivery strategy | ask-on-risk (chain pre-chosen) |
| Chain strategy | feature-branch-chain |

### Suggested Work Units

| Unit | Goal | Likely PR | Base boundary |
|------|------|-----------|---------------|
| 1 | `AlertRule` + `0007_alertrule` + `OWNED_MODELS` + isolation tests | PR 1 | tracker |
| 2 | `src/alert_rules.py` engine + `PURE_MODULES` + engine battery | PR 2 | PR 1 branch |
| 3 | `run_alert_rules` + `on_fired` + `run_once` step + worker tests | PR 3 | PR 2 branch |

## Guard/Edge Matrix

- [ ] `PURE_MODULES` gains `"alert_rules.py"` (S2) — else stdlib-only + boundary check stays blind.
- [ ] `OWNED_MODELS` gains `AlertRule` (S1) — request-path unscoped query must be flagged.
- [ ] R14.4: unscoped `AlertRule.objects.filter(is_active=True)` stays ONLY in `web/worker.py`; never in `web/trading/`.
- [ ] determinism/no-wall-clock: engine imports no `time`/`datetime`/`random`; same input → identical `(state, fired)`.
- [ ] dedup by bar time: same bar twice = one fire; restart after fired bar = no re-fire.
- [ ] per-rule isolation: own `try/except Exception`; one bad rule logged+skipped, peers continue.
- [ ] rule isolation from loop: `run_once` broad-`except`; `(funding,ticker)` contract unchanged.
- [ ] empty/short/mismatched candles → `matches` `False`; `<2` bars → `edge_fired` `False`; warm-up `None` → `False`; never raise.
- [ ] unknown `type`/`op`/`name`/`direction`, tuple indicator → `False` (no raise); bad config → `parse_condition` raises → worker skips rule.
- [ ] `interval` not in `CANDLE_INTERVALS` (e.g. `1m`) skipped before evaluation.
- [ ] read-only/no-order: no order verb/path, no `client` in engine, no events table; `requirements.txt` unchanged.
- [ ] patch 100%; ruff `check` + `format --check` green.

## Slice 1 — model + guard (base: tracker)

Dep: none. Rollback: drop migration `0007_alertrule` (+ migration row) + `AlertRule`; revert `OWNED_MODELS`/isolation tests; drop per-user-isolation delta.

- [ ] 1.1 **RED** `tests/web/test_isolation.py`: add `AlertRule` A≠B cross-user `DoesNotExist`; collection (two rows same `(symbol,interval)`, no `IntegrityError`); `for_user` scoping; owner required; index `(user,is_active)` present + `_meta.constraints == []`. Acceptance: fails before 1.3.
- [ ] 1.2 **RED** `tests/web/test_owned_model_guard.py`: add `AlertRule.objects.all()` to the flagged parametrize (`OWNED_MODELS += "AlertRule"`); unscoped `filter(is_active=True)` flagged. Acceptance: fails before 1.3/1.4.
- [ ] 1.3 **GREEN** `web/trading/models.py`: `AlertRule(UserOwnedModel)` with `symbol`, `interval`, `condition=JSONField(default=dict)`, `is_active=BooleanField(default=True)`, `last_fired_at=DateTimeField(null=True)`; `Meta.indexes=[Index(fields=["user","is_active"], name="ix_alertrule_user_active")]`; **no unique constraint**. Acceptance: 1.1 green.
- [ ] 1.4 **GREEN** `web/trading/migrations/0007_alertrule.py`: additive, `dependencies 0006_drawing`. Acceptance: `migrate` clean; 1.2 green.
- [ ] 1.5 **GREEN** `openspec/changes/alert-rules/specs/per-user-isolation/spec.md` already declares R14.2/R14.3/R14.4 `AlertRule`; confirm reconciliation at archive.
- [ ] 1.6 **REFACTOR** ruff clean. Acceptance: S1 green, patch 100%.

## Slice 2 — pure engine `src/alert_rules.py` (base: S1 branch)

Dep: frozen `src/smc`/`src/indicators` only (no code from S1). Rollback: delete `alert_rules.py` + `tests/test_alert_rules.py`; revert one `PURE_MODULES` line.

- [ ] 2.1 **RED** `tests/test_alert_rules.py`: literal OHLC fixtures; per type (`price`/`indicator`/`smc_setup`) fire + no-fire, strict ops; `index` slicing (`-1`/`-2`); warm-up `None`→`False`; empty/short/mismatched→`False`; unknown type/op/name/direction + tuple indicator→`False`; `parse_condition` raises `ValueError` on breach; edge false→true fires, true→true/true→false don't, `<2` bars→`False`; same input→identical output; no `time`/`datetime`/`random` import. Acceptance: fails before 2.3.
- [ ] 2.2 **GREEN** `tests/test_boundary.py`: `PURE_MODULES += ("alert_rules.py",)`. Acceptance: stdlib-only test green; negative control still flags.
- [ ] 2.3 **GREEN** `src/alert_rules.py`: `parse_condition(condition)->dict` (raise `ValueError` on breach); `matches(condition, candles, *, index=-1)->bool` (total, never raise); `edge_fired(condition, candles)->bool` (last two closed bars; `<2`→`False`). Imports `src.smc.*` + `src.indicators`; stdlib-only; no clock. Acceptance: 2.1 green.
- [ ] 2.4 **REFACTOR** ruff clean; factor duplicated fixtures with S1/SMC tests. Acceptance: S2 green, patch 100%.

## Slice 3 — worker wiring (base: S2 branch; final)

Dep: S1 (model) + S2 (engine). Rollback: revert `web/worker.py` hunks (`run_alert_rules`, `on_fired`, `run_once` step, `ALERT_CANDLE_WINDOW`); delete `tests/web/test_worker_alerts.py`.

- [ ] 3.1 **RED** `tests/web/test_worker_alerts.py`: `@pytest.mark.django_db` seeded `Candle`; fires once per edge; same bar twice = one fire; per-rule isolation (one bad condition logged+skipped, peer fires); A≠B rules both readable unscoped; unsupported `interval` skipped; `on_fired` once per fire; `run_once` still returns `(funding,ticker)` when `run_alert_rules` raises. Acceptance: fails before 3.3.
- [ ] 3.2 **GREEN** `web/worker.py`: `ALERT_CANDLE_WINDOW=100`; module-level `on_fired(rule, detail)` (logger stub); `run_alert_rules(on_fired_sink=None)->int` — unscoped `AlertRule.objects.filter(is_active=True)` (R14.4), group by `(symbol,interval)`, skip `interval` not in `CANDLE_INTERVALS`, one `Candle` window per group, per-rule `try/except`, dedup `last_fired_at.timestamp() >= edge_time` → skip else `save(update_fields=["last_fired_at"])`; `detail={"symbol","interval","edge_time","condition"}`. Acceptance: 3.1 green.
- [ ] 3.3 **GREEN** `run_once`: add isolated step AFTER private sync, `try: run_alert_rules() except Exception`; `(funding,ticker)` return unchanged. Acceptance: 3.1 green.
- [ ] 3.4 **REFACTOR** ruff clean; confirm no `client`/order path in engine. Acceptance: S3 green, patch 100%.

## Phase Verification (per slice + close)

- [ ] V.1 `python -m pytest` green; `diff-cover --fail-under=100` on changed lines.
- [ ] V.2 `ruff check . && ruff format --check .` green; no new dependency; `requirements.txt` unchanged; order scanner clean.
- [ ] V.3 boundary + owned-model guard + isolation green; `PURE_MODULES` and `OWNED_MODELS` entries present.

## Risks

- **R1** Slice 3 consumes S1+S2 — do not branch it before both merge to the tracker.
- **R2** S2 alone ~410 lines at the budget edge; split its test battery if the reviewer prefers.
- **R3** Framework-free drift — engine in `src/` + `PURE_MODULES`; Django only in `web/` (worker imports `src`, allowed).
- **R4** Owned-model guard — unscoped read must stay in `worker.py`; model still in `OWNED_MODELS`.
- **R5** Determinism — no clock in engine; explicit no-`time`/`datetime` test guards it.
