"""Market routes. Bare names on purpose (mirrors accounts — no app_name)."""

from __future__ import annotations

from django.urls import path

from market import alerts, views, watchlist
from market import templates as template_api

urlpatterns = [
    path("market/", views.market_page, name="market_page"),
    path("signals/", views.signals_page, name="signals"),
    path("market/api/kline", views.api_kline, name="market_api_kline"),
    path("market/api/smc", views.api_smc, name="market_api_smc"),
    path("market/api/symbols", views.api_symbols, name="market_api_symbols"),
    path("market/api/layout", views.api_layout, name="market_api_layout"),
    path(
        "market/api/templates", template_api.api_templates, name="market_api_templates"
    ),
    path(
        "market/api/templates/<int:id>",
        template_api.api_template_detail,
        name="market_api_template_detail",
    ),
    path("market/api/watchlist", watchlist.api_watchlist, name="market_api_watchlist"),
    path(
        "market/api/watchlist/<str:symbol>",
        watchlist.api_watchlist_detail,
        name="market_api_watchlist_detail",
    ),
    path(
        "market/api/preference",
        views.api_preference,
        name="market_api_preference",
    ),
    path("market/api/alerts", alerts.api_alerts, name="market_api_alerts"),
    path(
        "market/api/alerts/<int:id>",
        alerts.api_alert_detail,
        name="market_api_alert_detail",
    ),
    path("market/api/drawings", views.api_drawings, name="market_api_drawings"),
    path(
        "market/api/drawings/<int:id>",
        views.api_drawing_detail,
        name="market_api_drawing_detail",
    ),
    path("market/chart.js", views.chart_js, name="market_chart_js"),
    path(
        "market/controllers/<slug:name>.js",
        views.market_controller_js,
        name="market_controller_js",
    ),
    path(
        "market/<slug:name>.js",
        views.market_chart_module_js,
        name="market_chart_module_js",
    ),
]
