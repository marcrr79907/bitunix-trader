"""Landing page and invite-link UX contracts.

R-landing: `/` never 404s; anonymous is redirected to login, authenticated sees
the home page.
R-invite-link: creating an invite shows the shareable signup URL.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_home_redirects_anonymous_to_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.url == "/login/"


@pytest.mark.django_db
def test_home_renders_for_authenticated_user(client):
    user = User.objects.create_user(email="u@example.com", password="pw-123456")
    client.force_login(user)
    response = client.get("/")
    assert response.status_code == 200
    assert b"u@example.com" in response.content


@pytest.mark.django_db
def test_invite_create_shows_shareable_link(client):
    staff = User.objects.create_user(
        email="staff@example.com", password="pw-123456", is_staff=True
    )
    client.force_login(staff)
    response = client.post(
        "/accounts/invites/new/",
        {"email": "guest@example.com", "role": "member"},
    )
    assert response.status_code == 200
    assert b"/accounts/signup/" in response.content
