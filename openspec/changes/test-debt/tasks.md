# Tasks: test-debt

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

## Guard/Edge Matrix (every row = a test/assertion in its WU)

- [ ] Guard passes current `web/**`+`src/**` tree (0 offenders) (R7)
- [ ] Guard fails on injected `import pandas` (R7)
- [ ] Guard ignores stdlib (`os`), declared (`django`), local (`src`,`market`), relative (R7)
- [ ] Sync: every declared dist maps to an allowlisted root (R7)
- [ ] E2E tail frames == `[("unsubscribe","market_kline_1min"),("subscribe","market_kline_5min")]` (R5)
- [ ] E2E same-bucket push: length +1 then unchanged; last `time` unchanged (R5)
- [ ] No `web/`/`src/` production line changes; `requirements.txt` unchanged (R7)
- [ ] Patch gate 100% on the new Python tests

## WU1 — dependency guard (Python, testable)

Base `main`. Depends: none. Strict TDD (`python -m pytest`). Headless (~90 lines).

- [ ] 1.1 **RED** `tests/test_dependency_guard.py`: AST scanner mirroring `test_boundary.py` — roots via `ast.walk` (`Import`/`ImportFrom`, `level == 0`); scan `web/**/*.py`+`src/**/*.py`; skip `__pycache__`+this file.
- [ ] 1.2 **RED** allowlist `= sys.stdlib_module_names ∪ declared ∪ local`; local = `web/*/` dirs with `__init__.py` + flat `web/*.py` stems + `src`.
- [ ] 1.3 **RED** declared: parse `requirements.txt`, strip version/extras/markers; map `psycopg[binary]→psycopg`, `dj-database-url→dj_database_url`, else lowercase identity (`Django→django`).
- [ ] 1.4 **RED** tests: tree passes; positive (`django`/`os`/`src`/relative not flagged); negative (`import pandas`→offender); sync (declared dist without mapped root, or mapped root absent→fails).
- [ ] 1.5 **GREEN** implement scanner+allowlist; `ponytail:` note on `TYPE_CHECKING` ceiling.
- [ ] 1.6 Suite + `ruff check` green; patch gate 100%.
- [ ] 1.7 **Rollback**: delete the file. No production/dep change.

## WU2 — W1 WS-lifecycle E2E (dev-only)

Base WU1 branch. Depends: WU1. Strict TDD. Browser (~60 lines).

- [ ] 2.1 **RED** extend `tests/web/test_market_e2e.py` (`@pytest.mark.e2e`, `seeded_5m_candles`): `page.route_web_socket("wss://fapi.bitunix.com/**", handler)` **before** `goto`; handler stores `ws_route`, appends parsed frames.
- [ ] 2.2 **RED** ordering: bounded-poll (~2s, `wait_for_timeout(50)`) until boot `subscribe(market_kline_1min)`; `select_option("#interval","5m")`; `wait_for_function` REST redraw; assert tail two parsed `op`+`args[0].ch` == expected pair.
- [ ] 2.3 **RED** bucketing: `t=last_time+300`; `route.send({symbol,ts:t*1000,data:{o,h,l,c}})`; `wait_for_function` `len==n+1`; second push same bucket; assert length+last `time` unchanged.
- [ ] 2.4 **GREEN** helpers; all DOM/series asserts via `wait_for_function`; no fixed long sleep, no timing assert.
- [ ] 2.5 Run `playwright install chromium` then `pytest -m e2e`; default suite green (e2e deselected).
- [ ] 2.6 **Rollback**: revert E2E file. Dev-only; CI unaffected.

## WU3 — doc/spec hygiene (R9)

Base WU2 branch. Depends: WU1/WU2 (independent). No code (~5 lines).

- [ ] 3.1 `pyproject.toml` `[tool.coverage.run].omit`: comment `web/manage.py` naming `tests/web/test_manage_boot.py` as its contract; keep the entry.
- [ ] 3.2 **Rollback**: remove the comment only.

## Phase 4 — Verification

- [ ] 4.1 `python -m pytest` green (e2e deselected); `ruff check . && ruff format --check .` green.
- [ ] 4.2 `tests/test_boundary.py`+guard green; `requirements.txt` unchanged; `git diff --stat` touches no `web/`/`src/` line.

## Review Workload Forecast

- Per WU: WU1 ~90, WU2 ~60, WU3 ~5 → **~155–220 total**.
- Suggested split: single PR (WU1 → WU2 → WU3 only if a chain is chosen).
- Delivery strategy: ask-on-risk.

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low
