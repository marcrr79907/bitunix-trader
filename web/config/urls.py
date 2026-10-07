"""Root URL configuration."""

from __future__ import annotations

from django.contrib import admin
from django.urls import path

from config.health import healthz

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("admin/", admin.site.urls),
]
