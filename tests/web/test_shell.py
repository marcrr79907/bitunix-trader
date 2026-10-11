"""design-system contract: same-origin tokens stylesheet + app shell.

R1 the theme stylesheet is served as text/css, anonymously.
R2 the shell (topbar + nav) renders on every page; active nav is marked.
R3 logout is a POST form (Django 5.2 LogoutView).
R4 pages can inject scripts without breaking the shell.
R7 CSP unchanged; no inline handler remains.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

THEME_URL = "/theme.css"
PAGES = [
    ("/", "home"),
    ("/login/", "login"),
    ("/market/", "market"),
]
TEMPLATES = Path(__file__).resolve().parents[2] / "web"


@pytest.mark.django_db
def test_theme_css_is_served_anonymously_as_text_css(client):
    response = client.get(THEME_URL)
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/css")
    body = response.content.decode()
    assert ":root" in body
    for token in ("--bg", "--text", "--accent", "--up", "--dn", "--surface"):
        assert token in body, f"missing token {token}"


@pytest.mark.django_db
def test_invite_js_is_served_same_origin(client):
    response = client.get("/invite.js")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/javascript")


@pytest.mark.django_db
def test_shell_renders_on_public_pages(client):
    for path, _ in PAGES:
        response = client.get(path)
        assert response.status_code in (200, 302)
        if response.status_code == 200:
            body = response.content.decode()
            assert 'class="topbar"' in body
            assert 'aria-label="Primary"' in body


@pytest.mark.django_db
def test_shell_renders_for_authenticated_pages(client):
    user = User.objects.create_user(email="u@example.com", password="pw-123456")
    client.force_login(user)
    for path in ("/", "/market/"):
        body = client.get(path).content.decode()
        assert 'class="topbar"' in body
        assert user.email in body
        assert 'method="post"' in body  # logout form


@pytest.mark.django_db
def test_market_nav_marked_active(client):
    user = User.objects.create_user(email="u@example.com", password="pw-123456")
    client.force_login(user)
    body = client.get("/market/").content.decode()
    assert 'aria-current="page"' in body


@pytest.mark.django_db
def test_placeholder_nav_does_not_crash(client):
    # Positions/Journal routes do not exist yet (Fase 6c); shell must still render.
    user = User.objects.create_user(email="u@example.com", password="pw-123456")
    client.force_login(user)
    body = client.get("/").content.decode()
    assert 'href="/positions/"' in body
    assert 'href="/journal/"' in body


@pytest.mark.django_db
def test_logout_is_post_form_not_get_link(client):
    user = User.objects.create_user(email="u@example.com", password="pw-123456")
    client.force_login(user)
    body = client.get("/").content.decode()
    # a POST form to logout, not an anchor issuing GET
    assert re.search(r"<form[^>]*method=\"post\"[^>]*action=\"/logout/\"", body)
    assert 'href="/logout/"' not in body


@pytest.mark.django_db
def test_logout_post_works(client):
    user = User.objects.create_user(email="u@example.com", password="pw-123456")
    client.force_login(user)
    response = client.post("/logout/")
    assert response.status_code == 302
    assert "_auth_user_id" not in client.session


def test_no_inline_event_handler_in_templates():
    # R7: no on*= inline handlers (CSP script-src forbids them).
    offenders = []
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text()
        if re.search(r"\son[a-z]+\s*=", text):
            offenders.append(str(path))
    assert offenders == [], f"inline event handler found: {offenders}"


def test_no_inline_script_tag():
    # R7: no inline <script> without src.
    offenders = []
    for path in TEMPLATES.rglob("*.html"):
        for m in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>", path.read_text()):
            offenders.append(f"{path}: {m.group(0)}")
    assert offenders == [], f"inline <script> found: {offenders}"
