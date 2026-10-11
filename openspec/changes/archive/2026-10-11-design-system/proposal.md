# Proposal: design-system

## Intent

Every dashboard page inherits `web/accounts/templates/registration/base.html`,
which is bare HTML — zero CSS, no viewport, no shared navigation. Pages render as
unstyled browser defaults, and the market chart already carries dead layout hooks
(`.market-layout`, `.panel`, `.pairs`). Fase 6c (positions/journal UI) needs a
shared visual system first; building the shell inside 6c would couple it to one
feature. This change delivers the dark terminal-style tokens + app shell all
pages inherit.

## Scope

### In Scope
- `registration/theme.css` token stylesheet: surfaces, text, single accent,
  semantic up/down, type scale, spacing, radius; `.num` tabular-nums.
- `base.html` → app shell: topbar (brand + nav Market/Positions/Journal +
  user email + POST logout), content region, `{% block head/scripts %}`.
- CSS served via a Django view (`accounts.views.theme_css`) mirroring
  `market.views.chart_js` (no staticfiles in prod; CSP-clean; zero build).
- Migrate the 5 extending pages with content-only tweaks; fix the logout link to
  POST (Django 5 `LogoutView` is POST-only — the current GET `<a>` 405s).
- A11y: AA contrast, `:focus-visible`, semantic landmarks, `aria-current`.
- `/impeccable` audit+polish; `tests/web/test_shell.py` (Strict TDD).

### Out of Scope
- Functional market redesign (shell/tokens applied only).
- Positions/journal UI (6c); their nav links are placeholders (`href`, not `{% url %}`).
- TradingView brand/assets; external branding.
- Any new runtime dependency; any CSP relaxation.

## Capabilities

### New Capabilities
- `design-system`: token stylesheet + app shell inherited by every page, served
  same-origin, CSP-clean, zero-build, a11y-compliant.

### Modified Capabilities
- None. (`security-invariants` R11/R12 and `market-chart` R6 CSP are constraints
  to satisfy, not alter — same-origin CSS under `style-src 'self'`.)

## Approach

Reuse the proven `chart_js` pattern: one small view renders the CSS template with
`content_type="text/css"` (public — a stylesheet has nothing to protect; gating it
would 302 the login page's CSS). Tokens live in `:root` custom properties;
element selectors style forms so the 3 form pages need no markup change; existing
chart class hooks get styled. `base.html` gains the topbar/landmarks and
`{% block scripts %}`; the 5 pages keep their content blocks verbatim.
`request.user` comes from the auth context processor (already configured) — no new
context processor. Active nav uses `request.resolver_match.url_name`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/accounts/templates/registration/base.html` | Modified | app shell |
| `web/accounts/templates/registration/theme.css` | New | tokens + base + components |
| `web/accounts/views.py` / `urls.py` | Modified | `theme_css` view + route |
| `accounts/{home,invite_create,signup}.html`, `registration/login.html` | Modified | minor content |
| `web/market/templates/market/chart.html` | Modified | inherit shell; scripts block |
| `tests/web/test_shell.py` | New | shell/token/CSS/a11y contract |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Nav to unbuilt `/positions/`,`/journal/` 404s | Med | plain `href` placeholders; 6c wires routes |
| `invite_create.html` inline `onclick` already CSP-blocked | Low | pre-existing; spec decides fix vs defer |
| `theme_css` route accidentally auth-gated | Low | explicit public-route test |
| Regressing chart/tests | Low | `test_shell.py` + existing suites green |

## Rollback Plan

Revert the branch: restore `base.html`, delete `theme.css` + the `theme_css`
view/route + `test_shell.py`, restore the 5 page templates. No DB, no migration,
no settings, no CSP change — nothing to roll back beyond files.

## Dependencies

None. No new package, no build step, no CDN for our own CSS.

## Success Criteria

- [ ] Tokens + shell implemented; all 5 existing pages inherit, no regression.
- [ ] `python -m pytest` green; `test_shell.py` per Strict TDD; patch gate 100%; ruff clean.
- [ ] `GET /accounts/theme.css` 200 `text/css`; CSP unchanged; no inline `<script>`.
- [ ] `/impeccable audit` no findings; AA contrast; visible focus; POST logout works.
- [ ] No new runtime dependency; `requirements.txt` unchanged.

## Review Workload Forecast

- Estimated diff: **~300–420 changed lines** (CSS ~150, base.html ~40, view/urls
  ~15, 5 templates ~30, tests ~120).
- Decision needed before apply: No
- Chained PRs recommended: No
- 400-line budget risk: Medium
