# Delta for core-domain-boundary

## MODIFIED Requirements

### Requirement: R11 — smc package joins the framework-free inventory

The `src/smc/` package (`__init__.py`, `config.py`, `swings.py`, `structure.py`,
`zones.py`, `range.py`, `signals.py`) MUST be subject to the same one-way boundary
as the rest of the core: it MUST import stdlib only, MUST NOT import Django or any
web framework, and MUST be importable without Django. Its six compute modules
(`config.py`, `swings.py`, `structure.py`, `zones.py`, `range.py`, `signals.py`),
plus the pure alert engine `alert_rules.py`, MUST be registered in `PURE_MODULES`
in `tests/test_boundary.py` so the stdlib-only check is not blind to them.
(Previously: registered the six smc compute modules only.)

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
