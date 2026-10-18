# Exploration: f9-drawing-tools-more

Issue #122, Fase F9 (the LAST "Ola 4" frontend feature). Branch `develop` @
`1150b07`. Read-only — no code changed, no branch created. Builds on the archived
F6 chain (`openspec/changes/archive/2026-10-17-f6-measure-position/`).

## 1. Problem framing — the 8 tools

Eight new `kind` values, each a different geometry over the SAME persistence /
print / interaction stack the six existing kinds already use. The geometry:

| kind | points | geometry | reuses |
|---|---|---|---|
| `ray` | 2 `{time,price}` | line from p1 through p2, extended to the RIGHT edge only | `trendlinePath` (add right extension) |
| `vline` | 1 `{time}` | full-height vertical line at a bar/time | new (mirror of `hlinePath`) |
| `channel` | 2–3 `{time,price}` | two PARALLEL lines (base p1→p2, parallel offset by p3) | `trendlinePath` ×2 |
| `price` | 1 `{price}` | horizontal line + a right-axis price LABEL (labelled `hline`) | `hlinePath` + label |
| `callout` | 2 `{time,price}` + `text` | anchor point + an arrow to a text balloon | `textPath` + arrow |
| `fib_ext` | 3 `{time,price}` | Fib EXTENSION levels projected from a 3-point swing (ratios > 1) | new levels, reuse `FIB_RATIOS` |
| `fib_time` | 2 `{time,price}` | VERTICAL time lines at Fib ratios of the bar span | `FIB_RATIOS` over time |
| `fib_zone` | 2 `{time,price}` | coloured BANDS between consecutive Fib levels | `fibLevels` bands |

`FIB_RATIOS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]` (`drawing-core.js:16`) is
the retracement set; `fib_ext` needs ratios ABOVE 1 (e.g. 1.272 / 1.618 / 2.618)
— a NEW `FIB_EXT_RATIOS` set, extension not replacement. `fib_time`/`fib_zone`
reuse `FIB_RATIOS` verbatim.

## 2. Codebase map — every layer a kind touches

For a new kind to create/move/persist, it must reach **all five layers** (F6 did
exactly this for `position`):

1. **Enum** — `web/trading/models.py:244-249` (`Drawing.Kind`); `kind` field
   `:253` (`CharField(max_length=16, choices=Kind.choices)`).
2. **Validator** — `web/market/quotes.py:402` (`DRAWING_KINDS =
   frozenset(Drawing.Kind.values)`) and the per-kind branch matrix in
   `parse_drawing` `:427-461` (a `position` `elif` at `:445-460` is the precedent).
   **A new kind with no branch here 400s.**
3. **Pure core (JS)** — `drawing-core.js:13` (`DRAWING_KINDS`), `:25-33`
   (`defaultStyle`), the path builders `:74-131` (`hlinePath`/`trendlinePath`/
   `fibLevels`/`fibPath`/`rectPath`/`textPath`), `fromApi` `:40-50`.
4. **Render** — `drawing-primitive.js:36-86` (`renderShape` per-kind branches),
   `priceRangeFor` `:14-32` (autoscale), `drawHandles` `:125-136`.
5. **Interaction** — `drawing-interaction-core.js:31-60` (`handlesFor`),
   `:107-146` (`bodyHit`), `:162-227` (`applyDrag`).
6. **Click flow** — `controllers/drawings.js:193-230` (`onChartClick`: hline 1
   click, trendline/fib/rect 2, position 3 via `positionDraft`, text dialog).
7. **Toolbar** — `tool-icons-core.js:14-23` (`TOOL_GROUPS`), `:37-46`
   (`ICON_BODIES`); `controllers/draw-toolbar.js:20-28` (`TOOL_KEYS`),
   `:31-39` (`TOOL_LABELS`).

Cross-cutting (must NOT regress): `object-tree.js` renders rows generically
(`row.kind + " #" + row.id`, `:130` — no per-kind match, so new kinds appear for
free); `undo.js`/`history-core.js` replay create/move/delete through the SAME bus
events (`history-core.js` is opaque to `kind`; `undo.js:101-108` records
`drawing:created` with `kind/points/style` verbatim); `fromApi` `:41` already
accepts any kind in `DRAWING_KINDS`.

## 3. The migration question (KEY FORK) — **ONE choices-only `0016`**

