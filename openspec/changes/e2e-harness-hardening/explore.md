# Exploration: e2e-harness-hardening (issue #149, DEBT-8, P3)

## Current State

The E2E harness (`tests/web/test_market_e2e.py`, 65 selected tests) is dev-only:
`pyproject.toml` `addopts = "-q -m 'not e2e'"` deselects it, CI never runs it, no
browser is downloaded in CI. A `browser_page` fixture (L80-103) launches Chromium
via `sync_playwright`, creates a `context` + `page`, injects the Django session
cookie, and yields `(page, live_server.url)`. Four tests mock the exchange socket
with `page.route_web_socket("wss://fapi.bitunix.com/**", handler)` (L333, L370,
L419, L482). Three verify reports (`chart-drawings` W3, `smc-overlay` W4,
`chart-scales` W3) recorded an intermittent harness flake under load and
prescribed `-m e2e -p no:randomly` on an idle machine.

**Two DIFFERENT defects are conflated under the "flake" label.** One is
deterministic and reproducible; one is genuinely intermittent.

---

## Root cause of `KeyError: 'route'` (deterministic — class A)

**Reproduced:** `test_ws_same_bucket_updates_in_place` fails **3/3** runs,
in isolation and in the full suite, with `KeyError: 'route'` at the
`holder["route"].send(...)` line. The other two WS tests fail identically in the
full suite. `test_ws_switch_unsubscribes_before_subscribing` **passes** — the
orchestrator's hypothesis that it is the discriminator is CONFIRMED.

**It is NOT an environment/version problem.** A standalone `sync_playwright`
probe AND a pytest probe (minimal fixture, no `select_option`) both fire the
handler 100%. The Playwright `route_web_socket` API works fine under pytest +
`live_server`.

**Exact mechanism** (proven by instrumentation — adding a `print` in the handler
made the test pass by perturbing timing, and a diag probe with no `select_option`
fired the handler every time):

1. `page.goto()` returns as soon as the document loads. The app's `boot()`
   (`main.js:26`) then runs an **async** `start()`: `loadPreference()` →
   `loadLayout()` → `buildChart()` → **`stream.connect()` (L241)**.
2. The 3 failing tests immediately call `page.select_option("#interval", "5m")`
   (L372, L421, L484) — i.e. **before** `loadPreference()` resolves.
3. `select_option` dispatches `change` → `config:changed` → `switchTo()`
   (`main.js:123`), which does `++gen` (gen 0 → 1).
4. When `loadPreference()` finally resolves, `start()`'s guard
   `if (gen !== 0) return;` (`main.js:223`) sees `gen === 1` and **aborts boot
   before `stream.connect()` is ever called**.
5. `switchTo()` calls `stream.subscribe({symbol, interval})`
   (`main.js:132`), but `subscribe()` (`stream.js:111-114`) only does
   `sendSubscribe(next)` when `ws && ws.readyState === 1`; otherwise it just
   does `sub = next` and **never calls `connect()`**. So **no WebSocket is ever
   created** → the route handler never runs → `holder["route"]` stays empty →
   `KeyError: 'route'`.

**Why `test_ws_switch` passes:** it inserts `_poll(...)` for the boot
`subscribe` frame (L337-344) **before** the `select_option`, which consumes
enough time for `start()` to finish and open the socket.

**The EXACT fix (test-harness-only, one line per test):** wait for boot to
complete before the interval switch. The cleanest form reuses the existing
`_wait_ready(page)` helper (`main.js`-agnostic, already used by ~20 tests):

```python
page.goto(f"{base_url}/market/")
_wait_ready(page)                       # <- FIX: boot (and stream.connect()) finished
page.select_option("#interval", "5m")
```

or, keeping the WS tests self-contained, a bounded poll for the socket:

```python
page.goto(f"{base_url}/market/")
assert _poll(page, lambda: "route" in holder), "socket never opened"
page.select_option("#interval", "5m")
```

