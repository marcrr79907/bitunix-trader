# Tasks: persistence-foundation (Ola 3 / F11 / #124)

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

## Guard/Edge Matrix

- [ ] `0012` order on SQLite: `RemoveIndex(ix_drawing_user_sym_interval)` → `AlterField(default="1m")` → `RemoveField(interval)` → `AddIndex(ix_drawing_user_symbol)`; `.sqlmigrate` + `makemigrations --check` green
- [ ] keep-all/no-dedupe: rows differing only by interval coexist post-`0012` (no `IntegrityError`); NEW index `(user, symbol)`, no unique constraint
- [ ] reverse is LOSSY: `migrate trading 0011` re-adds `interval="1m"` every row; per-interval split unrecoverable (documented)
- [ ] drawings clear on SYMBOL change only; interval-only `switchTo` keeps shapes + skips refetch
- [ ] `gen` guard ordering preserved; DEBT-8 `stream.subscribe` untouched
- [ ] `window.marketChart` stays 8 keys (`drawings` kept, no new key); `MODULE_ALLOWLIST`/`CONTROLLER_ALLOWLIST` unchanged
- [ ] `drawings.js` ≤300 lines (`test_module_size_guard`, net-negative diff)
- [ ] `parse_smc`: dict, keys ∈ 6 families, bool values; breach → 400 no-write
- [ ] `parse_drawing` unchanged; POST `interval` accept-and-ignore (never 400)
- [ ] read-only: no order verb/endpoint; order scanner clean; no new dep; CSP unchanged; `src/` framework-free; `requirements.txt` unchanged
- [ ] patch 100% Python; `pytest` + `node --test` + ruff green

## WU1 — drawings per symbol (S1 / PR1)

Base `feat/persistence-foundation` (tracker); branch `feat/persistence-drawings-per-symbol`; deps none. Rollback: `migrate trading 0011` (LOSSY) or revert branch.

- [ ] 1.1 **RED** `tests/web/test_isolation.py` + `test_owned_model_guard.py`: per-`(user,symbol)` Drawing isolation; A≠B `DoesNotExist`; guard negative control. Files: `tests/web/test_isolation.py`, `tests/web/test_owned_model_guard.py`. Accept: red → green at 1.2.
- [ ] 1.2 **GREEN** `web/trading/models.py`: `Drawing` drops `interval`; `Meta.indexes=[Index(["user","symbol"], name="ix_drawing_user_symbol")]`, no unique constraint. Accept: 1.1 green.
- [ ] 1.3 **RED/GREEN** `web/trading/migrations/0012_drawing_per_symbol.py`: 4-op order above; assert no `interval` field + new index; reverse lossy. Files: migration. Accept: `makemigrations --check` green; round-trip test (both rows forward, all-`"1m"` reverse).
- [ ] 1.4 **RED** `tests/web/test_market_api.py`: GET `?symbol=` (no interval, stray ignored); empty→`[]` not 404; POST stores `(user,symbol)`, stale `interval`→201; DELETE 204/404; cross-user 404. Accept: red first.
- [ ] 1.5 **GREEN** `web/market/views.py`: `api_drawings` GET filters `(user,symbol)` only, no interval; `_post_drawing` drops interval require + `interval=interval` create; DELETE unchanged. `parse_drawing` unchanged. Accept: 1.4 green; patch 100%.
- [ ] 1.6 **RED** `tests/web/test_market_e2e.py`: drawing survives interval switch (no refetch); cleared+reloaded on symbol switch; rewrite `test_switch_clears_then_loads_drawings` + `per_interval_drawings` fixture → per-symbol; retire `test_drawing_distinct_intervals_coexist`; drop `interval` assert in `test_click_with_tool_fires_post`. Accept: red then green at 1.7.
- [ ] 1.7 **GREEN** `drawings.js`: `loadDrawings(symbol)`, `createDrawing` body drops interval, `refreshDrawings()` → symbol; `main.js::switchTo`: `clearForSwitch()` only when `state.symbol` changed; preserve `gen`/DEBT-8. `drawings.js` ≤300. Accept: 1.6 green.

## WU2 — SMC toggles persistence (S2 / PR2)

Base tracker (contains WU1 after S1 merges); branch `feat/persistence-smc-toggles`; deps WU1 (shared `main.js`). Rollback: revert branch; `0013` additive, zero data loss.

- [ ] 2.1 **RED** `test_market_api.py`: `parse_smc` matrix (dict, 6 families, bool; bad→`ValueError`); preference GET default `smc:{}`; PUT partial `{smc}` round-trip; invalid `smc`→400 no-write; field round-trip. Accept: red first.
- [ ] 2.2 **GREEN** `web/trading/models.py`: `ChartPreference.smc = JSONField(default=dict)`. Accept: model test green.
- [ ] 2.3 **GREEN** `web/trading/migrations/0013_chartpreference_smc.py`: `AddField(smc, JSONField(default=dict))`, additive. Accept: `makemigrations --check` green.
- [ ] 2.4 **GREEN** `web/market/quotes.py`: `parse_smc` (dict, keys ∈ 6 families, bool values; else `ValueError`). Accept: 2.1 matrix green.
- [ ] 2.5 **GREEN** `web/market/views.py`: `api_preference` GET default adds `smc:{}`; `_preference_body` adds `"smc"`; `_put_preference` validates `smc` → 400 no-write; partial PUT applies only present keys. Accept: 2.1 green; patch 100%.
- [ ] 2.6 **RED/GREEN** `tests/web/test_market_e2e.py`: toggle off → reload restores from pref; toggle off survives interval switch; failed pref fetch → all ON. `smc.js`: `applyToggles(saved)` sets checkbox/render no-emit; `main.js`: boot `smc.applyToggles(pref.smc)`, `bus.on("smc:toggles", p => savePreference({smc:p.families}))`. Accept: E2E green, readiness-gated.

## Phase 3 — Verification

- [ ] 3.1 `pytest` green; patch 100%; `node --test` green; ruff clean; `makemigrations --check` green.
- [ ] 3.2 Order scanner clean; CSP + `requirements.txt` unchanged; `src/` framework-free; `window.marketChart` 8 keys.
- [ ] 3.3 Playwright: drawings interval-keeps/symbol-clears; SMC toggle reload + interval survival; no console errors.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | S1 220–280, S2 130–170 → ~350–450 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 (WU1, base tracker) → PR2 (WU2, base tracker post-S1-merge) |
| Delivery strategy | feature-branch-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No — chain strategy fixed to feature-branch-chain.
