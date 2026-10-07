"""Production settings: fail closed when SECRET_KEY is absent."""

from __future__ import annotations

import os

from .base import *  # noqa: F403

# Dict-index on purpose: a missing SECRET_KEY raises KeyError at boot instead of
# silently falling back to a shared insecure secret.
SECRET_KEY = os.environ["SECRET_KEY"]

DEBUG = False

# Railway terminates TLS and forwards over HTTP, setting X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# https-only cookies + HSTS once we are sure the proxied scheme is correct.
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
