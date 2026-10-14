# Tasks: live-stream-race (issue #150, DEBT-1, P0)

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low

Single PR. Strict TDD (`node --test` + E2E). Read-only: no `src/`, no new dep, CSP
unchanged, `window.marketChart` stays 8 keys, live path stays `update()`-only (#68).
Python touched only by `tests/web/test_market_e2e.py` (add `ch` to 2 frames + 1 new test).

## Guard/Edge Matrix

- [ ] **Predicate frozen**: `isFrameForChannel(frame, expectedChannel) -> bool`; pure, never throws, fail-closed, exported from `chart-core.js`.
- [ ] **No second disposed guard**: `build()` `remove→create` is synchronous; `updateCandle` already null-guards `candleSeries`.
- [ ] **Guard uses `sub.interval`** (NOT `state.interval`) for both the channel compare and `bucketTime`.
- [ ] **Foreign / missing `ch`** → dropped before `updateCandle`: no `update()`, no re-bucket, no `candle:closed`, no error.
- [ ] **Valid same-channel frame** still applies via `update()` in place.
- [ ] **#68 single-write-path**: E2E setData spy `=== 0`; no refetch/rebuild on drop.
- [ ] **8-key seam / no-new-dep / CSP**: nothing added to the seam, no import, `script-src` untouched.

## Phase 1 — Pure predicate (RED→GREEN)

- [ ] 1.1 **RED** `tests/js/chart-core.test.js`: truth table — matching `ch` → true; foreign `ch` → false; `{}`/`{ch:null}`/`{ch:""}`/`null` frame → false; empty `expectedChannel` → false; never throws. Acceptance: fails pre-1.2.
- [ ] 1.2 **GREEN** `web/market/templates/market/chart-core.js`: add pure `isFrameForChannel`, add to `export`. Acceptance: 1.1 green.

## Phase 2 — Guard in `onPush`

- [ ] 2.1 **GREEN** `web/market/templates/market/controllers/stream.js`: in `onPush` (first check, after the `sub`/`symbol` guard) drop when `!Core.isFrameForChannel(m, config.channels[sub.interval])`; change `bucketTime(m.ts, state.interval)` → `Core.bucketTime(m.ts, sub.interval)`. Acceptance: no second guard added; `node --test` green.

## Phase 3 — E2E

- [ ] 3.1 **GREEN** `tests/web/test_market_e2e.py`: add `"ch":"market_kline_5min"` to the 2 existing WS frames in `test_ws_same_bucket_updates_in_place` + `test_ws_stream_never_calls_setdata` (guard would otherwise drop them). Acceptance: both tests green.
- [ ] 3.2 **RED** new `test_ws_stale_channel_push_during_switch`: boot `1m`, switch to `5m`, read `T`; inject `{ch:"market_kline_1min", symbol:"BTCUSDT", ts:(T-300)*1000+1000, data:{...}}`. Assert no `pageerror` containing `Cannot update oldest data`/`Object is disposed`; series length unchanged, last time still `T`; exactly 1 rebuild `setData`; spy `=== 0`; then a valid `{ch:"market_kline_5min", ts:(T+300)*1000}` grows the series by exactly 1. Acceptance: fails pre-Phase 2.

## Phase 4 — Verify

- [ ] 4.1 `node --test tests/js` + `pytest -m e2e` + ruff green; confirm no new dep, CSP untouched, seam still 8 keys.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~60–90 (guard ~5, predicate ~10, Node test ~25, E2E ~40, specs ~10) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | single PR |
| Delivery strategy | single-pr |
| Chain strategy | stacked-to-main |

Single autonomous PR, trivial revert (restore `onPush`, drop predicate + tests).
