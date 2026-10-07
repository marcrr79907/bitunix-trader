# invite-access Specification

## Purpose

Invitation-only account lifecycle for the web dashboard: admins create invites, invitees sign up via a token link, and users authenticate with Django-native login/logout/password-reset. New capability — no prior spec.

## Requirements

### Requirement: R1 — Invite creation

An authorized actor MUST be able to create an `Invite` with a unique email, a securely generated single-use token, a role, and an expiry timestamp. `used_at` MUST be null at creation.

#### Scenario: Create a valid invite

- GIVEN an authenticated admin
- WHEN they create an invite for `new@example.com` with role `member` and a future expiry
- THEN an `Invite` row exists with a non-empty unique token, `used_at` null, and `expires_at` in the future

#### Scenario: Duplicate active invite rejected

- GIVEN an active unused invite for `new@example.com`
- WHEN an admin creates another invite for the same email
- THEN the system rejects it (validation error) and no second row is created

#### Scenario: Past expiry rejected at creation

- GIVEN an admin providing `expires_at` in the past
- WHEN they submit the invite
- THEN the system rejects it (validation error)

### Requirement: R2 — Token-gated signup

Signup MUST be reachable only through a valid, unused, unexpired invite token. On success the account MUST be created with the invite's email and role, and the invite MUST be marked single-use by setting `used_at`.

#### Scenario: Signup with valid token

- GIVEN a valid unused, unexpired invite token
- WHEN a visitor submits a password for that token
- THEN a `User` is created with the invite's email and role
- AND that invite's `used_at` is set

#### Scenario: Expired token rejected

- GIVEN an invite whose `expires_at` is in the past
- WHEN a visitor submits the signup form
- THEN no `User` is created and the request is rejected

#### Scenario: Reused token rejected

- GIVEN an invite with `used_at` already set
- WHEN a visitor submits the same token
- THEN no `User` is created and the request is rejected

#### Scenario: Unknown token rejected

- GIVEN a token that matches no `Invite`
- WHEN the signup page is requested
- THEN the system returns a rejection and exposes no account form

#### Scenario: Open self-registration absent

- GIVEN no invite token
- WHEN a visitor looks for a public registration route
- THEN none exists (signup requires a token)

### Requirement: R3 — Login, logout, password reset

Authenticated sessions MUST use Django's built-in auth views. Login MUST accept the email identifier. Logout MUST end the session. Password reset MUST deliver a tokenized reset flow.

#### Scenario: Login with email

- GIVEN an existing active user
- WHEN they submit correct email and password to login
- THEN they receive an authenticated session

#### Scenario: Logout ends session

- GIVEN an authenticated user
- WHEN they request logout
- THEN the session is invalidated and protected pages redirect to login

#### Scenario: Password reset round-trip

- GIVEN an existing user who requests a reset for their email
- WHEN they follow the delivered token and set a new password
- THEN the new password authenticates and the old one no longer does

#### Scenario: Wrong credentials rejected

- GIVEN an existing user
- WHEN they submit an incorrect password
- THEN no session is created
