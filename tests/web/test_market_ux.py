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


def test_smc_overlay_core_served_as_javascript(client):
    # Pure SMC overlay mapping is same-origin and NOT auth-gated (no state).
    response = client.get("/market/smc-overlay-core.js")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/javascript"
    assert b"visibleFamilies" in response.content
    assert b"setupMarkers" in response.content


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

    assert len(views.CONTROLLER_ALLOWLIST) == 6
    for name in views.CONTROLLER_ALLOWLIST:
        response = logged_in_client.get(f"/market/controllers/{name}.js")
        assert response.status_code == 200, name
        assert response["Content-Type"] == "text/javascript", name

    # main.js (orchestration) is an allowlisted ESM module too.
    main = logged_in_client.get("/market/main.js")
    assert main.status_code == 200
    assert main["Content-Type"] == "text/javascript"


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
