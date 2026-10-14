# Proposal: live-stream-race

## Intent

P0 race (issue #150, DEBT-1). `stream.js::onPush` filters only `m.symbol`,
never the channel, so an old-channel frame buffered during `switchTo` is
re-bucketed with the NEW interval → stale `series.update()` → `Cannot update
oldest data` (and `Object is disposed` across `chart.remove()`). One dropped
invariant: a frame is applied regardless of whether its channel matches the
active subscription (#68 kin).

## Scope

### In Scope
- `stream.js::onPush` guard: reject `frame.ch !== config.channels[sub.interval]`;
  keep the `symbol` check; use `sub.interval` (not `state.interval`) for the
  compare and `bucketTime`.
- Pure `isFrameForChannel(frame, expectedChannel)` in `chart-core.js`.
- RED-first E2E: stale frame dropped, valid new-channel frame grows the series,
  `setData` spy stays 0.
- R5 delta specs: `market-chart`, `chart-live-stream`.

### Out of Scope
- WS transport/reconnect rewrite, `gen` token, host rewrite, disposed flag
  (only if RED proves it). New dep, npm/build, CSP relaxation. Order execution
  (read-only HARD).

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `market-chart`: R5 — frame-channel-matches-active-subscription MUST.
- `chart-live-stream`: R5 — reject non-active-channel frames.

## Approach

Frame identity = `frame.ch` (verified via BitUnix `BasicWsRespEntity`:
`ch`+`symbol`+`ts`). `sub` is the active-subscription record, authoritative
mid-switch where `state.interval` is mutated but the socket is unconfirmed.
One guard drops the stale frame before `updateCandle`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/market/templates/market/controllers/stream.js` | Modified | `ch` guard in `onPush` |
| `web/market/templates/market/chart-core.js` | Modified | pure `isFrameForChannel` |
| `tests/js/chart-core.test.js` | Modified | `node --test` predicate |
| `tests/web/test_market_e2e.py` | Modified | RED-first stale-channel E2E |
| `openspec/specs/{market-chart,chart-live-stream}/spec.md` | Modified | R5 delta |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Same-bucket regression | Med | exact string equality on `config.channels[sub.interval]`; keep `symbol` |
| Mock omits `ch` / vacuous RED | Med | mock emits `ch`; stale `ts` genuinely stale under new interval |
| Frozen 8-key seam | Low | no new seam key; reuse setData spy |
| Patch coverage | Low | predicate in `.js`; `node --test` + E2E |

## Rollback Plan

Revert the branch: restore `onPush`, remove `isFrameForChannel` + its Node test,
revert the E2E and two delta specs. No DB, dep, or CSP change.

## Dependency

None. `chart-core.js` UMD seam exists.

## Success Criteria

- [ ] `node --test tests/js` green (matching `ch` accepted, stale rejected).
- [ ] E2E: stale `1min` frame during `5m` switch → no `pageerror`, series
  unchanged; valid `5min` frame grows it by 1; `setData` spy === 0.
- [ ] `pytest`/ruff green; no new dep; CSP untouched.

## Review Workload Forecast

- Diff: **~60–90 lines** (guard ~5, predicate ~10, Node test ~25, E2E ~40, specs ~10).
- Decision before apply: No | Chained PRs: No | 400-line risk: Low
