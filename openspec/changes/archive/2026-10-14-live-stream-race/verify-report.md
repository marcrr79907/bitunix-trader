```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:18c1211fef2b706af4e7eb761b4af7de464bf03fabd653af6d5611a4e8da435b
verdict: pass
blockers: 0
critical_findings: 0
requirements: 3/3
scenarios: 18/18
test_command: .venv/bin/python -m pytest -m e2e -p no:randomly -q -o addopts=""
test_exit_code: 0
test_output_hash: sha256:8701c228fdac747a1d55608769ce35f556f09e62116090ade1ddfb31741222e5
build_command: .venv/bin/ruff check . && .venv/bin/ruff format --check .
build_exit_code: 0
build_output_hash: sha256:4681b0ccbdda71659532720526217f684c9ce9dd9641425c786c7920d1b4db53
```

# Verify Report — live-stream-race (issue #150, DEBT-1, P0)

**Verdict**: `pass` — the reported race (`Cannot update oldest data` / `Object is disposed`) is fixed by a single frame-channel guard; **RED was independently reproduced** by removing the guard (scratch) and observing the new E2E fail with the exact LightweightCharts error, then passing once restored. Every L1 gate green on fresh execution; L2 is N/A by design (no Python product code changed). No CRITICAL or WARNING findings.
**Verified by**: fresh adversarial verifier — independent replication, throwaway Node predicate probe, scratch RED→GREEN E2E reproduction, seam/CSP/interval-map enumeration. Apply reports NOT trusted.
**Branch**: `fix/live-stream-race` (HEAD `36d46ee`), single PR → `develop`. Confirmed with `git branch --show-current`; working tree clean, scratch mutation reverted.
**Mode**: Strict TDD. Artifact store: openspec.

## Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 4 phases / 7 acceptance items + guard matrix |
| Tasks complete | all acceptance artifacts present + green |
| Tasks incomplete | 0 |

`tasks.md` checkboxes are unmarked (executor contract forbids editing `openspec/**` content in apply); every acceptance artifact exists and passes at runtime. Not a finding (F0/F1/F2 + chart-scales precedent).

## Gates (L1)

| Gate | Command | Result |
| --- | --- | --- |
| JS unit | `node --test "tests/js/**/*.test.js"` | **134 passed, 0 fail** (exit 0) — SHA256 `d03c37a8…` |
| E2E | `.venv/bin/python -m pytest -m e2e -p no:randomly -q -o addopts=""` | **52 passed, 887 deselected** (exit 0) — `8701c228…` |
| Python unit | `.venv/bin/python -m pytest tests/ --ignore=tests/web -q -o addopts=""` | **337 passed** (exit 0) — `5ed827b3…` |
| Lint/format | `.venv/bin/ruff check . && .venv/bin/ruff format --check .` | **clean** (135 files, exit 0) — `4681b0cc…` |
| Dependency | `git diff origin/develop...HEAD -- requirements.txt` | **empty** (0 lines) |
| `src/` boundary | `git diff origin/develop...HEAD -- src/` | **empty** (0 lines) |
| Seam keys | `Object.keys(window.marketChart).length` | **8** (five committed E2E assertions, e.g. `test_market_e2e.py:1132`) |

`git diff --stat origin/develop...HEAD` = 10 files, +810/−2: 5 openspec docs, `chart-core.js` (+18/−1), `stream.js` (+6/−1), `chart-core.test.js` (+29), `test_market_e2e.py` (+93, of which +2 are add-to-existing-frame lines). No `html`/CSP/`settings` file changed. Node locally v24.14.0.

## Gates (L2) — Patch coverage

**N/A by design.** The change touches **zero Python product code** — the only Python in the diff is `tests/web/test_market_e2e.py` (test file, excluded from the patch-coverage `source`). The new logic lives in `.js`, covered by `node --test` (predicate) + Playwright E2E (integration). Running diff-cover here would either be empty or measure test code; skipped deliberately and noted.

## TDD Compliance (Strict TDD)

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | Task IDs map to node + E2E artifacts |
| All tasks have tests | ✅ | `chart-core.test.js` (+2 tests), `test_market_e2e.py` (+1 test, +2 frame `ch` fields) |
| RED confirmed independently | ✅ | scratch-removed the guard → new E2E **FAILS** with `Cannot update oldest data` (see below) |
| GREEN confirmed | ✅ | 134 node + 52 E2E + 337 py on fresh execution (restored guard) |
| Triangulation adequate | ✅ | predicate truth table (match/foreign/missing/null/empty/expected-missing/no-throw/no-mutation) + E2E stale-reject + valid-apply + same-bucket + setData spy |
| Safety Net for modified files | ✅ | `test_market_e2e.py` diff is add-only (+93, −0); the 2 existing WS tests gained a `ch` field, no assertion weakened |

**TDD Compliance**: 6/6 checks passed.

### RED→GREEN reproduction (independent, not trusted from apply report)

