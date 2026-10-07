# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/).

## [Unreleased]

### Added
- Etapa 6 — alertas por Telegram (pendiente)

[Unreleased]: https://github.com/marcrr79907/bitunix-trader/compare/v0.3.0...HEAD

## [0.3.0] - 2026-10-07

### Added
- Etapa 5: journal de trades y métricas (`src/journal.py`).
  - `sync()` pagina el historial de trades a SQLite (idempotente por `trade_id`).
  - `report()`: win rate, PnL neto por par (realizado − fees), mejor/peor par.

## [0.2.0] - 2026-10-07

### Added
- Etapa 4: panel de posiciones (Liq price, distancia, margin rate, uPnL).
- Etapa 3: persistencia de funding y precios en SQLite.
- Etapa 2: monitor público de funding y precios (BTC/ETH/SOL/1000PEPE).
- Etapa 1: cliente REST de BitUnix con firma SHA256 doble.
- Etapa 0: scaffold del proyecto.

### Fixed
- Normalización de `side` (`BUY`/`SELL` que la API devuelve, no `LONG`/`SHORT`).
- `account()` devuelve un objeto, no una lista como indica la doc.
- Endpoint de funding correcto: `/funding_rate/batch`.
- Símbolo de PEPE: `1000PEPEUSDT`.

### Security
- Solo endpoints de lectura; la API key no puede operar ni retirar.

[0.3.0]: https://github.com/marcrr79907/bitunix-trader/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/marcrr79907/bitunix-trader/releases/tag/v0.2.0
