# Deployment

Git drives deploys. Railway's own GitHub autodeploy is **off**; GitHub Actions
owns build, publish, deploy and verification.

```
push develop        -> staging
push tag vX.Y.Z     -> production
```

## Deploy modes

**Current mode — autodeploy + smoke.** Railway's GitHub autodeploy is ON and
ships every push (staging from `develop`, production from `main`). CD runs the
quality gate and the `/healthz` smoke, but its image-deploy step is a no-op
because no Railway project token is configured yet (creating project tokens
requires a verified Railway account). The pipeline stays green: the smoke
verifies whatever autodeploy shipped.

**Target mode — build-once.** Once `RAILWAY_TOKEN_STAGING` / `RAILWAY_TOKEN_PROD`
exist, the image-deploy step activates automatically and ships the immutable
GHCR image. Then **disable Railway autodeploy** on `web`, `worker`, `scheduler`
or the two deploys race.

## Pipeline

1. **CI (gate)** — `ci.yml`, invoked by CD as a reusable workflow. Lint, tests
   with coverage gate, Django checks, core-isolation, security scans, and the
   L2 Docker build. If any job fails, nothing is published or deployed.
2. **Publish** — on a successful gate, CI builds the image and pushes it to
   GHCR as `ghcr.io/marcr79907/bitunix-trader:<git-sha>`. The deployed artifact
   is exactly the one that passed CI.
3. **Deploy** — CD points each service (`web`, `worker`, `scheduler`) at that
   immutable image tag via the Railway GraphQL API, using a project token
   scoped to one environment.
4. **Smoke (L3)** — CD polls `<URL>/healthz` until it returns 200 (or fails).

A production tag must be strict semver (`vX.Y.Z`) and its commit must be an
ancestor of `origin/main`; staging commits must be on `origin/develop`.

## Required secrets (GitHub -> Settings -> Secrets -> Actions)

| Secret | Value |
|---|---|
| `RAILWAY_PROJECT_ID` | `75c28786-9399-48a4-a952-719af9b08bb5` |
| `RAILWAY_TOKEN_STAGING` | Railway **project token** for the `staging` environment |
| `RAILWAY_TOKEN_PROD` | Railway **project token** for the `production` environment |
| `STAGING_URL` | `https://web-staging-e8bd.up.railway.app` |
| `PROD_URL` | production web URL (set when prod exists) |
| `GHCR_USER` / `GHCR_TOKEN` | only if the GHCR package is **private**: a GitHub PAT with `read:packages` (used as Railway registry credentials) |

The `RAILWAY_TOKEN_*` secrets are **optional today**: without them the CD smoke
still runs and autodeploy ships the commit. Set them to switch to build-once.

Create project tokens in Railway: **Project -> Settings -> Tokens**. A project
token is scoped to a single environment, so a leaked CI token exposes one
environment, not the account.

## One-time Railway setup (per service, per environment)

1. **Disable** GitHub autodeploy on `web`, `worker`, `scheduler`
   (Service -> Settings -> Source -> Disable). Otherwise Railway deploys on
   push *and* CD deploys the image, racing each other.
2. Keep the per-service settings already applied:
   - `web`: start `sh web/start.sh` (runs `migrate` then gunicorn), healthcheck `/healthz`.
   - `worker`: start `python web/worker.py`.
   - `scheduler`: start `python web/scheduler.py`.
   - Variables: `DJANGO_SETTINGS_MODULE=config.settings.prod`, `SECRET_KEY`,
     `CREDENTIALS_FERNET_KEY`, `DATABASE_URL=${{Postgres.DATABASE_URL}}`,
     `REDIS_URL=${{Redis.REDIS_URL}}`, `DEBUG=false`,
     `ALLOWED_HOSTS=.up.railway.app,.railway.internal`.
3. The image source is set by CD on each run; no manual image pinning needed.

## Why `/healthz` bypasses host validation

Railway's internal healthcheck connects to the container's private IP
(`100.64.0.0/10`), so the request `Host` is a bare IP that `ALLOWED_HOSTS`
cannot express, and Django would answer 400. `config.middleware
.HealthProbeHostMiddleware` short-circuits only `/healthz` before host
validation; every other route keeps strict validation.

## Rollback

- **Fast**: Railway Dashboard -> Deployments -> pick the previous successful
  deployment -> Rollback. This restores the image tag and variables.
- **By tag**: re-run CD against an earlier commit's SHA (its image is still in
  GHCR), or set `source.image` to that tag via the API.

Migrations run on every `web` boot. Keep schema changes backward-compatible
(expand/contract) so a rollback to the previous image does not break the DB.

## Candle store volumetry

The worker persists closed OHLC candles for every symbol × interval
(`trading.candles.CANDLE_INTERVALS`: 5m, 15m, 1h, 2h, 4h, 1d, 1w, 1M) into the
global `trading_candle` table. Each cycle fetches only the just-closed candle
(`limit=2`), so growth is bounded and idempotent.

| Interval | bars/sym/yr | ×4 sym/yr | Interval | bars/sym/yr | ×4 sym/yr |
|---|---|---|---|---|---|
| 5m | 105,120 | 420,480 | 1d | 365 | 1,460 |
| 15m | 35,040 | 140,160 | 1w | 52 | 208 |
| 1h | 8,760 | 35,040 | 1M | 12 | 48 |
| 2h | 4,380 | 17,520 | **Total** | **155,919** | **623,676** |
| 4h | 2,190 | 8,760 | | | |

Steady-state growth ≈ **1,709 rows/day** across all intervals and symbols. A
full one-time backfill (`manage.py backfill_candles`) is ≈ **1.87M rows**
(~3y × 4 symbols). No prune is scheduled — retention is tracked separately
(issue #45).

## Known limits (GitHub Free, private repo)

Branch protection, tag protection and environment protection rules require
GitHub Pro for private repos. Security is compensated **inside the pipeline**:
CI gate before publish, semver + branch-ancestry checks before prod deploy,
least-privilege project tokens, and SHA-pinned actions.
