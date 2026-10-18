# Proposal: f9-drawing-tools-more

Issue #122, Fase F9. Branch `develop` @ `1150b07`. Read-only. Builds on archived
F6 (`archive/2026-10-17-f6-measure-position/`) and F7
(`archive/2026-10-17-f7-chart-shortcuts/`). Resolutions honor `explore.md` §8 forks as decided.

## Intent

Eight TradingView-parity drawing kinds (`ray`, `vline`, `channel`, `price`, `callout`,
`fib_ext`, `fib_time`, `fib_zone`) over the SAME persistence/render/interaction stack the
six existing kinds use (`models.py:244-249`). Each is a new geometry, not a new subsystem.

**Why the issue's framing is corrected.** The issue says the new kinds "son solo valores
del JSON existente." That is wrong at the persistence layer: `Drawing.kind` is a
`CharField` with a `choices` enum (`models.py:244-249,253`) and `parse_drawing` rejects any
kind outside `DRAWING_KINDS` (`quotes.py:402,440-441`) → an unknown kind 400s, and
`makemigrations --check` fails when model choices drift from the last migration. So ONE
choices-only `AlterField` migration is required, mirroring F6's `0015_drawing_kind_position`.

**Why the click-flow extraction is forced.** The 300-line ceiling is enforced with an EMPTY
allowlist (`test_module_size_guard.py:20,23`). `drawings.js` = **298** (2 free) and
`drawing-interaction-core.js` = **271** cannot absorb 8 kinds. The 8-kind click flow must
move OUT of `drawings.js`; the existing 2-click + `positionDraft` flow must move with it to
stay ≤300. Forced, not optional — covered by e2e.

## Scope

### In Scope
- New pure cores (node-tested): `drawing-tools-core.js` (kind descriptor map:
  path/style/clicks/handles/bodyHit/drag), `fib-tools-core.js` (`FIB_EXT_RATIOS` + fib
  extension/time/zone math), `drawing-click-flow-core.js` (generic 1/2/3-click state machine).
- `Drawing.Kind` +8 + `0016_drawing_kind_tools` (choices-only `AlterField`).
- `parse_drawing` +8 per-kind branches (`quotes.py:427-461`).
- Dispatch guards in `drawing-core.js:13,28`, `drawing-primitive.js:37,14`,
  `drawing-interaction-core.js:31,107,162`.
- `drawings.js` click-flow extraction (shrinks); `tool-icons-core.js` +8 icons;
  `draw-toolbar.js` +8 `TOOL_KEYS`/labels.
- `MODULE_ALLOWLIST` +3 cores (`views.py:44`), `CONTROLLER_ALLOWLIST` unchanged (`:71`).
- Node + API + migration (`test_migration_0016.py`) + e2e tests.

### Out of Scope
Order execution **HARD** (read-only repo); SMC internals (`find_setups`/scoring untouched);
new dependency or build; CSP relaxation; `src/` changes; store/seam changes (`STORE_KEYS`
stays 11, `window.marketChart` stays 8 keys); per-tool global letters.

## Capabilities

### New Capabilities
- None — the 8 tools extend existing drawing capabilities, not new domains.

### Modified Capabilities
- `chart-drawings`: gains 8 new kinds (geometry + `parse_drawing` branches + R4/R5 validation);
  `channel` = 3-point `{p1,p2,p3}`, `fib_ext` uses new `FIB_EXT_RATIOS`; R-numbers per kind.
- `chart-toolbar`: gains 8 tool buttons/icons + non-colliding letters
  `ray=A, vline=I, channel=C, price=U, callout=O, fib_ext=E, fib_time=W, fib_zone=Z`.
- `market-chart`: **R14** inventory gains the 3 new cores; `MODULE_ALLOWLIST` +3; **R18/R20**
  seam stays 8 keys and `STORE_KEYS` stays 11.
- `design-system`: **R6/R7** a11y — icons as plain strings (CSP), not-color-only (price
  label, callout text, fib ratio labels), `callout` reuses `#text-dialog`.

## Approach

Layered F5/F6/F7 extension; logic lives in pure cores so every touched controller stays ≤300.

- **Pure cores first** (no DOM): `drawing-tools-core.js` exports `NEW_KINDS`, `TOOL_SPECS`,
  `defaultToolStyle`, `toolPath`, `toolHandles`, `toolBodyHit`, `toolDrag`, `clicksFor`;
  `fib-tools-core.js` adds `FIB_EXT_RATIOS` + `fibExtLevels`/`fibTimePath`/`fibZoneBands`;
  `drawing-click-flow-core.js` `collect(kind, point) → points | null` (precedent
  `position-draft-core.js`, 42 lines).
- **Existing cores stay generic**: `drawing-core.js` `+8` kinds (`:13`) + `defaultStyle`
  delegates new kinds (`:28`); `drawing-primitive.js` `renderShape:37` gains ONE guarded
  block dispatching `renderTool` (canvas stays in the primitive); `priceRangeFor:14` adds a
  `p3` push; `drawing-interaction-core.js:31,107,162` each gain ONE guard → `Tools.tool*`.
- **Click flow**: `drawings.js` `onChartClick:193-230` becomes a delegate to
  `Flow.collect`; the existing 2-click block (`:223-229`) and `positionDraft` (`:218-222`)
  move into the core (net shrink to ~286).
- **Migration**: ONE `0016_drawing_kind_tools` choices-only `AlterField` adding all 8
  choices; SQLite-safe (choices live in Django state, no column constraint), reversible,
  zero data loss.
