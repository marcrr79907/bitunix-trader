# user-identity Specification

## Purpose

Per-user identity foundation: a custom Django `User` whose unique identifier is email, configured from day 1 to avoid a later data migration. New capability — no prior spec.

## Requirements

### Requirement: R4 — Email-identifier custom User

The project MUST define a custom `User` model with `email` as the unique identifier and authentication field. A `role` attribute MUST exist and default to a non-privileged value. The model MUST be set as `AUTH_USER_MODEL` before the first migration is applied.

#### Scenario: Custom user model is active

- GIVEN the project settings and initial migrations
- WHEN the auth user model is inspected
- THEN it is the project's custom `User`, not the default Django user

#### Scenario: Email is unique and required

- GIVEN an existing user with email `a@example.com`
- WHEN creating another user with the same email
- THEN the database rejects it (unique constraint)

#### Scenario: Role defaults safely

- GIVEN a user created without an explicit role
- WHEN the role is inspected
- THEN it is the default non-privileged role

#### Scenario: Authentication uses email

- GIVEN a user with a known email and password
- WHEN authenticating with email plus password
- THEN authentication succeeds
