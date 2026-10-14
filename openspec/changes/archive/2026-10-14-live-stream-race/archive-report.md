# Archive Report: live-stream-race

**Archived**: 2026-10-14
**Verdict**: `pass` (0 blockers, 0 critical, 0 warnings; 3/3 requirements, 18/18
scenarios COMPLIANT) — `market-chart` R5 update (frame-channel guard) +
`chart-live-stream` R1 update (pure `isFrameForChannel`) + R5 update (frame-channel
invariant + stale-drop + E2E contract).
**Delivery**: Single PR — #151 (no chain), merged to `develop`.
**Issue**: #150 (DEBT-1, P0) — first DEBT issue; part of the debt pass before Ola 3.
**Branch**: `fix/live-stream-race` (verify HEAD `36d46ee`) → `develop`.

## What Shipped

The P0 live-stream race is fixed at the root with ONE guard. `stream.js::onPush`
previously filtered only `m.symbol`, never the channel, so an old-channel frame
buffered during `switchTo` was re-bucketed under the NEW interval → stale
`series.update()` → `Cannot update oldest data` (and `Object is disposed` across
`chart.remove()`).

| Area | Delivered |
|------|-----------|
| Pure predicate | `web/market/templates/market/chart-core.js` — new `isFrameForChannel(frame, expectedChannel) -> boolean`: pure (no imports/DOM), fail-closed (`if (!frame \|\| !expectedChannel) return false;`), exact string equality on `frame.ch`, never throws, exported. |
| Channel guard | `web/market/templates/market/controllers/stream.js` — `onPush` drops any frame where `!Core.isFrameForChannel(m, config.channels[sub.interval])`, and buckets with `Core.bucketTime(m.ts, sub.interval)` (was `state.interval`). `sub.interval` is authoritative for BOTH compare and bucket, since `state.interval` is mutated before the socket confirms the switch. |
| One guard, both errors | The same line, placed BEFORE `updateCandle`, covers the out-of-order write (`Cannot update oldest data`) and the post-`chart.remove()` write (`Object is disposed`). No second disposed guard; `build()`'s `remove→create` is synchronous and `updateCandle` already null-guards `candleSeries`. |
| Tests | `tests/js/chart-core.test.js` (+2 tests: exact-channel truth table, fail-closed + no-mutation + no-throw); `tests/web/test_market_e2e.py` (+1 RED-first test `test_ws_stale_channel_push_during_switch`, +`ch` added to the 2 existing WS frames so the guard does not drop them). |
| Specs | `openspec/specs/market-chart/spec.md` R5; `openspec/specs/chart-live-stream/spec.md` R1 + R5. |

## Requirements Satisfied

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| market-chart | R5 — Live candles over browser WS (MODIFIED) | ✅ Frame-channel guard: a push applies ONLY when `frame.ch` equals the subscribed channel; `sub.interval` authoritative for compare + bucket; drop before `updateCandle` (no update/re-bucket/`candle:closed`/error); one guard covers both errors; no refetch/rebuild/`setData` (#68 held). 4 scenarios added. |
| chart-live-stream | R1 — Pure series core (MODIFIED) | ✅ `isFrameForChannel` added to the pure export set; frozen signature `(frame, expectedChannel) -> boolean`; fail-closed on missing/empty `ch` or `expectedChannel`; no input mutation; native ESM load in Node + browser. 2 scenarios added. |
| chart-live-stream | R5 — Single write path in the adapter (MODIFIED) | ✅ Frame-channel invariant: apply ONLY when `isFrameForChannel(frame, config.channels[sub.interval])`; drop costs no network work and issues no `setData`; the single guard also absorbs post-`chart.remove()` `Object is disposed`. 4 scenarios added. |

R1–R4 and R6–R21 (`market-chart`) and R2–R4, R6–R7 (`chart-live-stream`) preserved
untouched. No requirement dropped.

## RED → GREEN (independently reproduced)

The verifier did NOT trust the apply report. It backed up `stream.js`, scratch-removed
the guard line and restored `bucketTime(m.ts, state.interval)`, then ran the new E2E:
`test_ws_stale_channel_push_during_switch` **failed** with
`AssertionError: ['Cannot update oldest data, last time=[object Object], new
time=[object Object]']` — the exact P0 error, from the exact new test. Restoring
`stream.js` (byte-identical to HEAD; `git diff` empty) made it pass (3/3 WS tests).
The RED is genuine and non-vacuous: the injected stale frame uses
`ts=(T−300)*1000+1000`, which under the buggy `state.interval="5m"` bucket math
re-buckets to `T−300 < T`.

## Gates

`node --test "tests/js/**/*.test.js"` **134 passed** (exit 0); E2E
`pytest -m e2e -p no:randomly -q -o addopts=""` **52 passed, 887 deselected**
(exit 0); `pytest tests/ --ignore=tests/web -q` **337 passed** (exit 0);
`ruff check . && ruff format --check .` clean (135 files, exit 0). L2 patch coverage
**N/A by design** — zero Python product code changed (only
`tests/web/test_market_e2e.py`, excluded from patch-coverage `source`); `.js` logic
covered by `node --test` + Playwright. `requirements.txt` and `src/` diffs vs
`origin/develop` empty; `window.marketChart` seam stays **8 keys**; no html/CSP file
touched. Diff: 10 files, +810/−2.

## Warnings Carried (non-blocking)

- **G1 — residual NEW-channel race, documented not fixed.** A frame from the *new*
  channel arriving after `subscribe(new)` but before `build()` runs still lands on
  the pre-rebuild series. Design.md flags this as pre-existing (the old code had no
  guard at all) and explicitly out of #150's reported scope. A follow-up could key
  the guard/bucket on the host's built interval instead of `sub.interval`. Recorded
  here so it is not mistaken for a regression.
- **G2 — `tasks.md` checkboxes unmarked.** The apply executor contract forbids
  editing `openspec/**` content, so the acceptance checkboxes stay `[ ]`; every
  acceptance artifact exists and passes at runtime. Reconciled at archive per the
  process decision (F0/F1/F2 + chart-scales precedent). Not a finding.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| market-chart | Updated | R5 modified — added the frame-channel guard paragraph + 4 scenarios (stale-channel dropped, valid-channel applies, disposed chart never receives, guard is update-only). R1–R4/R6–R21 preserved untouched |
| chart-live-stream | Updated | R1 modified — pure set now includes `isFrameForChannel` + frozen predicate contract + 2 scenarios (exact-channel match, fail-closed); R5 modified — frame-channel invariant paragraph + 4 scenarios (stale fails invariant, same-channel same-bucket applies, guard survives rebuild, E2E drop/apply/update-only contract). R2–R4/R6/R7 preserved untouched |

## Carry-forward

- **G1 remains open** (pre-existing, out of #150 scope) — candidate for a follow-up
  guard keyed on the host's built interval.
- **First DEBT issue closed.** Part of the debt pass before Ola 3; frozen seams
  (layered ESM inventory, 8-key `window.marketChart`, `window.SmcOverlayCore`,
  #68 single-write-path, per-user ownership) remain in force.

## SDD Cycle Complete

Planned (explore/proposal/design/tasks) → implemented (single PR #151) → verified
(`pass`; RED→GREEN independently reproduced) → merged to `develop` → archived.

Traceability: `openspec/changes/archive/2026-10-14-live-stream-race/`
(explore, proposal, design, specs, tasks, verify-report); engram
`sdd/live-stream-race/{archive-report,proposal,spec,design,tasks,verify-report}`.
