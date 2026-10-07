# deployment-foundation Specification

## Purpose

Environment-driven configuration and a deployable skeleton: settings that read URLs from the environment, a Railway project with `web`/`worker`/`scheduler` services, a `/healthz` probe, and local Docker Compose. New capability — no prior spec.

## Requirements

### Requirement: R5 — Environment-driven settings

Settings MUST be split into `base`, `dev`, and `prod`, and MUST read `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, and `DEBUG` from the environment. `DATABASE_URL` MUST be parsed to the Django database config. No connection target (host, port, password) MAY be hardcoded. `SECRET_KEY` MUST NOT have a usable production default in `prod`.

#### Scenario: Database from DATABASE_URL

- GIVEN `DATABASE_URL` points at a Postgres instance
- WHEN settings load in `prod`
- THEN the database config targets that URL with no hardcoded host

#### Scenario: Redis from REDIS_URL

- GIVEN `REDIS_URL` is set
- WHEN settings load
- THEN the cache/queue config uses that URL

#### Scenario: Missing SECRET_KEY in prod fails closed

- GIVEN `prod` settings with no `SECRET_KEY` in the environment
- WHEN the app boots
- THEN startup fails rather than running with a fallback secret

#### Scenario: Dev defaults are local-only

- GIVEN `dev` settings with no environment overrides
- WHEN the app boots
- THEN it uses local development defaults and `DEBUG` is true

#### Scenario: DEBUG is environment-controlled

- GIVEN `DEBUG` is set to a falsey value
- WHEN settings load
- THEN `DEBUG` is disabled regardless of settings module

### Requirement: R6 — Local Docker Compose

`docker compose up` MUST bring up a Postgres service and a Redis service usable by `dev` settings, with no cloud dependency.

#### Scenario: Compose brings up dependencies

- GIVEN Docker is available and no services are running
- WHEN `docker compose up` runs
- THEN both Postgres and Redis containers are healthy and reachable from the local app

### Requirement: R7 — Deployable skeleton on Railway

A Railway project MUST exist with managed Postgres and Redis and three independently bootable services: `web`, `worker`, and `scheduler`. `web` MUST serve HTTP against managed Postgres; `worker` and `scheduler` MUST boot as stubs without executing business logic.

#### Scenario: Web responds

- GIVEN the deployed `web` service
- WHEN an HTTP request reaches it
- THEN it responds successfully using the managed database

#### Scenario: Worker and scheduler boot

- GIVEN the deployed `worker` and `scheduler` services
- WHEN each starts
- THEN each reaches a running state without performing real synchronization

#### Scenario: Prod uses managed services

- GIVEN the deployed services' environment
- WHEN configuration is inspected
- THEN `DATABASE_URL`/`REDIS_URL` point at the managed instances

### Requirement: R8 — Health endpoint

The `web` service MUST expose `GET /healthz` returning HTTP 200 without requiring authentication, for the deploy healthcheck.

#### Scenario: Healthcheck succeeds

- GIVEN a running `web` service
- WHEN `GET /healthz` is requested anonymously
- THEN the response status is 200

#### Scenario: Health does not leak secrets

- GIVEN a health response
- WHEN the body is inspected
- THEN it contains no credentials or connection strings
