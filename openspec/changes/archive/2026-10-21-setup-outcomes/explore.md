# Exploration: setup-outcomes (#261)

Verificación de hechos: el proposal ya está aprobado; este documento ancla cada
afirmación de implementación en el código real (branch `develop` @ `23a160c`).

## Current state

El ledger de setups (#260, archived `2026-10-21-setup-ledger`) persiste cada
setup SMC al emitirse: el worker, tras el ciclo de velas y sólo si la ventana
movió, corre `run_setup_capture(symbols)` (`web/worker.py:97-110`) que lee las
200 velas persistidas de cada `(symbol, interval)`, corre la cadena pura
`capture_setups` (`src/smc/signals.py:153`) y hace `bulk_create(
ignore_conflicts=True)` sobre `trading.Setup`. Hoy **nada** resuelve esos
setups contra las velas posteriores: no existe `SetupOutcome`, ni comando
`evaluate_setups`, ni métrica MFE/MAE/`sl_then_tp`. `Trade` guarda fills reales
sin vínculo a setups.

## Verified facts

### 1. Modelo `Setup` (`web/trading/models.py:90-126`)

- Campos exactos: `symbol` Char(32), `interval` Char(8), `anchor_time`
  **BigIntegerField** (candle OPEN en UNIX **segundos**), `direction` Char(8)
  (`"long"`/`"short"` — campo real, no implícito), `entry`/`stop`/
  `take_profit`/`rr` Float, `score` PositiveSmallIntegerField, `atr` Float
  **nullable** (único campo null), `engine_version` Char(16),
  `created_at` auto_now_add.
- `direction` SÍ existe como columna: `SetupRecord.direction` proviene de
  `structure[-1].trend == "up"` → `"long"` (`src/smc/signals.py:68-69`).
- Unique: `(symbol, interval, anchor_time, engine_version)` +
  índice `(symbol, interval, anchor_time)`.
- **`engine_version` en las filas es el stamp `"{SMC_ENGINE_VERSION}:w{window}"`
  — con datos reales hoy: `"1:w200"`**, NO la constante `"1"` pelada
  (`web/trading/setups.py:37`, `engine_stamp()`). Cualquier filtro por
  engine_version en el outcome debe esperar el stamp compuesto.
- En producción el intervalo de captura por defecto es `1h`
  (`DEFAULT_CAPTURE_INTERVALS = ("1h",)`, `web/trading/setups.py:26`).

### 2. Cómo se setean entry/stop/take_profit y qué es R (`src/smc/signals.py:37-130`)

- Direction: `structure[-1].trend` (`"up"`→long, `"down"`→short).
- Zona: order block de la dirección buscada dentro de `OB_LOOKBACK` (10), o FVG
  fallback. Entry = proximal edge; stop = distal edge ∓ `SL_BUFFER` (0.0):
  long → `entry = zone.top`, `stop = zone.bottom - sl_buffer`; short → inverso.
- `entry == stop` → no se emite (guard en `signals.py:96-97`). **R = 0 es
  imposible en filas emitidas por el motor actual**; aun así el proposal pide
  `None` en MFE/MAE para R=0.
- TP: fallback fijo `MIN_RR_TP_R = 3.0` R; si el extremo estructural del dealing
  range da `reward_risk >= MIN_RR = 2.0`, se usa ese. Se emite sólo con
  `rr >= 2.0` y `score >= 3`. Todo setup emitido tiene, por construcción,
  `rr >= MIN_RR (2.0)`.
- Significado de "R": `R = |entry − stop|` (riesgo unitario). Para MFE/MAE en R:
  long → `(high − entry)/R` favorable, `(low − entry)/R` adverso (≤0);
  short → espejo. La semántica de signo NO está en código aún — el proposal
  fija `mae_r ≤ 0`.

### 3. Patrón de comandos (`run(...)` + `out` inyectable)

- `backfill_candles.py`: `run(client, symbols, intervals, start, end, dry_run,
  sleep, out, delay, max_pages) -> int` a nivel de módulo
  (`backfill_candles.py:43`); `Command.handle` sólo parsea args (`--symbol`
  append, `--interval` append, `--start`, `--end`, `--sleep`, `--dry-run`,
  `--max-pages`) y delega pasando `out=self.stdout.write` (:160-189).
- `prune_snapshots.py`: `run(cutoff, batch_size, dry_run, out) -> int`
  (:23); `handle` deriva `cutoff = now(UTC) - timedelta(days=older_than)` y
  delega (:52-58). `--older-than` es `required=True`.
- Ambos imprimen por `out(...)` un resumen final (`"backfill done: N rows"`,
  `"prune done ..."`). Directorio completo de commands: sólo
  `backfill_candles.py` y `prune_snapshots.py` (+ `__init__.py`).

### 4. `web/trading/candles.py`

- `INTERVAL_SECONDS`: `5m:300, 15m:900, 1h:3600, 2h:7200, 4h:14400, 1d:86400,
  1w:604800, 1M:2678400`; `CANDLE_INTERVALS = tuple(INTERVAL_SECONDS)` (:25-36).
- **No existe función de consulta por rango de tiempo.** El helper disponible
  es `market.quotes._db_rows(symbol, interval, before, want) -> list[dict]`
  (`web/market/quotes.py:523`): las `want` filas más nuevas `< before`,
  ascendentes, con keys `time/open/high/low/close/quote_vol`. Para "velas desde
  anchor_time+1" hay que derivar `before`/`want` o escribir un query directo
  `Candle.objects.filter(symbol=, interval=, time__gt=anchor_time)
  .order_by("time")[:horizon]` — la consulta directa es más simple y no depende
  de `market/`.
- `is_closed(candle_time, interval, now)` (:44) es la definición canónica de
  "ventana completa": `now >= candle_time + INTERVAL_SECONDS[interval]`.

### 5. Modelo `Candle` (`web/trading/models.py:57-87`)

- Campos: `symbol` Char(32), `interval` Char(8), `time` **BigIntegerField**,
  `open`/`high`/`low`/`close` Float, `quote_vol` Float nullable.
- `time` = OPEN de la vela en UNIX **segundos** (BigInt, NO ms; el ms sólo se
  usa como cursor en la API de BitUnix dentro de `backfill_candles`).
- Unique `(symbol, interval, time)` + índice idéntico.
- Coincidencia de unidades: `Setup.anchor_time` y `Candle.time` son ambos
  segundos → el walk de resolución compara enteros directamente.

### 6. Tests existentes (patrones a imitar)

- **Comandos Django**: tests llaman al seam `run()` del módulo directamente con
  sinks inyectados (`OutRecorder` clase con `__call__`, `SleepRecorder`) y un
  solo test `call_command(...)` para probar el wiring CLI
  (`tests/web/test_prune_snapshots.py:40-58, 160-170`,
  `tests/web/test_backfill_candles.py:71-80`). Sin `django.test.LiveServer`.
- **Funciones puras SMC**: `tests/test_smc_capture.py` usa fixtures OHLC
  deterministas (zigzag `_zigzag([110,112,114],[100,102,104])`) sin DB, y
  asserts de igualdad de NamedTuples.
- **Modelos**: `tests/web/test_setups_model.py` — contratos de campo vía
  `Setup._meta.get_field(...).get_internal_type()`, AST-guard de migración
  aditiva, leaf `>= "0018"` (NUNCA `==`).
- Guardas que deben quedar verdes sin editar: `test_boundary.py`
  (`PURE_MODULES` incluye `smc/signals.py` — un helper de resolución pura en
  `src/smc/` debe ir ahí o ser stdlib-only), `test_no_order_surface.py`,
  `test_owned_model_guard.py` (SetupOutcome NO debe ir en `OWNED_MODELS`).

### 7. Worker gating — qué significa "ventana completa"

- La captura corre sólo cuando `n_candles > 0` o el ciclo falló
  (`web/worker.py:97`): en régimen, se captura tras cada vela cerrada del
  intervalo. Con `SETUP_CAPTURE_INTERVALS=1h` hay como máximo un setup nuevo
  por símbolo por hora.
- El anchor es la vela que disparó la estructura (`times[setup.index]`), NO la
  vela de la corrida; `capture_setups` puede emitir un setup cuyo anchor es
  hasta 200 barras atrás dentro de la ventana. Esto significa que un setup
  persistido hoy puede tener anchors recientes o antiguos — el evaluador debe
  manejar setups con `anchor_time` ya "viejo" respecto de su `created_at`.
- "Ventana completa" para evaluar: propuesta práctica = el candle store debe
  tener la vela cuyo bucket cerró, es decir existir una vela con
  `time + INTERVAL_SECONDS[interval] <= now` después del anchor (o más simple:
  la vela más nueva persistida ya está cerrada). La definición exacta es
  **decisión pendiente** (ver ambigüedades).

### 8. Cron / deployment (`docs/deployment.md:110-142`)

- Convención: servicios Railway cron nativos, container-decoupled, arrancan,
  corren UN `manage.py` command y terminan. Tabla con `| Service | Cron
  schedule | Start command |`.
- Existentes: `cron-backfill` `0 * * * *` → `python web/manage.py
  backfill_candles --max-pages 3000`; `cron-prune` `0 3 * * *` →
  `python web/manage.py prune_snapshots --older-than 7`.
- Reglas: NO gunicorn, NO migraciones, NO Redis, NO puerto; env prod
  (`DJANGO_SETTINGS_MODULE=config.settings.prod`, `DATABASE_URL`, etc.);
  crearlos manualmente en dashboard; autodeploy disabled.
- `batch-jobs/spec.md` R3 exige el contrato documentado en `docs/`.

### 9. Formato openspec (archive setup-ledger)

- `proposal.md`: Intent / Scope (In/Out) / Capabilities / Approach / Affected
  Areas / Risks / Rollback Plan / Success Criteria (checkboxes) / Changed-lines
  forecast con guard lines explícitas (`Decision needed before apply:`,
  `Chained PRs recommended:`, `400-line budget risk:`).
- `tasks.md`: Strict TDD declarado, fases con numeración jerárquica, tareas
  RED/GREEN con `[S1]`/`[S2]` y `(n)` líneas estimadas, tabla Review Workload
  Forecast, gates de ruff/pytest al final.
- Convención de idioma: prosa en español aceptada en artefactos openspec;
  identificadores en inglés (`openspec/config.yaml` contexto).

## Ambiguities / decisions needed

1. **Semántica de dirección para MFE/MAE**: el proposal fija `mae_r ≤ 0` y R
   como excursión desde entry. Convención propuesta: `mfe_r =
   max((high−entry)/R)` para long, `max((entry−low)/R)` para short; `mae_r` el
   espejo con signo ≤0. Necesita quedar en spec con las 4 fórmulas explícitas.
2. **`ambiguous` intra-vela**: si una MISMA vela toca stop y TP, ¿el walk marca
   `ambiguous` y cuenta como SL pero sigue caminando para `sl_then_tp`? El
   proposal dice sí (conservador, luego continúa). Confirmar orden dentro de la
   vela es imposible con OHLC — `ambiguous` es la única opción honesta.
3. **"Ventana completa" operativa**: el proposal exige no evaluar setups con
   estados transitorios. Opciones: (a) exigir `now >= anchor_time +
   horizon_bars*INTERVAL_SECONDS` (ventana COMPLETA del horizonte — descarta
   `expired` falso, pero deja setups viejos sin evaluar hasta mucho después);
   (b) exigir sólo que la última vela persistida esté cerrada y evaluar hasta
   donde haya velas, marcando `expired` cuando se agota el horizonte con datos
   reales completos. (b) es más fiel al espíritu (los 5 estados existen para
   eso) pero depende de un `now` — el comando tendría que inyectarlo. DECISIÓN
   DEL ORCHESTRATOR/USUARIO.
4. **`resolved_time` y `bars_to_resolution`**: definalas como el candle OPEN
   donde se resolvió (BigInt) y `index_resolución − índice_activación` (no
   desde anchor). El proposal dice "barras desde el anchor" — si el setup
   activa varias barras después, contar desde anchor infla el número. Aclarar.
5. **`sl_then_tp` cuando status es `expired`**: si agotó horizonte sin tocar
   SL, ¿se evalúa igual? Proposal: sólo para `stop_loss`/`ambiguous`; en
   `expired` con SL tocado hay que decidir. Sugerencia: `sl_then_tp` aplica
   siempre que se haya tocado SL (status ∈ {stop_loss, ambiguous} O expired
   con SL tocado), `None` en caso contrario.
6. **`not_triggered` + MFE/MAE**: el criterio de aceptación pide MFE/MAE "igual"
   para `not_triggered` — ¿desde entry aunque nunca se activó? Sí: MFE/MAE se
   calculan sobre todo el camino del horizonte desde `anchor_time+1`
   independientemente de activación (el proposal lo dice: "sobre todo el camino
   desde la activación" para activados; para not_triggered "con MFE/MAE
   calculados igual" — se interpreta: sobre el horizonte completo). Escribir en
   spec la interpretación elegida.
7. **Engine_version del outcome**: el campo `SetupOutcome.engine_version` debe
   copiar el `engine_version` DEL SETUP evaluado (stamp `"1:w200"`), no la
   constante. Al re-evaluar con otro horizonte, el stamp de engine no cambia
   (el criterio cambió, no el motor).
8. **Alcance de `--interval`**: dado que captura por defecto es sólo `1h`,
   ¿el comando itera sobre los intervals de los setups existentes (distinct)
   o sobre un flag? `--interval` como filtro (default: todos los presentes) es
   lo simple.

## Risks

- **Volumetría del walk**: `Candle` en 1h crece ~8.8k filas/símbolo/año. Con
  4 símbolos y 200 barras de horizonte por setup, un cron horario evalúa ~decenas
  de setups nuevos — barato. Pero si se re-evalúa todo el ledger sin `--max-setups`,
  puede escanear miles de velas; `--max-setups` y el índice
  `(symbol, interval, time)` lo acotan.
- **Doctest del proposal sobre R=0**: imposible con el motor actual (guard
  `entry == stop`), pero el código puro igual debe devolver `None`/no-dividir
  por cero (defensa barata).
- **Contaminación del outcome por setups de intervals no capturados**: si
  `SETUP_CAPTURE_INTERVALS` se amplía a 5m, el horizonte de 200 barras 5m es
  ~17h — la semántica de `expired` cambia radicalmente por intervalo. El
  horizonte por defecto fijo (200) tiene sentido distinto por timeframe; el
  flag `--horizon-bars` mitiga.
- **Boundary guards**: un helper de resolución puro debería vivir en `src/smc/`
  (stdlib-only, en `PURE_MODULES`) o en `web/trading/` si lee modelos. La
  versión pura (recibe listas OHLC, devuelve NamedTuple) es la que exige el
  criterio "test unitario puro sin DB" y respeta `test_boundary.py`.
- **Idempotencia con horizonte variable**: `update_or_create` por setup con
  re-evaluación sobrescribe — correcto, pero `evaluated_at` (auto_now) cambia
  en cada re-run; si se quiere historia de evaluaciones, NO: el proposal es 1:1,
  sobrescribe.
- **test_no_order_surface / owned-model guard**: `SetupOutcome` global,
  OneToOne a `Setup`, fuera de `OWNED_MODELS` — mismo contrato que `Setup`.
  No debe heredar `UserOwnedModel`.

## Ready for Proposal

Sí — el proposal #261 ya existe y está aprobado; este documento solo fija los
hechos verificados y deja 8 ambigüedades explícitas para sdd-spec/sdd-design.
