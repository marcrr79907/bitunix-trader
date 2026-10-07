"""Custom User: email is the identifier; `role` is the product concept.

`is_staff` is deliberately NOT the role. Per design D1 it only marks "may use
the Django admin"; the domain role lives in the `role` enum.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models

from accounts.managers import UserManager


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
