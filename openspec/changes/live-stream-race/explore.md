# Exploration: live-stream-race (issue #150, DEBT-1, P0)

## Current State

The chart is a jQuery-free ESM app under `web/market/templates/market/`. The
live path is owned by `controllers/stream.js` (LEAF DI factory
`create({store,bus,host,config})`). It owns the socket, the ping/backoff timers
and a single mutable `sub = {symbol, interval}` key. On a push it calls
`host.updateCandle(bar)` — the ONE live candle write (`series.update()`, never
`setData`, #68).

`main.js::switchTo(symbol, interval)` bumps `gen`, mutates `state.symbol` /
`state.interval`, clears drawings/SMC, resets `host.setLastBucket(0)`, then
`stream.subscribe({symbol, interval})` and async-loads layout → build →
drawings → SMC → history, each step guarded by `if (mine !== gen) return`.

`stream.subscribe(next)`:
- socket OPEN → `sendSubscribe(next)`: `unsubscribe(old)` then `subscribe(new)`,
  then `sub = next` (assignment happens BETWEEN the two sends).
- socket not open → just `sub = next`.

`onPush(m)` (stream.js:21-35):
```js
if (!sub || m.symbol !== state.symbol) return;          // symbol guard only
const t = Core.bucketTime(m.ts, state.interval);         // uses state.interval
host.updateCandle(...);                                  // series.update()
```
The channel is a `(symbol, interval)` pair via `config.channels[interval]`, but
`onPush` filters ONLY on `m.symbol`. There is NO interval check and NO
subscription-generation token.

### Exchange frame shape (verified against the official demo repo)

Cloned `github.com/BitunixOfficial/open-api`. `BasicWsRespEntity` (the base of
`KlineResp`) is:
```java
private String ch;   // e.g. "market_kline_5min"
private Long   ts;   // frame timestamp (ms)
private T      data; // KlineItem { o,h,l,c,b,q }
```
`KlineResp` adds `symbol`. So a kline frame carries **`ch`, `symbol`, `ts`,
`data`** — the channel STRING is present on the frame and unambiguously encodes
the interval (`market_kline_<interval>`). The frame is therefore rejectable
WITHOUT guessing. (The E2E mock currently only sets `symbol/ts/data`, but real
frames carry `ch`.)

## Root Cause (confirmed)

`onPush` is interval-blind. The bug is a two-part stale-write:

**Interleaving that produces `Cannot update oldest data`:**
1. User is on channel `market_kline_1min`; `sub = {BTCUSDT,"1m"}`, series last
   time T₁.
2. `switchTo(BTCUSDT,"5m")` → `stream.subscribe({"5m"})` → `sendSubscribe`:
   `unsubscribe(1min)` is SENT, but a frame for `1m` was already in flight in
   the socket's receive buffer.
3. `sub = {"5m"}` (mid-`sendSubscribe`). `state.interval = "5m"` already.
4. The in-flight `1m` frame arrives → `onPush`: `m.symbol === state.symbol`
   passes; `bucketTime(m.ts, "5m")` is computed with the NEW interval over the
   OLD-interval timestamp → yields a bucket `t` that is `<=` the current series
   last time → `series.update(bar)` with a stale/out-of-order `time` → LWC v5
   throws `Cannot update oldest data`.
5. Separately, the `1m` frame may arrive AFTER `switchTo`'s async chain ran
   `buildChart()` → `chart.remove()` + `createChart()`; `updateCandle` writes to
   `candleSeries` of a removed chart → `Object is disposed`.

Both errors are the SAME missing invariant: a frame is applied regardless of
whether its channel still matches the active subscription. `Object is disposed`
is the narrower flavour where the push lands during/after the rebuild window
(`chart.remove()` in `host.build()` line 168). One guard keyed on the frame's
channel covers both, because a stale `1m` frame is stale for `5m` however far
along the switch has progressed.

## Affected Areas

- `web/market/templates/market/controllers/stream.js` — `onPush` (add interval
  guard), `sendSubscribe`/`sub` (source of truth for the active channel).
- `web/market/templates/market/main.js` — `switchTo` sets `state.interval` then
  calls `stream.subscribe`; ordering matters for which interval value `onPush`
  compares against.
- `web/market/templates/market/chart-host.js` — `build()` calls `chart.remove()`
  (line 168); `updateCandle` writes the live bar. No change expected (disposed
  protection is a rejection upstream, not a host rewrite).
- `tests/web/test_market_e2e.py` — new E2E reproducing the race via
  `page.route_web_socket`.
- `openspec/specs/market-chart/spec.md` (R5) and `chart-live-stream/spec.md`
  (R5) — delta specs add the interval-guard invariant.

## Approaches

### 1. Channel guard on the frame (`ch` vs `sub`)
`onPush` rejects when `m.ch !== config.channels[sub.interval]` (plus the existing
`symbol` check). The frame self-identifies its channel; `sub` is the active
subscription.
- Pros: uses a field the exchange actually sends; no new state; rejects BOTH the
  stale-time write and the disposed write; trivially unit-testable in Node if
  `onPush` is exposed (currently a closure — see open question).
- Cons: depends on the frame carrying `ch` (verified true upstream, but the
  current E2E mock omits it → mock must emit `ch`).
- Effort: Low.

### 2. Monotonic subscription token (`gen`-style) captured by the handler
Bump a `streamGen` in `sendSubscribe`/`connect`, capture it in the
`ws.onmessage` closure; reject if `captured !== streamGen`.
- Pros: no dependency on frame fields; mirrors the existing `gen` guard idiom.
- Cons: a frame that arrives BEFORE the token bump but from the old channel still
  passes (the unsubscribe/subscribe send itself is async); needs the handler to
  read current `sub` anyway for the disposed case; more moving parts than
  approach 1 for the same outcome.
- Effort: Low–Medium.

### 3. Monotonic `bar.time` insensitivity in the host
Swallow `update()` when `bar.time < last`.
- Pros: last-line defense.
- Cons: hides the real bug; `bucketTime` mis-computes with the wrong interval so
  `t` can equal (not be less than) the last time; does not address the disposed
  write; changes host semantics.
- Effort: Low, but wrong layer.

## Recommendation

**Approach 1 (channel guard), combined with using `sub.interval` (not
`state.interval`) as the authoritative interval in `onPush`.**

Rationale:
- The frame's `ch` is the honest identity of the channel (verified upstream).
  Comparing it to `config.channels[sub.interval]` rejects any old-interval frame
  deterministically, no guessing.
- `sub` is the stream's own record of the active subscription and is updated in
  `sendSubscribe`/`subscribe`. During the switch window `state.interval` is set
  synchronously in `switchTo` BEFORE the async chain, while `sub` follows the
  socket's actual subscribe. Using `sub.interval` for BOTH the channel compare
  and `bucketTime` keeps the bucket math consistent with the channel being
  streamed. (`state.interval` and `sub.interval` converge once the switch
  settles; `sub` is the safer mid-switch value.)
- This single guard also covers `Object is disposed`: a stale-channel frame is
  dropped before it ever reaches `updateCandle`. A frame from the NEW channel
  that lands after `chart.remove()` but before the new `build()` completes is a
  residual window — mitigate with a minimal host-side disposed check ONLY if the
  E2E proves it reachable (recommended: add `if (!candleSeries) return;` is
  already present in `updateCandle`; but `build()` reassigns `candleSeries`
  synchronously, so the practical window is the synchronous `remove→create`
  gap, which no async frame can interleave). **Decision: channel guard only;
  no separate disposed flag unless RED-first test proves it.** See Open
  Questions.

Minimal diff: ~3 lines in `onPush` + use `sub.interval` in `bucketTime`. No new
runtime dependency, no CSP change, still `update()`-only.

## Test Harness

`page.route_web_socket("wss://fapi.bitunix.com/**", handler)` is installed
BEFORE `goto`; `handler(ws_route)` stores the route, tests call
`route.send(json.dumps(frame))` to inject a frame (see
`test_ws_same_bucket_updates_in_place`, `test_ws_stream_never_calls_setdata`).
Frames today are `{symbol, ts, data:{o,h,l,c}}` — the new tests MUST include the
`ch` field the real exchange sends (`market_kline_<interval>`).

**RED-first E2E (`test_ws_stale_channel_push_during_switch`):**
1. `page.on("pageerror", ...)` and `page.on("console", ...)` collectors.
2. Install the WS route, `goto`, `_wait_ready(page)`.
3. Switch to `5m` (`page.select_option("#interval","5m")`), wait for the 5m
   subscribe frame to appear in the captured `frames` list.
4. Inject a frame carrying `ch:"market_kline_1min"` with a `ts` inside the LAST
   5m bucket (so `bucketTime(ts,"5m")` would be `<=` the series last time).
5. Assert: no `pageerror`/console error containing `Cannot update oldest data`
   or `Object is disposed`; the series length is unchanged by the stale frame;
   the last candle time is the correct 5m bucket.
6. Inject a VALID `ch:"market_kline_5min"` frame in the next bucket → assert the
   series grows by exactly 1 (legitimate path still works).
7. `setData` spy after history load (copy of `test_ws_stream_never_calls_setdata`)
   → assert `=== 0` (update()-only preserved).

Earlier variant to consider: inject the stale `1m` frame in the SAME tick as the
`switchTo` dispatch (before the 5m subscribe is confirmed) to exercise the
mid-`sendSubscribe` window directly; use `page.evaluate` to dispatch the
`config:changed` bus event and `route.send` back-to-back.

**Node unit:** `onPush` is currently a private closure. To unit-test the guard
cheaply, the smallest seam is to extract the predicate
(`isStaleFrame(frame, sub, config)`) into `chart-core.js` (pure) and unit-test
it in `tests/js/`. This also satisfies the "one runnable check" rule and keeps
`patch-coverage` honest (JS is verified by `node --test`, not Python coverage).

## Open Questions / Decisions

1. **Frame-identity source** — DECIDED: `frame.ch` (verified upstream). The E2E
   mock must be upgraded to emit `ch`.
2. **Guard location** — DECIDED: `stream.js::onPush` (where the subscription
   lives). Extract the pure predicate to `chart-core.js` for Node coverage.
3. **`state.interval` vs `sub.interval`** — RECOMMENDED: `sub.interval` is
   authoritative in `onPush` (channel + bucket math). Confirm during RED: with
   `state.interval` the guard would also pass for the new channel but the bucket
   math could already be wrong for a frame that raced the state mutation.
4. **Disposed-chart guard** — DEFERRED: add a flag only if the RED test shows a
   frame from the NEW channel reaching a removed series. The synchronous
   `remove→create` in `build()` makes this unlikely; do not add speculative
   state.
5. **`gen` token vs channel compare** — DECIDED: channel compare (approach 1);
   the `gen` guard is scoped to main's orchestration and does not cleanly reach
   the socket handler.

## Risks

- **Breaking the legitimate same-bucket path** — the guard must compare the
  ACTIVE channel exactly; a too-strict compare (e.g. exact object identity) would
  drop valid `5m` frames. Mitigate: string equality on
  `config.channels[sub.interval]`, plus the existing `symbol` check.
- **E2E mock fidelity** — the mock currently omits `ch`; tests must add it, and
  the injected stale frame must use a `ts` that would genuinely produce a stale
  bucket under the new interval, else the RED test is vacuous.
- **Frozen `window.marketChart` 8-key seam** — no new seam key; the setData spy
  pattern is reused. Adding a seam key would break the frozen-shape assertion in
  `test_market_ux.py` / E2E.
- **No-deps / CSP** — pure JS change; no new import, no inline script, CSP
  untouched.
- **Patch coverage** — the JS guard is covered by `node --test` (pure predicate)
  + E2E; no lib change, so the Python patch gate is unaffected. Keep the pure
  predicate in a `.js` file (JS is excluded from the Python diff-cover scope).

## Ready for Proposal

**Yes.** Root cause is confirmed with code + upstream-frame evidence, the guard
approach is chosen and minimal, and the test harness is proven (the three
existing `test_ws_*` tests show exactly how to inject frames). The proposal
should scope: (a) `ch`/`sub.interval` guard in `onPush`, (b) pure predicate in
`chart-core.js` + Node test, (c) RED-first E2E two new scenarios (stale-reject +
valid-still-works, setData spy), (d) delta specs to `market-chart` R5 and
`chart-live-stream` R5. No dependency, no CSP, no seam change.
