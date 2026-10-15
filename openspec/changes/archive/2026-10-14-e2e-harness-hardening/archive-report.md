# Archive Report: e2e-harness-hardening

**Archived**: 2026-10-14
**Verdict**: `pass_with_warnings` (0 blockers, 0 critical; 3 non-blocking warnings —
W1 record correction, W2 residual class-C flake documented not fixed, W3 CI does not
run E2E) — `chart-live-stream` R8 + R9 (new) + `market-chart` R23 (new).
**Delivery**: Single PR — **#162** (no chain), merged to `develop`.
**Issue**: #149 (DEBT-8, P3) — **the final DEBT issue; this CLOSES the debt pass**.
**Branch**: `fix/e2e-harness-hardening` (verify HEAD `d42e9b5`) → `develop`.

## What Shipped

A mixed change: a small **product fix** + E2E harness hardening + docs. The
"environment flake" the verify reports of `chart-drawings` (W3), `smc-overlay`
(W4) and `chart-scales` (W3) had recorded was **actually a real product defect**
(see W1 below). Both were fixed at the root; no retry was introduced.

| Area | Delivered |
|------|-----------|
| Product fix | `web/market/templates/market/controllers/stream.js` — `subscribe(next)` now opens the socket when none exists: `if (ws && ws.readyState === 1) sendSubscribe(next); else if (!ws) connect(next); else sub = next;`. A subscription requested before boot completes (an interval/symbol switch firing before `start()` resolves) now calls `connect(next)` and streams the requested key, instead of only recording `sub` while `start()`'s `gen !== 0` guard aborts boot with no socket ever created. `connect`/`sendSubscribe`/`onPush`/`isFrameForChannel` untouched; `main.js` unedited (the `gen` guards are byte-identical). |
| CI-pinned regression | `tests/js/stream.test.js` (new) — stubs `globalThis.WebSocket` (constructor counter, `readyState`) and asserts: a first `subscribe` on a null-`ws` stream constructs exactly **1** socket; a 2nd `subscribe` before open constructs **none**; an OPEN-socket `subscribe` sends the `subscribe` frame and constructs none. This runs in the CI `node --test` job (unlike the E2E, which is deselected). RED pre-fix: first count 0. |
| Harness readiness gates | `tests/web/test_market_e2e.py` — `_wait_ready(page)` inserted after `page.goto(...)` and BEFORE `select_option("#interval", ...)` in the 3 mocked-socket WS tests (`test_ws_same_bucket_updates_in_place`, `test_ws_stream_never_calls_setdata`, `test_ws_stale_channel_push_during_switch`). Readiness replaces retry as the determinism mechanism. |
| Null-guarded predicates | `tests/web/test_market_e2e.py` — the 13 unguarded `wait_for_function` predicates gained `window.marketChart.candleSeries &&` before `.data()`, so a mid-boot `candleSeries === null` returns falsy and Playwright keeps polling instead of surfacing a hard `TypeError: Cannot read properties of null (reading 'data')`. Already-guarded pane predicates left unchanged. |
| Docs | `test_market_e2e.py` module docstring + `README.md` dev/E2E note: `python -m pytest -m e2e -p no:randomly` on an idle machine, and `playwright install chromium`. |
| Specs | `openspec/specs/chart-live-stream/spec.md` R8 + R9; `openspec/specs/market-chart/spec.md` R23. |

## Record Correction (W1)

**The "environment flake" was actually a real product bug.** The earlier verify
reports (`chart-drawings` W3, `smc-overlay` W4, `chart-scales` W3) labeled the
intermittent `KeyError: 'route'` in the 3 WS E2E tests an environment/version
flake and prescribed running on an idle machine. Investigation proved otherwise:

- The failure was **deterministic** (`test_ws_same_bucket_updates_in_place` failed
  3/3 in isolation and in the full suite), not intermittent.
- Root cause: `page.goto()` returns before boot's async `start()` resolves; the
  tests switched interval immediately; `switchTo` bumped `gen` 0→1; `start()` then
  aborted at its `if (gen !== 0) return;` guard **before `stream.connect()`** — and
  `stream.subscribe` never opened a socket on its own. No WebSocket was ever
  created → `holder["route"]` stayed empty → `KeyError: 'route'`.
- **Real user impact**: a user switching interval before boot completes loses the
  live WebSocket for the whole session (chart renders, never streams). Normally
  masked because boot is fast.
- A harness-only fix would have hidden this. Both were fixed: the product at the
  root (`stream.js::subscribe`), the harness made deterministic by readiness gating
  (not retry). `#149` scope was "harden the harness"; the latent product bug found
  during exploration was folded into the same single PR because the harness fix is
  only honest once the product defect is fixed.

## Requirements Satisfied

