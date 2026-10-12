# Verify Report — chart-drawings (issue #72, Fase A3)

**Verdict**: `pass_with_warnings`
**Verified by**: orchestrator (adversarial, fresh probes) — the delegated verify sub-agent timed out without output, so verification was executed inline.
**Branch**: `feat/chart-drawings-ui` (HEAD `2f01eed`), chain: tracker `feat/chart-drawings` ← PR1 `feat/chart-drawings-model` (`2e2771f`) + PR2 `feat/chart-drawings-endpoint` (`2377131`) + PR3 `feat/chart-drawings-ui` (`2f01eed`); all slice PRs base on the tracker.

## Gates (L1)

| Gate | Result |
| --- | --- |
| `python -m pytest` | **523 passed, 19 deselected** (baseline 477 after PR1) |
| `ruff check .` | clean |
| `ruff format --check .` | clean |
| `makemigrations --check --dry-run` | No changes detected |
| `node --test "tests/js/**/*.test.js"` | **26 passed, 0 fail** (9 chart-core + 17 drawing-core) |
| `pytest -m e2e -p no:randomly` | **19 passed** (14 pre-existing + 5 new drawings) |
| `tests/web/test_owned_model_guard.py` + `test_no_order_surface.py` + `test_boundary.py` | green |
| `requirements.txt` vs develop | **empty diff** (no new dependency) |

## Gates (L2)

- `diff-cover coverage.xml --compare-branch=origin/develop --fail-under=100` → **100%** (94 changed lines, 0 missing: `web/market/views.py`, `web/trading/models.py`).
- JS is outside the Python patch gate → `drawing-core.js` geometry is covered by `node --test` (17 cases) and the adapter by E2E, per tasks WU3.

## Spec conformance (L3)

- `Drawing(UserOwnedModel)`: owner FK CASCADE + `for_user`; **no unique constraint** (collection semantics); index on `(user, symbol, interval)`; JSON `points`/`style`; `kind` TextChoices; additive migration `0006`; `Drawing` in `OWNED_MODELS` with a negative control (`Drawing.objects.all()` is flagged).
- CRUD `/market/api/drawings`: GET list / POST create / DELETE `<id>`, all via `for_user`; validation per kind → 400 **without write**; cross-user DELETE → **404**, victim survives; anonymous → 302; CSRF enforced.
- Render: v5 `ISeriesPrimitive` attached to `candleSeries` on its own canvas layer; **single-write-path #68 preserved** (WS push → `update()`; `setData` only on history/config); `timeToCoordinate`/`coordinateToTime` null off-bar guarded; boot loads drawings for `(symbol, interval)`; `switchTo` clears + reloads; toolbar CSP-safe (no inline handlers); native `<dialog>` for text; no new dep; CSP unchanged.

### Adversarial probes (independent, throwaway)
- Model: many drawings coexist on the same `(user, symbol, interval)`; A≠B via `for_user`; JSON round-trip.
- Endpoint: hline create → 201; invalid kind → 400; hline missing `price` → 400; trendline with a single point → 400; **only the valid row persisted** (no partial writes).
- Cross-user: B deletes A's id → 404, A's row still present; A deletes own → 204.
- Browser (Playwright, real): toolbar renders 5 tools; tool click + chart click → **POST fired (1)**; after reload the drawing is **re-rendered and listed** (drawings=1 before and after), 0 page errors.
- `Drawing.objects.all()` negative control in the guard test suite proves the R14.3 scan catches unscoped access.

## Warnings (non-blocking)

- **W1 — Index name deviation**: design/spec literal `ix_drawing_user_symbol_interval` is 31 chars and fails Django `E034` (30-char limit). Implemented as `ix_drawing_user_sym_interval`. R1 requires the tuple be indexed, not the literal name → requirement holds. Archive should record the deviation.
- **W2 — `style` not key-validated**: `parse_drawing` requires `style` to be an object but does not enforce per-kind style keys (`{color, lineWidth}`). Spec R5 requires only point-count/label rejection; style stays open-ended like `ChartLayout`. Acceptable.
- **W3 — Pre-existing E2E flake (not drawings-specific)**: the threaded live server + SQLite session contention makes some tests intermittently 302/500 under parallel load. PR3 serialized the drawings boot path (layout→build→connect→drawings→history). Run `-m e2e -p no:randomly` on an idle machine.
- **W4 — `timeToCoordinate` null off-bar** is guarded by inspection and E2E covers the happy path; a drawing anchored outside the loaded range degrades gracefully (skipped) rather than crashing.
- **SUGGESTION**: WU1/WU2 checkboxes in `tasks.md` were left unmarked by apply (orchestrator hard contract); WU3 marked. No node unit test for the adapter layer itself (geometry only); E2E is the adapter net.

## Requirement coverage

- New capability `chart-drawings`: **8 requirements / 32 scenarios** — satisfied (with W1, W2, W4 notes).
- `per-user-isolation` DELTA: R14.2/R14.3 gain `Drawing` — satisfied, negative control proves the guard.
- `market-chart` DELTA: R11 (drawings endpoint + render/restore) — satisfied.

## Blockers

None.
