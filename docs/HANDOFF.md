# Handoff — bitunix-trader (roadmap completo)

**Fecha**: 2026-10-19 · **Branch**: `develop` (== `origin/develop`, árbol limpio; confirmá con `git log --oneline -1`).
> El SHA no se fija a propósito: cualquier commit posterior lo dejaría obsoleto.
**Estado**: no hay issues abiertos, ni PRs abiertos, ni ramas pendientes.

## Qué es este proyecto

Sistema de trading-intelligence **read-only** (NUNCA ejecuta órdenes) sobre la API de futuros de BitUnix.
Backend: Python 3.12 + Django + SQLite; `src/` framework-free (Django nunca lo importa).
Frontend: chart ESM nativo en `web/market/templates/market/`.

**Crítico**: nunca órdenes · `src/` sin Django · sin deps de runtime · CSP estricto (no inline) ·
R14 (A≠B vía `for_user`) · patch coverage 100% · Strict TDD.

## Estado del roadmap

**Olas 0–5 — COMPLETAS.** No queda trabajo planificado.

| Ola | Contenido | Estado |
|---|---|---|
| 0–3 | Fundación web, chart config, indicadores, persistencia | ✅ |
| 4 | F0–F9 chart (split ESM, legend, settings, drawings, toolbar, measure, shortcuts, scales, 8 tools) | ✅ |
| 5 | F10 alerts-on-chart (#123) · F11-A symbol-universe · F11-B layout-templates (#124, #248) | ✅ |
| — | chore: railway.json → IaC (#54) | ✅ |

Especificaciones canónicas: **46** en `openspec/specs/`. Changes archivados en
`openspec/changes/archive/` (nada activo en `openspec/changes/`).

## Últimas tres entregas (para contexto)

| Entrega | PRs | Qué añadió |
|---|---|---|
| F11-A `symbol-universe` | #239–#247 | Catálogo de todo el universo BitUnix, watchlist CRUD, ingesta de pares seguidos con `due_intervals`, búsqueda + combobox |
| F11-B `layout-templates` | #250–#255 | `ChartTemplate` + migración `0017`, CRUD JSON, UI guardar/aplicar/eliminar |
| #54 IaC | #257 | `.railway/railway.ts` (importado del proyecto vivo), `railway.json` eliminado, deploy verificado |
| docs: handoffs | #258 | Consolidados en `docs/HANDOFF.md`; los anteriores a `docs/handoff/archive/` |

Archive reports con el detalle: `openspec/changes/archive/2026-10-19-*/archive-report.md`.

## Cómo retomar

1. `git checkout develop && git pull`
2. Leer este doc + `docs/architecture/chart-modules.md` (capas ESM del chart).
3. No hay tarea siguiente asignada. Si aparece una:
   - Preflight SDD (por defecto **A1** interactivo · **B1** OpenSpec · **C1** ask-on-risk · **D1** 400 líneas).
   - `/sdd-new <change>` → explore → proposal → specs/design → tasks → apply → verify → archive.
4. Memoria Engram: `architecture/chart-frontend-roadmap`,
   `architecture/deployment-railway`, y los session summaries recientes.

## Flujo de trabajo (SIEMPRE seguir)

- **SDD por OpenSpec**: `openspec/changes/<name>/`; al cerrar, `openspec/changes/archive/YYYY-MM-DD-<name>/`.
- **Rama nueva ANTES de editar. Nunca push directo a `develop`** (se cometió un error en la sesión de #54; CI pasó, pero viola el flujo).
- **Cadena de PRs** cuando el forecast supera 400 líneas: tracker → slices → tracker → `develop`.
- **Slices ≤400 líneas, MEDIDAS**:
  `git diff --numstat <base>..<head> -- web src tests | awk '{a+=$1;d+=$2} END {print a+d}'`.
- **Conventional commits**, sin atribución AI.
- **Gates**: `node --test "tests/js/**/*.test.js"` · `.venv/bin/python -m pytest -p no:randomly` ·
  `.venv/bin/ruff check .` + `format --check` · `.venv/bin/python web/manage.py makemigrations --check --dry-run` ·
  `diff-cover cov.xml --compare-branch=origin/develop --fail-under=100`.
- **Calidad antes de mergear**: `sdd-verify` + review adversarial fresco +
  `impeccable detect --json <files>` y auditoría manual si hay UI.
- **Push**: `GIT_TERMINAL_PROMPT=0`.

## Gotchas críticos

1. **`gh pr merge --delete-branch` en una cadena apilada DESTRUYE la cadena.** Borra la rama
   base y GitHub auto-cierra los PRs downstream. Nunca lo uses hasta que toda la cadena lande.
2. **En una cadena apilada el merge va a la base, no al tracker.** El PR final a `develop`
   debe salir de la rama que contiene la cadena completa, verificando
   `git diff <tree-validado>` == 0 líneas.
3. **Techo de 300 líneas por módulo JS**, allowlist VACÍA. `controllers/smc.js` = **300**,
   `main.js` = **297**: sin margen. Cualquier feature del chart va en un controller/core
   nuevo, no en `main.js`.
4. **`window.marketChart` = 8 keys congeladas. `STORE_KEYS` = 11 congeladas.**
5. **#68 single-write-path**: live → `update()`; history/config → `setData()`;
   overlays (drawings, measure, markers) → primitive (`requestUpdate`).
6. **R14**: modelos owned → `for_user` en el request path (unscoped solo en `web/worker.py`).
   Ojo: `for_user(...).create()` **filtra, no inyecta**; pasá el owner explícito:
   `for_user(u).create(user=u, ...)`.
7. **Alertas leen SOLO la DB** (`run_alert_rules` → `_db_rows`). Un par sin ingesta nunca
   dispara. La ingesta cubre `config.SYMBOLS` + watchlists (cap 50, `due_intervals`).
8. **No se backfillea historial** a SQLite (decisión del owner). El chart pide al upstream
   vía `_fetch_window`; el worker persiste solo velas cerradas.
9. **Tests de migración no deben fijar el leaf** (`=="0016"`); usar `>=` para tolerar
   migraciones aditivas posteriores.
10. **Diálogos**: validar en `submit` con `preventDefault()`, NUNCA en `close` — un error
    escrito a un diálogo cerrado es invisible (pasó en F10 y F11-B).
11. **a11y de color**: `--up` sobre superficie clara = 4.36:1 (bajo AA 4.5). Usar `--text` +
    peso o verificar con el helper de `tests/web/test_market_ux.py`.
12. **`git add -A` mete `openspec/`** en commits de código — stagear selectivo.
13. **E2E es dev-only** (`-m e2e`) y tiene flake #149 (SQLite threaded); CI no lo corre.
14. **Los subagentes SDD timeoutean por red** de forma recurrente. Verificá si el archivo
    existe; si no, escribilo inline con evidencia directa. No reintentes más de una vez.
15. **Railway IaC**: `env _="$(which railway)" railway config plan` — el SDK TypeScript lee
    la versión del CLI de `$ _`. Variables unmanaged; `railway config pull`, nunca
    `config migrate` (inventa un servicio fantasma con el nombre del repo).

## Archivos clave

- `docs/architecture/chart-modules.md` — ADR de capas ESM (leer primero).
- `docs/deployment.md` — CI/CD, Railway IaC, modos de deploy.
- `web/market/` — `catalog.py`, `watchlist.py`, `alerts.py`, `templates.py` (APIs JSON),
  `quotes.py` (kline/SMC/validadores).
- `web/market/templates/market/` — cores puros (`*-core.js`), `chart-host.js`, `controllers/*`, `main.js`.
- `web/worker.py` + `web/trading/candles.py` — ingesta, `due_intervals`, alertas.
- `web/trading/models.py` — `Drawing`, `ChartLayout`, `ChartPreference`, `AlertRule`,
  `Watchlist`, `ChartTemplate`.
- `src/smc/`, `src/indicators.py`, `src/metrics.py`, `src/alert_rules.py` — motores puros.
- `.railway/railway.ts` — infraestructura (5 recursos + 2 volúmenes).
- `openspec/specs/` (46) · `openspec/changes/archive/`.

## Historial de handoffs

Los handoffs anteriores están en `docs/handoff/archive/` (16-oct, 18-oct) y en
`openspec/changes/archive/2026-10-19-*/archive-report.md` (F11-A y F11-B).
