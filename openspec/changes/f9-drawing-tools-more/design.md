# Design: f9-drawing-tools-more (issue #122, Fase F9)

## Technical Approach

Eight new kinds (`ray`, `vline`, `channel`, `price`, `callout`, `fib_ext`,
`fib_time`, `fib_zone`) ride the SAME five-layer stack the six existing kinds use
(`proposal.md:9-11`). All new geometry lives in **three new pure cores**; the
existing cores gain exactly **one dispatch guard each** and never a growing
`if/else` (`explore.md:113-128`). The 300-line ceiling is enforced with an EMPTY
allowlist (`test_module_size_guard.py:20,23`), so the design is driven by line
arithmetic, not taste: `drawings.js`=298 (`wc -l`, verified) has 2 lines of
headroom and `drawing-interaction-core.js`=271 has 29, so both the 8-kind flow
AND the pre-existing 2-click flow must move out of `drawings.js`. Persistence is
reused unchanged; the only server delta is one choices-only migration plus eight
`parse_drawing` branches (`quotes.py:427-461`). #68 holds: new kinds render on
primitives + `requestUpdate` and POST only via `createDrawing`
(`drawings.js:152`).

## Architecture Decisions

| # | Decision | Choice | Alternatives rejected | Rationale |
|---|---|---|---|---|
| D1 | New geometry home | Three new pure cores: `drawing-tools-core`, `fib-tools-core`, `drawing-click-flow-core` | extend `drawing-interaction-core` (271) / `drawing-core` inline | `drawing-interaction-core` has 29 free lines; 8 kinds × 3 fns ≈ 100+ (`explore.md:99-101`). A core is the seam the ceiling demands. |
| D2 | Descriptor dispatch | `TOOL_SPECS[kind] = {clicks, style, path, handles, bodyHit, drag}`; each existing core adds ONE guard `if (Tools.NEW_KINDS.includes(kind))` | per-kind `if/else` in each core | One guard keeps the 6-kind branches byte-identical and the diff tiny (`proposal.md:70-73`). |
| D3 | `channel` schema | 3-point `{p1,p2,p3}` (p3 = parallel offset) | 2-point + fixed pixel width | Geometrically honest: the offset is data, so it survives a zoom and a reload (`explore.md:200-202`, Q1). |
| D4 | `fib_ext` ratios | New `FIB_EXT_RATIOS = [0, 0.618, 1, 1.272, 1.618, 2.618]` in `fib-tools-core` | mutate `FIB_RATIOS` | Extension ≠ retracement; `fib_time`/`fib_zone` reuse `FIB_RATIOS` verbatim (`explore.md:23-26`). |
| D5 | `price` vs `hline` | Distinct kind `price`: `hlinePath` + a right-axis price label | style option on `hline` | Carries a right-axis tag `hline` lacks; deletion test — removing it loses the label (`explore.md:207-209`, Q3). |
| D6 | Click flow | Extract BOTH the new 8-kind flow and the existing 2-click + `positionDraft` into `drawing-click-flow-core` | extract only the new flow | Only-key-that-fits: 298 + 8-kind flow > 300. Forced, covered by e2e (`drawings.js:976-1010`), (`explore.md:130-143`, Q5). |
| D7 | `callout` text | Reuse `#text-dialog` (`chart.html:71-78`) | new dialog | Zero DOM change, one dialog for text + callout (`explore.md:215-216`, Q6). |
| D8 | Migration | ONE choices-only `AlterField` `0016_drawing_kind_tools`, reversible | 8 migrations | Mirrors F6 `0015` precedent (`0015:12-33`); `choices` lives in Django state, SQLite-safe. |

## Module Decomposition & Line Budget

New files (all ≤300):

| File | Lines | Exports / role |
|---|---|---|
| `market/drawing-tools-core.js` | ~235 | `NEW_KINDS`, `TOOL_SPECS`, `defaultToolStyle`, `toolPath`, `toolHandles`, `toolBodyHit`, `toolDrag`, `clicksFor` |
| `market/fib-tools-core.js` | ~95 | `FIB_EXT_RATIOS`, `fibExtLevels`, `fibTimePath`, `fibZoneBands` |
| `market/drawing-click-flow-core.js` | ~85 | `createFlow()` → `{collect, cancel, active, reset}` |
| `web/trading/migrations/0016_drawing_kind_tools.py` | ~40 | choices-only `AlterField` |

Before → after on every **touched** module (`wc -l`, verified this session):

