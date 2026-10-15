# Verify Report — e2e-harness-hardening (issue #149, DEBT-8)

**Verdict**: `pass_with_warnings`
**Verified by**: orchestrator (adversarial, inline — the delegated verify sub-agent was repeatedly cancelled by network/tooling, so verification was executed inline).
**Branch**: `fix/e2e-harness-hardening` (single PR → `develop`), commit `d42e9b5`.

## Gates (L1)

| Gate | Result |
| --- | --- |
| `node --test "tests/js/**/*.test.js"` | **159 passed, 0 fail** |
| `pytest tests/ --ignore=tests/web` | **337 passed** |
| `ruff check .` | clean |
| `requirements.txt` diff vs develop | **empty** |
| Full E2E (`-m e2e -p no:randomly`) | the 3 WS tests: **0/3 → passing** (see W2) |

## Gates (L2)

- Python change: none (the change is `stream.js` + JS/E2E tests + docs). diff-cover N/A.

## Spec conformance (L3)

- **Product fix**: `stream.js::subscribe` now `if (ws && ws.readyState === 1) sendSubscribe(next); else if (!ws) connect(next); else sub = next;` — a pre-boot switch OPENS the socket (previously it only stored `sub` and the `gen` guard made `start()` skip `connect()` → dead stream until reload).
- **#68 preserved**: the live path stays `update()`-only (the 3 `setData` hits in `stream.js` are comments; `host.updateCandle` is the only live write). No `setData` call.
- **DEBT-1 guard intact**: `isFrameForChannel` still present.
- **`main.js` UNCHANGED**: `git diff origin/develop -- web/market/templates/market/main.js` = 0 lines → the `gen` guards untouched.
- **Regression**: `tests/js/stream.test.js` (CI `node --test`) proves the pre-boot subscribe opens exactly 1 socket; a 2nd subscribe → no new socket; an open ws → `sendSubscribe`.
- **Harness**: the 3 WS tests call `_wait_ready(page)` before the switch; the `.data()` predicates are null-guarded.
- **Docs**: the `-m e2e -p no:randomly` idle-machine note exists (module docstring + README).
- No new dep; no `addopts`/CI change; no retry.

### Adversarial probes
- **RED→GREEN reproduced independently**: with the `else if (!ws) connect` line scratch-removed, `tests/js/stream.test.js` FAILS 3/3; restored → passes 3/3.
- **Original symptom gone**: the 3 WS E2E no longer raise `KeyError: 'route'`; they pass (together: 4/4 on one run, 3/4 on another — the miss is the class-C flake below, not the `KeyError`).

## Warnings (non-blocking)

- **W1 — Product bug was MISLABELED as an "environment flake".** The `KeyError: 'route'` was a real product defect (`stream.subscribe` never opened the socket pre-boot), not Playwright drift. Fixed at the root; now CI-pinned by `tests/js/stream.test.js` (which runs in CI, unlike the E2E).
- **W2 — Residual class-C flake (documented, NOT fixed)**: running the 3 WS E2E concurrently can still fail one intermittently (`assert 200 == 201` / `database table is locked`) — the SQLite + threaded `live_server` contention the issue names. It passes in isolation (3/3) and the fix removed the deterministic failure. Not hidden, not retried.
- **W3 — CI does not run E2E** (`addopts = "-m 'not e2e'"`): the harness fix is local-verified; the product invariant is the CI-gated `stream.test.js`.
- **SUGGESTION**: `tasks.md` checkboxes state reconciles at archive.

## Blockers

None.
