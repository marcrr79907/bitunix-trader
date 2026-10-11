"""Per-user trading routes (positions, journal). Bare names (mirrors market)."""

from __future__ import annotations

from django.urls import path

from trading import views

urlpatterns = [
    path("positions/", views.positions, name="positions"),
    path("journal/", views.journal, name="journal"),
]
