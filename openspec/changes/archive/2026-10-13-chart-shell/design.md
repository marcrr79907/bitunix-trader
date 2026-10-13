# Design: chart-shell (issue #116, Fase F3)

## Technical Approach

Shell pass on the MERGED F0/F1 layered ESM: full-height chart, `aria-pressed`
interval chips over a retained hidden `<select>`, collapsible sidebar, and a
user-global last-interval preference. No new module, no new runtime dep, CSP
unchanged, `src/` untouched, `window.marketChart` stays 8 keys. The chips are
**derived from the existing `<select>.options` at runtime**, so the 14 intervals
stay single-source in the template (no 4th copy) and the 15 E2E
`select_option("#interval", …)` calls keep working (R18, zero assertion edits).

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|---|---|---|---|
| **Q3 persistence** | **`ChartPreference(UserOwnedModel)`, `OneToOneField(user)`, `last_interval CharField(8, default="1m")`, `updated_at`; additive migration `0009`; `GET/PUT /market/api/preference`** | sentinel-symbol row in `ChartLayout` (no migration) | Honest model for a *user-global* pref; reuses the `ChartLayout` `for_user`+GET/PUT idiom exactly. Option B overloads a per-`(user,symbol,interval)` table (`symbol=""` currently 400s) — documented design smell, rejected. One additive `CreateModel` migration is the only schema change. |
| **Q2 frozen select** | Keep `<select id="interval">`; JS adds `.visually-hidden` (clip, never `display:none`) once chips exist | remove select; `hidden` attr | The select is a hard E2E dependency. Clip keeps it in the a11y/action tree; no-JS fallback also survives (select visible until JS hides it). |
| **Q1 chip source** | `toolbar.js` builds `.interval-chips` from `select.options` | hardcode a 2nd template list; `CONFIG.intervals` | Reuses the existing template list — no 4th interval copy. Server still validates via `quotes.INTERVALS`. |
| **Q5 height** | `autoSize:true`, **remove `height:480`**; `#chart` sized by flex/grid chain | keep `height:480` + resize JS | v5 `autoSize` installs a `ResizeObserver`; a fixed option would be ignored + warn. Container must have a resolved height (below). |
| **Q4 collapse** | `<button aria-expanded aria-controls="panel">` + `.panel-collapsed` class; hidden ≥821px | checkbox-hack | Native focusable/activatable; no new lib. |
| Boot preference owner | `main.js` (orchestration) does GET before `start()`, debounced PUT on interval change | toolbar-owned fetch | main already owns async boot sequencing + the `config:changed` handler; mirrors `indicators.loadLayout`/`saveLayout` debounce. |

## Height / responsive (exact CSS)

```css
body{display:flex; flex-direction:column; min-height:100dvh}
main{flex:1 1 auto; width:100%; max-width:1200px; margin:0 auto;
     padding:var(--sp-4); min-height:0}
.market-layout{height:100%}            /* grid row stretches -> #chart fills */
#chart{min-height:460px; position:relative}
.visually-hidden{position:absolute; width:1px; height:1px; margin:-1px;
  padding:0; border:0; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap}
.interval-chips{display:flex; flex-wrap:wrap; gap:var(--sp-1)}
.interval-chip{background:var(--surface); border:1px solid var(--border);
  color:var(--text); padding:var(--sp-1) var(--sp-2)}
.interval-chip[aria-pressed="true"]{border-color:var(--accent); color:var(--accent)}
.panel-toggle{display:none}
@media (max-width:820px){
  .market-layout{grid-template-columns:1fr; height:auto}
  #chart{height:70dvh; min-height:320px}          /* ponytail: tunable, panel stacks below */
  .panel-toggle{display:inline-block; grid-column:1/-1; justify-self:start}
  .market-layout.panel-collapsed .panel{display:none}
}
```

`flex:1 1 auto` + `min-height:0` gives `main` a definite height (viewport −
topbar) so `height:100%` resolves — no `--topbar-h` magic number. Resize and
pane layout stay correct: v5's `ResizeObserver` recomputes every pane on
container resize, so `addSeries(..., paneIndex)` needs no change.

## Frozen DOM

```html
<div class="market-layout">
  <button type="button" class="panel-toggle" aria-expanded="true" aria-controls="panel">Panel</button>
  <section id="chart" aria-label="Candlestick chart"></section>
  <aside class="panel" id="panel"> … <select id="interval" aria-label="Interval">…14 options…</select> … </aside>
</div>
```
`toolbar.js` inserts `<div class="interval-chips" role="group" aria-label="Interval">`
+ `<button type="button" class="interval-chip" data-interval="5m" aria-pressed="false">5m</button>`
per option, immediately after the `<select>`, then adds `.visually-hidden` to it.

## Data Flow

    boot ──GET /market/api/preference──▶ main (interval, else "1m")
    main ──set select.value + state.interval + toolbar.setInterval──▶ start()
    chip click ──▶ select.value=sync + aria-pressed + emit config:changed ──▶ main.switchTo
    select change ──▶ emit config:changed + sync chips ──▶ main.switchTo
    interval change ──▶ main debounced PUT preference (captured value, like saveLayout)
    panel-toggle click ──▶ classList.toggle("panel-collapsed") + aria-expanded