The issue says "los nuevos `kind` son solo valores del JSON existente" — **that
framing is wrong at the persistence layer, and the explore must correct it.**
`Drawing.kind` is a `CharField` with a `choices` enum (`models.py:244-249,253`).
Django does not enforce `choices` at the DB level, but two things DO depend on
the model choice list:
- `parse_drawing` rejects any kind outside `DRAWING_KINDS`
  (`quotes.py:402,440-441`) → an unknown kind 400s.
- `makemigrations --check` fails when the model's `choices` drift from the last
  migration (F6 added `0015` for exactly this reason).

F6 precedent: `web/trading/migrations/0015_drawing_kind_position.py` — a
**choices-only `AlterField`** (no column, no row change; reversible to `0014`
with zero data loss). Round-trip proven by `tests/web/test_migration_0015.py`.

**Recommendation: ONE new choices-only `AlterField` migration
`0016_drawing_kind_tools` adding ALL EIGHT new choices at once** (not 8
migrations). It is SQLite-safe: `choices` lives in Django's state, not in a
column constraint, so re-declaring the field touches no schema. `DRAWING_KINDS`
(`quotes.py:402`) auto-includes the new values once the model choice lands.
`Ray, Vline, Channel, Price, Callout, FibExt, FibTime, FibZone` — the emitted
`choices=[...]` list order is cosmetic (Django sorts by value string in
migrations, but only the *set* matters). Cite `models.py:244-249` + `0015`.

## 4. Pure-core split (CRITICAL for the 300-line ceiling)

Baseline `wc -l` (verified this session):

```
smc.js=300  object-tree.js=299  drawings.js=298  drawing-interaction.js=291
main.js=274  drawing-interaction-core.js=271  chart-host.js=267
drawing-primitive.js=178  drawing-core.js=165  draw-toolbar.js=144
position-core.js=127  tool-icons-core.js=76
```

`test_module_size_guard.py` (`CEILING=300`, `ALLOWLIST` EMPTY, `:20,23`) fails
ANY module over 300. **Two modules have no headroom at all:**

- `drawings.js` = **298** (2 lines free) — the 8-kind click flow CANNOT live here.
- `drawing-interaction-core.js` = **271** (29 lines free) — 8 kinds × 3 functions
  (handles/bodyHit/drag) ≈ 100+ lines CANNOT live here.

Adding 8 path builders to `drawing-core.js` (165) and 8 render branches to
`drawing-primitive.js` (178) is possible but leaves little margin.

**Recommended split — new pure cores, mirroring the F6 `position-core` pattern:**

| New module | Responsibility | ~Lines |
|---|---|---|
| `drawing-tools-core.js` | per-kind **descriptor map** for the 8 new kinds: `path`, `style`, `clicks`, `handles`, `bodyHit`, `drag`; exports `NEW_KINDS`, `TOOL_SPECS`, `defaultToolStyle`, `toolPath`, `toolHandles`, `toolBodyHit`, `toolDrag`, `clicksFor` | ~230 |
| `fib-tools-core.js` | `fibExtLevels`, `fibTimePath`, `fibZoneBands`; imports `FIB_RATIOS` from `drawing-core.js`, adds `FIB_EXT_RATIOS` | ~90 |
| `drawing-click-flow-core.js` | generic kind→clicks collector: `collect(kind, point) → points \| null`; the 1/2/3-click state machine (precedent: `position-draft-core.js`) | ~80 |

**How each existing module stays generic (kind→builder dispatch, never a growing
`if/else` chain):**

- `drawing-core.js` (165): `+8` kind strings in `DRAWING_KINDS:13`; `defaultStyle`
  `:28-33` delegates new kinds to `Tools.defaultToolStyle(kind)` (~+12 → ~177).
  New path builders live in `drawing-tools-core.js`, NOT here.
