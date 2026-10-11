"""Market routes. Bare names on purpose (mirrors accounts — no app_name)."""

from __future__ import annotations

from django.urls import path

from market import views

urlpatterns = [
    path("market/", views.market_page, name="market_page"),
    path("market/api/kline", views.api_kline, name="market_api_kline"),
    path("market/chart-core.js", views.chart_core_js, name="market_chart_core_js"),
    path("market/chart.js", views.chart_js, name="market_chart_js"),
]
