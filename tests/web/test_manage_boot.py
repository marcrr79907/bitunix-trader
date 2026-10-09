"""Regression: Django startup must not depend on the caller's PYTHONPATH.

The root URLconf reaches the framework-free core (`src/`) via `market.quotes`,
so `manage.py check` / `makemigrations` would raise `ModuleNotFoundError: No
module named 'src'` if `manage.py` relied on the environment. CI runs those
commands with no PYTHONPATH; this test locks the fix.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_manage_py_check_works_without_pythonpath():
    env = {"PATH": "/usr/bin:/bin", "DJANGO_SETTINGS_MODULE": "config.settings.dev"}
    result = subprocess.run(
        [sys.executable, "web/manage.py", "check"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ModuleNotFoundError" not in result.stderr
