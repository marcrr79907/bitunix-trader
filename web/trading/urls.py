"""Per-user trading routes (positions, journal). Bare names (mirrors market)."""

from __future__ import annotations

from django.urls import path

from trading import views

urlpatterns = [
    path("positions/", views.positions, name="positions"),
    path("journal/", views.journal, name="journal"),
    path("rules/", views.rules, name="rules"),
    path("rules/new/", views.rule_create, name="rule_create"),
    path("rules/<int:pk>/edit/", views.rule_edit, name="rule_edit"),
    path("rules/<int:pk>/toggle/", views.rule_toggle, name="rule_toggle"),
    path("rules/<int:pk>/delete/", views.rule_delete, name="rule_delete"),
]
