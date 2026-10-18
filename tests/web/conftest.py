"""R14 isolation harness: two independent users for cross-tenant tests.

PR2 ships the harness only. No green isolation assertion yet — Phase 2 of the
product adds owned rows and the test that flips red -> green uses these fixtures.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def user_a(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="user_a@example.com", password="pw-a-12345"
    )


@pytest.fixture
def user_b(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="user_b@example.com", password="pw-b-12345"
    )


# --- shared Playwright fixtures (moved out of test_market_e2e.py) ------------
# A second E2E module (test_market_alert_e2e.py) needs the same authenticated
# page; importing fixtures across test modules shadows names and trips ruff.
# ``sync_playwright`` is imported lazily so non-e2e runs never touch it.


@pytest.fixture
def e2e_user(db):
    """The Playwright session user (shared so layout seeds target the same row)."""
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="e2e@example.com", password="pw-123456"
    )


@pytest.fixture
def browser_page(live_server, client, e2e_user):
    """A Playwright page carrying the Django session cookie."""
    from playwright.sync_api import sync_playwright

    client.force_login(e2e_user)
    cookie = client.cookies["sessionid"]

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": "sessionid",
                    "value": cookie.value,
                    "domain": "localhost",
                    "path": "/",
                }
            ]
        )
        page = context.new_page()
        yield page, live_server.url
        browser.close()
