# core-domain-boundary Specification

## Purpose

Preserve the framework-free core: `web/` (Django) MAY import `src/`, but `src/` MUST remain dependency-free. A boundary test is the enforcement seam. New capability — no prior spec.

## Requirements

### Requirement: R9 — One-way dependency direction

The dependency arrow MUST point only from the Django layer (`web/`) into the core (`src/`). The core MUST NOT import Django or any web framework. The core MUST remain importable without a Django installation.

#### Scenario: No Django import in core

- GIVEN the files under `src/`
- WHEN the boundary test scans them
- THEN no file imports Django (`django`, `django.*`)

#### Scenario: Boundary test fails on violation

- GIVEN a change that adds `import django` to any `src/` module
- WHEN the test suite runs
- THEN the boundary test fails

#### Scenario: Core imports without Django

- GIVEN an environment where Django is not importable
- WHEN the `src/` modules are imported
- THEN imports succeed

#### Scenario: Web may depend on core

- GIVEN the `web/` Django project
- WHEN it uses functionality from `src/`
- THEN the import is permitted and resolves without changing `src/`

### Requirement: R10 — Core reused unchanged

Existing `src/` modules, their tests, and the ruff configuration MUST remain behaviorally unchanged by this change; the CLI MUST keep working.

#### Scenario: Existing suite stays green

- GIVEN the pre-existing tests
- WHEN the full suite runs
- THEN all previously passing tests still pass

#### Scenario: CLI behavior preserved

- GIVEN the CLI entry points
- WHEN invoked as before
- THEN behavior is unchanged

### Requirement: R11 — smc package joins the framework-free inventory

The `src/smc/` package (`__init__.py`, `config.py`, `swings.py`, `structure.py`,
`zones.py`, `range.py`, `signals.py`) MUST be subject to the same one-way boundary
as the rest of the core: it MUST import stdlib only, MUST NOT import Django or any
web framework, and MUST be importable without Django. Its six compute modules
(`config.py`, `swings.py`, `structure.py`, `zones.py`, `range.py`, `signals.py`),
plus the pure alert engine `alert_rules.py`, MUST be registered in `PURE_MODULES`
in `tests/test_boundary.py` so the stdlib-only check is not blind to them.

#### Scenario: smc modules are stdlib-only

- GIVEN the `src/smc/` modules
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

#### Scenario: B2 modules are registered in PURE_MODULES

- GIVEN `tests/test_boundary.py`
- WHEN `PURE_MODULES` is read
- THEN it contains `"smc/zones.py"`, `"smc/range.py"`, and `"smc/signals.py"`

#### Scenario: alert engine is registered in PURE_MODULES

- GIVEN `tests/test_boundary.py`
- WHEN `PURE_MODULES` is read
- THEN it contains `"alert_rules.py"`

#### Scenario: alert engine is stdlib-only

- GIVEN `src/alert_rules.py`
- WHEN `test_pure_modules_are_stdlib_only` runs
- THEN no non-stdlib import is found and the test passes

#### Scenario: alert engine imports without Django

- GIVEN an environment where Django is not importable
- WHEN `src/alert_rules.py` is imported
- THEN the import succeeds

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
