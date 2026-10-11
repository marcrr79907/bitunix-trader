# Tasks: design-system (issue #65, Fase 5.5)

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a (single PR)
400-line budget risk: Medium

## Guard/Edge Matrix

- [x] `GET /accounts/theme.css` → 200 `text/css`, **anonymous** (no redirect)
- [x] `:root` tokens present (surfaces, text, accent, up/down, scale, spacing, radius)
- [x] Shell (topbar + nav) on home, login, signup, invite, market
- [x] Market nav carries `aria-current="page"` on the market page
- [x] Logout is a `method="post"` form (CSRF); POST logs out
- [x] Positions/Journal placeholders do not raise `NoReverseMatch`
- [x] Chart page keeps its script (via `{% block scripts %}`) + shell intact
- [x] No inline `<script>` / inline event handler remains in templates
- [x] CSP header unchanged (no `unsafe-inline` in `script-src`)
- [x] `src/` framework-free (boundary green)
- [x] `requirements.txt` unchanged
- [x] Patch coverage 100% (new views)

## WU1 — CSS view + tokens

Branch `feat/design-system` (base `develop`). Depends: none.

- [x] 1.1 **RED** `tests/web/test_shell.py`: `GET /accounts/theme.css` anonymous → 200 `text/css`; body contains `:root` + key custom properties.
- [x] 1.2 **GREEN** `web/accounts/templates/registration/theme.css`: `:root` tokens (bg/bg-2/surface/border/text/muted/accent/up/dn/fs/sp/r); base styles; `.num` tabular-nums; element selectors for forms; style `.market-layout/.panel/.pairs`.
- [x] 1.3 **GREEN** `web/accounts/views.py::theme_css` (`HttpResponse(render(...).content, content_type="text/css")`, PUBLIC) + `accounts/urls.py` route `theme.css` name `theme_css`.
- [x] 1.4 Rollback: delete `theme.css`, the view + route.

## WU2 — App shell + logout

Depends: WU1.

- [x] 2.1 **RED** test: shell topbar+nav on each of the 5 pages; `aria-current="page"` on Market; logout is POST form; no page raises `NoReverseMatch`.
- [x] 2.2 **GREEN** `web/accounts/templates/registration/base.html`: shell (viewport meta, `link` to `theme_css`, topbar brand + nav [Market `{% url %}`, Positions/Journal static href] + user + POST logout form + login link when anonymous), `<main>`, `{% block head %}`, `{% block scripts %}`.
- [x] 2.3 Rollback: restore prior `base.html`.

## WU3 — Page migration + inline-onclick fix

Depends: WU2.

- [x] 3.1 **RED** test: market page keeps its chart script (scripts block) + shell; invite page has NO inline handler.
- [x] 3.2 **GREEN** `web/market/templates/market/chart.html`: move `<script>` tags into `{% block scripts %}`.
- [x] 3.3 **GREEN** `web/accounts/templates/accounts/invite_create.html`: remove `onclick="this.select()"`; add `id` to the input; `+ "invite_js"` view (mirror chart_js) served same-origin + scripts block binding select-on-focus.
- [x] 3.4 **GREEN** minor content tweaks on `home.html`, `signup.html`, `registration/login.html` (shell inheritance; no functional change).
- [x] 3.5 Rollback: restore the 4 page templates; delete `invite.js` view/route.

## WU4 — Tests + a11y + CSP

Depends: WU1–WU3.

- [x] 4.1 Full `tests/web/test_shell.py`: all Guard rows.
- [x] 4.2 `/impeccable audit` on the templates → no findings; note AA contrast + `:focus-visible`.
- [x] 4.3 Confirm CSP header value unchanged; no inline handler in templates (scan).
- [x] 4.4 `pytest` green; `ruff check . && ruff format --check .`; `makemigrations --check`.

## Phase 5 — Verification

- [x] 5.1 `python -m pytest` green (Strict TDD); patch coverage 100%.
- [x] 5.2 Existing suites (`test_ux.py`, `test_market_ux.py`, E2E) green.
- [x] 5.3 `src/` boundary green; `requirements.txt` unchanged.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | WU1 ~160, WU2 ~50, WU3 ~40, WU4 ~120 → ~300–420 total |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | single PR (one cohesive visual-system change; CSS is one file) |
| Delivery strategy | ask-on-risk |
| Chain strategy | n/a |
| Tracker branch | `feat/design-system` → `develop` |

```text
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
400-line budget risk: Medium
```
