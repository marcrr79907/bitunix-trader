"""R12 contract: no secrets in the repo; runtime secrets come from env.

Scans settings source for literal secret assignments and asserts .env is
gitignored. Stdlib + subprocess only — no Django import needed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / "web" / "config" / "settings"


def test_dotenv_is_gitignored():
    result = subprocess.run(
        ["git", "check-ignore", ".env"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, ".env is NOT gitignored"
    assert result.stdout.strip().endswith(".env")


def test_settings_have_no_hardcoded_secrets():
    needle = ("postgres://", "redis://", "password=", "api_secret")
    for path in sorted(SETTINGS.rglob("*.py")):
        text = path.read_text().lower()
        for bad in needle:
            assert bad not in text, f"{path} contains literal secret marker {bad!r}"
