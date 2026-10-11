# Exploration: design-system (Fase 5.5, issue #65)

## Current State

- `web/accounts/templates/registration/base.html` (9 lines) is the shared shell —
  bare HTML: `<!DOCTYPE html>`, `<head>` with only charset + title, `<body><main>{% block content %}</main></body>`.
  **No CSS, no viewport meta, no head extras.** Every page extends it.
- Extending pages (5): `accounts/home.html`, `accounts/invite_create.html`,
  `accounts/signup.html`, `registration/login.html`, `market/chart.html`. Each
  only overrides `{% block title %}` / `{% block content %}`; none add head
  assets.
- `market/chart.html` already assumes a dark trading layout (chart + `<aside class="panel">`,
  `.pair` buttons, interval `<select>`, `#rsi`) but **renders unstyled** — its
  class names (`.market-layout`, `.panel`, `.pairs`, `.pair`) are dead hooks
  waiting for CSS.
- **CSS delivery infra**: NO staticfiles in prod. `STATIC_URL = "static/"` but
  no `STATIC_ROOT`, no whitenoise, Dockerfile runs gunicorn only
  (`web/config/settings/base.py:132`; `Dockerfile`). Precedent for serving
  browser assets without static: `market.views.chart_js`
  (`web/market/views.py:71-77`) renders `market/chart.js` and returns
  `content_type="text/javascript"`; routed `market/chart.js`
  (`web/market/urls.py:12`).
- **CSP** (`web/config/middleware.py:27-32`), path-conditional, `/admin/` exempt:
  `script-src 'self' https://unpkg.com` (NO `unsafe-inline`),
  `style-src 'self' 'unsafe-inline' https://unpkg.com`. So: same-origin CSS file
  under `'self'` is allowed; inline `<style>` is also allowed; inline `<script>`
  is NOT.
- **Django 5.2.18** (`LogoutView.http_method_names = ["post", "options"]`).
  `home.html:13` uses `<a href="{% url 'logout' %}">` → a GET → **405 today**
  (broken logout link in the UI, untested; `test_auth.py:51` POSTs so it stays
  green).
- No `positions/` or `journal/` routes exist yet (`web/**/urls.py`). The shell
  nav must not use `{% url %}` for them or every page raises `NoReverseMatch`.
- Tests: `tests/web/test_ux.py` (home/invite), `tests/web/test_market_ux.py`
  (chart container, `href="/market/"`, CSP matrix), `test_market_e2e.py`
  (Playwright, deselected by `addopts = "-q -m 'not e2e'"`, `pyproject.toml:18`).
- Memory reference palette: green `#26a69a` / red `#ef5350`.

## Affected Areas

- `web/accounts/templates/registration/base.html` — rewrite into the app shell.
- `web/accounts/templates/registration/theme.css` — NEW token stylesheet (template).
- `web/accounts/views.py` + `web/accounts/urls.py` — `theme_css` view + route.
- `web/accounts/templates/accounts/{home,invite_create,signup}.html`,
  `web/accounts/templates/registration/login.html` — minor content tweaks only.
- `web/market/templates/market/chart.html` — inherit shell; scripts placement.
- `tests/web/test_shell.py` — NEW shell/token/CSS contract suite.
- `tests/web/test_ux.py` — existing home-email assertion stays valid via topbar.

## Key Findings

### 1. How to serve CSS (the infra decision)

Staticfiles is **out**: no `STATIC_ROOT`, no whitenoise, and adding whitenoise
violates "no new runtime dependency" (issue invariant; enforced by the AST
dependency guard in `market-chart` R7). Three viable options:

| Option | Pros | Cons | Effort |
|---|---|---|---|
| **(a) Django view + `theme.css` template (mirror `chart_js`)** | Established house pattern; base.html stays declarative; cacheable; sets pattern for 6c | +1 view, +1 route, +1 test; CSS is not auth-bound so a `login_required` view is debatable | Low |
| (b) Inline `<style>` in base.html | Smallest diff (1 file); allowed by `style-src 'unsafe-inline'` today | Bloats shell; no separation; every page redownloads; not the "proper stylesheet" the issue asks for | Lowest |
| (c) staticfiles | Standard Django | Broken in prod (no collectstatic/whitenoise); new dep or deploy work; violates zero-build | High |

