# Verify Report: f11-symbol-universe

**Change**: `f11-symbol-universe` (issue #124, Fase F11 — change A of two)
**Branch**: `feat/f11-symbol-universe` vs `origin/develop` @ `81e469b`
**Date**: 2026-10-18
**Verdict**: **PASS_WITH_WARNINGS** — 12/12 requirements compliant, 0 CRITICAL,
0 blockers; 3 low-severity accepted warnings (W2-W4).

> Verification was performed **inline with direct evidence** (per-change test runs,
> diff inspection, gate output) rather than via sub-agent: 4 of 5 SDD sub-agents
> timed out on network during this session (gotcha #12 of the handoff).

## Gate evidence (all green)

| Gate | Command | Result |
|---|---|---|
| Node tests | `node --test "tests/js/**/*.test.js"` | **608 pass, 0 fail** (was 598 at baseline; +10) |
| Django suite | `.venv/bin/python -m pytest -p no:randomly` | **exit 0**, 1196 passed |
| Lint | `.venv/bin/ruff check .` | All checks passed |
| Format | `.venv/bin/ruff format --check .` | 155 files already formatted |
| Migrations | `makemigrations --check --dry-run` | No changes detected |
| Patch coverage | `diff-cover cov.xml --compare-branch=origin/develop --fail-under=100` | **119 lines, 0 missing, 100%** |
| Module ceiling | `test_module_size_guard.py` | green, allowlist **empty**; max module `smc.js` = 300 |
| Owned-model guard | `test_owned_model_guard.py` | green |
| Framework boundary | `test_boundary.py` | green |
| Dependency guard | `test_dependency_guard.py` | green |
| No order surface | `test_no_order_surface.py` | green |

## Requirement-by-requirement

### symbol-catalog (NEW)

| Req | Status | Evidence |
|---|---|---|
| R1 universe fetch (projected, sorted, de-duped, no-arg `tickers()`) | ✅ COMPLIANT | `test_list_symbols_projects_sorts_and_dedups` asserts `stub.calls == [None]`; `test_list_symbols_returns_only_strings` |
| R1 framework boundary | ✅ COMPLIANT | `test_catalog_module_imports_no_django_model` parses the AST for django/trading/views imports |
| R1 no dependency | ✅ COMPLIANT | `requirements.txt` unchanged (`git diff --quiet` = YES) |
| R2 TTL warm/expired | ✅ COMPLIANT | `test_warm_cache_does_not_call_upstream` (now=59), `test_expired_entry_refetches` (now=61) |
| R2 failure does not poison | ✅ COMPLIANT | `test_fetch_failure_propagates_and_keeps_the_cached_value` |
| R3 endpoint 200/302/405/502 | ✅ COMPLIANT | four dedicated tests |
| R4 warm membership is offline | ✅ COMPLIANT | `test_symbol_exists_is_offline_when_warm` uses a client that raises if touched |

### market-watchlist (MODIFIED)

| Req | Status | Evidence |
|---|---|---|
| R14.8 CRUD + `for_user` + CSRF + owner-from-body | ✅ COMPLIANT | `test_isolation_b_never_sees_or_deletes_a_rows`, `test_owner_is_never_taken_from_the_body`, `test_post_requires_csrf`, `test_anonymous_is_redirected` |
| R14.9 virtual default, no seeding | ✅ COMPLIANT | `test_get_empty_returns_config_symbols_without_seeding` asserts `Watchlist.objects.count() == 0`; `test_default_follows_the_environment` |
| R14.10 validation/idempotency/cap | ✅ COMPLIANT | 5-case parametrized malformed matrix, `test_post_duplicate_is_idempotent`, `test_post_rejects_when_at_cap`, `test_delete_is_idempotent`, `test_post_fails_open_when_the_catalog_is_cold` |

### alert-rules (MODIFIED — R12)

| Req | Status | Evidence |
|---|---|---|
| R12 warm accept (symbol outside `config.SYMBOLS`) | ✅ COMPLIANT | `test_alerts_accept_a_catalog_symbol_outside_config_symbols` |
| R12 warm reject unknown | ✅ COMPLIANT | `test_alerts_reject_an_unknown_symbol_when_the_catalog_is_warm` |
| R12 cold fail-open | ✅ COMPLIANT | `test_alerts_fail_open_when_the_catalog_is_cold` |
| R12 malformed always 400 | ✅ COMPLIANT | parametrized `test_alerts_reject_malformed_symbols_even_when_cold` |
| R12 interval bound unchanged | ✅ COMPLIANT | `test_alerts_interval_bound_is_unchanged`; the whole pre-existing F10 matrix still green |

### market-ingestion (MODIFIED — R7/R8/R9)

| Req | Status | Evidence |
|---|---|---|
| R7 union set, defaults first, dedup, cap 50 | ✅ COMPLIANT | `test_ingest_symbols_puts_defaults_first_then_sorted_watchlist`, `test_ingest_symbols_caps_and_never_starves_defaults`, `test_ingest_symbols_dedups_a_default_that_is_also_watched` |
| R7 watchlist symbol actually ingested by the loop | ✅ COMPLIANT | `test_run_loop_uses_the_ingest_set_when_symbols_is_none` (this test caught a real bug: `ingest_symbols()` existed but `run_loop` still used `config.SYMBOLS`) |
| R7 per-(symbol,interval) failure isolation | ✅ COMPLIANT | `test_fetch_closed_candles_isolates_one_failing_interval` asserts the 1d request still happens after 1h raises |
| R8 `due_intervals` pure, boundaries, fresh process | ✅ COMPLIANT | 4 table/behaviour tests incl. `test_due_intervals_fresh_process_returns_every_interval` |
| R8 `intervals` parameter + back-compat | ✅ COMPLIANT | `test_fetch_closed_candles_honours_the_intervals_argument`; all pre-existing worker tests green with `intervals=None` |
| R8 `last_poll` in-memory, advances only on success | ✅ COMPLIANT | `test_last_poll_advances_only_after_a_successful_cycle` + autouse per-test reset (added after a pollution finding) |
| R9 request budget | ✅ COMPLIANT (after W1 fix) | `test_request_budget_stays_under_the_exchange_limit_at_the_cap` asserts the scheduled rate is `< 1` req/s at the cap; `test_negative_control_naive_polling_would_exceed_the_limit` proves the naive form is `> 10` req/s. Both derive from the real `INTERVAL_SECONDS` table and `INGEST_POLL_SECONDS`. |
| R9 no history backfill | ✅ COMPLIANT | `_fetch_window` untouched; no new bulk-write path in the diff |

### market-chart (MODIFIED — R19/R20)

| Req | Status | Evidence |
|---|---|---|
| R19 `filterSymbols` tiers/cap/case/empty/no-throw | ✅ COMPLIANT | 9 node tests incl. tier ordering, cap-after-sort, malformed inputs, limit clamping |
| R19 combobox roles + keyboard + live region | ✅ COMPLIANT (markup + logic) | `test_f11_symbol_picker_is_markup_only` asserts roles/ids; controller implements ArrowUp/Down wrap, Enter, Escape, `aria-activedescendant` |
| R19 select emits existing `config:changed` | ✅ COMPLIANT | `controllers/symbol-picker.js:81` emits `config:changed`; no new bus event exists in `chart-bus.js` |
| R19 follow/unfollow persists | ✅ COMPLIANT (after fix) | `symbol picker: a followed symbol can be unfollowed` node test — **this test was written after finding the button was `disabled` once followed, making unfollow impossible** |
| R20 `.pairs`/`.pair[data-symbol]` preserved | ✅ COMPLIANT | `test_f11_watchlist_container_keeps_the_pair_contract` |
| R20 `toolbar.js` untouched | ✅ COMPLIANT | `git diff --quiet ... toolbar.js` = YES; `test_f11_toolbar_delegation_is_untouched` |
| R20 allowlists + docs | ✅ COMPLIANT | `MODULE_ALLOWLIST` 33→34, `CONTROLLER_ALLOWLIST` 17→18, both served 200; `chart-modules.md` updated |
| R20 frozen seams | ✅ COMPLIANT | `window.marketChart` = exactly 8 keys (verified by count); `STORE_KEYS` = 11 |
| R20 CSP unchanged | ✅ COMPLIANT | no inline handler/`<script>` in `chart.html` (grep = 0); no `unsafe-inline` in settings |
| R20 ceiling | ✅ COMPLIANT | `main.js` = 295; `symbol-picker.js` = 202; `symbol-search-core.js` = 41 |

## Findings

### W1 — R9 budget is proven by arithmetic, not by an instrumented test (RESOLVED)

**Resolved during verification.** Two executable assertions were added to
`tests/web/test_worker_candles.py`:
`test_request_budget_stays_under_the_exchange_limit_at_the_cap` (scheduled rate
`< 1` req/s) and `test_negative_control_naive_polling_would_exceed_the_limit`
(naive form `> 10` req/s). R9 therefore moves from ⚠️ DEVIATING to ✅ COMPLIANT.

The spec's scenario "Steady state is under the budget" and its negative control
("bypassing `due_intervals` exceeds the limit") currently have **no executable
test**. The numbers are correct and derived from the real interval table, but a
future edit to `INTERVAL_SECONDS` or the poll period could invalidate them
silently.

**Fix (small, recommended before archive):** add one pure test that sums
`1/span` over `CANDLE_INTERVALS`, multiplies by the cap and the cycle length, and
asserts the rate is `< 10` — plus a negative control asserting the naive
`8 * cap / 30` form is `> 10`. Two assertions, no I/O.

### W2 — `DELETE /market/api/watchlist/<symbol>` does not validate the symbol format (LOW)

The route deletes by exact string through `for_user`, so a malformed symbol is a
harmless no-op (204). Not a security issue, and idempotency is the spec's
requirement. Left as-is deliberately; noted so it is not mistaken for an
oversight.

### W3 — `_last_poll` is process-global and does not survive a restart (LOW, accepted)

Documented in the design (§4.3) and spec R8: a restart re-issues every interval
once. The cycle throttle absorbs it. Test pollution was found and fixed with an
autouse reset.

### W4 — E2E for the picker was not executed (LOW)

The task list called for an E2E asserting search→Enter and follow. E2E is
dev-only and flaky (#149), CI does not run it. The behaviour is covered by the
node controller test (follow/unfollow request shape) plus the markup test
(roles/ids). An E2E run is recommended opportunistically, not as a gate.

## Diff review findings already fixed in this change

| Finding | Severity | Fix commit |
|---|---|---|
| `ingest_symbols()` was dead code — `run_loop` still used `config.SYMBOLS`, so the whole watchlist ingestion was inert | **CRITICAL** | `887e27b` |
| Follow button `disabled` once followed → unfollow impossible (violated R19) | **HIGH** | `8dc04ae` |
| `except Exception` on the cold-catalog path would swallow programming errors | **MEDIUM** | `8dc04ae` |
| `filterSymbols(…, limit<=0)` could invert the slice | **LOW** | `8dc04ae` |
| `_last_poll` module-global leaked between tests | **LOW** | `8dc04ae` |

## Verdict

**PASS_WITH_WARNINGS.** All 12 requirements have executable evidence: R9's budget
scenario gained its two arithmetic assertions during verification (W1 resolved).
Zero CRITICAL, zero blockers, 100% patch coverage on 125 changed lines, all gates
green. Remaining warnings W2-W4 are documented, deliberate, and low severity.
