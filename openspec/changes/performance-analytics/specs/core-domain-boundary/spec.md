# Delta for core-domain-boundary

E1 adds a NEW pure module `src/analytics.py`. R9–R11 are unchanged; this delta
extends the framework-free inventory so the stdlib-only check is not blind to it.

## ADDED Requirements

### Requirement: R12 — analytics module joins the framework-free inventory

`src/analytics.py` MUST be subject to the same one-way boundary as the rest of
the core: it MUST import stdlib only (plus `src.metrics`), MUST NOT import Django
or any web framework, and MUST be importable without Django. It MUST be
registered in `PURE_MODULES` in `tests/test_boundary.py` so
`test_pure_modules_are_stdlib_only` checks it.

#### Scenario: analytics is registered in PURE_MODULES

- GIVEN `tests/test_boundary.py`
- WHEN `PURE_MODULES` is read
- THEN it contains `"analytics.py"`

#### Scenario: analytics is stdlib-only

- GIVEN `src/analytics.py`
- WHEN `test_pure_modules_are_stdlib_only` runs
- THEN no non-stdlib import is found and the test passes

#### Scenario: analytics imports without Django

- GIVEN an environment where Django is not importable
- WHEN `src/analytics.py` is imported
- THEN the import succeeds

#### Scenario: Django violation is caught

- GIVEN a change that adds `import django` to `src/analytics.py`
- WHEN the boundary test runs
- THEN it fails

#### Scenario: metrics stays registered

- GIVEN `tests/test_boundary.py`
- WHEN `PURE_MODULES` is read
- THEN it still contains `"metrics.py"` (the E1 additions did not remove it)