**RECOMMEND (a)** — mirrors `chart_js` exactly, keeps base.html clean, and is the
issue's stated preference ("a proper stylesheet is cleaner"). Rejected staticfiles
(prod-broken + dep) and inline (works, but the issue explicitly wants a stylesheet;
retain as fallback if the review budget is tight).

**Placement**: put the view + template in `accounts` (co-located with the
base shell it serves): `accounts.views.theme_css` renders
`registration/theme.css` → `HttpResponse(..., content_type="text/css")`, route
`path("theme.css", views.theme_css, name="theme_css")` in `accounts/urls.py`.
Route is public (no `login_required`) — a stylesheet has nothing to protect and
gating it would 302 the browser's CSS fetch on the login page. Alternative if
design prefers clean domain separation: a tiny `web/ui` app (new scaffolding for
2 files — deferred unless asked). NOTE: `web/config/health.py` is precedent for a
`config`-level view, but `config` has no template dir, so `accounts` wins.

### 2. Token set (`:root` custom properties, dark theme)

```css
:root{
  /* surfaces (dark, layered) */
  --bg-0:#0e1116; --bg-1:#161b22; --bg-2:#1f2630; --border:#2a323d;
  /* text */
  --text:#e6edf3; --muted:#8b98a5;
  /* accent (single) + semantic */
  --accent:#4c8dff; --up:#26a69a; --down:#ef5350;
  /* type */
  --font-ui:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --font-mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --fs-xs:.75rem; --fs-sm:.875rem; --fs-md:1rem; --fs-lg:1.25rem;
  /* spacing (4px base) */
  --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-5:24px;
  --radius:6px;
}
```
Utility: `.num{font-variant-numeric:tabular-nums}` for prices/RSI. Base reset
(`box-sizing:border-box`, `body{background:var(--bg-0);color:var(--text);font:var(--fs-md)/1.5 var(--font-ui)}`).
Forms: element selectors (`input,select,button`) styled to the tokens so the 3
form pages need no markup change. Chart page: `.market-layout`, `.panel`,
`.pairs`, `.pair` styled to match the existing class hooks. Keep it minimal but
complete for market/positions/journal/forms.

### 3. App shell structure (base.html)

```
<head> charset · viewport · <title>{% block title %}</title>
        <link rel="stylesheet" href="{% url 'theme_css' %}">
        {% block head %}{% endblock %}
<body class="app">
  <header class="topbar">
    <a class="brand" href="{% url 'home' %}">bitunix-trader</a>
    <nav class="nav" aria-label="Primary">
      Market | Positions | Journal   (aria-current="page" on active)
    </nav>
    <div class="user">{{ user.email }}</div>
    <form method="post" action="{% url 'logout' %}">{% csrf_token %}
      <button type="submit">Log out</button></form>
  </header>
  <main id="content" class="content">{% block content %}{% endblock %}</main>
  {% block scripts %}{% endblock %}
</body>
```
- **Authenticated user**: `request.user` is already available (auth context
  processor, `base.py:108`) — **no context processor needed**. Show
  `{{ user.email }}` in the topbar (keeps `test_ux.py:29` green).
- **Active nav**: use `request.resolver_match.url_name` in the template
  (`{% if request.resolver_match.url_name == 'market_page' %}aria-current="page"{% endif %}`)
  — no context processor, no per-page block.
- **Logout MUST be a POST form** (`LogoutView` is POST-only, Django 5) — this
  fixes the currently-broken GET link (`home.html:13`) and is the correct
  behavior, not a regression.
- **Nav hrefs for Positions/Journal**: no routes exist yet (6c). Use plain
  `href="/positions/"` / `href="/journal/"` (NOT `{% url %}`) so no page raises
  `NoReverseMatch`; 6c points them at real routes. Market uses `{% url 'market_page' %}`.
- Footer: skip (YAGNI). `{% block scripts %}` added so `chart.html` can move its
  two `<script>` tags out of `content` and keep them after the shell markup.

### 4. Migration of existing pages (no regressions)

- `base.html`: full rewrite (shell + head link + blocks). The 5 pages keep their
  `{% block content %}` verbatim; only `chart.html` moves its scripts to
  `{% block scripts %}` (optional — leaving them in content works too, but the
  block is cleaner).
