"""R5 contract: settings are env-driven, split, and fail closed in prod.

Each case boots a settings module in a clean subprocess so the assertions
describe real boot behavior (env -> config), not import-time artifacts of the
test process. Django is imported only inside the subprocess, never here.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"

_PROBE = (
    "import importlib, json\n"
    "m = importlib.import_module({module!r})\n"
    "print(json.dumps({{k: m.__dict__.get(k) for k in "
    "['DEBUG', 'ALLOWED_HOSTS', 'DATABASES', 'CACHES', 'SECRET_KEY', "
    "'REDIS_URL']}}, default=str))\n"
)


def _boot(module: str, **env: str) -> subprocess.CompletedProcess:
    child_env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(WEB),
        **env,
    }
    return subprocess.run(
        [sys.executable, "-c", _PROBE.format(module=f"config.settings.{module}")],
        cwd=WEB,
        env=child_env,
        capture_output=True,
        text=True,
    )


def _load(module: str, **env: str) -> dict:
    result = _boot(module, **env)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_database_url_is_parsed_not_hardcoded():
    loaded = _load(
        "base",
        DATABASE_URL="postgres://alice:pa55@dbhost:5432/traderdb",
    )
    default = loaded["DATABASES"]["default"]
    assert default["NAME"] == "traderdb"
    assert default["HOST"] == "dbhost"
    assert default["USER"] == "alice"
    assert str(default["PORT"]) == "5432"
    assert "postgres" in default["ENGINE"]


def test_redis_url_is_used_for_cache():
    loaded = _load("base", REDIS_URL="redis://cachehost:6379/3")
    assert loaded["REDIS_URL"] == "redis://cachehost:6379/3"
    assert loaded["CACHES"]["default"]["LOCATION"] == "redis://cachehost:6379/3"


def test_prod_without_secret_key_fails_closed():
    result = _boot("prod", DATABASE_URL="postgres://u:p@h:5432/d", DEBUG="false")
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr


def test_prod_uses_env_secret_key():
    loaded = _load(
        "prod",
        DATABASE_URL="postgres://u:p@h:5432/d",
        SECRET_KEY="prod-secret-from-env",
        DEBUG="false",
    )
    assert loaded["SECRET_KEY"] == "prod-secret-from-env"
    assert loaded["DEBUG"] is False


def test_dev_defaults_are_local_only():
    loaded = _load("dev")
    assert loaded["DEBUG"] is True
    assert loaded["DATABASES"]["default"]["ENGINE"] == "django.db.backends.sqlite3"
    assert "localhost" in loaded["ALLOWED_HOSTS"]


def test_debug_falsey_disables_regardless_of_module():
    for falsey in ("0", "false", "off", ""):
        assert _load("dev", DEBUG=falsey)["DEBUG"] is False
        assert _load("base", DEBUG=falsey)["DEBUG"] is False
