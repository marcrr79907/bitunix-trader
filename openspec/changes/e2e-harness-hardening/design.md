# Design: e2e-harness-hardening

## Technical Approach

Three coordinated edits, single PR, no runtime deps. **Product**: one guard in
`stream.js::subscribe` so a pre-boot interval switch opens the socket instead of
silently recording `sub` forever. **Harness**: `_wait_ready(page)` before the
interval switch in the 3 mocked-socket E2E tests (boot completes → socket open
when frames are injected). **Flake-hardening**: null-guard the 13 unguarded
`wait_for_function` predicates. **Docs**: docstring + one README dev note. A new
CI-run JS unit test pins the product invariant. `#68` (live writes = `update()`
only), the `gen` guards, and the DEBT-1 channel guard are untouched.

## Architecture Decisions

| Decision | Option A | Option B | Choice + rationale |
|---|---|---|---|
| Product fix site | `stream.subscribe` opens `connect` when `ws` absent | `main.switchTo` calls `stream.connect` | **A** — `stream` owns `ws`; `main` cannot see socket state. One guard at the single chokepoint all callers route through; B risks a duplicate socket. |
| Regression test | JS unit `tests/js/stream.test.js` + WebSocket stub | E2E switch-immediately-after-goto | **A** — runs in the CI `js-core` job, browser-free, deterministic, ~20 lines. E2E is deselected in CI (local-only). |
| Harness readiness | `_wait_ready(page)` (existing helper, ~20 users) | bounded `_poll(... "route" in holder)` | **A** — reuses the proven helper; boot-complete is the real precondition. |
| Predicate guard | insert `candleSeries &&` before `.data()` | wrap in try/wait-for-timeout | **A** — matches the already-guarded form (L663); Playwright then polls instead of surfacing a JS TypeError. |

## Product Fix (before / after)

```js
// BEFORE (stream.js:111) — pre-boot switch records sub, never connects.
function subscribe(next) {
  if (ws && ws.readyState === 1) sendSubscribe(next);
  else sub = next;
}

// AFTER — open the socket when none exists yet.
function subscribe(next) {
  if (ws && ws.readyState === 1) sendSubscribe(next);
  else if (!ws) connect(next); // pre-boot: no socket -> open it now
  else sub = next;             // connecting/closing: queue the newest key
}
```

`connect(next)` sets `sub` then `new WebSocket(...)` **synchronously**, so
`ws` is non-null immediately after; a second `subscribe` sees `ws` and takes
the `else` branch → **no duplicate socket**. On `onopen` the queued `sub` is sent
(new channel wins). `sendSubscribe`, `onPush`, and `isFrameForChannel` are
unchanged, so `#68` and the DEBT-1 stale-frame guard hold. `main.switchTo` and
its `gen` guards are not edited.

## Harness Fix (3 tests, one line each)

Insert `_wait_ready(page)` immediately after `page.goto(...)` and before
`page.select_option("#interval", "5m")` in:

- `test_ws_same_bucket_updates_in_place` (L371→372)
- `test_ws_stream_never_calls_setdata` (L420→421)
- `test_ws_stale_channel_push_during_switch` (L483→484)

With boot complete, `ws.readyState === 1`, so `switchTo` emits
`unsubscribe`+`subscribe` on the open socket and the `holder["route"]` assertion
is deterministic. No retry.

## Null-guard Predicates

Change the 13 predicates from
`window.marketChart && window.marketChart.candleSeries.data()...` to
`window.marketChart && window.marketChart.candleSeries && window.marketChart.candleSeries.data()...`
(lines 270, 291, 348, 374, 423, 486, 689, 828, 1086, 1144, 1975, 2023, 2071).
`.panes.*.rsi` / `.panes.*.macd` predicates are already guarded — no change.

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit (JS, CI) | `subscribe` opens exactly one socket when `ws` is null; a 2nd `subscribe` opens none | `tests/js/stream.test.js` — stub `globalThis.WebSocket`, assert construction count (RED pre-fix: 0). |
| E2E (dev-only) | Frame order, same-bucket update, `#68`, stale-frame drop | 3 WS tests now gated by `_wait_ready`; null guards remove the rotating class-B crash. |
| Static | Import boundary unchanged | existing `test_boundary.py` / dependency guard. |

## Guard / Edge Matrix

| Case | Pre-fix behavior | Post-fix | Guard |
|---|---|---|---|
| Switch before boot (real user) | socket never opens, dead stream | `subscribe` → `connect`, streams | `!ws` branch |
| `subscribe` while CONNECTING | records `sub` | records `sub` (no 2nd socket) | `else` branch |
| `subscribe` on open socket | unsub+sub | unchanged | `readyState===1` |
| Boot completes normally | — | `connect` from `start()`; `subscribe` not called pre-ready | `gen !== 0` unchanged |
| Stale channel frame | dropped | dropped | `isFrameForChannel` unchanged |
| Live candle write | `update()` only | `update()` only | `#68` unchanged |
| Predicate mid-boot (`candleSeries` null) | TypeError hard-fails | predicate `false` → poll | `candleSeries &&` |

## File Changes

| File | Action | Description |
|---|---|---|
| `web/market/templates/market/controllers/stream.js` | Modify | `subscribe`: `!ws` → `connect(next)`; comment updated |
| `tests/js/stream.test.js` | Create | WebSocket-stub unit test (no socket / no duplicate) |
| `tests/web/test_market_e2e.py` | Modify | `_wait_ready` in 3 WS tests; 13 predicates null-guarded; docstring line |
| `README.md` | Modify | One E2E dev note (`-m e2e -p no:randomly`, `playwright install chromium`) |

## Migration / Rollout

No migration, flag, or config change. Rollback: revert the branch — restore
`stream.js::subscribe`, the docstring/README, the 3 WS tests, delete
`tests/js/stream.test.js`. Zero runtime surface to unwind. E2E stays deselected
by `addopts`; CI gains one `node --test` file.

## Delivery

**Single PR**, ~80–140 changed lines (product ~4, JS test ~30, tests ~50, docs
~10), under the 400-line budget. `Decision needed before apply: No`;
`Chained PRs recommended: No`; `400-line budget risk: Low`.

## Open Questions

None blocking. Residual class C (SQLite + threaded `live_server`) stays
documented, not papered.