| File | Now | Δ | After | What changes |
|---|---|---|---|---|
| `controllers/drawings.js` | 298 | **−36** | **~262** | import `createFlow` replaces `createDraft` (−1); `pendingAnchor`/`pendingAnchorKind`/`positionDraft` (25-29) → `const flow = createFlow()` (−4); `onChartClick` 193-230 (38 lines) → ~11-line delegate (−27); `store.subscribe` 248-254 (−2); Escape 260-267 (−3); `clearForSwitch` (−2); callout dialog merge (+4) |
| `drawing-interaction-core.js` | 271 | +10 | **~281** | 3 guards (`handlesFor:31`, `bodyHit:107`, `applyDrag:162`) → `Tools.tool*`; import |
| `drawing-primitive.js` | 178 | +50 | **~228** | `renderTool` canvas switch (8 branches) + 1 guard in `renderShape:37` + `priceRangeFor:14` pushes `p3`; imports |
| `drawing-core.js` | 165 | +13 | **~178** | `DRAWING_KINDS:13` +8; `COLORS:17` +8; `defaultStyle:28` one delegate guard; import `Tools` |
| `tool-icons-core.js` | 76 | +12 | **~88** | `TOOL_GROUPS:14` regroups 8; `TREE_GROUPS[0].kinds:28` +8; `ICON_BODIES:37` +8 plain strings |
| `controllers/draw-toolbar.js` | 144 | +16 | **~160** | `TOOL_KEYS:20` +8 letters; `TOOL_LABELS:31` +8 names |
| `views.py` | — | +3 | — | `MODULE_ALLOWLIST:44` +3 cores; `CONTROLLER_ALLOWLIST:71` **unchanged** |
| `web/trading/models.py` | — | +8 | — | `Kind:244-249` +8 (choices only) |
| `quotes.py` | — | +24 | — | `parse_drawing:427-461` +8 branches |
| `controllers/smc.js` (300) | 300 | **0** | 300 | **BYTE-UNTOUCHED** |
| `controllers/object-tree.js` (299) | 299 | **0** | 299 | **BYTE-UNTOUCHED** — generic row `:130` renders new kinds free |
| `chart-store.js`, `chart-host.js`, `main.js`, `drawing-interaction.js` | — | **0** | — | untouched — no key, no seam, no event |

**Ceiling proof.** Every touched module ends ≤281. The two at-ceiling modules
(`smc.js`=300, `object-tree.js`=299) are structurally untouchable: rows are
generic (`object-tree.js:130` prints `row.kind + " #" + row.id`) and the new
geometry never imports `smc.js`. If `drawing-primitive.js` ever approaches 300,
the extraction is `renderTool` → a `drawing-tool-render.js` module (a fourth
core); it is NOT needed at ~228 (72 lines of margin).

## Layer Compliance

| New module | Layer (`chart-modules.md:11-18`) | Allowed imports | DI |
|---|---|---|---|
| `drawing-tools-core.js` | Pure core | `drawing-core.js` (`FIB_RATIOS`), `fib-tools-core.js` | — |
| `fib-tools-core.js` | Pure core | `drawing-core.js` (`FIB_RATIOS`) only | — |
| `drawing-click-flow-core.js` | Pure core | `drawing-tools-core.js`, `position-core.js` | — |

New cross-core edges are core→core (allowed, mirrors `drawing-primitive →
position-core` F6). `drawings.js`/`draw-toolbar.js` stay controllers and never
import `main` (`chart-modules.md:16,20-21`). `chart-store` config-only and the
`window.marketChart` 8-key seam (`main.js`) are untouched.

## The Descriptor-Map Contract

```js
// drawing-tools-core.js — pure; kind → behaviour, no if/else. ratio 0 == p2.
export const NEW_KINDS = ["ray","vline","channel","price","callout","fib_ext","fib_time","fib_zone"];
export const TOOL_SPECS = {
  ray: {
    clicks: 2,
    style: { color: COLORS.ray, lineWidth: 1 },
    path(row, map) { /* {a:{x,y}, b:{x,y}} where b is projected to the right edge */ },
    handles(points, map) { /* [{id:"p1",x,y},{id:"p2",x,y}] (off-bar omitted) */ },
    bodyHit(points, x, y, map) { /* point-seg dist <= BODY_RADIUS */ },
    drag(points, target, d, map) { /* fresh {p1,p2}; null inverse keeps old component */ },
  },
  // vline, channel, price, callout, fib_ext, fib_time, fib_zone — same six keys
};
export function clicksFor(kind) { return (TOOL_SPECS[kind] || {}).clicks || 0; }
export function defaultToolStyle(kind) { return { ...TOOL_SPECS[kind].style }; }
export function toolPath(kind, row, map) { return TOOL_SPECS[kind].path(row, map); }
export function toolHandles(kind, points, map) { return TOOL_SPECS[kind].handles(points, map); }
export function toolBodyHit(kind, points, x, y, map) { return TOOL_SPECS[kind].bodyHit(points, x, y, map); }
export function toolDrag(kind, points, target, d, map) { return TOOL_SPECS[kind].drag(points, target, d, map); }
```