## Interfaces / Contracts

```python
class ChartPreference(UserOwnedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name="chart_preference")
    last_interval = models.CharField(max_length=8, default="1m")
    updated_at = models.DateTimeField(auto_now=True)
```
`GET /market/api/preference` → `{"interval": str, "exists": bool}` (miss → `"1m"`,
`exists:false`, never 404). `PUT {"interval": str}` → validates `interval in
INTERVALS` (else 400) → `for_user(user).update_or_create(user=user,
defaults={"last_interval": interval})`. All access via `for_user` (R14.3). Both
`@login_required`; GET+PUT via `require_http_methods`. URL name
`market_api_preference`; `CONFIG.urls.preference = "/market/api/preference"`.

## File Changes

| File | Action | Description |
|---|---|---|
| `web/market/templates/market/chart.html` | Modify | `.panel-toggle` button, `id="panel"` (Slice 1) |
| `web/accounts/templates/registration/theme.css` | Modify | flex/dvh height, `.interval-chips`/`.interval-chip`, `.visually-hidden`, `.panel-collapsed`, 820px + 375px (Slices 1) |
| `web/market/templates/market/chart-host.js` | Modify | `autoSize:true`, drop `height:480` (S1) |
| `web/market/templates/market/controllers/toolbar.js` | Modify | chips from options + chip↔select sync + collapse toggle + `setInterval` (S1) |
| `web/trading/models.py` | Modify | `ChartPreference` (S2) |
| `web/trading/migrations/0009_chartpreference.py` | Create | Additive `CreateModel` (S2) |
| `web/market/views.py` | Modify | `api_preference` GET/PUT (S2) |
| `web/market/urls.py` | Modify | `/market/api/preference` route (S2) |
| `web/market/templates/market/chart.js` | Modify | `CONFIG.urls.preference` (S2) |
| `web/market/templates/market/main.js` | Modify | pref GET before `start()`, debounced PUT on interval change, `toolbar.setInterval` (S2) |
| `tests/web/test_market_api.py` | Modify | preference contract: round-trip, invalid interval 400, A≠B isolation (S2) |
| `tests/web/test_market_e2e.py` | Modify | ADD-ONLY: chips aria-pressed + switch, hidden select still selectable, toggle, 375px no overflow, chart fills height, 8 keys (S1 chips/toggle; S2 pref restore) |
| `tests/web/test_owned_model_guard.py` | Modify | `OWNED_MODELS += "ChartPreference"` + one offender param (S2) |

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit (py) | preference GET/PUT, validation, isolation | `@pytest.mark.django_db` in `test_market_api.py` |
| Guard (py) | `ChartPreference.objects.*` flagged; `for_user` allowed | `test_owned_model_guard.py` add-only |
| E2E | chips, hidden select, collapse, height bbox, 375px, 8 keys | new `@p` tests in `test_market_e2e.py`, DOM-only; **no edits to existing assertions** |
| Build | `makemigrations --check`, `ruff`, `pytest` | CI |

## Migration / Rollout

No migration in Slice 1. Slice 2 ships additive `0009`; rollback = reverse
migration (`DROP TABLE`) + revert commit; boot falls back to `"1m"` so no user
is left chartless. `processExit`-free; no feature flag.

## Delivery (Feature Branch Chain — 2 slices; all PRs base on tracker `feat/chart-shell`)

| Slice | Scope | ~Lines | Rollback boundary |
|---|---|---|---|
| 1 | shell: CSS + template + chips + collapse + `autoSize`; no migration | ~150 | revert → `height:480`, no chips/toggle |
| 2 | persistence: model + `0009` + endpoint + boot read/save + API/guard tests | ~160 | revert → reverse migration; boot `"1m"` |

### Guard / Edge Matrix

| Edge | Handling |
|---|---|
| E2E `select_option` preserved | select retained, `.visually-hidden` clip (never `display:none`); chips only add listeners |
| `autoSize` resize | `height:480` removed; `#chart` resolves via flex/grid; assert canvas bbox in E2E |
| 8-key seam | chips/toggle write no global; E2E asserts `Object.keys(...).length === 8` |
| migration additive | `CreateModel` only; `makemigrations --check` green; `OWNED_MODELS += ChartPreference` |
| R14 ownership | endpoint + boot use `for_user`; A≠B isolation tested |
| no new dep / CSP | template buttons + theme.css + existing ESM; no inline handler; `script-src 'self' https://unpkg.com` unchanged |
| 375px | `.interval-chips{flex-wrap:wrap}`; assumed `max-width:1200px` kept; no `overflow-x` |
| boot ordering | pref GET precedes `start()`; failure → `"1m"`; `gen` guard intact |
| no-JS fallback | select visible until JS clips it; chips additive |

## Open Questions

None blocking. Q3 locked: `ChartPreference` + `0009` + `/market/api/preference`.