**Verified:** the `_wait_ready` fix makes all 3 WS tests pass **3/3**; the `_poll`
fix passes `test_ws_same_bucket` **5/5**. Apply the same guard to all three
failing tests (`test_ws_same_bucket_updates_in_place`, `test_ws_stream_never_calls_setdata`,
`test_ws_stale_channel_push_during_switch`).

**LATENT PRODUCT BUG (found, out of harness scope):** `switchTo()` never calls
`stream.connect()`. A real user switching interval before boot's `loadPreference`
resolves loses the live WebSocket for the whole session — the chart renders but
never streams. Normally masked because boot is fast. This is a production defect,
not a test defect; recommend a separate ticket (see Open Questions).

---

## The genuine flake (intermittent — class B and C)

With the 3 WS tests deselected, the suite still fails intermittently on a
**rotating** test. Three consecutive runs: pass / FAIL `test_legend_idle_lists_all_active_series_exact`
/ pass; two earlier runs failed `test_selected_indicator_renders_a_pane`,
`test_legend_aria_live_debounced_not_per_move`, `test_legend_resubscribes_across_rebuild`,
`test_chart_renders_seeded_candles`. Two signatures:

**Class B — unguarded `wait_for_function` predicate throws instead of retrying.**
Signature:
```
playwright._impl._errors.Error: Page.wait_for_function:
  TypeError: Cannot read properties of null (reading 'data')
```
Cause: ~13 predicates are written `() => window.marketChart && window.marketChart.candleSeries.data().length > 0`.
When the page has `window.marketChart` but `candleSeries` is still `null`
(mid-boot), `window.marketChart.candleSeries.data()` throws; Playwright surfaces a
JS exception from `wait_for_function` as a hard error rather than polling.
Repro: a minimal test calling the unguarded predicate right after `goto` failed
1/5; the null-guarded form `window.marketChart && window.marketChart.candleSeries && …`
survived more often but **still failed intermittently (3/6) with `assert 0 > 0`** —
residual boot/switch ordering race, so the null guard alone is necessary but not
sufficient.

**Class C — SQLite + threaded `live_server` contention** (documented in
`chart-scales` W3): `sqlite3.OperationalError: no such savepoint` /
`database table is locked`. Settings use SQLite (`web/config/settings/base.py:46-51`);
`live_server` is threaded and shares the DB file. This is the historically named
flake; not reproduced verbatim in this session but corroborated by the archive.

**Net:** class A is deterministic and fully explained. The "flake" is class B
(harness predicate/ordering) + class C (SQLite/live_server contention). The WS
tests were mislabeled as flaky in the verify reports — they fail deterministically.

---

## Affected Areas

- `tests/web/test_market_e2e.py` — the ONLY file that must change. 3 WS tests need
  a readiness guard; ~13 predicates need `window.marketChart.candleSeries &&`
  null-guarding.
- `web/market/templates/market/controllers/stream.js` — `subscribe()` never
  connects (latent product bug, mentioned only).
- `web/market/templates/market/main.js` — `start()` `gen` guard + `switchTo()`
  (product behavior; NOT changed in a harness-only PR).
- `README.md` / a dev-docs note — where the `-m e2e -p no:randomly` idle-machine
  requirement belongs.
- `pyproject.toml` — only IF a marker/doc note is added; no `addopts` change.

## Approaches

1. **Wait-for-readiness before interacting + null-guard predicates (recommended).**
   Add `_wait_ready(page)` (or a bounded `_poll` for the socket) before every
   `select_option("#interval", …)` in the 3 WS tests; change the ~13 predicates to
   null-guard `candleSeries`. Document `-m e2e -p no:randomly` in one place.
   - Pros: fixes the deterministic KeyError AND class B; no new deps; test-only;
     no hidden failures (a real regression still fails); minimal diff.
   - Cons: does not address class C (SQLite contention) — but that is genuinely
     environmental and already documented.
   - Effort: Low.