Dispatch (three call sites, one guard each — never a growing chain):

```js
// drawing-core.js defaultStyle:28
if (Tools.NEW_KINDS.includes(kind)) return Tools.defaultToolStyle(kind);
// drawing-primitive.js renderShape:37
else if (Tools.NEW_KINDS.includes(kind)) { renderTool(ctx, row, map); }
// drawing-interaction-core.js handlesFor:31 / bodyHit:107 / applyDrag:162
if (Tools.NEW_KINDS.includes(kind)) return Tools.toolHandles(kind, points, map); // etc.
```

## Data Flow

**(a) Create — click(s) → collect → POST → fromApi → primitive:**

    host.subscribeClick(drawings.onChartClick)            [main.js:135]
      └─▶ flow.collect(state.tool, {time, price})
            clicks < clicksFor(kind) → {status:"pending"}
            clicks == N              → {status:"ready", points}
            kind ∈ {text,callout}     → {status:"dialog", points}
      ├─ dialog → #text-dialog.showModal() → close merges text → createDrawing
      └─ ready  → createDrawing(kind, points, styleFor(kind, points))
            └─▶ POST /market/api/drawings  [drawings.js:152-177, no new route]
                  └─▶ _post_drawing → parse_drawing(kind,…)  [views.py:442,quotes.py:427]
            └─▶ Draw.fromApi → currentDrawings.push → attachAllDrawings()
                  └─▶ makeDrawingPrimitive → renderShape dispatch

**(b) Render dispatch:**

    makeDrawingPrimitive.autoscaleInfo → priceRangeFor(row)   [primitive:172]
      priceRangeFor:14 pushes p1/p2/p3/price/stop/tp
    paneViews.draw → renderShape(ctx, size, row, map, selected)   [primitive:37]
      NEW_KINDS guard → renderTool(ctx,row,map) → toolPath(kind,row,map) → canvas

**(c) Drag dispatch (kind-agnostic controller, one guard):**

    #chart pointerdown → grabHandle(rows,…)   [drawing-interaction.js:158]
      handlesFor:31 → NEW_KINDS guard → Tools.toolHandles(kind,points,map)
    pointermove → applyDrag(row,target,dx,dy,map)   [:182]
      applyDrag:162 → NEW_KINDS guard → Tools.toolDrag(...) → fresh points
      └─▶ bus.emit("drawing:changed",{id,points,persist:false}) → requestUpdate()
    pointerup → bus.emit("drawing:changed",{id,points,persist:true}) → ONE PUT  [:201]

**(d) Undo replay (kind-agnostic, unchanged):**

    bus.on("drawing:created") → history.push({op:"create",after:{kind,points,style}})
      undo.js:101-108 — opaque to kind; replay re-POSTs via drawings.createDrawing:134
      fib_ext/channel/… replay verbatim; NO new event, NO new key.

## Interfaces / Contracts

```js
// fib-tools-core.js — pure, never throws; null inverse / off-bar degrades.
export const FIB_EXT_RATIOS = [0, 0.618, 1, 1.272, 1.618, 2.618];
export function fibExtLevels(price1, price2, ratios) {
  // ratio 0 == price2 (mirrors fibLevels drawing-core.js:96-101); ratio 1 = the
  // p1→p2 leg projected BEYOND p2. -> [{ratio, price}]  (p3 provides x extent only)
  return (ratios || FIB_EXT_RATIOS).map(r => ({ ratio: r, price: price2 + (price2 - price1) * r }));
}
export function fibTimePath(p1, p2, ratios) {
  // -> { levels: [{ratio, time, x}] } at time = p1.time + (p2.time-p1.time)*ratio.
  // time/x null when the mapper has no bar for it (the vertical leg is skipped).
}
export function fibZoneBands(p1Price, p2Price, ratios) {
  // -> [{ ratioLo, ratioHi, priceLo, priceHi, yLo, yHi }] between consecutive
  // FIB_RATIOS levels; y may be null and the band is skipped.
}

// drawing-click-flow-core.js — pure; the ONE 1/2/3-click machine.
export function createFlow() {
  let kind = null, clicks = [];
  function collect(k, point) {
    // k changes → reset (a tool switch drops the half-collected draft).
    // Special: hline/price/vline need 1 click; text/callout return "dialog"
    // on their final click so the controller owns the modal; the rest return
    // "ready" with the kind-shaped points:
    //   ray/fib_time/fib_zone → {p1,p2};  channel/fib_ext → {p1,p2,p3};
    //   callout → {p1,p2};  text → {time,price};  position → {entry,stop,take_profit}.
    // -> {status:"pending"} | {status:"ready", kind, points} | {status:"dialog", kind, points}
  }
  function cancel() { kind = null; clicks = []; }
  function active() { return clicks.length > 0; }
  function reset() { cancel(); }
  return { collect, cancel, active, reset };
}
```