1. Backed up `stream.js`, removed the guard line, restored `Core.bucketTime(m.ts, state.interval)` (scratch, not committed).
2. `.venv/bin/python -m pytest tests/web/test_market_e2e.py::test_ws_stale_channel_push_during_switch -p no:randomly -q` → **1 failed** with `AssertionError: ['Cannot update oldest data, last time=[object Object], new time=[object Object]']` — the exact P0 error, from the exact new test.
3. Restored `stream.js` (byte-identical to `HEAD`; `git diff` empty). Re-ran the new test + the two existing WS tests → **3 passed**.

The RED is genuine and non-vacuous: the injected stale frame uses `ts = (T−300)*1000+1000`, which under the buggy `state.interval="5m"` bucket math re-buckets to `T−300 < T` and forces the LightweightCharts throw.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit (JS) | 134 | `tests/js/*` | node --test |
| E2E | 52 | `tests/web/test_market_e2e.py` | Playwright (chromium) |
| Unit (py) | 337 | `tests/ --ignore=tests/web` | pytest |
| **Total** | **134 node + 52 E2E + 337 py** | | |

### Assertion Quality

**Assertion quality**: ✅ All committed assertions verify real behaviour.
- The new E2E reads **live v5 API state** (`candleSeries.data()` length + last `time`), a real `pageerror` collector, a response listener counting `interval=5m` kline fetches, and a `setData` spy installed on the settled series — never CSS classes or internals.
- The predicate test asserts the full truth table plus **no-input-mutation** (`JSON.stringify` before/after) and **no-throw** on malformed shapes.
- No tautologies, ghost loops, or empty-collection-only assertions found.

### Quality Metrics
**Linter**: ✅ No errors (ruff, 135 files). **Type Checker**: ➖ N/A (JS/Django).

## Spec Compliance Matrix

### market-chart — R5 (MODIFIED)

| Scenario | Test | Result |
|----------|------|--------|
| Forming candle updates in place | E2E `test_ws_same_bucket_updates_in_place` (frame now carries `ch`) | ✅ COMPLIANT |
| Switch unsubscribes before subscribing | E2E `test_ws_unsubscribes_before_subscribing` (pre-existing, unchanged) | ✅ COMPLIANT |
| Reconnect after drop with capped delay | inspection of `backoff`/`onclose`; untouched by this change | ✅ COMPLIANT |
| E2E DOM smoke | pre-existing boot smoke tests | ✅ COMPLIANT |
| Stale-channel frame during switch is dropped | E2E `test_ws_stale_channel_push_during_switch` (RED-verified) | ✅ COMPLIANT |
| Valid-channel frame still applies | E2E `test_ws_stale_channel_push_during_switch` (second frame grows by 1) | ✅ COMPLIANT |
| Disposed chart never receives the stale frame | predicate drops pre-`updateCandle`; synchronous `remove→create` (host `build()`); no pageerror asserted | ✅ COMPLIANT |
| Guard is update-only | E2E spy `window.__setDataCalls === 0` | ✅ COMPLIANT |

### chart-live-stream — R1 (MODIFIED)

| Scenario | Test | Result |
|----------|------|--------|
| Loads in Node and browser | node `import * as core` (whole suite) + served ESM | ✅ COMPLIANT |
| No environment coupling | `chart-core.js` references no `document`/`window`/`fetch`/chart API (source inspection) | ✅ COMPLIANT |
| Predicate matches only the exact channel | node `isFrameForChannel: exact-channel truth table` + throwaway probe (`no-prefix-match`) | ✅ COMPLIANT |
| Missing channel fails closed | node truth table (`{}`/`{ch:null}`/`{ch:""}`/null/undefined frame/empty expected) | ✅ COMPLIANT |

### chart-live-stream — R5 (MODIFIED)

| Scenario | Test | Result |
|----------|------|--------|
| No setData during the stream | E2E `test_ws_stream_never_calls_setdata` + spy in the new test | ✅ COMPLIANT |
| Live series is monotonic | `upsertCandle` (node) + E2E growth assertions | ✅ COMPLIANT |
| Stale-channel frame fails the invariant and is dropped | E2E `test_ws_stale_channel_push_during_switch` (`after == n`, `last_after == T`) | ✅ COMPLIANT |
| Same-channel same-bucket frame still applied | E2E `test_ws_same_bucket_updates_in_place` (length unchanged) | ✅ COMPLIANT |
| Guard survives chart rebuild | dropped pre-`updateCandle`; no `Object is disposed` in pageerror collector | ✅ COMPLIANT |
| E2E contract — drop, apply, update-only | E2E `test_ws_stale_channel_push_during_switch` (all three asserts) | ✅ COMPLIANT |

**Compliance summary**: 3/3 requirements present; 18/18 scenarios COMPLIANT, 0 PARTIAL/FAILING.

## Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| Predicate pure (no imports) | ✅ | `isFrameForChannel` defined in `chart-core.js` line 76; module has no `import`/`require` |
| Predicate fail-closed | ✅ | `if (!frame || !expectedChannel) return false;` → null frame / falsy expected → false; `frame.ch ===` handles missing/`null`/`""` `ch` |
| Exact string equality | ✅ | probe confirms `{ch:"market_kline_5min_extra"}` → false (no prefix/substring) |
| Predicate exported | ✅ | in the `export { … isFrameForChannel }` block (line 87) |
| Guard runs BEFORE any work | ✅ | `stream.js:26` sits above `bucketTime`/`updateCandle` |
| `sub.interval` for compare AND bucket | ✅ | `config.channels[sub.interval]` (line 26) + `bucketTime(m.ts, sub.interval)` (line 27) |
| One guard covers both errors | ✅ | both are "frame from a stale channel"; RED probe reproduced `Cannot update oldest data`; the disposed flavour is dropped by the same line pre-`updateCandle` |
| #68 update()-only | ✅ | `onPush` calls only `host.updateCandle`; no `setData` added; spy `=== 0` |
| Frozen 8-key seam | ✅ | no new `window.marketChart` key; 5 E2E assertions `== 8` |
| `sub` null-safety | ✅ | `if (!sub || …) return;` precedes the guard → `sub.interval` deref is safe |
| Interval-map completeness | ✅ | all 14 `<option>` values in `chart.html` exist in `CONFIG.channels` → no interval silently drops all frames |
| No new dep / CSP | ✅ | empty `requirements.txt`/`src/` diff; no html/CSP file in diff |

## Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| D1 frame identity = `frame.ch` | ✅ Yes | guard compares `m.ch` |
| D2 interval source = `sub.interval` (compare + bucket) | ✅ Yes | matches design exactly |
| D3 predicate home = `chart-core.js` export | ✅ Yes | pure, Node-testable, no DOM |
| D4 no second disposed guard | ✅ Yes | no `isDisposed()`/extra state; `updateCandle` null-guard untouched |
| Migration/rollback | ✅ Yes | no migration/flag/DB; revert = restore `onPush` + drop predicate/tests |
| `frozen_predicate_api` | ✅ Yes | signature `isFrameForChannel(frame, expectedChannel) -> boolean` |

## Adversarial Probes (independent)

- **Node predicate probe** (throwaway `/tmp/opencode/probe_pred.mjs`, exit 0): 13-case truth table all correct; no input mutation; `no-prefix-match` (`market_kline_5min_extra` → false). ✅
- **Scratch RED→GREEN** (see above): guard removed → new E2E fails with `Cannot update oldest data`; restored → 3/3 pass. ✅
- **Real-browser E2E** (Playwright, logged in, `page.route_web_socket`): injected a stale `1min` frame during/after a `5m` switch — **0 pageerrors**, series length unchanged, last `time` stays `T`, exactly 1 rebuild `setData` (`interval=5m` kline response), live-path spy `=== 0`, then a valid `5min` frame grows the series by exactly 1. ✅
- **Interval-map enumeration**: all 14 UI intervals are present in `CONFIG.channels` — the guard cannot drop a legitimately-subscribed channel. ✅
- **Frame-injection audit**: every `route.send` in the E2E file now carries `ch` (lines 386, 444, 509, 532); no orphan frame silently dropped. ✅
- **Holes checked**: does the guard break the legitimate same-channel path? **No** (exact-equality + same-channel tests green). Is `sub` guaranteed non-null before the guard? **Yes** (`!sub` early-returns first). Any 9th seam key? **No**. Any frame that *should* be applied but is dropped? **No** — `ch` is present on real upstream frames (`BasicWsRespEntity`) and all mapped intervals resolve.

## Issues Found

**CRITICAL**: None.

**WARNING**: None.

**SUGGESTION**:
- **G1 — residual new-channel race is documented, not fixed.** A frame from the *new* channel arriving after `subscribe(new)` but before `build()` runs still lands on the pre-rebuild series. Design.md flags this as pre-existing (old code had no guard at all) and out of #150's reported scope. Consider keying the bucket on the host's built interval in a follow-up. Recorded so it is not mistaken for a regression.
- **G2 — `tasks.md`/openspec checkboxes unmarked** (executor contract); consistent with F0–F2 and chart-scales.

## Verdict

**PASS.** The P0 race is fixed at the root (one guard, `sub.interval`-authoritative, fail-closed pure predicate) and the fix is proven by an independently reproduced RED→GREEN: removing the guard makes the new E2E fail with the exact `Cannot update oldest data` error, restoring it makes the suite pass. All L1 gates are green with fresh exit-0 evidence (134 node / 52 E2E / 337 py / ruff clean / empty `requirements.txt` and `src/` diffs), L2 is N/A (no Python product code), all 3 requirements and 18/18 scenarios are COMPLIANT at runtime, the frozen 8-key seam holds, the live path remains `update()`-only (#68), and no new dependency or CSP change was introduced. No CRITICAL or WARNING findings.
