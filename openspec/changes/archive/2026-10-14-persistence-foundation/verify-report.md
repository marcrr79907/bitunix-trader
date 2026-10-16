```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:2f283260257db1a72427a95b1d9c692b2f170598008432f01e08557caa56bef1
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 8/8
scenarios: 47/47
test_command: .venv/bin/python -m pytest tests/ -rA
test_exit_code: 0
test_output_hash: sha256:c6e1913c609e96decf5de599da9ef3c70fe7212b10bd1037d02412eeb69503bf
build_command: .venv/bin/python web/manage.py makemigrations --check --dry-run
build_exit_code: 0
build_output_hash: sha256:a2bfa7b376c38062f77ce2b1e703876aaa04662f96355cdf5dc9d0d075302b05
```

## Verification Report

**Change**: persistence-foundation (Ola 3 / F11 / #124)
**Version**: N/A (delta specs)
**Mode**: Strict TDD
**Branch**: `feat/persistence-foundation-smc` (HEAD `20c6787`), chain: tracker `feat/persistence-foundation` (`2db9262`) ← S1 `feat/persistence-foundation-drawings` (`025a381`) + S2 `feat/persistence-foundation-smc` (`20c6787`). Confirmed: slice PRs base on the tracker, S2 contains S1.

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total | 27 (WU1 1.1–1.7 = 7; WU2 2.1–2.6 = 10 incl. 2.6b; Phase 3 = 3; guard matrix = 11) |
| Tasks complete | 27 (apply-progress reports all `[x]`; `tasks.md` checkboxes left unmarked per session contract — see S1) |
| Tasks incomplete | 0 |

### Build & Tests Execution
**Build**: ✅ Passed — `makemigrations --check --dry-run` → `No changes detected` (exit 0).

**Tests**: ✅ all green
```text
node --test "tests/js/**/*.test.js"                 → 162 passed, 0 fail (exit 0)   [expect 162 ✅]
.venv/bin/python -m pytest tests/ -rA               → 914 passed, 69 deselected (exit 0)
.venv/bin/python -m pytest tests/ --ignore=tests/web → 337 passed (exit 0)
.venv/bin/python -m pytest -m e2e -p no:randomly    → 65–69 pass, 0–4 flaky (class-C, see W1)
ruff check .                                         → All checks passed (exit 0)
ruff format --check .                                → 140 files already formatted (exit 0)
requirements.txt vs develop                          → empty diff (0 lines)
```

**Coverage**: 100% patch / threshold 100% → ✅ Above
```text
diff-cover --compare-branch=feat/persistence-foundation --fail-under=100
  web/market/quotes.py 100% | web/market/views.py 100% | web/trading/models.py 100%
  Total 22 lines, Missing 0 → 100%
diff-cover --compare-branch=develop --fail-under=100 (S1+S2)
  same files, Total 23 lines, Missing 0 → 100%
```

### Spec Compliance Matrix

**chart-drawings** (R1, R2, R4, R7 — 21 scenarios)
| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R1 | Many drawings coexist on one chart | `test_isolation.py > test_drawing_many_per_symbol_coexist` | ✅ COMPLIANT |
| R1 | Interval drop keeps every row | `test_migration_0012.py > test_0012_keeps_all_rows_forward_then_reverses_lossily` | ✅ COMPLIANT |
| R1 | JSON round-trip | `test_isolation.py > test_drawing_json_round_trip` | ✅ COMPLIANT |
| R1 | Destructive migration order | `test_migration_0012.py` (real graph; order proven by outcome — index absent/column dropped/new index present) | ✅ COMPLIANT |
| R1 | Reverse is lossy | `test_migration_0012.py` (`interval` all `"1m"`) | ✅ COMPLIANT |
| R2 | GET with no drawings returns empty list | `test_market_api.py > test_drawings_get_empty_returns_empty_list_not_404` | ✅ COMPLIANT |
| R2 | GET lists only the caller's symbol | `test_market_api.py > test_drawings_get_lists_only_the_requested_symbol` | ✅ COMPLIANT |
| R2 | POST creates a row with id | `test_drawings_post_then_get_lists_the_row_with_id` | ✅ COMPLIANT |
| R2 | Stale interval accepted and ignored | `test_drawings_post_accepts_and_ignores_stale_interval` | ✅ COMPLIANT |
| R2 | DELETE by id removes the row | `test_drawings_delete_own_removes_the_row` | ✅ COMPLIANT |
| R2 | DELETE miss is 404 | `test_drawings_delete_miss_is_404` | ✅ COMPLIANT |
| R2 | Unauthenticated → redirect | `test_drawings_anonymous_{get,post,delete}_redirects_to_login` | ✅ COMPLIANT |
| R2 | CSRF enforced on write | `test_drawings_post_requires_csrf` / `test_drawings_delete_requires_csrf` | ✅ COMPLIANT |
| R4 | Unknown kind → 400 before write | `test_drawings_post_invalid_payload_is_400_and_writes_nothing` | ✅ COMPLIANT |
| R4 | Interval in body never 400 | `test_drawings_post_accepts_and_ignores_stale_interval` | ✅ COMPLIANT |
| R4 | Bad shape for kind → 400 | `test_parse_drawing_rejects_bad_input` / `...invalid_payload...` | ✅ COMPLIANT |
| R7 | Reload restores saved drawings | E2E `test_boot_restores_saved_drawings` | ✅ COMPLIANT |
| R7 | Symbol switch clears then loads | E2E `test_symbol_switch_clears_then_loads_drawings` | ✅ COMPLIANT |
| R7 | Interval-only switch keeps drawings | E2E `test_interval_switch_keeps_drawings` | ✅ COMPLIANT |
| R7 | Failed fetch is non-fatal | E2E `test_failed_drawings_fetch_is_non_fatal` | ✅ COMPLIANT |
| R7 | Seam stays 8 keys | E2E `test_smc_toggle_persists_across_reload` (`Object.keys(...).length === 8`) | ✅ COMPLIANT |

**smc-overlay** (R7 — 4 scenarios)
| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R7 | Toggle hides a family without refetch | E2E `test_smc_toggle_hides_family_without_refetch` | ✅ COMPLIANT |
| R7 | Toggle survives reload | E2E `test_smc_toggle_persists_across_reload` | ✅ COMPLIANT |
| R7 | Toggles do not reset on interval switch | E2E `test_smc_toggle_survives_interval_switch` | ✅ COMPLIANT |
| R7 | Failed fetch is non-fatal | E2E `test_smc_boot_preference_fetch_failure_defaults_all_on` | ✅ COMPLIANT |

**chart-config** (R8, R9 — 12 scenarios)
| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R8 | One row per user | `test_isolation.py > test_chart_preference_one_row_per_user` | ✅ COMPLIANT |
| R8 | Additive migration 0013 | `makemigrations --check` green + `test_preference_smc_field_round_trips_json` | ✅ COMPLIANT |
| R8 | Field round-trip | `test_preference_smc_field_round_trips_json` | ✅ COMPLIANT |
| R9 | GET default when no preference | `test_preference_get_default_includes_empty_smc` | ✅ COMPLIANT |
| R9 | Partial PUT applies only present keys | `test_preference_partial_put_smc_applies_only_smc` / `test_preference_partial_put_updates_only_present_key` | ✅ COMPLIANT |
| R9 | smc round-trips through the API | `test_preference_put_smc_then_get_round_trip` | ✅ COMPLIANT |
| R9 | Invalid theme → 400 | `test_preference_put_invalid_theme_is_400_and_writes_nothing` | ✅ COMPLIANT |
| R9 | Invalid smc → 400 | `test_preference_put_invalid_smc_non_object_is_400_and_writes_nothing` | ✅ COMPLIANT |
| R9 | Invalid scale_mode → 400 | `test_preference_put_invalid_scale_mode_is_400_and_writes_nothing` | ✅ COMPLIANT |
| R9 | Invalid chart_type → 400 | `test_preference_put_invalid_chart_type_is_400_and_writes_nothing` | ✅ COMPLIANT |
| R9 | Invalid interval → 400 | `test_preference_put_invalid_interval_is_400_and_writes_nothing` | ✅ COMPLIANT |
| R9 | Unauthenticated → redirect | `test_preference_anonymous_{get,put}_redirects_to_login` | ✅ COMPLIANT |

**per-user-isolation** (R14.2 — 10 scenarios)
| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R14.2 | A cannot read B's ExchangeCredential / Watchlist / PositionSnapshot / AccountSnapshot / Trade / ChartLayout / styled ChartLayout / per-symbol Drawing / AlertRule / ChartPreference | `test_isolation.py` (10 dedicated tests) | ✅ COMPLIANT |

**Compliance summary**: 47/47 scenarios compliant (8/8 requirements).

### Correctness (Static Evidence)
| Requirement | Status | Notes |
|------------|--------|-------|
| R1 `Drawing` no `interval` | ✅ Implemented | Model drops the field; `Meta.indexes == [ix_drawing_user_symbol]` (22 chars ≤ 30); no unique constraint. Reproduced. |
| R1 `0012` op order | ✅ Implemented | `RemoveIndex(ix_drawing_user_sym_interval)` → `AlterField(default="1m")` → `RemoveField(interval)` → `AddIndex(ix_drawing_user_symbol)`. Independently reproduced on populated sqlite. |
| R1 reverse lossy | ✅ Implemented | `migrate trading 0011` re-adds `interval` all `"1m"`. Independently reproduced. |
| R2 GET per `(user, symbol)` only | ✅ Implemented | `Drawing.for_user(request.user).filter(symbol=symbol)` — no `interval`. Stray query key ignored. |
| R2 POST accept-and-ignore `interval` | ✅ Implemented | `_post_drawing` never reads `interval`; `create(user, symbol, kind, points, style)`. |
| R1/R7 adapter per symbol | ✅ Implemented | `loadDrawings(symbol)`; `createDrawing` body drops `interval`; `refreshDrawings()` → symbol. No interval literal except a comment. |
| R7 clear on symbol only | ✅ Implemented | `main.js::switchTo`: `if (symbolChanged) drawings.clearForSwitch()`; interval-only path returns before `refreshDrawings()`. |
| R7 `gen` guard + DEBT-8 | ✅ Implemented | `stream.js` byte-identical vs both tracker and develop; `stream.subscribe` untouched; live path uses `update()`/`host.updateCandle` only (no `setData`). |
| R8/R9 `ChartPreference.smc` | ✅ Implemented | `JSONField(default=dict)`; `0013` additive `AddField`; GET default `smc:{}`; `_preference_body` carries `smc`. |
| R7 `parse_smc` | ✅ Implemented | dict, keys ⊆ 6 `SMC_FAMILIES`, values `bool`; else `ValueError` → 400 no-write. |
| R7 boot apply + #68 | ✅ Implemented | `main.js` `smc.applyToggles(pref.smc)` at boot (no emit); toggle → `refreshSmc` (re-render from fetched payload, no refetch) → `bus.on("smc:toggles", …)` → debounced PUT. |
| Seam frozen 8 keys | ✅ Implemented | `window.marketChart` literal has exactly 8 keys; `marketChart.*` assignments = same 8. No 9th key. |
| Module ceiling | ✅ Implemented | `drawings.js` 300, `smc.js` 300, `main.js` 275; `test_module_size_guard` green (ceil 300). |
| Read-only boundary | ✅ Implemented | No settings/CSP/urls touched; `test_no_order_surface.py` + `test_owned_model_guard.py` green; `requirements.txt` unchanged. |

### Coherence (Design)
| Decision | Followed? | Notes |
|----------|-----------|-------|
| Drawings key `(user, symbol)` | ✅ Yes | Model + endpoint + adapter all per symbol. |
| `0012` op order + load-bearing `AlterField` | ✅ Yes | Reproduced; reverse survives on populated rows only because of the default. |
| Keep-all / no dedupe | ✅ Yes | 3 seeded rows (differing only by `interval`) all survive forward. |
| Reverse lossy | ✅ Yes | All rows `interval="1m"`. |
| POST accept-and-ignore `interval` | ✅ Yes | 201 with a row; never 400. |
| SMC home = `ChartPreference` | ✅ Yes | User-global; reuses partial-PUT. |
| `parse_smc` validation | ✅ Yes | Frozen 6-family vocabulary, bool values. |
| No `drawings.js` extract | ✅ Yes | Stays ≤300 (net-negative diff). |
| `_preference_defaults()` refactor (beyond design) | ✅ Acceptable | De-duplicates 3 default dicts; preserves 5-key shape; covered. |

### TDD Compliance (Strict TDD)
| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | "TDD Cycle Evidence" table present in apply-progress (Slice 2). |
| All tasks have tests | ✅ | 27/27 tasks have covering tests. |
| RED confirmed (tests exist) | ✅ | All named test files exist and run. |
| GREEN confirmed (tests pass) | ✅ | 914 pytest + 162 node pass on execution. |
| Triangulation adequate | ✅ | `parse_smc` matrix (non-dict/unknown-family/non-bool); drawings invalid-payload matrix; `resolveToggles` 3 cases. |
| Safety Net for modified files | ✅ | S1/S2 modified existing suites with deltas; new files verified new. |

**TDD Compliance**: 6/6 checks passed.

### Assertion Quality
**Assertion quality**: ✅ All assertions verify real behavior. Spot-checks found no tautologies, no ghost loops, no mock-heavy tests. `test_preference_smc_field_round_trips_json` asserts both the JSON round-trip and the `{}` default; the migration test drives real DDL and asserts exact row counts/interval values, not just "no error".

### Test Layer Distribution
| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit (Python) | ~30 | `test_market_api.py`, `test_isolation.py` | pytest |
| Integration (Python) | ~20 | `test_market_api.py`, `test_migration_0012.py` | pytest + Django test client |
| Unit (JS) | 3 | `tests/js/chart-controllers.test.js` (`resolveToggles`) | node:test |
| E2E | 9 | `test_market_e2e.py` (drawings + SMC) | Playwright |
| **Total** | — | — | |

---

### Adversarial Probes (independent, reproduced)
- **Migration (throwaway sqlite, real `migrate` CLI)**: seeded 3 pre-0012 rows (same symbol, differing `interval`) → `migrate trading 0012` kept all 3, dropped `interval`, replaced the index (`ix_drawing_user_symbol` present, `ix_drawing_user_sym_interval` gone); `migrate trading 0011` restored `interval` = `"1m","1m","1m"` (lossy) + old index. ✅
- **Endpoint (throwaway pytest)**: POST with stale `interval:"1h"` → 201; GET `?symbol=` and `?symbol=&interval=7m` returned identical bodies with the row; A≠B isolated (B sees `[]`). ✅
- **SMC (throwaway pytest)**: pref GET default `smc:{}`; PUT `{"range":false,"fvg":true}` round-trips; `smc:"nope"` / `{"bogus":true}` / `{"range":1}` each → 400 with no write and the prior value intact. ✅
- **Grep**: `Drawing` has no `interval` field; `stream.js` unchanged vs develop; no `setData` in the live path (comments only); `drawings.js`/`smc.js` = 300 lines; `window.marketChart` = 8 keys. ✅
- **Class-C E2E**: full-suite runs flaked on 4 pre-existing, **untouched** tests (`test_interval_chips_switch_and_reflect_store`, `test_toggle_adds_and_removes_panes`, `test_theme_round_trip_persists_across_reload`, `test_scale_and_type_round_trip_persists_across_reload`, `test_system_theme_follows_emulated_color_scheme`) with `Page.goto`/`wait_for_function` timeouts; the same tests and all 9 change-specific tests pass in isolation and on an idle run. Not introduced by this change.

### Issues Found
**CRITICAL**: None.

**WARNING**:
- **W1 — class-C E2E flake under load (DEBT-8)**: the E2E suite is non-deterministic when run end-to-end under resource pressure (run1 all-green, run2 1 failure, run3 4 failures — each a different, untouched test). The 9 change-specific E2E tests are deterministic in isolation. CI does not run E2E; judged as pre-existing infra flake, not a regression. **Warned, not blocking.**
- **W2 — `tasks.md` checkboxes unmarked**: 27/27 tasks are complete (apply-progress) but `openspec/changes/persistence-foundation/tasks.md` shows 0 `[x]` (session hard contract forbids editing `openspec/**`). Bookkeeping only; the archive phase owns the checkbox flip.

**SUGGESTION**:
- The "Destructive migration order" scenario is proven by outcome (wrong order fails on SQLite) rather than by inspecting the literal op list. An explicit `.sqlmigrate`/op-sequence assertion would make the requirement self-evident.

### Verdict
**PASS WITH WARNINGS**
Every spec scenario (47/47) has a covering test that passed at runtime; migration round-trip, endpoint contract, and SMC persistence independently reproduced; patch coverage 100%; no new dependency; read-only boundary and 8-key seam held. The only warning is the pre-existing class-C E2E flake (DEBT-8), which does not affect the change's own tests or CI.