`drawings.js onChartClick` becomes a ~11-line delegate:

```js
function onChartClick(param) {
  const candleSeries = host.getCandleSeries();
  if (!state.tool || !param || !param.point || !candleSeries) return;
  if (state.tool === "measure") return;           // ephemeral (measure.js owns it)
  const price = candleSeries.coordinateToPrice(param.point.y);
  if (price === null || price === undefined) return;
  const out = flow.collect(state.tool, { time: param.time, price: price });
  if (!out) return;
  if (out.status === "dialog") { pendingDialog = out; openTextDialog(out); return; }
  if (out.status === "ready") createDrawing(out.kind, out.points, styleFor(out.kind, out.points));
}
```

`styleFor(kind, points)` = `position → defaultPositionStyle(points)`, `text →
textStyle()`, else `Draw.defaultStyle(kind)`. `#text-dialog` close (269-282) reads
`pendingDialog` and merges the typed text for BOTH `text` and `callout` before
calling `createDrawing`. `store.subscribe` (248-254), Escape (260-267) and
`clearForSwitch` (287-295) call `flow.cancel()` / `flow.reset()`.

## Server Design

**Migration `0016_drawing_kind_tools`** (choices-only `AlterField`, reversible;
mirrors `0015:12-33`):

```python
class Migration(migrations.Migration):
    dependencies = [("trading", "0015_drawing_kind_position")]
    operations = [migrations.AlterField(
        model_name="drawing", name="kind",
        field=models.CharField(choices=[
            ("hline","Hline"),("trendline","Trendline"),("fib","Fib"),("rect","Rect"),
            ("text","Text"),("position","Position"),
            ("ray","Ray"),("vline","Vline"),("channel","Channel"),("price","Price"),
            ("callout","Callout"),("fib_ext","FibExt"),("fib_time","FibTime"),("fib_zone","FibZone"),
        ], max_length=16),
    )]
```

No column/row change; `python manage.py migrate trading 0015_drawing_kind_position`
reverses with zero loss. `DRAWING_KINDS = frozenset(Drawing.Kind.values)`
(`quotes.py:402`) auto-includes the 8 once the model choice lands.

**`parse_drawing` +8 branches** (`quotes.py:427-461`; one `elif` each, after
`text`/`position`), reusing `_parse_point` (`:412-419`):

| kind | `points` schema | 400 when |
|---|---|---|
| `ray` | `{p1,p2}` both `{time:int,price:num}` | keys ≠ set; p1/p2 not dict; time non-int; price non-num |
| `vline` | `{time:int}` | `time` non-int; extra keys |
| `channel` | `{p1,p2,p3}` all anchors | keys ≠ set; any anchor malformed |
| `price` | `{price:num}` | price non-num/bool |
| `callout` | `{p1,p2,text:str}` p1/p2 anchors, text non-empty | keys ≠ set; anchor malformed; text not str / blank |
| `fib_ext` | `{p1,p2,p3}` all anchors | keys ≠ set; anchor malformed |
| `fib_time` | `{p1,p2}` both anchors | keys ≠ set; anchor malformed |
| `fib_zone` | `{p1,p2}` both anchors | keys ≠ set; anchor malformed |

Every `ray`/`trendline`-style branch uses `set(points) != {…}` (exact keys, as
`:449`). No new route (`urls.py` reused). `for_user` unchanged — CRUD reuses
`api_drawings`/`api_drawing_detail` (`views.py:407,491`); cross-user id → 404,
R14 preserved.

## a11y + CSP + CSS

- **8 icons as plain strings** in `ICON_BODIES` (`tool-icons-core.js:37-46`), no
  `on*` attribute, injected with `innerHTML` on a native `<button>`
  (`draw-toolbar.js:98`) — CSP `script-src` unchanged.
