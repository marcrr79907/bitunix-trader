# Proposal: f6-measure-position

Issue #119, Fase F6. Branch `develop` @ `80070c0`. Read-only.

## Intent

F5 shipped the primitive/drawing/toolbar substrate (`openspec/changes/archive/2026-10-16-f5-chart-toolbar/`). F6 adds the two TradingView instruments that substrate was built to carry:

- **Measure tool** — a *gesture*: press-drag across the chart, release, read the delta between two points — price Δ (abs + %), elapsed time, bar count, candle count (`explore.md:11-14`). It is **ephemeral**: it lives only while being drawn and is deleted by starting a new one. Persisting it would pollute the object tree and earn a migration for zero user value (`explore.md:149-158`).
- **Position tool** — an *object*: a Long/Short box with entry / stop-loss / take-profit and a **live R:R** readout, draggable and persisted like a rectangle (`explore.md:16-20`).

**Why align with SMC.** The server already computes, single-source, a `Setup` carrying exactly the levels a position needs (`entry, stop, take_profit, rr` — `src/smc/signals.py:26-33`), delivered as `window.marketChart.smc.setups` (`web/market/quotes.py:697-708`, `controllers/smc.js:230,240`). The position tool may be **seeded from those levels verbatim**; the client only re-derives R:R while the user *edits* the box, which is inherent to any draggable drawing and is NOT a re-run of the SMC engine (`docs/architecture/chart-modules.md` "Single source"; `explore.md:172-182`).

## Scope

### In Scope
- Pure cores `measure-core.js` (reuses `intervalSeconds` from `chart-core.js:16-38`) and `position-core.js`.
- New controller `controllers/measure.js` — ephemeral overlay primitive + DOM readout.
- `Drawing.Kind.POSITION`: `{entry:{time,price}, stop:number, take_profit:number}` (`explore.md:305-309`), reusing `api_drawings` CRUD, `drawing-primitive`, `drawing-interaction-core`, object tree.
- Choices-only `AlterField` migration **`0015`** + one `parse_drawing` schema branch (`web/market/quotes.py:402,422-461`).
- `drawing-core`/`drawing-primitive`/`drawing-interaction-core` position branches.
- `drawings.js` 3-click position flow + explicit "position from setup" SMC seed (`explore.md:196`).
- `tool-icons-core` +2 tool entries; `MODULE_ALLOWLIST` +2 cores, `CONTROLLER_ALLOWLIST` +1 (`web/market/views.py:44-73`).

### Out of Scope
Order execution (HARD — read-only repo, `chart-drawings` R8); SMC internals (`find_setups`/scoring untouched); undo/versioning; saving a measure; shared drawings; new dependency or build; CSP relaxation; `src/` changes.

## Capabilities

### New Capabilities
- `chart-measure`: the ephemeral measure **gesture** — pointer-drag between two points, delta readout (price Δ/% , time, bars, candles), `aria-live` DOM readout, Esc/tool-change/symbol-switch cancel. **Fork 4 resolved:** measure gets its **own** capability, not a stretch of `chart-drawings` — it is not a `Drawing` (no CRUD, no row, no tree entry), so folding it into `chart-drawings` would break that spec's persistence contract (`explore.md:316-320`). Position stays in `chart-drawings`.

### Modified Capabilities
- `chart-drawings`: gains a `position` kind — **R1** `Kind` enum; **R5** `points` schema `{entry,stop,take_profit}`; **R6** render (risk/reward zones + 3 levels + R:R text; `autoscaleInfo` includes `stop`/`tp`); **R10** handles (`handlesFor`/`applyDrag`/`bodyHit`) for the 3 levels + entry anchor; **R8** read-only boundary unchanged.
- `chart-toolbar`: **R1** gains a `Measure` group and a `Positions` group; two `TOOL_LABELS` + two `ICON_BODIES` (`tool-icons-core.js:14-19`, `explore.md:253-259`).
- `market-chart`: **R14** inventory gains `measure-core.js`/`position-core.js` (pure cores) + `controllers/measure.js` (controller); `MODULE_ALLOWLIST` +2, `CONTROLLER_ALLOWLIST` 11→12; **R18/R20** seam stays 8 keys and `STORE_KEYS` stays 11 — neither tool adds a key (`explore.md:290-292`).
- `design-system`: **R6/R9** — Long/Short MUST NOT be color-only (text label + arrow), readouts are `aria-live` DOM (`explore.md:270-276`).

## Approach

Layered F0/F5 extension; geometry lives in pure cores so every touched controller stays ≤300 (`explore.md:201-219`).

