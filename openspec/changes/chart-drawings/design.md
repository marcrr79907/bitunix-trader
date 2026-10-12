# Design: chart-drawings (issue #72, Fase A3)

## Technical Approach

Extend A2's seams from a blob to a **collection**. `Drawing` (UserOwnedModel)
joins `trading.models` (R14); `market/api/drawings` reads/mutates it via
`for_user`, keyed by `id` (no upsert — many per chart). Pure `parse_drawing`
validates before write. Rendering is a v5 `ISeriesPrimitive` on `candleSeries`
(already-loaded CDN, no new dep); persistence reuses A2's CSRF/debounce seam.
Geometry lives in `drawing-core.js` (`node --test`). #68 single-write-path
untouched — primitives are a separate canvas layer, never series `setData`/`update`.

    boot:   layout ─→ buildChart ─→ GET drawings ─→ attach primitives ─→ connect ─→ fetchHistory
    click:  subscribeClick ─→ core.pointFromEvent ─→ POST ─→ attach (requestUpdate)
    switch: teardown chart+primitives ─→ GET drawings(new key) ─→ attach

## Architecture Decisions

| Decision | Choice + rationale |
|---|---|
| Row per shape vs blob | **Row per drawing**, CRUD by `id`, **no unique constraint**; index `(user,symbol,interval)`. Many shapes per chart; blob kills delete granularity/concurrency. |
| `points` shape | **One JSON object per kind** (`points` JSONField `default=dict`): the validator's contract, mirroring the spec schema exactly. |
| Validation home | **`quotes.parse_drawing`** (pure, raise-`ValueError`), mirroring `parse_layout_indicators` — view stays thin, patch-covered. |
| Render layer | **`ISeriesPrimitive` on `candleSeries`** over DOM/SVG overlays: coordinates from `priceToCoordinate`/`timeToCoordinate`, CSP untouched, no re-anchor on zoom. |
| Create-owner gotcha | **Explicit `user=request.user` on create**: A2 proved `for_user(qs).create()` filters, it does not inject the owner — omitting `user` raises IntegrityError. |
| Cross-user safety | **GET/DELETE via `for_user`**: B's id resolves to nothing for A → 404 on DELETE, absent from GET. No id-only lookup ever. |

## Data Model

```python
class Drawing(UserOwnedModel):                # web/trading/models.py
    class Kind(models.TextChoices):
        HLINE = "hline"; TRENDLINE = "trendline"; FIB = "fib"
        RECT = "rect"; TEXT = "text"
    symbol = models.CharField(max_length=32)
    interval = models.CharField(max_length=8)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    points = models.JSONField(default=dict)   # per-kind object (below)
    style = models.JSONField(default=dict)    # {color, lineWidth, ...}
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes = [models.Index(fields=["user","symbol","interval"],
                                name="ix_drawing_user_symbol_interval")]
```

Migration `web/trading/migrations/0006_drawing.py`, **additive**,
`dependencies = [("trading", "0005_chartlayout")]`. No unique constraint (many
per key). `OWNED_MODELS` in `tests/web/test_owned_model_guard.py` gains
`"Drawing"` + a negative-control case.

**JSON schemas (exact, frozen):**

| kind | `points` | `style` |
|---|---|---|
| `hline` | `{"price": float}` | `{color, lineWidth}` |
| `trendline` | `{"p1":{"time":int,"price":float},"p2":{...}}` | `{color, lineWidth}` |
| `fib` | same 2-point object as trendline | `{color, lineWidth, levels:[float]}` |
| `rect` | `{"p1":{...},"p2":{...}}` | `{color, lineWidth, fill}` |
| `text` | `{"time":int,"price":float,"text":str}` | `{color, fontSize}` |

`parse_drawing(kind, points, style) -> (points, style)`: `kind ∈ DRAWING_KINDS`
(TextChoices), per-kind shape check (required keys, numeric values), `style` an
object with known keys; any breach raises `ValueError`.

## Endpoint (`web/market/views.py` + `urls.py`)

Routes: `market/api/drawings` (`market_api_drawings`) and
`market/api/drawings/<int:id>` (`market_api_drawing_detail`).

- **GET** `?symbol=&interval=` — `@login_required @require_http_methods(["GET"])`.
  Empty `symbol` / `interval ∉ INTERVALS` → `400`. Then
  `Drawing.for_user(request.user).filter(symbol=…, interval=…)` →
  `200 {"drawings":[{id,kind,points,style}]}` (empty list, never 404).
- **POST** — `@login_required @require_http_methods(["POST"])`, CSRF via
  middleware. Body `{symbol,interval,kind,points,style}`; validate symbol,
  interval, then `parse_drawing` **before any write** → `400`. Create with
  `Drawing.for_user(request.user).create(user=request.user, …)` (explicit
  owner — A2 gotcha). Return `201 {"id","kind","points","style"}`.
