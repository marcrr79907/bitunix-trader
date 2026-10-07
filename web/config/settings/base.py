"""Environment-driven Django settings shared by all environments.

Nothing here hardcodes a connection target: everything comes from the
environment so the same image runs locally and on the platform.
"""

from __future__ import annotations

import os
from pathlib import Path

import dj_database_url

# web/ — the Django project root (this file lives in web/config/settings/).
BASE_DIR = Path(__file__).resolve().parent.parent.parent

_FALSEY = {"", "0", "false", "off", "no"}


def env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean from the environment; falsey spellings disable it."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in _FALSEY


def env_list(name: str) -> list[str]:
    """Read a comma-separated list from the environment."""
    return [
        item.strip() for item in os.environ.get(name, "").split(",") if item.strip()
    ]


# DEBUG is environment-controlled in every environment; default off.
DEBUG = env_bool("DEBUG", False)

SECRET_KEY = os.environ.get("SECRET_KEY", "")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")

# Database: parse DATABASE_URL when present, else local sqlite for dev.
if os.environ.get("DATABASE_URL"):
    DATABASES = {"default": dj_database_url.parse(os.environ["DATABASE_URL"])}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Cache/queue: REDIS_URL when present, else in-memory (dev/tests).
REDIS_URL = os.environ.get("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
]

AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

MIDDLEWARE = [
    # First: short-circuit /healthz before host validation (Railway's internal
    # probe arrives with a private-IP Host that ALLOWED_HOSTS cannot express).
    "config.middleware.HealthProbeHostMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"  # noqa: E501
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# Origins allowed to POST with CSRF protection. Behind Railway's HTTPS proxy
# the browser sends https://... while Django may see the request as http, so
# these must be listed explicitly (comma-separated, full scheme).
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