- **Reuse, no new path**: new kinds POST through `createDrawing` (#68 single-write-path);
  `undo.js`/`history-core.js` are kind-agnostic; `object-tree.js:130` renders new kinds for free.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/market/templates/market/drawing-tools-core.js` | New | 8-kind descriptor map (path/style/clicks/handles/drag) |
| `web/market/templates/market/fib-tools-core.js` | New | `FIB_EXT_RATIOS` + fib ext/time/zone math |
| `web/market/templates/market/drawing-click-flow-core.js` | New | generic 1/2/3-click state machine |
| `web/trading/models.py` | Modified | `Kind` +8 (`:244-249`) |
| `web/trading/migrations/0016_drawing_kind_tools.py` | New | choices-only `AlterField` (mirrors `0015`) |
| `web/market/quotes.py` | Modified | `parse_drawing` +8 branches (`:427-461`) |
| `market/drawing-core.js` (165) | Modified | `DRAWING_KINDS` +8 + `defaultStyle` delegate |
| `market/drawing-primitive.js` (178) | Modified | `renderShape` + `renderTool` + `priceRangeFor` p3 |
| `market/drawing-interaction-core.js` (271) | Modified | 3 guards → `tool*` descriptors |
| `controllers/drawings.js` (298) | Modified | click-flow extraction (shrinks ~286) |
| `market/tool-icons-core.js` (76), `controllers/draw-toolbar.js` (144) | Modified | +8 icons/letters/labels |
| `controllers/smc.js` (300), `object-tree.js` (299) | Untouched | MUST stay ≤300 |
| `market/chart-store.js` (11), `chart-host.js` (267), `main.js` (274) | Untouched | no key/seam change |
| `web/market/views.py` | Modified | `MODULE_ALLOWLIST` +3 (`:44`) |
| `tests/js/*`, `tests/web/*` | Modified | node cores, API matrix, `test_migration_0016.py`, e2e |

## Rollback Plan

- **Migration**: `0016` is choices-only and reversible — `python manage.py migrate trading
  0015_drawing_kind_position` restores the prior choices; no column, no row change, zero data
  loss (`0015` precedent).
- **Feature-branch chain**: drop the tracker branch and all child slices; no merge to
  `develop` until green.
- **Revert** the 3 new cores + their JS/CSS/allowlist edits atomically — nothing else is
  persisted (no store key, no seam key, no schema column).

## Risks

| Risk | L | Mitigation |
|------|---|------------|
| 300-line ceiling (`drawings.js`=298, `drawing-interaction-core.js`=271) | High | geometry in new cores; click flow extracted OUT of `drawings.js` (net shrink); `smc.js`/`object-tree.js` byte-untouched |
| Seam freeze 8 keys | High | new kinds reuse the existing `drawings` key (`drawings.js:50,111`); assert via DOM/bus |
| `STORE_KEYS` frozen 11 | High | new kinds use the existing `tool` value only; no new key (`chart-store.js:13-27`) |
| #68 single-write-path | High | render on primitives + `requestUpdate`; POST only via `createDrawing` |
| 8 `parse_drawing` branches / POST 400s | High | per-kind valid/invalid matrix in `test_market_api.py` |
| Choices drift → `makemigrations --check` red | Med | one `0016` + `test_migration_0016.py` (copy `test_migration_0015.py`) |
| Patch coverage 100% | High | `diff-cover`; node + API + migration tests |
| R14 `for_user` isolation | Med | CRUD reuses `api_drawings`/`api_drawing_detail` (`views.py:403,491`) |
| Fib ratio correctness (orientation `ratio 0 == p2`) | Med | node-test each fib kind's level math (`drawing-core.js:96-101`) |
| Undo/history replay (F7) | Med | `undo.js`/`history-core.js` kind-agnostic; verify via e2e undo |
| E2E class-C flake (#149) | Med | assert DOM + captured network, never pixels; readiness-gated `_wait_ready` |

## Read-Only Boundary

MUST NOT place/modify/cancel orders or relax any read-only invariant. `src/` framework-free
and unchanged; no new dependency; no build; ESM `.js`; CSP unchanged (icons are plain strings
on native `<button>`, no inline `on*`). Strict TDD (`openspec/config.yaml`): tests precede
implementation.

## Delivery (Feature Branch Chain)

Over the 400-line budget → chained PRs, mirroring F6. S1: the 3 pure cores + node tests.
S2: `Kind` +8 + `0016` + `parse_drawing` + API matrix + migration test. S3: render/interaction/
click-flow dispatch + toolbar icons/letters + allowlists + e2e. Base: tracker branch
`feat/f9-drawing-tools-more`.

- Chained PRs recommended: **Yes**
- 400-line budget risk: **High**

## Success Criteria

- [ ] Each of the 8 kinds creates, moves, and persists (POST/PUT/DELETE) via one write path.
- [ ] Path builders node-tested for all 8 kinds; `fib_ext` uses `FIB_EXT_RATIOS`; `fib_time`/`fib_zone` reuse `FIB_RATIOS`.
- [ ] `0016` applies forward and reverses (`migrate trading 0015`) with zero data loss; `makemigrations --check` green.
- [ ] `window.marketChart` stays 8 keys; `STORE_KEYS` stays 11; size guard passes with empty allowlist (`smc.js`/`object-tree.js` untouched).
- [ ] `MODULE_ALLOWLIST` +3 cores; toolbar letters non-colliding; `callout` reuses `#text-dialog`.
- [ ] `node --test` + `pytest` green; patch coverage 100%; undo replays new kinds.
