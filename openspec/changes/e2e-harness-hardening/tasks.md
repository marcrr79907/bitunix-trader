# Tasks: e2e-harness-hardening

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

## Guard/Edge Matrix (every row = a test/assertion in its WU)

- [ ] `subscribe` with `ws === null` constructs exactly 1 socket (R8) — JS `node --test`
- [ ] 2nd `subscribe` before open → still 1 socket (R8) — JS
- [ ] `subscribe` with OPEN `ws` → `sendSubscribe`, no new socket (R8) — JS
- [ ] `connect(next)` sets `ws` synchronously; queued `sub` sent on open (R8) — JS
- [ ] `#68` live writes: `setData` spy reads 0 during stream (R8, R23) — E2E
- [ ] DEBT-1 stale-frame drop: `isFrameForChannel` unchanged (R8) — E2E
- [ ] 3 WS E2E tests green with `_wait_ready` gated, no retry (R9, R23)
- [ ] Unguarded predicate mid-boot returns falsy, no `TypeError` (R9)

## WU1 — Product fix + JS regression (strict TDD, CI)

Base `main`. Depends: none. `node --test`. Headless (~35 lines).

- [ ] 1.1 **RED** `tests/js/stream.test.js`: stub `globalThis.WebSocket` (constructor counter, `readyState`); assert `subscribe({symbol,interval:"5m"})` on a null-`ws` stream constructs **1** socket.
- [ ] 1.2 **RED** assert a 2nd `subscribe` before open constructs **no** new socket; with an OPEN stub socket, `subscribe` sends `subscribe` frame and constructs none. RED pre-fix: first count 0.
- [ ] 1.3 **GREEN** `stream.js::subscribe` — add `else if (!ws) connect(next);` between the OPEN branch and `else sub = next;`; update the comment. `connect`/`sendSubscribe`/`onPush`/`isFrameForChannel` untouched; `main.js` unedited.
- [ ] 1.4 **GREEN** `node --test "tests/js/**/*.test.js"` green.
- [ ] 1.5 **Rollback**: revert `subscribe`; delete `tests/js/stream.test.js`.

## WU2 — Harness readiness (dev-only E2E)

Base WU1. Depends: WU1. Browser (~3 lines).

- [ ] 2.1 Insert `_wait_ready(page)` after `page.goto(...)` in `test_ws_same_bucket_updates_in_place` (L371→372).
- [ ] 2.2 Same in `test_ws_stream_never_calls_setdata` (L420→421) and `test_ws_stale_channel_push_during_switch` (L483→484). No retry wrapper.
- [ ] 2.3 **Rollback**: remove the 3 inserted lines.

## WU3 — Predicate null-guards (dev-only E2E)

Base WU2. Depends: WU2. Browser (~13 lines).

- [ ] 3.1 Insert `window.marketChart.candleSeries &&` before `.data()` in the 13 `wait_for_function` predicates: L270, 291, 348, 374, 423, 486, 689, 828, 1086, 1144, 1975, 2023, 2071.
- [ ] 3.2 Leave already-guarded `.rsi`/`.macd` pane predicates and bare `page.evaluate` reads unchanged.
- [ ] 3.3 **Rollback**: revert the 13 predicate strings.

## WU4 — Docs (R9)

Base WU3. Depends: WU2/WU3 (independent). Docs (~10 lines).

- [ ] 4.1 Extend `test_market_e2e.py` module docstring "Run locally": `python -m pytest -m e2e -p no:randomly` on an idle machine + boot-readiness note.
- [ ] 4.2 One `README.md` dev/E2E note pointing at the command and `playwright install chromium`.
- [ ] 4.3 **Rollback**: revert both doc edits.

## Phase 5 — Verification

- [ ] 5.1 `python -m pytest` green (e2e deselected); `ruff check . && ruff format --check .` green.
- [ ] 5.2 `node --test "tests/js/**/*.test.js"` green; `stream.test.js` RED-before/GREEN-after confirmed.
- [ ] 5.3 `playwright install chromium` then `python -m pytest -m e2e -p no:randomly` on an idle machine green; 3 WS tests pass without retry.
- [ ] 5.4 `git diff --stat` touches only `stream.js` + 2 test files + README; `main.js`, `pyproject.toml`, `.github/workflows` unchanged.

## Review Workload Forecast

- Estimated changed lines: **~80–140** (product ~4, JS test ~30, tests ~50, docs ~10).
- Suggested split: single PR (WU1 → WU2 → WU3 → WU4 as commits).
- Delivery strategy: single-pr.

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low
