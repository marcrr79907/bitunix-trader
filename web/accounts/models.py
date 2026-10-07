"""Custom User: email is the identifier; `role` is the product concept.

`is_staff` is deliberately NOT the role. Per design D1 it only marks "may use
the Django admin"; the domain role lives in the `role` enum.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from accounts.managers import UserManager

INVITE_TTL = timedelta(days=7)


def gen_token() -> str:
    """Single-use invite token; URL-safe, ~256 bits of entropy."""
    return secrets.token_urlsafe(32)


def default_expiry():
    return timezone.now() + INVITE_TTL


class User(AbstractUser):
    class Role(models.TextChoices):
        MEMBER = "member", "Member"
        ADMIN = "admin", "Admin"

    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def __str__(self) -> str:
        return self.email


class Invite(models.Model):
    """Invitation-only signup: one email, one single-use token, one role."""

    email = models.EmailField(db_index=True)
    token = models.CharField(max_length=64, unique=True, default=gen_token)
    role = models.CharField(
        max_length=16, choices=User.Role.choices, default=User.Role.MEMBER
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invites_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_expiry)
    used_at = models.DateTimeField(null=True, blank=True)

    def is_valid(self) -> bool:
        return self.used_at is None and self.expires_at > timezone.now()

    def __str__(self) -> str:
        return f"Invite<{self.email}>"