- `home.html`: the email/role line and links stay in content; email also appears
  in the topbar. `test_ux.py` stays green.
- `login.html` / `signup.html` / `invite_create.html`: **forms unchanged** —
  element-selector styling covers them. `invite_create.html:16` has an inline
  `onclick="this.select()"` which is **already CSP-blocked today** (strict
  `script-src`, non-admin path) — pre-existing, flag (see Risks); do not silently
  "fix" behavior without a spec decision.
- `chart.html`: `id="chart"`, `#interval`, `.pair`, `#rsi` and the two script
  tags all stay → `test_market_ux.py:30-50` and the E2E suite stay green.
- CSP untouched: same-origin stylesheet under `style-src 'self'`; `test_market_ux.py:59-75`
  unaffected.

### 5. A11y

- Contrast: text `#e6edf3` on `#0e1116` ≈ 15:1; muted `#8b98a5` ≈ 6:1 (both AA).
  Semantic up/down paired with numerals, never color alone.
- `:focus-visible{outline:2px solid var(--accent);outline-offset:2px}` on all
  interactive elements; do not remove outlines.
- Semantic landmarks: `<header>` + `<nav aria-label="Primary">` + `<main id="content">`;
  active link `aria-current="page"`; logout is a real `<button>`. Native elements
  = keyboard nav for free. Optional skip link to `#content`.

### 6. Tests (Strict TDD, `python -m pytest`)

New `tests/web/test_shell.py` (uses existing `client` + `force_login` pattern):
- shell renders on all 5 protected pages: brand + `topbar` + `theme_css` link present.
- nav links Market/Positions/Journal present; `aria-current="page"` on Market at `/market/`.
- topbar shows `{{ user.email }}`.
- logout is a POST form with `action="/logout/"` and a csrf token (guard the 405 fix).
- `GET /accounts/theme.css` → 200, `Content-Type: text/css`, contains `--accent` and `--up`.
- login page still 200 with a form; `test_ux.py`/`test_market_ux.py` stay green (regression).
- no inline `<script>` in the shell (CSP: assert base-rendered pages contain no
  `onclick=` in shell markup).
- E2E smoke (optional, `@pytest.mark.e2e`): shell topbar renders on `/market/`
  alongside the chart (extend `test_market_e2e.py`).

Coverage: only `accounts.views.theme_css` is Python → one test covers it 100%
(CSS/HTML are not measured).

## Approaches

1. **View-served stylesheet + shell in base.html** (RECOMMENDED) — mirrors
   `chart_js`; clean separation; sets the 6c pattern. Effort: Low.
2. **Inline `<style>` in base.html** — smallest diff, allowed by current CSP;
   retains no separation and contradicts the issue's stylesheet preference.
   Effort: Lowest.
3. **staticfiles/whitenoise** — rejected: prod-broken or new runtime dep,
   violates zero-build.

## Recommendation

Option 1: `theme_css` view in `accounts` (template `registration/theme.css`,
route `theme.css`), token stylesheet + shell (topbar/nav/user/POST-logout) in
`base.html`, minimal content tweaks to the 5 pages, `tests/web/test_shell.py`.

## Risks

- **Inline `onclick` in `invite_create.html:16` is already CSP-blocked** (strict
  `script-src`). Pre-existing; flag for a spec decision (fix in this change vs defer).
- **Nav links to unbuilt `/positions/`, `/journal/`** 404 until 6c — acceptable
  placeholder; must NOT use `{% url %}` (would break every page).
- **Logout GET → 405 today**; the shell's POST form fixes it. Verify no test
  relied on the GET link.
- **`style_css` route must stay public** — `login_required` would 302 the CSS on
  the login page (unstyled login).
- **`chart.html` scripts** must stay same-origin/after markup; moving to
  `{% block scripts %}` is safe but touches a tested page.
- Patch gate counts Python only — the one new view needs its test; CSS/HTML
  verified by the shell suite + `/impeccable`.

## Ready for Proposal

YES — the CSS-delivery decision, token set, shell structure, page migration, a11y
and test plan are all answered with file references. Open items for spec/design:
(a) inline-`onclick` fix in or out, (b) `accounts` vs a `web/ui` app for the CSS
view, (c) whether Positions/Journal nav shows before their routes exist.