| Domain | Requirement | Outcome |
|--------|-------------|---------|
| chart-live-stream | R8 — Pre-boot switch opens the live socket (ADDED) | ✅ `subscribe(next)` opens the WS via the existing `connect(next)` seam when no socket is OPEN; a pre-boot switch establishes the requested channel; an OPEN socket keeps `unsubscribe(old)` strictly before `subscribe(new)` with no second socket; `#68` (update-only) and the DEBT-1 stale-frame guard (`isFrameForChannel`) unchanged. 3 scenarios. |
| chart-live-stream | R9 — Deterministic E2E readiness contract (ADDED) | ✅ The 3 mocked-socket E2E tests await boot readiness (or a bounded poll) before switching/injecting; readiness replaces retry; predicates null-guard `candleSeries`; the idle-machine `-m e2e -p no:randomly` command documented in module docstring + README. No new dependency, no CI `addopts` change. 3 scenarios. |
| market-chart | R23 — E2E readiness for the WS verification scenarios (ADDED) | ✅ The dev-only E2E scenarios verifying R5 are readiness-gated; the `page.route_web_socket` mock and its frame-ordering assertions unchanged. 1 scenario. |

**Preserved untouched** (no requirement dropped):
- `chart-live-stream`: R1–R7 — including the DEBT-1 stale-frame guard (R1
  `isFrameForChannel`, R5 frame-channel invariant), `#68` single-write-path, and
  unsubscribe-before-subscribe.
- `market-chart`: R1–R22 — including R5 (live candles, `#68`, frame-channel guard),
  R17 single-write-path invariants, R20 seam envelope, R22 theme host contract.

Delta fit: `chart-live-stream` canonical ended at R7 → R8/R9 appended cleanly;
`market-chart` canonical ended at R22 → R23 appended cleanly. No requirement name
collision, no MODIFIED/REMOVED delta, merge non-destructive.

## Warnings Carried (non-blocking)

- **W2 — Residual class-C flake, documented NOT fixed.** Running the 3 WS E2E
  concurrently can still intermittently fail one test (`assert 200 == 201` /
  `database table is locked`) — the SQLite + threaded `live_server` contention
  named in the issue. It passes in isolation (3/3); the fix removed the
  deterministic failure. Class-C root fix (per-test DB isolation / transactional
  live server) was explicitly out of scope (a larger harness rework). Not hidden,
  not retried.
- **W3 — CI does not run E2E** (`pyproject.toml` `addopts = "-q -m 'not e2e'"`). The
  harness fix is local-verified only. The product invariant is CI-gated through the
  browser-free `tests/js/stream.test.js`. A CI E2E job is out of scope (needs a
  browser download; the repo deliberately avoids it).
- **W1** is a record correction, restated above — not an open defect.

## Verification Evidence (from verify-report)

- `node --test "tests/js/**/*.test.js"`: **159 passed, 0 fail** (includes the new
  `stream.test.js`).
- `pytest tests/ --ignore=tests/web`: **337 passed**.
- `ruff check .`: clean.
- `requirements.txt` diff vs `develop`: **empty** (no runtime dependency).
- Full E2E `-m e2e -p no:randomly`: the 3 WS tests **0/3 → passing** (modulo W2).
- Adversarial RED→GREEN reproduced independently: with the `else if (!ws) connect`
  line scratch-removed, `stream.test.js` FAILS 3/3; restored → passes 3/3.
- `main.js` diff vs `origin/develop` = 0 lines (the `gen` guards untouched).
- DEBT-1 guard intact (`isFrameForChannel` present); `#68` update-only held (the
  `setData` hits in `stream.js` are comments; `host.updateCandle` is the only live
  write).

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| chart-live-stream | Updated | +R8 (pre-boot switch opens the WS; no duplicate socket; `#68` + stale-frame guard hold) and +R9 (deterministic E2E readiness contract: readiness gate, null-guarded predicates, documented idle-machine command). R1–R7 preserved untouched. |
| market-chart | Updated | +R23 (E2E readiness for the R5 WS verification scenarios). R1–R22 preserved untouched. |

## Carry-forward

- **DEBT pass CLOSED.** #149 (DEBT-8) is the last debt issue; with it archived, the
  pre-Ola-3 debt batch is complete.
- **W2 remains open** (residual class-C SQLite/live_server flake) — bounded and
  documented; a follow-up harness rework could add per-test DB isolation.
- **W3 remains open** (CI does not run E2E) — the CI-gated product invariant is the
  JS regression; full E2E stays dev-only by design.
- Frozen seams remain in force: layered ESM inventory, 8-key `window.marketChart`,
  `window.SmcOverlayCore`, `#68` single-write-path, DEBT-1 channel guard, per-user
  ownership.

## SDD Cycle Complete

Explored (root cause proven; product bug separated from harness flake) → proposed
(single PR, product fix + harness + docs) → designed → tasked → implemented
(single PR **#162**) → verified (`pass_with_warnings`; RED→GREEN independently
reproduced) → merged to `develop` → archived.

Traceability: `openspec/changes/archive/2026-10-14-e2e-harness-hardening/`
(explore, proposal, design, specs, tasks, verify-report); engram
`sdd/e2e-harness-hardening/archive-report`.