- **DELETE** `<int:id>` — `@require_http_methods(["DELETE"])`. Resolve via
  `for_user(request.user).filter(id=id)`; miss → `404` (also the cross-user
  case); hit → delete → `204`. Idempotent for the caller's own rows.

## Render / primitive (`drawing-core.js`, `chart.js`, `chart.html`)

`drawing-core.js` (UMD, mirror `chart-core.js`): pure **hit-test math** and
**per-kind path builders** (`hlinePath`, `trendlinePath`, `fibLevels`,
`rectPath`), plus null guards (`timeToCoordinate` → `null` off-bar → skip leg).
No chart import.

Adapter: one `DrawingPrimitive` class per kind implementing `paneViews()` (a
`draw(target)` renderer using `useMediaCoordinateSpace`), `autoscaleInfo()`
(price range so rays/rects keep scale), `attached({requestUpdate})`; attach via
`candleSeries.attachPrimitive(prim)`; `requestUpdate()` on every change. Toolbar
`<fieldset class="drawings">` of `<button class="draw-tool" data-kind=…>`
(mirrors `.pair`), CSP-safe `addEventListener`; active tool in `state.tool`.
`chart.subscribeClick` → `core.pointFromEvent(param, series, chart)` → POST →
attach. Clear+reload primitives on symbol/interval switch; render after
`loadLayout`/`boot`. Seam: `window.marketChart.drawings = [{id,kind,points,style}]`.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Model | `for_user` scoping, A≠B `DoesNotExist`, many rows per key, index, JSON round-trip, owner required | `test_isolation.py` |
| Guard | `Drawing` in `OWNED_MODELS` + negative-control fixture | `test_owned_model_guard.py` |
| Endpoint | anon→302; GET list/empty; POST 201→GET; 400 bad kind/points/style/interval before write; DELETE 204 + 404 cross-user; CSRF 403; A≠B | `test_market_api.py` |
| JS | path builders, fib levels, hit-test, off-bar null | `tests/js/drawing-core.test.js` |
| E2E | seed via endpoint → boot renders (`drawings` seam + network); click → POST fired; delete → DELETE fired | `test_market_e2e.py` |

## File Changes

| File | Action | Description |
|---|---|---|
| `web/trading/models.py` | Modify | + `Drawing(UserOwnedModel)` |
| `web/trading/migrations/0006_drawing.py` | Create | additive |
| `web/market/views.py` | Modify | + `api_drawings` (GET/POST/DELETE) |
| `web/market/urls.py` | Modify | + drawings + detail routes |
| `web/market/quotes.py` | Modify | + `DRAWING_KINDS`, `parse_drawing` |
| `web/market/templates/market/chart.html` | Modify | drawings toolbar |
| `web/market/templates/market/chart.js` | Modify | primitives, pointer capture, load/save, seam |
| `web/market/templates/market/drawing-core.js` | Create | pure geometry |
| `tests/web/test_owned_model_guard.py` | Modify | `OWNED_MODELS` + fixture |
| `tests/web/test_isolation.py` | Modify | `Drawing` A≠B / many-per-key |
| `tests/web/test_market_api.py` | Modify | endpoint contract |
| `tests/web/test_market_e2e.py` | Modify | draw/save/restore E2E |
| `tests/js/drawing-core.test.js` | Create | pure geometry |

## Guard / Edge Matrix

| Edge | Handling |
|---|---|
| Forgetting `Drawing` in `OWNED_MODELS` | Explicit task + negative-control test case. |
| Cross-user DELETE | `for_user` scope → B's id 404 for A; never an id-only lookup. |
| Create without owner | Explicit `user=request.user` (A2 `update_or_create` lesson). |
| `timeToCoordinate` null off-bar | Core null-guards the leg; E2E interval switch clears primitives. |
| Interval switch | Teardown primitives with the chart; reload per `(symbol,interval)`. |
| Patch coverage (Python-only gate) | Geometry in `drawing-core.js` (`node --test`); E2E is the integration net. |

## Delivery (Feature Branch Chain)

PR1 → tracker branch; PR2 → PR1; PR3 → PR2.

- **PR1 — model** (~90 lines): `Drawing` + `0006` + `OWNED_MODELS` + isolation/guard tests.
- **PR2 — endpoint** (~150 lines): `api_drawings` GET/POST/DELETE + routes + `parse_drawing`/`DRAWING_KINDS` + tests.
- **PR3 — primitive + UI** (~200 lines): `drawing-core.js`, v5 primitives, toolbar, boot/switch seams, E2E + `drawings` seam.

Each slice autonomous, own-tested, trivially revertible. Total ≈ 400–440 lines.

Decision needed before apply: Yes
Chained PRs recommended: Yes
400-line budget risk: Medium

## Boundary Note

`src/` unchanged/framework-free; `requirements.txt`, CSP, #68 single-write-path
unchanged; read-only — no order surface. No npm/build. `Drawing` is a new
additive table only.

## Open Questions

None blocking. Text input uses a native `<dialog>` (locked, proposal);
per-interval storage, delete-by-id, and delete-via-panel-list are locked in explore.
