"""R14 module-size guard: no market module exceeds ~300 lines (issue #144 / W4).

Committed, executable form of the R14 layer rule that used to be verified by
inspection only. Pure filesystem (no Django client, no network, no dependency):
it line-counts every ``web/market/templates/market/**/*.js`` file, including
``controllers/``, and fails any module above ``CEILING`` unless it is in the
documented allowlist.

``chart-host.js`` (326 lines) is the one exempt module: it is the tracked
DEBT-5 refactor (#146), which will split host responsibilities so the file can
drop under the ceiling. Every OTHER module — cores, controllers, entry — MUST
comply; the guard names the offending file and its line count when it does not.
"""

from __future__ import annotations

from pathlib import Path

# R14: "no module MUST exceed ~300 lines".
CEILING = 300

# DEBT-5 / #146 — tracked refactor target. chart-host.js is 326 lines today (its
# high-water mark); it is the single sanctioned exception, not a general escape
# hatch. Removing this entry without refactoring the file fails the guard.
ALLOWLIST = {"chart-host.js"}

_MODULES_DIR = Path(__file__).resolve().parents[2] / "web/market/templates/market"
# Anti-vacuity: the scan MUST see the real inventory, not a near-empty glob.
_MIN_MODULES_SCANNED = 5


def _line_count(text: str) -> int:
    """Non-empty traversal line count (``splitlines`` semantics)."""
    return len(text.splitlines())


def over_ceiling(
    modules: dict[str, str],
    *,
    ceiling: int = CEILING,
    allowlist: set[str] = ALLOWLIST,
) -> dict[str, int]:
    """Return ``{name: line_count}`` for non-allowlisted modules over ``ceiling``.

    Pure and file-system-free so the negative control can drive it directly with
    a synthetic oversized module (proving the check can actually fail).
    """
    return {
        name: _line_count(text)
        for name, text in modules.items()
        if name not in allowlist and _line_count(text) > ceiling
    }


def _scan_modules() -> dict[str, str]:
    """Read every market JS module by name (rglob, controllers included)."""
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in _MODULES_DIR.rglob("*.js")
    }


def test_every_market_module_is_within_the_ceiling():
    modules = _scan_modules()

    # Anti-vacuous: a broken glob would otherwise pass with nothing to check.
    assert len(modules) > _MIN_MODULES_SCANNED, sorted(modules)

    offenders = over_ceiling(modules)
    assert offenders == {}, (
        "R14 ceiling ({} lines) exceeded by non-allowlisted module(s): {}".format(
            CEILING,
            ", ".join(f"{name}={n}" for name, n in sorted(offenders.items())),
        )
    )


def test_allowlist_exempts_chart_host_but_not_others():
    # The documented exception holds for chart-host.js (326 lines) ...
    assert over_ceiling({"chart-host.js": "\n" * 326}) == {}
    # ... and does NOT leak to any other file of the same size.
    over = over_ceiling({"indicator-settings-core.js": "\n" * 326})
    assert over == {"indicator-settings-core.js": 326}


def test_negative_control_oversized_module_fails():
    # Negative control (R7): a synthetic module one line over the ceiling MUST be
    # reported with its name and count — the guard provably can fail.
    synthetic = {"synthetic_oversized.js": "// x\n" * (CEILING + 1)}
    over = over_ceiling(synthetic)
    assert over == {"synthetic_oversized.js": CEILING + 1}
