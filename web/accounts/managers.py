"""Email-based user manager: no username anywhere in the lifecycle."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Create and manage users identified by email."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra: Any):
        if not email:
            raise ValueError("An email address is required.")
        # ponytail: lowercase the whole address so all callers store one canonical
        # form; the DB unique constraint then rejects case-variant duplicates.
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra: Any):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: Any):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra)

    def get_by_natural_key(self, username: str | None):
        # Login path: ModelBackend calls this with the raw email; normalize so
        # `MiXeD@Example.com` authenticates against the stored lowercase form.
        return self.get(**{self.model.USERNAME_FIELD + "__iexact": username})
