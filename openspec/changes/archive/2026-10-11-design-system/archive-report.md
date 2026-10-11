# Archive Report: design-system

**Archived**: 2026-10-11
**Verdict**: PASS (0 blockers, 0 criticals) — 8/8 requirements, R1–R8 delivered
**Delivery**: single PR — #66 (`feat/design-system`) merged to `develop`
**Merged commit range**: `fcbfe72`…`84feea5` on `develop` (merge `84feea5` PR #66; branch commits `3ec36fa` planning artifacts, `75b6a01` tokens + shell)

## What Shipped

Issue #65 (Fase 5.5) makes the shared visual system the first thing every
dashboard page inherits. `registration/base.html` becomes an app shell (topbar +
primary nav + user + POST logout) and a single same-origin token stylesheet
(`registration/theme.css`) is served by a Django view mirroring the proven
`market.views.chart_js` pattern — no staticfiles, no build step, no CSP
relaxation. The 5 extending pages adopt the shell with content-only tweaks. This
is the foundation Fase 6c (positions/journal UI, `feat/positions-journal`) will
consume.

| Area | Delivered |
|------|-----------|
| Tokens | `web/accounts/templates/registration/theme.css` (new, 57 lines) — `:root` palette (bg/bg-2/surface/border/text/muted/accent/up/dn), type scale `--fs-*`, spacing `--sp-*`, `--r`, `--mono`; `.num` tabular-nums; element selectors style the 3 form pages with zero markup change; dead chart hooks (`.market-layout`/`.panel`/`.pairs`) styled |
| CSS view | `web/accounts/views.py::theme_css` → `HttpResponse(render(...).content, content_type="text/css")`, **PUBLIC** (no `@login_required`); route `theme.css` name `theme_css` |
| App shell | `web/accounts/templates/registration/base.html` — viewport meta, `link` to `theme_css`, `<header class="topbar">` (brand + `<nav aria-label="Primary">` + user email + POST logout form + login link when anonymous), `<main>`, `{% block head %}`, `{% block scripts %}`; active nav via `request.resolver_match.url_name` |
| Invite JS | `web/accounts/templates/accounts/invite.js` + `views.invite_js` view + `invite.js` route — replaces the CSP-blocked inline `onclick="this.select()"` |
| Page migration | `chart.html` scripts moved into `{% block scripts %}`; `invite_create.html` drops the inline handler; `home.html` drops the stale GET logout `<li>`; `signup.html`/`login.html` inherit the shell |
| Tests | `tests/web/test_shell.py` (new, 10 tests, 122 lines) — anonymous CSS, shell on public/authed pages, `aria-current`, placeholder nav, POST logout, no inline handler/script |
| Untouched | `src/`, `requirements.txt` (diff empty), CSP header value, no migration/settings change |

## Requirement Outcomes

| Req | Domain | Outcome | Notes |
|-----|--------|---------|-------|
| R1 | design-system | ✅ Green | `theme_css` route → 200 `text/css` **anonymous**; `:root` tokens present; `.num` tabular-nums. Public route verified by a dedicated test |
| R2 | design-system | ✅ Green | Shell (topbar + nav) on all 5 pages; `aria-current="page"` on Market; Positions/Journal are static `href` placeholders → no `NoReverseMatch` |
| R3 | design-system | ✅ Green | Logout is `method="post"` + CSRF form; POST logs out; the prior GET `<a>` (405 on Django 5.2) removed |
| R4 | design-system | ✅ Green | `{% block scripts %}`; chart page keeps its two `<script>` tags with the shell intact |
| R5 | design-system | ✅ Green | Login/signup/invite forms submit unchanged; chart container present; test_shell (10) green |
| R6 | design-system | ✅ Green | AA contrast on the dark palette (~15:1 text, ~6:1 muted); `:focus-visible` outline on links/buttons/inputs; `<header>/<nav>/<main>` landmarks; up/down never colour-only |
| R7 | design-system | ✅ Green | CSP header value unchanged (no `unsafe-inline` in `script-src`); the pre-existing inline `onclick` in `invite_create.html` removed → same-origin `invite.js`; no inline `<script>`/handler remains (scan test) |
| R8 | design-system | ✅ Green | `src/` framework-free; `requirements.txt` byte-identical; no npm/build |

**Legend**: ✅ green · ⚠️ partial (invariant holds; coverage gap).

## Findings & Process Notes

| # | Kind | Finding | Status |
|---|------|---------|--------|
| N1 | Fix | Pre-existing CSP-blocked inline `onclick` in `invite_create.html` **fixed** (moved to same-origin `invite.js` served by `invite_js`) | ✅ Shipped in `75b6a01` |
| N2 | Fix | `theme_css` route is deliberately **PUBLIC** — a stylesheet must not 302 the login page's own CSS | ✅ Shipped + tested (`test_theme_css_is_served_anonymously_as_text_css`) |
| N3 | Fix | Logout is now **POST** — fixed a real HTTP 405 from the prior GET link (Django 5.2 `LogoutView` is POST-only) | ✅ Shipped + tested |
| N4 | Process | The `sdd-*` sub-agents (spec/tasks) failed with **"Bad request"**, so proposal/spec/design/tasks/apply/verify were produced **inline by the orchestrator**. Recorded honestly — the artifacts exist and are consistent; only the execution path differed | Noted |
| N5 | Process | **No `verify-report.md` artifact exists** — verification was performed inline (Playwright, real browser) | Noted — audit trail is this report + the archived artifacts |
| N6 | Note | `tasks.md` was `0/31` checked at review time; completion was not readable from the artifact (mirrors the W3 pattern from private-data-sync) | ✅ Closed at archive — archived copy is 31/31 `[x]` |

## Carry-Forward Items

1. **Positions/Journal nav are `href` placeholders** (`/positions/`, `/journal/`
   → 404 if clicked) until **Fase 6c** wires the routes. Not a defect: the design
   chose static hrefs over `{% url %}` specifically to avoid `NoReverseMatch`
   before 6c exists.
2. **The shell + tokens are the 6c consumption surface.** Fase 6c
   (`positions-journal-ui`, already spec'd and parked on branch
   `feat/positions-journal`) will replace the placeholder hrefs with real routes
   and style the positions/journal tables using `.num` + the token vars.
3. **`test_shell.py` inline-handler/script scans are template greps**, not a full
   CSP enforcement harness. Acceptable for the scope; a future change could pin
   the literal CSP header value in a test if drift becomes a concern.

## SDD Cycle Complete

Planned (`3ec36fa`) → implemented (`75b6a01` tokens + shell) → verified inline
(`PASS`, 0 blockers, 0 criticals, real-browser Playwright) → merged (PR #66 →
`develop`, `84feea5`) → archived.

Delta spec merged into the main spec store (source of truth):

- `openspec/specs/design-system/spec.md` — **created** (new capability, R1–R8,
  15 scenarios; delta copied verbatim as the canonical full spec).

No pre-existing requirement was touched; this capability is entirely new.

Archive audit trail: `openspec/changes/archive/2026-10-11-design-system/`
(explore, proposal, specs, design, tasks, archive-report). No `verify-report.md`
(see N5).

## Merge Inventory (main store after sync)

| Domain | Action | Requirements | Scenarios |
|--------|--------|--------------|-----------|
| design-system | Created | R1–R8 (8) | 15 |

No requirement was dropped; no other domain was modified.

## Traceability — Engram Observation IDs

| Artifact | Observation ID |
|----------|----------------|
| `sdd/design-system/explore` | (openspec file store; see archive folder) |
| `sdd/design-system/proposal` | (openspec file store) |
| `sdd/design-system/spec` | (openspec file store) |
| `sdd/design-system/design` | (openspec file store) |
| `sdd/design-system/tasks` | (openspec file store) |
| `sdd/design-system/verify-report` | **absent** — inline verify only (N5) |
| `sdd/design-system/archive-report` | Engram `sdd/design-system/archive-report` |

Merged specs have no standalone Engram observations — they live in the OpenSpec
file store (`openspec/specs/design-system/spec.md`).
