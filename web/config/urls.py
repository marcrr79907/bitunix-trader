"""Root URL configuration."""

from __future__ import annotations

from django.contrib import admin
from django.urls import include, path

from config.health import healthz

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("market.urls")),
]
