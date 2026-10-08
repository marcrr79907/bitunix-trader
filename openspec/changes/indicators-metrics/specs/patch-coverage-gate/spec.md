# patch-coverage-gate Specification

## Purpose

CI enforcement that no changed line ships untested. A pull request MUST fail when any line added or modified in the diff is uncovered, while the pre-existing web coverage gate stays intact. New capability — no prior spec.

## Requirements

### Requirement: R1 — Patch coverage gate fails on uncovered changed lines

The CI workflow MUST run `diff-cover` against a coverage XML report and MUST fail when patch coverage is below 100%. The gate MUST be scoped to changed lines only, comparing the branch merge-base against `origin/develop` with `--fail-under=100`.

#### Scenario: Uncovered changed line fails CI
- GIVEN a branch that adds a line with no covering test
- WHEN the patch-coverage step runs
- THEN `diff-cover ... --fail-under=100` reports less than 100% and the job fails

#### Scenario: Fully covered patch passes
- GIVEN a branch whose every changed line is covered by tests
- WHEN the patch-coverage step runs
- THEN `diff-cover ... --fail-under=100` passes

#### Scenario: Compare base is origin/develop
- GIVEN a pull request targeting `develop`
- WHEN `diff-cover` is invoked
- THEN its comparison base is `origin/develop`

### Requirement: R2 — Full history available for merge-base

The CI checkout MUST use `fetch-depth: 0` so the merge-base with `origin/develop` can be resolved. A shallow clone that cannot compute the merge-base MUST be treated as a failure, not a silent skip.

#### Scenario: Deep clone enables merge-base
- GIVEN the CI checkout step
- WHEN it runs
- THEN the checkout uses `fetch-depth: 0` and the merge-base resolves

### Requirement: R3 — Coverage report spans web and src

The coverage configuration MUST measure both `web` and `src`. The global report-level `fail_under` under `[tool.coverage.report]` MUST be removed so the per-scope gates (patch gate + web gate) are authoritative instead of a global floor.

#### Scenario: Source includes both trees
- GIVEN the coverage configuration
- WHEN coverage runs
- THEN measured source includes `web` and `src`

#### Scenario: No global fail_under
- GIVEN `[tool.coverage.report]`
- WHEN inspected
- THEN it contains no `fail_under` key

### Requirement: R4 — Preserved web coverage gate

The existing web coverage step MUST remain: `coverage report --include="web/*" --fail-under=85` MUST still run and still fail below 85% web coverage.

#### Scenario: Web gate preserved
- GIVEN the CI workflow
- WHEN a change lowers `web/*` coverage below 85%
- THEN the web gate step fails

#### Scenario: Web gate passes unchanged
- GIVEN `web/*` coverage at or above 85%
- WHEN the web gate runs
- THEN it passes

### Requirement: R5 — Development-only tooling

`diff-cover` MUST be declared as a development-only dependency and MUST NOT enter the runtime dependency set.

#### Scenario: Dev-only dependency
- GIVEN `requirements-dev.txt`
- WHEN the diff-coverage tooling is inspected
- THEN `diff-cover` is present there and absent from runtime requirements

#### Scenario: No new runtime dependency
- GIVEN the runtime requirements
- WHEN compared before and after this change
- THEN no new runtime package was added