2. **Per-test DB isolation or serialize the live server.**
   - Pros: would address class C.
   - Cons: `live_server` is threaded and shares one DB; true per-test isolation
     needs a transactional live server or a temp file DB, which is a larger
     harness rework touching the fixture for all 65 tests; high risk of new
     breakage; contradicts "minimal". Effort: High.

3. **Explicit bounded retry (a pytest marker + a `pytest_runtest_makereport`/
   `pytest_runtest_protocol` hook that retries once and LOGS loudly).**
   - Pros: visible, no new dep, satisfies "no silent" if it logs.
   - Cons: `pytest-rerunfailures` is a new dep (excluded); a hand-rolled retry hook
     is ~30 lines of plugin code for a problem (class A) that is fully fixable by
     a one-line wait. A retry would MASK the deterministic KeyError rather than
     fix it — the opposite of "no ocultar fallos reales". Rejected as the primary
     mechanism.

## Recommendation

**Approach 1.** It is the minimal change that removes the deterministic failure
and most of the rotating flake, introduces no dependency, and keeps failures
visible. Specifically:

- Add `_wait_ready(page)` before the interval switch in the 3 WS tests (deterministic
  fix, verified 3/3).
- Null-guard `window.marketChart.candleSeries &&` in the ~13 unguarded predicates.
- Do NOT add a silent retry. If a retry is still wanted for residual class C,
  make it an OPT-IN, LOGGED hook — never the default and never silently swallowing.
- Document `python -m pytest -m e2e -p no:randomly` on an idle machine in ONE
  place (test module docstring + a short `README.md` dev note pointing at it).

## Risks

- **Hiding real failures** if a retry is added silently → mitigated by choosing the
  wait/guard fix, not a retry.
- **Residual class C** (SQLite/live_server contention) may still produce isolated
  failures under heavy load; this is bounded and documented, not introduced.
- **CI does not run E2E** → this fix is local-verified only; a CI job for E2E is
  out of scope (needs a browser download; the repo deliberately avoids it).
- **Latent product bug** (`switchTo` never connects the stream) is NOT fixed by a
  harness-only PR; leaving it undocumented would let it rot → flag a separate ticket.

## Documentation plan

- `tests/web/test_market_e2e.py` module docstring (L11-12): extend the "Run
  locally" line to `python -m pytest -m e2e -p no:randomly` on an idle machine,
  and note the boot-readiness requirement (why tests must wait for `ready` before
  switching interval).
- `README.md`: one short "Development / E2E" line pointing at the command and the
  `playwright install chromium` prerequisite. (No README E2E section exists today.)

## Open questions / decisions

1. **Harness-only vs. also fix the latent `switchTo` connect bug.** Recommend
   harness-only for #149 (scope: "endurecer el harness"), and file a separate
   ticket for `switchTo()` not calling `stream.connect()`. Needs orchestrator
   decision because it changes production code.
2. **Retry or not.** Recommend NO retry (the deterministic bug must be fixed, not
   retried). If residual class C warrants it, use a visible, opt-in logged hook.
3. **Scope boundary:** test-harness only; no production `main.js`/`stream.js`
   change; no new deps; no `addopts` change; CI unchanged.

## Recommended PR shape + size

**Single PR, test-harness-only.** Two files touched at most
(`tests/web/test_market_e2e.py` + a docstring/README note). Estimated < 60 changed
lines, well under the 400-line review budget. No production code, no deps, no CI
change. `Decision needed before apply: No`. `Chained PRs recommended: No`.
`400-line budget risk: Low`.

## Ready for Proposal

Yes. The deterministic root cause is proven with a verified fix; the approaches,
risks, and doc plan are settled. One decision to surface to the user before
proposal: whether to also fix the latent `switchTo` connect bug or keep the PR
strictly harness-only (recommend harness-only).