- **Pure cores first** (node-tested, no DOM): `measure-core.js` (`measure(a,b,intervalSeconds)→{priceDelta,pricePct,timeDelta,bars,candles}` + `formatMeasure`) and `position-core.js` (`levelsFrom`/`riskReward`/`positionBox`/`positionHandles`/`defaultPositionStyle`).
- **Measure (ephemeral, own controller):** `controllers/measure.js` owns its own `#chart` pointer listeners guarded by `state.tool==="measure"`; attaches ONE primitive to `host.getCandleSeries()` while a measurement exists; `autoscaleInfo` returns `null`; redraw via `requestUpdate` only; cleared on release/Esc/tool-change. No store key, no seam key, no persistence (`explore.md:224-230`). Its `onPointerDown` guard is safe because `drawing-interaction.js:94` already bails when a tool is active.
- **Position (persisted `Drawing.Kind.POSITION`):** 3-click collection through the existing `host.subscribeClick → drawings.onChartClick` path (mirrors trendline/rect `drawings.js:193-199`), finalize POSTs `kind="position"` via `createDrawing` — no new endpoint (`drawings.js:134-155`). Drag reuses the kind-agnostic interaction controller; only the core gains position cases (`explore.md:238-251`).
- **SMC seed — explicit** (`explore.md:312-316`): a "position from setup" action copies `entry/stop/take_profit` verbatim from `window.marketChart.smc.setups`; no JS recompute; works without a setup too.
- **Ceiling discipline:** `controllers/smc.js`=300 and `controllers/object-tree.js`=299 MUST stay untouched; both are by construction — position rows appear in the existing generic `Drawings` group, measure is a separate controller (`explore.md:210-219`).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `market/measure-core.js` | New | pure measure math (+`formatMeasure`) |
| `market/position-core.js` | New | pure position geometry + R:R |
| `controllers/measure.js` | New | ephemeral measure overlay + readout |
| `market/drawing-core.js` | Modified | `DRAWING_KINDS` + `defaultStyle` position |
| `market/drawing-primitive.js` | Modified | position render branch → `position-core.positionBox` |
| `market/drawing-interaction-core.js` | Modified | position `handlesFor`/`applyDrag`/`bodyHit` |
| `controllers/drawings.js` | Modified | 3-click position flow + SMC seed |
| `market/tool-icons-core.js` | Modified | +Measure/+Positions groups + icons |
| `controllers/smc.js`, `controllers/object-tree.js` | Untouched | MUST stay ≤300/≤299 |
| `web/trading/models.py`, `migrations/0015_*` | Modified/New | `Kind.POSITION` choice, choices-only `AlterField` |
| `web/market/quotes.py` | Modified | `parse_drawing` position schema branch |
| `web/market/views.py` | Modified | allowlists +2 modules, +1 controller |
| `chart.html`, `theme.css` | Modified | modulepreload, readout tokens |
| `tests/js/*`, `tests/web/*` | Modified | cores, api/e2e, allowlist count 12 |

## Rollback Plan

- **Migration `0015`** is a choices-only `AlterField` (no schema/data change, `explore.md:292-295`) → `python manage.py migrate trading 0014`; zero data loss.
- **Feature-branch chain** → drop the tracker branch and all child slices; no merge to `develop` until green.
- **Measure is ephemeral** → revert `controllers/measure.js` + its JS/CSS/markup; no persisted state to unwind.
- No CSP, dependency, `src/`, or destructive-schema change; each slice independently revertible.

## Risks

| Risk | L | Mitigation |
|------|---|------------|
| 300-line ceiling (`smc.js`=300, `object-tree.js`=299) | High | both MUST stay untouched; geometry in cores; measure in its own controller |
| `window.marketChart` 8-key freeze (no 9th) | High | assert via DOM/bus + captured POST (`market-chart` R18/R20) |
| `STORE_KEYS` frozen 11 (R14) | High | no store key added; tool value only (`chart-store.js:13-27`) |
| #68 single-write-path | High | both render on primitives + `requestUpdate`; `setData` spy green |
| Single-source (no JS SMC recompute) | Med | seed copies `setups` verbatim; only drag re-derives R:R |
| New `Kind` needs `parse_drawing` branch or POST 400s | High | add `position` branch + full branch matrix (`quotes.py:422-461`) |
| `Kind` choices change → migration `0015` | Med | `makemigrations --check` green; `0015` round-trip test |
| Patch coverage 100% | High | `diff-cover`; valid/bad/degenerate (`entry==stop`) matrix |
| E2E class-C flake (#149) | Med | readiness-gated `_wait_ready`; assert DOM + network, never pixels |

## Read-Only Boundary

MUST NOT place/modify/cancel orders, expose order endpoints, or relax any read-only invariant (read-only repo). `src/` framework-free and unchanged; `requirements.txt` unchanged; CSP unchanged (icons are JS-built inline SVG strings). Strict TDD (`openspec/config.yaml`): tests precede implementation.

## Delivery (Feature Branch Chain)

Over the 400-line budget (`explore.md:339-343`) → chained PRs. S1 cores + node tests; S2 `Kind.POSITION` + migration `0015` + `parse_drawing` + API round-trip; S3 measure controller + toolbar + position render/interaction + E2E. Base: tracker branch `feat/f6-measure-position`.

- Chained PRs recommended: **Yes**
- 400-line budget risk: **High**

## Success Criteria

- [ ] Measure shows price Δ/%, time, bars, candles between two points; ephemeral (no store/seam/persistence).
- [ ] Position draws entry/SL/TP + correct R:R; draggable; persists across reload.
- [ ] SMC seed copies server `entry/stop/take_profit` verbatim; no JS SMC recompute.
- [ ] `window.marketChart` stays 8 keys; `STORE_KEYS` stays 11; size guard passes with empty allowlist (`smc.js`/`object-tree.js` untouched).
- [ ] POST/PUT validate the position schema (bad → 400); cross-user A≠B → 404; patch coverage 100%.
- [ ] `node --test` + `pytest` green; migration `0015` round-trips (`makemigrations --check`).
