# Verify Report — alert-rules (issue #76, Fase D1)

**Verdict**: `pass`
**Verified by**: orchestrator (adversarial, fresh probes). The delegated verify sub-agent pattern timed out earlier this session; verification was executed inline.
**Branch**: `feat/alert-rules-worker` (HEAD `7f2073e`), chain: tracker `feat/alert-rules` + Slice1 `…-model` (`45b878b`) + Slice2 `…-engine` (`4124cc0`) + Slice3 `…-worker` (`7f2073e`); all slice PRs base on the tracker.

## Gates (L1)

| Gate | Result |
| --- | --- |
| `python -m pytest tests/` | **717 passed, 23 deselected** (baseline 650 after S1) |
| `pytest tests/test_alert_rules.py tests/test_boundary.py` | green (71) |
| `pytest tests/web/test_worker_alerts.py tests/web/test_owned_model_guard.py` | green (36) |
| `ruff check .` | clean |
| `ruff format --check .` | clean (122 files) |
| `makemigrations --check --dry-run` | No changes detected |
| `requirements.txt` vs develop | **empty diff** (no new dependency) |
| `src/alert_rules.py` imports | stdlib + intra-package (`src.indicators`, `src.smc.*`) only — no Django/requests/I/O |

## Gates (L2)

- `diff-cover coverage.xml --compare-branch=235e6cf --fail-under=100` (pre-D1 base) → **100%** (163 changed lines, 0 missing: `src/alert_rules.py`, `web/trading/models.py`, `web/worker.py`).

## Spec conformance (L3)

- **Model** `AlertRule(UserOwnedModel)`: `symbol`, `interval`, `condition` JSON, `is_active` (default True), `last_fired_at` (DateTimeField null); index `(user, is_active)`; **no unique constraint** (collection); additive migration `0007`; in `OWNED_MODELS` (+ negative control).
- **Pure engine** `src/alert_rules.py` (framework-free, `PURE_MODULES`): `parse_condition` raises `ValueError` on config breach; `matches` total/never-raise (short/warm-up/None → False); `edge_fired` = **Option B** over the latest two closed bars (`<2` → False). Condition schema `price`/`indicator` (scalar series only)/`smc_setup`; tuple indicators → False. Deterministic, no wall-clock, inputs not mutated.
- **Worker** `run_alert_rules`: reads active rules **unscoped in `web/worker.py`** only (R14.4 — probe: the ONLY `AlertRule.objects` reference outside tests); one candle window per `(symbol, interval)`; dedup by `last_fired_at` (idempotent); per-rule broad-`except` isolation; `on_fired(rule, detail)` sink (default logger); wired into `run_once` as an isolated step. No order surface.
- **D2 seam**: `on_fired(rule, detail)`, `detail = {"symbol","interval","edge_time","condition"}`. No events table.
- **Read-only**: no order verbs/imports anywhere in the D1 surface.

### Adversarial probes (independent, throwaway)
- Model: 2 rules coexist on the same `(user,symbol,interval)`; A≠B via `for_user`; `is_active` default True; `last_fired_at` null.
- Engine: price above/below fire+no-fire; `edge_fired` false→true fires, true→true does NOT; `<2` bars → False; breaches (`type=nope`, `op=sideways`, tuple indicator `macd`) → `ValueError`; invalid condition passed to `matches` → False (no raise); determinism + non-mutation confirmed.
- Worker (e2e): seed 2 candles (prev close 90, last 110) with a `price above 100` rule → **fires=1**, sink called once with `edge_time=2000`, `last_fired_at` set; **second run → 0** (dedup).

## Warnings (non-blocking)

- **W1 — `parse_condition` requires explicit `direction` on `smc_setup`**: the apply deviated from design prose (which said default `any`) to follow spec R2 (explicit required key). Correct per spec; design prose should be reconciled at archive.
- **W2 — Slice 2 diff ~530 lines** (tests-dominated) sits above the 400 review budget; split the test battery if a reviewer objects (delivery-strategy `ask-on-risk` accepted the chain).
- **W3 — `test_unexpected_rule_error_is_isolated` monkeypatches `alert_rules.edge_fired`** by name — low coupling risk (the single engine entry point the worker calls).
- **W4 — `ALERT_CANDLE_WINDOW=100`** is a conservative constant; revisit only if a condition needs deeper context.
- **SUGGESTION**: `tasks.md` checkboxes not marked by apply (orchestrator hard contract); engram `sdd/alert-rules/apply-progress` is the completion source.

## Requirement coverage

- New `alert-rules` capability (9 reqs): satisfied.
- `per-user-isolation` DELTA (R14.2/R14.3/R14.4 + `AlertRule`): satisfied (unscoped read correctly confined to `worker.py`).
- `core-domain-boundary` DELTA (`src/alert_rules.py` in `PURE_MODULES`): satisfied.

## Blockers

None.
