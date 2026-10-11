# Design: design-system (issue #65)

## Technical Approach

Deliver tokens + shell as one CSS template served same-origin, mirroring the
proven `market.views.chart_js` pattern. `base.html` becomes the app shell all
pages extend; existing content blocks are preserved verbatim. No staticfiles, no
build, no CSP relaxation.

## Tokens (`web/accounts/templates/registration/theme.css`)

`:root` custom properties (dark terminal palette):

```css
:root{
  --bg:#0e1117; --bg-2:#161b22; --surface:#1c2230; --border:#2a3240;
  --text:#e6edf3; --muted:#8b949e; --accent:#2962ff;
  --up:#26a69a; --dn:#ef5350;
  --fs-1:20px; --fs-2:15px; --fs-3:13px;
  --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px;
  --r:8px; --mono:ui-monospace,SFMono-Regular,Menlo,monospace;
}
```

Base: body bg/--text, `font-family` sans UI; `.num{font-variant-numeric:tabular-nums}`
for all numeric cells. Element selectors (`a`, `input`, `button`, `form p`, `code`)
style the 3 form pages with ZERO markup change. `.market-layout`/`.panel`/`.pairs`
(dead hooks already in chart.html) get styled.

## App shell (`registration/base.html`)

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}bitunix-trader{% endblock %}</title>
  <link rel="stylesheet" href="{% url 'theme_css' %}">
  {% block head %}{% endblock %}
</head>
<body>
  <header class="topbar">
    <span class="brand">bitunix-trader</span>
    <nav aria-label="Primary">
      <a href="{% url 'market_page' %}" {% if request.resolver_match.url_name == 'market_page' %}aria-current="page"{% endif %}>Market</a>
      <a href="/positions/">Positions</a>
      <a href="/journal/">Journal</a>
    </nav>
    {% if user.is_authenticated %}
      <span class="whoami">{{ user.email }}</span>
      <form method="post" action="{% url 'logout' %}">{% csrf_token %}<button type="submit">Log out</button></form>
    {% else %}
      <a href="{% url 'login' %}">Log in</a>
    {% endif %}
  </header>
  <main>{% block content %}{% endblock %}</main>
  {% block scripts %}{% endblock %}
</body>
</html>
```

- Nav active via `request.resolver_match.url_name` (no new context processor; `request` is already in context).
- **Positions/Journal are static `href` placeholders** (routes land in 6c) → no `NoReverseMatch` on any page.
- **Logout is a POST form** (Django 5.2 `LogoutView` is POST-only); fixes the current GET `<a>` 405.
- `{% block scripts %}` so `chart.html` keeps `<script src=...>` tags under the shell.

## CSS view (`web/accounts/views.py`)

```python
def theme_css(request):
    return HttpResponse(render(request, "registration/theme.css").content,
                        content_type="text/css")
```

Route in `accounts/urls.py`: `path("theme.css", views.theme_css, name="theme_css")`
— **NO `@login_required`** (a stylesheet protects nothing; gating it would 302 the
login page's own CSS). Mirrors `chart_js`.

## Interface migrations (5 pages)

- `home.html`, `signup.html`, `login.html`: content unchanged (they already use content blocks); login gets the shell too.
- `invite_create.html`: **remove the inline `onclick="this.select()"`** (CSP-blocked today) → move to a same-origin JS served by a `invite_js` view (mirror `chart_js`), wired via `{% block scripts %}`. Markup gains an `id` on the input + the script binds `select()` on focus.
- `market/chart.html`: move its `<script>` tags into `{% block scripts %}`; shell + chart coexist.

## CSP

Unchanged. `style-src 'self'` covers the same-origin stylesheet; `script-src` stays
strict (no inline script/handler introduced). `invite_js` is same-origin under `'self'`.

## Accessibility

AA contrast on the dark palette (text `#e6edf3` on `#0e1117` ≈ 15:1; muted
`#8b949e` on `#0e1117` ≈ 6:1). `:focus-visible` outline on links/inputs/buttons.
Semantic `<header>/<nav>/<main>` landmarks; `aria-label="Primary"`; active item
`aria-current`. Up/down never the sole signal (sign/quantity also shown).

## Testing Strategy (Strict TDD, `python -m pytest`)

New `tests/web/test_shell.py`:
- `GET /accounts/theme.css` → 200, `Content-Type: text/css`, works ANONYMOUS.
- Shell present on home/login/signup/invite/market (topbar + nav).
- `aria-current="page"` on Market when on market.
- Logout is a `method="post"` form; POST logs out.
- No `NoReverseMatch` on any page (placeholders).
- CSP header unchanged; no inline handler remains (AST/grep on templates).
- Chart page still loads its script (scripts block) + shell present.

Only the new `theme_css`/`invite_js` views are Python → patch gate 100%.
Existing `test_ux.py`/`test_market_ux.py`/E2E stay green.

## ADRs

- **(a) CSS via view vs staticfiles vs inline**: view — staticfiles is prod-broken (no STATIC_ROOT/whitenoise, gunicorn-only); inline `<style>` contradicts a proper stylesheet; the view mirrors `chart_js`.
- **(b) Public theme route**: yes — gating a stylesheet 302s the login page's CSS.
- **(c) POST logout**: Django 5.2 requires it; the GET link 405s today.
- **(d) Placeholder nav**: static hrefs until 6c wires the routes.
- **(e) Fix inline onclick in-change**: it is already CSP-blocked; leaving it ships a broken "select" UX.

## Boundary Note

`src/` untouched/framework-free; `requirements.txt` unchanged; no npm/build; CSP unchanged; read-only (R11).

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `web/accounts/templates/registration/theme.css` | New | tokens + base + components |
| `web/accounts/templates/registration/base.html` | Modify | app shell |
| `web/accounts/views.py` | Modify | `theme_css`, `invite_js` views |
| `web/accounts/urls.py` | Modify | `theme.css`, `invite.js` routes |
| `web/accounts/templates/accounts/invite_create.html` | Modify | drop inline onclick; scripts block |
| `web/accounts/templates/accounts/{home,signup}.html`, `registration/login.html` | Modify | minor (shell/content) |
| `web/market/templates/market/chart.html` | Modify | scripts block |
| `tests/web/test_shell.py` | New | shell/token/CSS/a11y contract |

## Task Breakdown Hint

~300–420 lines, single PR, budget risk Medium (no chaining — one cohesive
visual-system change; the CSS is one file).

## Open Questions

None blocking. Resolved: CSS via view; public route; POST logout; placeholders; inline onclick fixed now.
