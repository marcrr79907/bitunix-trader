"""Django admin registration for the custom User."""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from accounts.forms import InviteForm
from accounts.models import Invite, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Permissions", {"fields": ("role", "is_active", "is_staff", "is_superuser")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
    list_display = ("email", "role", "is_staff", "is_active")
    ordering = ("email",)
    search_fields = ("email",)


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    # W2: use InviteForm so admin creation runs the same email/expiry validation.
    form = InviteForm
    list_display = ("email", "role", "expires_at", "used_at", "created_by")
    list_filter = ("role", "used_at")
    search_fields = ("email", "token")
    readonly_fields = ("token", "created_at", "used_at")
