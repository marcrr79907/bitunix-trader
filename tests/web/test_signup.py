"""R2 contract: token-gated signup; expired/reused/unknown rejected; no open route."""

from __future__ import annotations

from datetime import timedelta

import pytest
from accounts.models import Invite
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

PASSWORD = "signup-pw-98765"  # gitleaks:allow (test fixture, not a real secret)


def _invite(**overrides) -> Invite:
    return Invite.objects.create(
        email=overrides.get("email", "invitee@example.com"),
        role=overrides.get("role", "member"),
        expires_at=overrides.get("expires_at", timezone.now() + timedelta(days=7)),
        used_at=overrides.get("used_at", None),
    )


@pytest.mark.django_db
def test_signup_page_renders_for_valid_token(client):
    invite = _invite()
    response = client.get(f"/accounts/signup/{invite.token}/")
    assert response.status_code == 200
    assert b"password" in response.content.lower()


@pytest.mark.django_db
def test_valid_token_creates_user_with_invite_role(client):
    invite = _invite(email="admin-invite@example.com", role="admin")
    response = client.post(
        f"/accounts/signup/{invite.token}/",
        {"password1": PASSWORD, "password2": PASSWORD},
    )
    assert response.status_code == 302
    user = User.objects.get(email="admin-invite@example.com")
    assert user.role == "admin"
    assert user.check_password(PASSWORD)
    invite.refresh_from_db()
    assert invite.used_at is not None


@pytest.mark.django_db
def test_expired_token_rejected(client):
    invite = _invite(expires_at=timezone.now() - timedelta(minutes=1))
    response = client.get(f"/accounts/signup/{invite.token}/")
    assert response.status_code == 404
    response = client.post(
        f"/accounts/signup/{invite.token}/",
        {"password1": PASSWORD, "password2": PASSWORD},
    )
    assert response.status_code == 404
    assert not User.objects.exists()


@pytest.mark.django_db
def test_reused_token_rejected(client):
    invite = _invite(used_at=timezone.now())
    response = client.get(f"/accounts/signup/{invite.token}/")
    assert response.status_code == 404
    response = client.post(
        f"/accounts/signup/{invite.token}/",
        {"password1": PASSWORD, "password2": PASSWORD},
    )
    assert response.status_code == 404
    assert not User.objects.exists()


@pytest.mark.django_db
def test_unknown_token_rejected(client):
    response = client.get("/accounts/signup/does-not-exist/")
    assert response.status_code == 404
    assert b"password" not in response.content.lower()
    assert not User.objects.exists()


@pytest.mark.django_db
def test_signup_normalises_email(client):
    invite = _invite(email="MiXeD@Example.COM")
    client.post(
        f"/accounts/signup/{invite.token}/",
        {"password1": PASSWORD, "password2": PASSWORD},
    )
    user = User.objects.get()
    assert user.email == "mixed@example.com"


@pytest.mark.django_db
def test_signup_for_existing_email_does_not_error(client):
    """W1: an invite for an already-registered email must not 500 or duplicate."""
    User.objects.create_user(email="taken@example.com", password="pw-123456")
    invite = _invite(email="taken@example.com")
    response = client.post(
        f"/accounts/signup/{invite.token}/",
        {"password1": PASSWORD, "password2": PASSWORD},
    )
    assert response.status_code == 404
    assert User.objects.filter(email="taken@example.com").count() == 1


@pytest.mark.django_db
def test_signup_weak_password_rejected(client):
    """W4: AUTH_PASSWORD_VALIDATORS must be enforced at signup."""
    invite = _invite(email="weak@example.com")
    response = client.post(
        f"/accounts/signup/{invite.token}/",
        {"password1": "1", "password2": "1"},
    )
    assert response.status_code == 200
    assert not User.objects.filter(email="weak@example.com").exists()


@pytest.mark.django_db
def test_no_open_self_registration_route(client):
    assert client.get("/signup/").status_code == 404
    assert client.get("/register/").status_code == 404
    assert client.get("/accounts/signup/").status_code == 404


@pytest.mark.django_db
def test_token_is_single_use(client):
    invite = _invite()
    client.post(
        f"/accounts/signup/{invite.token}/",
        {"password1": PASSWORD, "password2": PASSWORD},
    )
    assert User.objects.count() == 1
    response = client.post(
        f"/accounts/signup/{invite.token}/",
        {"password1": "another-pw-111", "password2": "another-pw-111"},
    )
    assert response.status_code == 404
    assert User.objects.count() == 1
