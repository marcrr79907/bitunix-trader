# bitunix-trader

CLI de solo lectura sobre la API de futuros de [BitUnix](https://www.bitunix.com/api-docs/):
monitor de funding y precios, panel de posiciones, journal propio en SQLite y alertas Telegram.

**Esta iteración NO automatiza órdenes.** No llama a ningún endpoint de crear/cancelar órdenes.

## Requisitos

- Python 3.12+ (verificado en 3.12.3)

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # editar solo si vas a usar paneles privados
```

## Uso

```bash
python -m src.monitor
```

Sin API key corre en modo público: muestra funding y precios de BTC/ETH/SOL/PEPE.
Ctrl+C para salir.

## Configuración

Todo por `.env` (ver `.env.example`). Sin `BITUNIX_API_KEY`, los paneles privados
se desactivan con aviso y el monitor sigue funcionando.

| Variable | Default | Uso |
|---|---|---|
| `BITUNIX_API_KEY` / `BITUNIX_API_SECRET` | vacío | Paneles privados (solo lectura) |
| `BITUNIX_SYMBOLS` | `BTCUSDT,ETHUSDT,SOLUSDT,1000PEPEUSDT` | Pares monitoreados |
| `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` | vacío | Alertas (Etapa 6) |

## Seguridad

- `.env` nunca va al repo (está en `.gitignore`).
- La API key debe ser **sin permiso de retiro** y con **IP whitelist**.
- Etapas 0-3 corren sin clave. Etapa 4-5 requieren clave solo lectura. Etapa 6 requiere token de Telegram.

## Riesgo

Apalancamiento sugerido para arrancar: 5-10x. Riesgo por operación ≤ 1-2% del capital.
(Recomendación, no enforcement.)

## Estado

- [x] Etapa 0 — scaffold
- [ ] Etapa 1 — cliente API + firma
- [ ] Etapa 2 — monitor público
- [ ] Etapa 3 — persistencia SQLite
- [ ] Etapa 4 — panel de posiciones
- [ ] Etapa 5 — journal / métricas
- [ ] Etapa 6 — alertas Telegram