- `drawing-primitive.js` (178): `renderShape` `:37` gains ONE guarded block —
  `else if (Tools.NEW_KINDS.includes(kind)) renderTool(ctx,row,map)` — where
  `renderTool` is a small per-kind canvas switch living in the primitive
  (canvas is not pure, so it can't move to a core). `priceRangeFor:14-32` already
  collects p1/p2/price/stop/tp; `fib_ext` needs a third anchor `p3` — add one
  push (~+50 → ~228).
- `drawing-interaction-core.js` (271): `handlesFor:31`, `bodyHit:107`,
  `applyDrag:162` each gain ONE guard — `if (Tools.NEW_KINDS.includes(kind))
  return Tools.toolHandles(...)` — dispatching to the descriptor map. Existing
  6-kind branches untouched (~+10 → ~281, 19 lines margin).

**Ceiling proof (after):** `drawings.js` SHRINKS: its inline 2-click block
(`:223-229`) and the `positionDraft` call (`:218-222`) move into
`drawing-click-flow-core.js`, so `onChartClick` becomes a ~10-line delegate to
`Flow.collect(state.tool, {time,price})` (~298-20+8 = ~286). The two at-ceiling
modules `smc.js` (300) and `object-tree.js` (299) stay **byte-untouched** —
object-tree rows are generic (`:130`), so the 8 new kinds appear with zero edits.
`chart-host.js` (267), `main.js` (274), `chart-store.js` unchanged.

**Trade-off to settle in design (Open Q5):** the lazy version extracts ONLY the
new-kind flow and keeps the existing trendline/fib/rect/position branches inline
— but that GROWS `drawings.js` past 300. Extracting the existing 2-click block
too is REQUIRED to stay under the ceiling, and it touches F6/F7 code (covered by
e2e tests: `test_market_e2e.py:976-1010` tool create, `:1339+` drag). This is a
forced, not optional, refactor.

## 5. Click flow per kind

| kind | clicks | notes |
|---|---|---|
| `vline` | 1 | time only (`map.x` of a bar) |
| `price` | 1 | price only (like `hline`) |
| `ray` | 2 | origin + direction point |
| `callout` | 2 + dialog | anchor + balloon point, then the text dialog (`text-dialog`, `chart.html:71-78`) |
| `fib_time` | 2 | span anchors; ratios over the bar distance |
| `fib_zone` | 2 | two price levels; bands between them |
| `channel` | 2 or 3 | **FORK**: 3 (p1,p2 base + p3 offset) is geometrically honest; 2 = fixed-width offset |
| `fib_ext` | 3 | swing p1,p2 + extension base p3 |

Generalization: the current `pendingAnchor` (2-click, `drawings.js:25,224-229`)
and `positionDraft` (3-click, `position-draft-core.js`) become ONE
`drawing-click-flow-core` state machine keyed by `clicksFor(kind)` (1/2/3). The
collector returns the finished `points` object on the Nth click (kind-shaped:
`{p1,p2}` / `{p1,p2,p3}` / `{time}` / `{price}` / `{time,price,text}`), and
`createDrawing(kind, points, defaultStyle(kind))` POSTs it — one write path
(#68). Cancel (Escape / tool change / symbol switch) drops a half-collected
draft, exactly as `positionDraft.cancel()` does today (`drawings.js:252,262,291`).

## 6. a11y + CSP

- 8 new icons as **plain strings** in `tool-icons-core.js:37-46` (CSP: no inline
  `on*` attribute; injected with `innerHTML` on a native `<button>`,
  `draw-toolbar.js:98`). `currentColor` follows the theme.
- 8 new `TOOL_KEYS` letters (`draw-toolbar.js:20-28`). **Must not collide** with
  existing `H/T/F/R/X/M/P` or the object-tree's `v/l/s/Delete`
  (`object-tree.js:112,119,140-141`). Suggested non-colliding set:
  `ray=A, vline=I, channel=C, price=U, callout=O, fib_ext=E, fib_time=W,
  fib_zone=Z` — settle in design (Open Q4).
- Not-color-only: `price` carries a price label; `callout` carries its text;
  `fib_ext`/`fib_zone`/`fib_time` render ratio labels (`fib` already does,
  `drawing-primitive.js:64`); ray/vline/channel are distinguished by shape.
- No DOM change needed in `chart.html` (callout reuses `#text-dialog`).

## 7. Risk list

| # | Risk | Sev | Evidence / mitigation |
|---|---|---|---|
| R1 | **300-line ceiling** — `drawings.js`=298, `drawing-interaction-core.js`=271 | **High** | `test_module_size_guard.py:20,23`; new geometry in cores, click flow extracted OUT of `drawings.js` (net shrink) |
| R2 | **Seam freeze** — no 9th `window.marketChart` key | High | new kinds reuse the existing `drawings` key (`drawings.js:50,111`); seam stays 8 |
| R3 | **`STORE_KEYS` frozen 11** (`chart-store.js:13-27`) | High | new kinds use the existing `tool` value only — no new key |
| R4 | **#68 single-write-path** — no `setData`/`update` | High | render on primitives + `requestUpdate` only (`drawing-primitive.js:157,173`) |
| R5 | **`parse_drawing` needs 8 new branches** or POST 400s | High | `quotes.py:402,427-461`; full per-kind 400 matrix in `test_market_api.py` |
| R6 | **Choices drift → `makemigrations --check` red** | Med | one `0016` choices-only `AlterField` + `test_migration_0016.py` (copy `test_migration_0015.py`) |
| R7 | **Patch coverage 100%** on new Python + 8 branches | High | `diff-cover`; per-kind valid/invalid matrix |
| R8 | **R14 `for_user`** unchanged | Med | CRUD reuses `api_drawings`/`api_drawing_detail` (`views.py:403,491`) |
| R9 | **E2E class-C flake (#149)** | Med | assert DOM + captured network, never pixels; readiness-gated `_wait_ready` |
| R10 | **Undo/history (F7)** — new kinds must replay | Med | `undo.js`/`history-core.js` are kind-agnostic; `recreate` clones points/style verbatim (`drawings.js:132-135`); verify via e2e undo |
| R11 | **Fib ratio correctness** — orientation `ratio 0 == p2` | Med | `fibLevels` `drawing-core.js:96-101`; test each new fib kind's level math (node) |
| R12 | **`price` vs `hline` overlap** | Low | `price` is a labelled `hline`; confirm the distinction is worth a kind (Open Q3) |
| R13 | **`channel` geometry fork** | Med | 2-point fixed-width vs 3-point offset (Open Q1) |

## 8. Open questions (real forks for proposal/design)

1. **`channel` point schema** — 3 points (`{p1,p2,p3}`, honest parallel) vs 2
   points + fixed pixel width. Affects `parse_drawing`, `handlesFor`, `applyDrag`,
   the click count, and `unit` tests. *(Recommend 3-point.)*
2. **`fib_ext` ratio set** — which extensions (1.272 / 1.618 / 2.618 / …)? New
   `FIB_EXT_RATIOS` in `fib-tools-core.js` (extension, not a `FIB_RATIOS` change).
3. **`price` distinct from `hline`?** — is a labelled horizontal line a new kind
   or a style option on `hline`? *(Recommend keep as a kind: it carries a
   right-axis tag, unlike `hline`.)*
4. **Toolbar letters** — confirm the non-colliding 8-letter set (§6) in design.
5. **Split boundary** — extract the EXISTING 2-click flow into
   `drawing-click-flow-core.js` (required to keep `drawings.js` ≤300, but touches
   F6/F7 code) vs add only the new-kind flow (blows the ceiling). *(Recommend
   extract both.)*
6. **`callout` text source** — reuse `#text-dialog` (lazy) vs a new dialog.
   *(Recommend reuse.)*

## Prioritized brief for the next phase (sdd-propose)

- **Intent**: eight TradingView-parity drawing tools (`ray`, `vline`, `channel`,
  `price`, `callout`, `fib_ext`, `fib_time`, `fib_zone`) on the existing
  drawing stack — pure path builders + per-kind render/interaction/click-flow,
  reusing `FIB_RATIOS`, with ONE choices-only migration `0016`.
- **In scope**: new pure `drawing-tools-core.js` + `fib-tools-core.js` +
  `drawing-click-flow-core.js`; `Drawing.Kind` +8 + `0016`; `parse_drawing` +8
  branches; `drawing-core`/`-primitive`/`-interaction-core` dispatch guards;
  `drawings.js` click-flow extraction; `tool-icons-core` +8 icons/letters;
  allowlists +3 modules; node + API + migration + e2e tests.
- **Out of scope**: orders (read-only, HARD), `src/`, new deps, CSP relaxation,
  `STORE_KEYS`/seam changes, SMC.
- **Delivery**: >400-line budget → chained PRs (S1 pure cores + node tests;
  S2 `Kind` + `0016` + `parse_drawing` + API matrix; S3 render/interaction/click
  flow + toolbar + e2e), mirroring F6's feature-branch chain.

### Ready for Proposal
**Yes.** Every layer is mapped with `file:line`, the migration fork is resolved
(ONE choices-only `0016`), the ceiling-forced split is sized (two modules have
near-zero headroom and dictate the click-flow extraction), and the only blocking
forks are the `channel` schema and the split boundary (both folded into §8).

**Status**: success
**Summary**: Explored F9 (8 new drawing kinds) against the F4/F5/F6/F7 stack; mapped every touched layer with file:line, resolved the migration fork (one choices-only `0016`), and sized the ceiling-forced pure-core split.
**Artifacts**: `openspec/changes/f9-drawing-tools-more/explore.md`
**Next**: sdd-propose
**Risks**: 300-line ceiling (drawings.js=298, drawing-interaction-core.js=271 force the click-flow extraction); 8 `parse_drawing` branches; fib-ratio orientation correctness.
**Skill Resolution**: paths-injected — 3 skills (chained-pr, codebase-design, _shared) + sdd-explore
