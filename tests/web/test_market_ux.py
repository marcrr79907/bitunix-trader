"""R2/R6 contract: chart page UX + CSP header matrix.

- R2: `/market/` is auth-gated — anonymous 302, authenticated 200 with the
  chart container; home links to it.
- R6: CSP present on market pages (wss + CDN + self allowlist), absent on
  `/admin/`, `/healthz` still 200.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def logged_in_client(client, db):
    user = User.objects.create_user(email="ux@example.com", password="pw-123456")
    client.force_login(user)
    return client


def test_market_page_redirects_anonymous_to_login(client):
    response = client.get("/market/")
    assert response.status_code == 302
    assert response.url.startswith("/login/")


def test_market_page_renders_chart_container(logged_in_client):
    response = logged_in_client.get("/market/")
    assert response.status_code == 200
    assert b'id="chart"' in response.content
    assert b"market_chart_js" in response.content or b"chart.js" in response.content


def test_market_page_lists_pairs_and_intervals(logged_in_client):
    response = logged_in_client.get("/market/")
    assert response.status_code == 200
    # First configured symbol button + the interval select exist.
    assert b"BTCUSDT" in response.content
    assert b"1m" in response.content


def test_chart_js_served_as_javascript(logged_in_client):
    response = logged_in_client.get("/market/chart.js")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/javascript"
    assert b"BTCUSDT" in response.content  # symbols JSON injected
    assert b"market_kline" in response.content  # WS channel prefix


def test_chart_core_served_as_javascript(client):
    # Pure core is same-origin and NOT auth-gated (it holds no state/secrets).
    response = client.get("/market/chart-core.js")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/javascript"
    assert b"bucketTime" in response.content
    assert b"upsertCandle" in response.content


def test_drawing_core_served_as_javascript(client):
    # Pure drawing geometry is same-origin and NOT auth-gated (no state).
    response = client.get("/market/drawing-core.js")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/javascript"
    assert b"hlinePath" in response.content
    assert b"fibLevels" in response.content


def test_tool_icons_core_served_as_javascript(client):
    # F5 S2 (R14): the pure icon core is same-origin and NOT auth-gated (no state).
    response = client.get("/market/tool-icons-core.js")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/javascript"
    assert b"iconFor" in response.content
    assert b"TOOL_GROUPS" in response.content


def test_draw_toolbar_controller_served_as_javascript(logged_in_client):
    # F5 S2 (R5): the toolbar controller is served same-origin as JS from
    # ``market/controllers/`` (a missing route = import 404 = blank chart).
    response = logged_in_client.get("/market/controllers/draw-toolbar.js")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/javascript"
    assert b"createDrawToolbar" in response.content


def test_smc_overlay_core_served_as_javascript(client):
    # Pure SMC overlay mapping is same-origin and NOT auth-gated (no state).
    response = client.get("/market/smc-overlay-core.js")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/javascript"
    assert b"visibleFamilies" in response.content
    assert b"setupMarkers" in response.content


def test_theme_core_served_as_javascript(client):
    # CT1/R14: the pure theme core is same-origin and NOT auth-gated (no state).
    response = client.get("/market/theme-core.js")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/javascript"
    assert b"optionsFor" in response.content
    assert b"resolve" in response.content


def test_market_page_includes_smc_core_and_toggles(logged_in_client):
    # R7/R11: the page loads the core same-origin and exposes one toggle per
    # family via data-family (no inline handler).
    response = logged_in_client.get("/market/")
    assert response.status_code == 200
    assert b"market_smc_overlay_core_js" in response.content or (
        b"smc-overlay-core.js" in response.content
    )
    families = (b"swings", b"structure", b"order_blocks", b"fvg", b"range", b"setups")
    for family in families:
        assert b'data-family="' + family + b'"' in response.content


def test_module_allowlist_routes_serve_javascript(logged_in_client):
    # R15/R16: every allowlisted ESM module is served same-origin as JS (a
    # missing route = import 404 = blank chart), a non-allowlisted name is
    # rejected (traversal guard), and the entry keeps its Django-injected
    # config literals. The allowlist constant is the route-coverage source.
    from market import views

    for name in views.MODULE_ALLOWLIST:
        response = logged_in_client.get(f"/market/{name}.js")
        assert response.status_code == 200, name
        assert response["Content-Type"] == "text/javascript", name

    assert logged_in_client.get("/market/not-allowed.js").status_code == 404
    assert logged_in_client.get("/market/controllers/nope.js").status_code == 404

    entry = logged_in_client.get("/market/chart.js")
    assert entry.status_code == 200
    assert b"BTCUSDT" in entry.content
    assert b"market_kline" in entry.content


def test_controller_allowlist_routes_serve_javascript(logged_in_client):
    # R14/R15: every allowlisted controller module is served same-origin from
    # ``market/controllers/`` as JS (a missing route = import 404 = blank chart).
    from market import views

    assert len(views.CONTROLLER_ALLOWLIST) == 17
    for name in views.CONTROLLER_ALLOWLIST:
        response = logged_in_client.get(f"/market/controllers/{name}.js")
        assert response.status_code == 200, name
        assert response["Content-Type"] == "text/javascript", name

    # main.js (orchestration) is an allowlisted ESM module too.
    main = logged_in_client.get("/market/main.js")
    assert main.status_code == 200
    assert main["Content-Type"] == "text/javascript"


def test_f6_cores_and_measure_controller_are_served(logged_in_client):
    # R14 (F6): measure-core/position-core join MODULE_ALLOWLIST and
    # ``measure`` joins CONTROLLER_ALLOWLIST; each MUST be served same-origin
    # as JS or its import 404s and blanks the chart.
    from market import views

    for name in ("measure-core", "position-core"):
        assert name in views.MODULE_ALLOWLIST, name
        response = logged_in_client.get(f"/market/{name}.js")
        assert response.status_code == 200, name
        assert response["Content-Type"] == "text/javascript", name

    assert "measure" in views.CONTROLLER_ALLOWLIST
    response = logged_in_client.get("/market/controllers/measure.js")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/javascript"

    # F6 UI #194: the position-seed controller is served too.
    assert "position-seed" in views.CONTROLLER_ALLOWLIST
    response = logged_in_client.get("/market/controllers/position-seed.js")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/javascript"


def test_f9_cores_are_served(logged_in_client):
    # F9 S3 (R14): the three F9 pure cores are allowlisted and served so the
    # chart's ESM imports (drawing-core -> drawing-tools-core, ...) never 404.
    # ``CONTROLLER_ALLOWLIST`` stays untouched: the cores are modules, not
    # controllers.
    from market import views

    for name in ("drawing-tools-core", "fib-tools-core", "drawing-click-flow-core"):
        assert name in views.MODULE_ALLOWLIST, name
        response = logged_in_client.get(f"/market/{name}.js")
        assert response.status_code == 200, name
        assert response["Content-Type"] == "text/javascript", name

    assert len(views.CONTROLLER_ALLOWLIST) == 17


def test_f10_alerts_are_served(logged_in_client):
    # F10 S3 (R14): the two alert cores join MODULE_ALLOWLIST and ``alerts``
    # joins CONTROLLER_ALLOWLIST; each MUST be served same-origin as JS or its
    # import 404s and blanks the chart.
    from market import views

    assert len(views.MODULE_ALLOWLIST) == 33
    for name in (
        "alert-markers-core",
        "alert-condition-core",
        "alert-ui-core",
        "alert-markers-view",
        "alert-bell-view",
    ):
        assert name in views.MODULE_ALLOWLIST, name
        response = logged_in_client.get(f"/market/{name}.js")
        assert response.status_code == 200, name
        assert response["Content-Type"] == "text/javascript", name

    assert "alerts" in views.CONTROLLER_ALLOWLIST
    response = logged_in_client.get("/market/controllers/alerts.js")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/javascript"


def test_f10_alert_ui_is_markup_only(logged_in_client):
    # F10 (design-system R6/R7): the dialog + live-status + reason nodes are
    # static markup (CSP-clean); the bell is JS-built, so a served controller is
    # what makes it exist. The marker layering proof lives at test level: the
    # served SMC controller never grows an alert token.
    body = logged_in_client.get("/market/").content.decode()
    for marker in (
        'id="alert-dialog"',
        'id="alert-status"',
        'id="alert-interval-reason"',
        'id="alert-cue"',
        'id="alert-confirm"',
        'aria-live="polite"',
    ):
        assert marker in body, marker

    for name in (
        "alert-markers-core",
        "alert-condition-core",
        "alert-ui-core",
        "alert-markers-view",
        "alert-bell-view",
        "controllers/alerts",
    ):
        assert f'href="/market/{name}.js"' in body, name

    smc = logged_in_client.get("/market/controllers/smc.js").content
    assert b"alert" not in smc.lower(), "markers must live in alerts.js only"


def test_market_page_preloads_f9_cores(logged_in_client):
    # F9 S3b: the chart shell modulepreloads the three new cores alongside the
    # existing blocks (a missing preload is a slower, not broken, chart — but
    # the block is part of the frozen inventory contract).
    response = logged_in_client.get("/market/")
    body = response.content.decode()

    for name in ("drawing-tools-core", "fib-tools-core", "drawing-click-flow-core"):
        assert f'href="/market/{name}.js"' in body, name


def test_market_page_preloads_f6_modules(logged_in_client):
    # R14 (F6): the chart shell modulepreloads measure-core/position-core/measure
    # alongside the existing blocks (a missing preload is a slower, not broken,
    # chart — but the block is part of the frozen inventory contract).
    response = logged_in_client.get("/market/")
    body = response.content.decode()

    assert 'rel="modulepreload"' in body
    for name in (
        "/market/measure-core.js",
        "/market/position-core.js",
        "/market/readout-coalesce-core.js",
        "/market/controllers/measure.js",
    ):
        assert f'href="{name}"' in body, name


def test_import_graph_routes_resolve(logged_in_client):
    # R15 final net: every relative ``import`` specifier across the SERVED chart
    # modules resolves to a 200 JS route. The allowlist-iteration tests above only
    # prove the listed names are served; they stay green if a module gains a new
    # ``./x.js`` import whose route was never added — that import would 404 and
    # blank the chart. Deriving the expected routes from the real import graph
    # closes that gap (missing route -> import 404 -> blank chart).
    import re

    from market import views

    served = [("", name) for name in views.MODULE_ALLOWLIST]
    served += [("controllers/", name) for name in views.CONTROLLER_ALLOWLIST]
    specifier = re.compile(r"""from\s+["']([^"']+)["']""")

    resolved: set[str] = set()
    for subdir, name in served:
        body = logged_in_client.get(f"/market/{subdir}{name}.js").content.decode()
        for target in specifier.findall(body):
            if not target.startswith("."):
                continue  # only relative, same-origin ESM imports
            # Normalise ``../chart-core.js`` (from controllers/) and ``./x.js``.
            parts = (subdir + target).split("/")
            stack: list[str] = []
            for part in parts:
                if part == "..":
                    stack.pop()
                elif part not in (".", ""):
                    stack.append(part)
            resolved.add("/".join(stack))

    assert resolved, "no relative imports parsed — regex or layout changed"
    for path in sorted(resolved):
        response = logged_in_client.get(f"/market/{path}")
        assert response.status_code == 200, path
        assert response["Content-Type"] == "text/javascript", path


def test_market_page_has_no_inline_script_or_handler(logged_in_client):
    # R11: no inline script and no inline event handler (CSP-safe).
    import re

    response = logged_in_client.get("/market/")
    body = response.content.decode()
    inline_scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", body)
    assert inline_scripts == [], inline_scripts
    assert not re.search(r"\son[a-z]+\s*=", body), "inline handler found"


def test_home_links_to_market_page(logged_in_client):
    response = logged_in_client.get("/")
    assert response.status_code == 200
    assert b'href="/market/"' in response.content


def test_nav_links_to_signals_page(logged_in_client):
    # D2: the base shell exposes the /signals/ screen in the primary nav.
    response = logged_in_client.get("/market/")
    assert response.status_code == 200
    assert b'href="/signals/"' in response.content


def test_signals_route_is_served(logged_in_client):
    response = logged_in_client.get("/signals/")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")


def test_f6_position_readout_is_an_aria_live_node(logged_in_client):
    # R6 (design-system): the position R:R lives in an aria-live DOM node (the
    # canvas text is only visual reinforcement). The node starts empty and is
    # filled by the interaction controller on selection/drag.
    response = logged_in_client.get("/market/")
    assert response.status_code == 200
    body = response.content.decode()
    assert 'id="position-readout"' in body
    assert 'aria-live="polite"' in body


def test_f6_position_panel_has_its_own_heading(logged_in_client):
    # F6 UI #194: the seed button + R:R readout belong to a Position group, not
    # under the Measure heading. The Position <h2> groups them.
    response = logged_in_client.get("/market/")
    body = response.content.decode()
    assert '<h2 id="position-heading">Position</h2>' in body
    # The Position heading sits BEFORE its seed + readout, and AFTER Measure.
    assert body.index("position-heading") < body.index('id="position-seed"')
    assert body.index('id="position-seed"') < body.index('id="position-readout"')


def test_f6_position_readout_mirrors_measure_readout_style(logged_in_client):
    # F6 UI #194: #position-readout must share the mono/small token styling of
    # #measure-readout (two readouts that should look alike instead of one
    # inheriting the body font).
    css = logged_in_client.get("/theme.css").content.decode()
    assert "#measure-readout" in css
    assert "#position-readout" in css
    for token in ("font-family:var(--mono)", "font-size:var(--fs-3)"):
        measure_rule = css[css.index("#measure-readout") :]
        position_rule = css[css.index("#position-readout") :]
        assert token in measure_rule.split("}")[0], token
        assert token in position_rule.split("}")[0], token


def test_ui_audit_undo_hint_uses_tokens(logged_in_client):
    # F7 UI audit (#205): the static discoverable undo/redo hint is muted/small,
    # token-only (no hard-coded hex).
    import re

    css = logged_in_client.get("/theme.css").content.decode()
    hint = css[css.index(".history-hint") :].split("}")[0]
    assert "var(--muted)" in hint and "var(--fs-3)" in hint
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", hint), "no hard-coded hex in the hint"


def test_f9_toolbar_groups_wrap_and_targets_are_touch_sized(logged_in_client):
    # R2 #223: a 15-icon wall in a 300px panel needs wrapping group rows, a
    # visible muted caption per group and 40-44px targets (the old 36px was
    # under the touch floor). Tokens only — no literal palette.
    import re

    css = logged_in_client.get("/theme.css").content.decode()
    group = css[css.index(".draw-tools [role=group]") :].split("}")[0]
    assert "flex-wrap:wrap" in group
    caption = css[css.index(".tool-group-label") :].split("}")[0]
    assert "var(--muted)" in caption and "var(--fs-3)" in caption
    button = css[css.index(".draw-tool{") :].split("}")[0]
    target = int(re.search(r"min-height:(\d+)px", button).group(1))
    assert 40 <= target <= 44, target
    assert int(re.search(r"min-width:(\d+)px", button).group(1)) == target
    for rule in (group, caption, button):
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", rule), "no hard-coded hex"


def test_ui_audit_menu_never_writes_empty_keyshortcut(logged_in_client):
    # F7 UI #206: the served context-menu controller must guard the
    # aria-keyshortcuts attribute — an empty value is a misleading attribute.
    js = logged_in_client.get("/market/controllers/context-menu.js").content.decode()
    assert 'aria-keyshortcuts", item.keyshortcut || ""' not in js, (
        "an empty aria-keyshortcuts must not be written"
    )
    assert "if (item.keyshortcut)" in js


def test_ui_audit_menu_has_token_elevation(logged_in_client):
    # F7 UI #207: .chart-context-menu gains an elevation shadow using tokens
    # only (no hard-coded hex), so it reads as a raised surface over the chart.
    import re

    css = logged_in_client.get("/theme.css").content.decode()
    menu = css[css.index(".chart-context-menu{") :].split("}")[0]
    assert "box-shadow" in menu, "the context menu has elevation"
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", menu), "no hard-coded hex"


def test_csp_present_on_market_page(logged_in_client):
    response = logged_in_client.get("/market/")
    assert response.status_code == 200
    csp = response.headers.get("Content-Security-Policy", "")
    assert "connect-src 'self' wss://fapi.bitunix.com" in csp
    assert "https://unpkg.com" in csp
    assert "default-src 'self'" in csp


def test_csp_absent_on_admin_login(client):
    response = client.get("/admin/login/")
    assert response.status_code == 200
    assert "Content-Security-Policy" not in response.headers


def test_healthz_still_200(client):
    response = client.get("/healthz")
    assert response.status_code == 200


def _luminance(hex_color):
    """WCAG 2.1 relative luminance of a #rrggbb color."""
    raw = hex_color.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(raw[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast(a, b):
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def test_f10_alert_marker_tokens_meet_contrast(logged_in_client):
    """#232: the tokens the alert markers read must clear 4.5:1 on their theme.

    Markers paint small text on the chart canvas, whose background is the
    theme's --bg. ``alerts.js`` reads ``--alert-armed`` (armed) and ``--dn``
    (fired), so those two tokens have to be legible in BOTH palettes. The brand
    ``--accent`` is not used: its dark value is 3.86:1, under the small-text
    floor, so the marker owns a dedicated token instead of shifting the brand.
    """
    import re

    css = logged_in_client.get("/theme.css").content.decode()
    dark = css[: css.index('[data-theme="light"]')]
    light = css[css.index('[data-theme="light"]') :]

    def tokens(block):
        return {
            name: re.search(rf"{name}:(#[0-9a-fA-F]{{6}})", block).group(1)
            for name in ("--bg", "--alert-armed", "--dn")
        }

    for name, block in (("dark", dark), ("light", light)):
        t = tokens(block)
        for token in ("--alert-armed", "--dn"):
            ratio = _contrast(t[token], t["--bg"])
            assert ratio >= 4.5, f"{name} {token} on --bg is {ratio:.2f}:1 < 4.5:1"


def test_f10_bell_clears_the_price_axis_and_is_touch_sized(logged_in_client):
    """#234: the bell must not cover the crosshair price tag, and its target must
    clear the 40px touch floor on coarse pointers."""
    import re

    css = logged_in_client.get("/theme.css").content.decode()
    bell = css[css.index(".chart-alert-bell{") :].split("}")[0]
    # The offset is computed at build time into an inline style; the CSS default
    # only has to leave room for a typical axis, never sit at 8px.
    assert "right:var(--sp-2)" not in bell, "the bell must not sit on the axis"
    # aria-disabled is the inert state now, so the :disabled rule is dead weight.
    bell_block = css[css.index(".chart-alert-bell") : css.index("#alert-dialog")]
    assert ":disabled" not in bell_block
    assert '[aria-disabled="true"]' in css
    # Coarse pointers get the touch floor (the desktop stays compact).
    coarse = css[css.index("@media (pointer:coarse)") :]
    coarse = coarse[: coarse.index("}}") + 1] if "}}" in coarse else coarse
    target = int(re.search(r"min-width:(\d+)px", coarse).group(1))
    assert 40 <= target <= 44, target
    assert f"min-height:{target}px" in coarse


def test_f10_alert_dialog_cue_and_confirm_are_token_only(logged_in_client):
    """#234: the silent-edit cue and the success confirmation reuse shell tokens."""
    import re

    css = logged_in_client.get("/theme.css").content.decode()
    for selector in ("#alert-dialog .alert-cue", "#alert-confirm"):
        rule = css[css.index(selector + "{") :].split("}")[0]
        assert "var(--" in rule, selector
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", rule), selector


def test_f10_alert_marker_token_is_declared_in_both_palettes(logged_in_client):
    """#232: a token read at render time must exist in BOTH palettes.

    The shell uses :root for dark and [data-theme="light"] for light; a name
    missing from either set silently falls back to the core literal.
    """
    css = logged_in_client.get("/theme.css").content.decode()
    dark = css[: css.index('[data-theme="light"]')]
    light = css[css.index('[data-theme="light"]') :]
    assert "--alert-armed:" in dark
    assert "--alert-armed:" in light
