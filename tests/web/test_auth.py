"""R3 contract: native Django auth — email login, logout, password reset."""

from __future__ import annotations

import re

import pytest
from django.core import mail

LOGIN_URL = "/login/"
LOGOUT_URL = "/logout/"
RESET_URL = "/password-reset/"

CREDS = {"email": "auth@example.com", "password": "pw-123456"}


def _make_user(**overrides):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email=overrides.get("email", CREDS["email"]),
        password=overrides.get("password", CREDS["password"]),
    )


@pytest.mark.django_db
def test_login_with_email_creates_session(client):
    _make_user()
    response = client.post(
        LOGIN_URL, {"username": CREDS["email"], "password": CREDS["password"]}
    )
    assert response.status_code == 302
    assert client.session["_auth_user_id"]


@pytest.mark.django_db
def test_wrong_credentials_no_session(client):
    _make_user()
    response = client.post(
        LOGIN_URL, {"username": CREDS["email"], "password": "not-the-password"}
    )
    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_logout_invalidates_session(client):
    _make_user()
    client.post(LOGIN_URL, {"username": CREDS["email"], "password": CREDS["password"]})
    assert client.session["_auth_user_id"]
    response = client.post(LOGOUT_URL)
    assert response.status_code == 302
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_password_reset_round_trip(client):
    user = _make_user()
    old_password = user.password

    response = client.post(RESET_URL, {"email": CREDS["email"]})
    assert response.status_code == 302
    assert len(mail.outbox) == 1

    match = re.search(
        r"/reset/(?P<uidb64>[^/]+)/(?P<token>[^/]+)/", mail.outbox[0].body
    )
    assert match, "reset email must carry a tokenized link"

    confirm_url = f"/reset/{match['uidb64']}/{match['token']}/"
    assert client.get(confirm_url).status_code == 302  # -> set-password URL

    set_password_url = client.get(confirm_url).url
    new = "new-pw-98765"
    response = client.post(
        set_password_url, {"new_password1": new, "new_password2": new}
    )
    assert response.status_code == 302

    user.refresh_from_db()
    assert user.password != old_password
    assert user.check_password("new-pw-98765")
    assert not user.check_password(CREDS["password"])
