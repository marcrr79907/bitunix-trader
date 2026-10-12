# Delta for core-domain-boundary

## ADDED Requirements

### Requirement: R11 — smc package joins the framework-free inventory

The `src/smc/` package (`__init__.py`, `config.py`, `swings.py`, `structure.py`)
MUST be subject to the same one-way boundary as the rest of the core: it MUST
import stdlib only, MUST NOT import Django or any web framework, and MUST be
importable without Django. Its three compute modules MUST be registered in
`PURE_MODULES` in `tests/test_boundary.py` so the stdlib-only check is not blind
to them.

#### Scenario: smc modules are stdlib-only

- GIVEN the new `src/smc/` modules
- WHEN `test_pure_modules_are_stdlib_only` runs
- THEN no non-stdlib import is found and the test passes

#### Scenario: smc imports without Django

- GIVEN an environment where Django is not importable
- WHEN `src/smc/` modules are imported
- THEN imports succeed

#### Scenario: Django violation is caught

- GIVEN a change that adds `import django` to any `src/smc/` module
- WHEN the boundary test runs
- THEN it fails