- **Letters** `ray=A, vline=I, channel=C, price=U, callout=O, fib_ext=E,
  fib_time=W, fib_zone=Z` — non-colliding with `H/T/F/R/X/M/P` (`draw-toolbar.js:20-28`)
  and object-tree `v/l/s/Delete` (`object-tree.js:112,119,141`). Router stays
  `#chart`-scoped (`draw-toolbar.js:124-141`); no global binding.
- **Not color-only**: `price` draws a right-axis price label; `callout` its text;
  `fib_ext`/`fib_time`/`fib_zone` ratio labels (primitive `fillText`, as `fib`
  already does at `:64`); ray/vline/channel are distinguished by shape.
- **No new CSS tokens** — icons reuse `currentColor`, labels use existing
  `--chart-text`/`--muted`/`--accent`. No `chart.html` change (callout reuses
  `#text-dialog`).

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit (node) | `drawing-tools-core` `TOOL_SPECS` completeness (8 kinds, each with clicks/path/handles/bodyHit/drag), `clicksFor`, each `toolPath`/`toolDrag`; `fib-tools-core` `fibExtLevels` (ratio 0 == p2), `fibTimePath`, `fibZoneBands`; `drawing-click-flow-core` 1/2/3-click + dialog + cancel/reset; `drawing-core.fromApi` accepts 8; `tool-icons-core` 8 CSP-clean distinct icons; `object-tree` renders new kinds | `node --test "tests/js/**/*.test.js"` (mirror `drawing-core.test.js` mapper + null-guard style) |
| Integration (pytest) | 8-kind POST/GET/PUT round-trip; per-kind 400 matrix (schema table above); A≠B→404; `diff-cover` 100% on `parse_drawing` | `test_market_api.py` |
| Migration | `0016` forward adds 8 choices, reverse to `0015`, every prior row survives, `makemigrations --check` green | `test_migration_0016.py` (copy `test_migration_0015.py`) |
| Contract | `MODULE_ALLOWLIST` +3 served JS; `CONTROLLER_ALLOWLIST == 15` unchanged; `STORE_KEYS == 11`; `window.marketChart` 8 keys | `test_market_ux.py:127,146` + `chart-store.test.js` + E2E seam |
| E2E | tool click → captured 8-kind POST; drag → ONE PUT; undo replays a new kind; `setData` spy green; readiness-gated `_wait_ready`, DOM+network only, never pixels (#149) | `test_market_e2e.py` (mirrors `:976-1010`) |
| Guard | no module >300 (`drawings.js` → ~262; `smc.js`/`object-tree.js` byte-untouched) | `test_module_size_guard.py` |

## Risks & Mitigations

Carried from `explore.md §7` / `proposal.md §Risks`: **R1** ceiling — three cores
+ `drawings.js` SHRINKS to ~262, `smc.js`/`object-tree.js` untouched (structural
proof above); **R2** 8-key seam — new kinds reuse the `drawings` key
(`drawings.js:50,111`); **R3** `STORE_KEYS` 11 — only the existing `tool` value;
**R4** #68 — primitives + `requestUpdate`, `setData` spy; **R5** 8 `parse_drawing`
branches — full per-kind 400 matrix; **R6** choices drift — `0016` + round-trip
test; **R7** patch 100% — node + API + migration tests; **R8** R14 `for_user` —
CRUD path unchanged; **R9** E2E flake (#149) — readiness gate, DOM+network, no
pixels; **R10** undo replay — kind-agnostic (`undo.js:101-108`), e2e-verified;
**R11** fib orientation — node-test `ratio 0 == p2` for ext/time/zone.
**New**: **R12** `renderTool` canvas switch grows `drawing-primitive.js` to ~228 —
if it ever passes 300, extract to `drawing-tool-render.js` (not needed now);
**R13** the extracted flow touches F6/F7 code (`drawings.js:218-229`) — covered by
the existing e2e tool/drag/undo scenarios.

## Migration / Rollout

Feature-branch chain off tracker `feat/f9-drawing-tools-more` (`proposal.md:136-144`;
>400 lines, `chained-pr`): **S1** the 3 pure cores + node tests (revert = delete 3
files, no app impact); **S2** `Kind` +8 + `0016` + `parse_drawing` + API/migration
tests + allowlist (revert = `migrate trading 0015`, drop 8 `elif`s); **S3** render/
interaction/click-flow dispatch + toolbar icons/letters + `drawings.js` shrink + e2e
(revert = revert S3). Each slice independently revertible; no CSP, dependency,
store-key, seam-key or destructive-schema change.

## Open Questions

None blocking. `explore.md §8` forks resolved: Q1→D3, Q2→D4, Q3→D5, Q4→§a11y
letters, Q5→D6, Q6→D7.
