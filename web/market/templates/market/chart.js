// Market chart — ESM entry (thin). Django renders this module to inject the
// symbol list below; everything else lives in imported modules.
//
// Consistency rule (issue #68): ONE write path per concern — history/config ->
// setData (controllers/history.js); live stream -> update() only
// (controllers/stream.js); drawings + SMC render on series primitives. All
// timeline/ordering math lives in the pure core (chart-core.js); indicator/SMC
// values are computed server-side (single source). main.js owns orchestration.
import { boot } from "./main.js";

// Django-injected config (R16). Keep the literal symbol list + WS channel map
// so the served entry stays the single source (test_market_ux.py).
export const CONFIG = {
  symbols: {{ symbols|safe }},
  wsUrl: "wss://fapi.bitunix.com/public/",
  historyLimit: 200,
  // REST interval -> BitUnix WS channel (live-verified 2026-10-08).
  channels: {
    "1m": "market_kline_1min", "5m": "market_kline_5min",
    "15m": "market_kline_15min", "30m": "market_kline_30min",
    "1h": "market_kline_60min", "2h": "market_kline_2h",
    "4h": "market_kline_4h", "6h": "market_kline_6h",
    "8h": "market_kline_8h", "12h": "market_kline_12h",
    "1d": "market_kline_1day", "3d": "market_kline_3day",
    "1w": "market_kline_1week", "1M": "market_kline_1month",
  },
  saveDelay: 500, // debounce for the layout PUT (R5)
  urls: {
    kline: "/market/api/kline",
    smc: "/market/api/smc",
    layout: "/market/api/layout",
    preference: "/market/api/preference",
    drawings: "/market/api/drawings",
    alerts: "/market/api/alerts",
    symbols: "/market/api/symbols",
    watchlist: "/market/api/watchlist",
  },
};

boot(CONFIG);
