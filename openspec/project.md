# Project — bitunix-trader

## Overview

Read-only CLI over the [BitUnix](https://www.bitunix.com/api-docs/) futures API:
funding/price monitor, positions panel, a local SQLite trade journal, and Telegram
alerts. **This iteration does not automate orders** — it never calls create/cancel
order endpoints.

Current direction: extend the CLI into a **multi-user Django web dashboard**.

## Stack

| Area | Choice |
|---|---|
| Language | Python 3.12 (verified 3.12.3) |
| HTTP client | `requests` |
| Terminal UI | `rich` |
| Persistence | SQLite (stdlib `sqlite3`) |
| Tests | pytest 9 (`testpaths = ["tests"]`, `addopts = "-q"`) |
| Lint / format | ruff (`line-length = 88`, rules `E/F/I/UP/B`) |
| CI | GitHub Actions (`.github/workflows/ci.yml`) |
| Planned | Django (multi-user web dashboard) |

## Repository layout

```
src/            # flat modules: client, config, db, monitor, journal, alerts, indicators, metrics
tests/          # pytest suites, one file per module
openspec/       # SDD artifacts (this directory)
.github/        # CI, PR/issue templates, dependabot, CODEOWNERS
```

## Conventions

- **Language**: Spanish for user-facing CLI strings; English for code, comments,
  identifiers, and docs.
- **Commits**: conventional commits.
- **Changelog**: Keep a Changelog format (`CHANGELOG.md`), semver tags.
- **Lint gate**: `ruff check .` and `ruff format --check .` must pass (enforced in CI).
- **Tests**: `python -m pytest` must pass (enforced in CI).
- **Secrets**: `.env` is gitignored. API key must be read-only with IP whitelist.

## SDD

- Artifact store: **openspec** (files under `openspec/`).
- Strict TDD: **enabled**.
- Test command: `python -m pytest`.
