# Design: live-stream-race (issue #150, DEBT-1)

## Technical Approach

One guard in `stream.js::onPush` rejects any frame whose exchange channel
(`frame.ch`, e.g. `market_kline_1min`) does not match the active subscription's
channel (`config.channels[sub.interval]`). `sub` is the stream's own record of the
live subscription, updated synchronously inside `sendSubscribe` right after the
`unsubscribe` send — so any old-channel frame buffered through the switch window
is dropped before `host.updateCandle` / `series.update()`. The comparison is
extracted as a pure predicate `isFrameForChannel` in `chart-core.js` (Node-testable,
no DOM). `sub.interval` (not `state.interval`) drives BOTH the compare and
`bucketTime`, keeping bucket math consistent with the channel actually streamed.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|---|---|---|---|
| Frame identity | `frame.ch` | symbol-only; `gen` token; `state.interval` | `ch` verified upstream (`BasicWsRespEntity`: `ch`+`symbol`+`ts`). Self-identifying → no guessing. `gen` is scoped to `main` and cannot reach the socket handler. |
| Interval source | `sub.interval` for guard AND `bucketTime` | `state.interval` | `state.interval` is mutated synchronously in `switchTo` before the socket confirms; `sub` follows the actual subscribe. Mid-switch `sub` is the safer, coherent value. |
| Predicate home | `chart-core.js` (pure export) | private closure in `stream.js` | `onPush` is a closure; extracting the predicate gives a `node --test` seam and keeps JS out of the Python diff-cover scope. |
| Disposed guard | **None** (see below) | `host.isDisposed()` / null-series check | `build()` does `chart.remove()` + `createChart()` + `addSeries` synchronously; no event-loop frame can interleave. `updateCandle` already has `if (!candleSeries) return;`. |

### `frozen_predicate_api`

```js
// chart-core.js — deterministic, never throws.
function isFrameForChannel(frame, expectedChannel) {
  if (!frame || !expectedChannel) return false; // null frame / missing ch / unknown interval → fail closed
  return frame.ch === expectedChannel;          // exact string equality
}
export { ..., isFrameForChannel };
```
Truth: matching `ch` → true; foreign `ch` → false; `{}` (no `ch`) → false;
`ch:null` → false; `null` frame → false; `expectedChannel` undefined → false.

### `disposed_guard_decision`

**No second guard.** `chart-host.js::build()` removes and recreates the chart in
one synchronous block (`chart.remove()` → `createChart` → `addSeries`), so no WS
`onmessage` callback can run while `candleSeries` is null. The
`if (!candleSeries) return;` already in `updateCandle` is the belt-and-braces.
A stale-channel frame arriving after the rebuild is dropped by the channel guard
(`1min ≠ 5min`). A **same-channel** post-remove frame is unreachable for the same
synchronous reason.

## Data Flow

    ws.onmessage ──▶ onPush(m)
        │  !sub || m.symbol !== state.symbol?        ──▶ return
        │  !isFrameForChannel(m, channels[sub.interval])? ──▶ return   (NEW)
        │  t = Core.bucketTime(m.ts, sub.interval)                     (was state.interval)
        └─▶ host.updateCandle(bar) ──▶ series.update()   (#68: never setData)

## File Changes

| File | Action | Description |
|---|---|---|
| `web/market/templates/market/chart-core.js` | Modify | `+isFrameForChannel`, added to `export`. |
| `web/market/templates/market/controllers/stream.js` | Modify | `onPush`: channel guard; `bucketTime` on `sub.interval`. |
| `tests/js/chart-core.test.js` | Modify | Truth table for `isFrameForChannel`. |
| `tests/web/test_market_e2e.py` | Modify | Add `ch` to the two existing WS frames; new stale-channel E2E. |
| `openspec/changes/live-stream-race/specs/{market-chart,chart-live-stream}/spec.md` | Modify | R5 deltas (authored by `sdd-spec`). |

### `onPush` before/after

```js
// BEFORE
if (!sub || m.symbol !== state.symbol) return;
const t = Core.bucketTime(m.ts, state.interval);
// AFTER
if (!sub || m.symbol !== state.symbol) return;
if (!Core.isFrameForChannel(m, config.channels[sub.interval])) return;
const t = Core.bucketTime(m.ts, sub.interval);
```

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| JS unit | `isFrameForChannel` truth table (match, foreign, no-`ch`, null, null-expected) | `node --test tests/js` |
| E2E | Stale `1min` frame during a `5m` switch is dropped; a valid `5min` frame still grows the series | `page.route_web_socket` |
| E2E | Existing same-bucket + setData-spy frames gain `ch` (the guard would otherwise drop them) | Edit two existing frames |

**E2E `test_ws_stale_channel_push_during_switch`:** boot `1m`; select `5m` and
wait for the 5m series; read `T = last candle time`. Inject
`{ch:"market_kline_1min", symbol:"BTCUSDT", ts:(T-300)*1000+1000, data:{...}}` —
a 1s-in timestamp belonging to the **previous** 5m bucket, so the buggy
`bucketTime(ts,"5m") = T-300 < T` forces `Cannot update oldest data`. Assert:
no `pageerror`/console error containing `Cannot update oldest data` or
`Object is disposed`; series length unchanged and last time still `T`; the 5m
rebuild issued exactly one history `setData` (one `interval=5m` kline response);
spy `setData` on the settled series and assert `0` during the stale + a valid
`{ch:"market_kline_5min", ts:T+300}` push that grows the series by exactly 1.

## Guard / Edge Matrix

| Edge | Handling |
|---|---|
| Same-channel frame | applied (`true`) |
| Foreign-channel frame | dropped before `updateCandle` |
| Missing / null `ch` | dropped (fail closed) |
| Unknown interval (`channels[…]` undefined) | dropped |
| Post-`remove()` frame | stale-channel → dropped; same-channel → unreachable (synchronous rebuild) |
| Same-bucket frame | `upsertCandle` replaces in place (unchanged) |
| #68 single-write-path | `update()` only; E2E spy `=== 0` |
| Frozen 8-key seam | no new key; no new global |
| No-deps / CSP | no import, no inline script, `script-src` untouched |
| Multi-user boundary | client-only change; no server/DB/user data touched |

## Migration / Rollout

No migration, flag, DB, or CSP change. Single PR. **Rollback boundary**: revert
the branch — restore `onPush`, remove `isFrameForChannel` + its Node test, revert
the E2E and the two delta specs. Ripple: `config.channels[sub.interval]` is the
only coupling to the channel map; the entry `chart.js` is untouched.

## Open Questions

None blocking. Deliberate residual (out of scope, pre-existing, not #150): a
**new**-channel frame arriving after `subscribe(new)` but before `build()` runs
still hits the old series. A follow-up could key the guard/bucket on the host's
built interval instead of `sub.interval`; excluded here to keep the fix at the
reported race and the diff reviewable.
