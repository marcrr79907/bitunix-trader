"""R4 contract: custom User keyed by email, safe default role, email auth."""

from __future__ import annotations

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction

User = get_user_model()


def test_auth_user_model_is_custom(settings):
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert User._meta.label == "accounts.User"


@pytest.mark.django_db
def test_duplicate_email_rejected():
    User.objects.create_user(email="dup@example.com", password="pw-123456")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            User.objects.create_user(email="dup@example.com", password="pw-654321")


@pytest.mark.django_db
def test_duplicate_email_case_insensitive():
    User.objects.create_user(email="Case@Example.com", password="pw-123456")
    stored = User.objects.get(email="case@example.com")
    assert stored.email == "case@example.com"
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            User.objects.create_user(email="CASE@EXAMPLE.COM", password="pw-654321")


@pytest.mark.django_db
def test_authenticate_email_is_case_insensitive():
    User.objects.create_user(email="mixed@example.com", password="pw-123456")
    assert authenticate(email="MiXeD@Example.com", password="pw-123456") is not None


@pytest.mark.django_db
def test_role_defaults_to_member():
    user = User.objects.create_user(email="role@example.com", password="pw-123456")
    assert user.role == "member"


@pytest.mark.django_db
def test_role_can_be_admin():
    user = User.objects.create_user(
        email="admin-role@example.com", password="pw-123456", role="admin"
    )
    assert user.role == "admin"


@pytest.mark.django_db
def test_authenticate_with_email_succeeds():
    user = User.objects.create_user(email="auth@example.com", password="pw-123456")
    assert authenticate(email="auth@example.com", password="pw-123456") == user
    assert authenticate(email="auth@example.com", password="wrong") is None


@pytest.mark.django_db
def test_create_superuser():
    admin = User.objects.create_superuser(
        email="root@example.com", password="pw-123456"
    )
    assert admin.is_staff is True
    assert admin.is_superuser is True
    assert admin.role == "member"
