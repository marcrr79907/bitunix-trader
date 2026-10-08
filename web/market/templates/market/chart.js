// Market chart: REST history from Django, live candles from BitUnix WS.
// Indicator math lives ONLY server-side (src/indicators.py via
// /market/api/kline) — the browser never recomputes it. Overlays catch up
// via a debounced REST refetch when the forming candle advances a bucket.
(function () {
  "use strict";

  // |safe: json.dumps output rendered into a JS file — autoescape would
  // produce &quot; and break parsing. Content is server-controlled config.
  var SYMBOLS = {{ symbols|safe }};
  var WS_URL = "wss://fapi.bitunix.com/public/";
  var REFETCH_DELAY = 2000;

  // REST interval -> BitUnix WS channel (live-verified 2026-10-08).
  var CHANNELS = {
    "1m": "market_kline_1min",
    "5m": "market_kline_5min",
    "15m": "market_kline_15min",
    "30m": "market_kline_30min",
    "1h": "market_kline_60min",
    "2h": "market_kline_2h",
    "4h": "market_kline_4h",
    "6h": "market_kline_6h",
    "8h": "market_kline_8h",
    "12h": "market_kline_12h",
    "1d": "market_kline_1day",
    "3d": "market_kline_3day",
    "1w": "market_kline_1week",
    "1M": "market_kline_1month",
  };

  var state = { symbol: SYMBOLS[0], interval: "1m" };

  var chart = LightweightCharts.createChart(document.getElementById("chart"), {
    height: 480,
    timeScale: { timeVisible: true },
  });
  var candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries);
  var smaSeries = chart.addSeries(LightweightCharts.LineSeries, { color: "#2962ff" });
  var emaSeries = chart.addSeries(LightweightCharts.LineSeries, { color: "#ff6d00" });

  var ws = null;
  var sub = null; // {symbol, interval} pending or active
  var retry = 0;
  var pingTimer = null;
  var refetchTimer = null;
  var lastBucket = 0;

  var backoff = function () {
    // 1s * 2^n capped at 60s, ±50% jitter (storm guard).
    return Math.min(1000 * Math.pow(2, retry), 60000) * (0.5 + Math.random());
  };

  // ms push timestamp -> interval-start unix seconds (forming-candle bucket).
  var bucket = function (tsMs, sec) {
    return Math.floor(tsMs / 1000 / sec) * sec;
  };

  var intervalSec = function (interval) {
    var unit = interval.slice(-1);
    var n = parseInt(interval, 10);
    if (unit === "m") return n * 60;
    if (unit === "h") return n * 3600;
    if (unit === "d") return n * 86400;
    if (unit === "w") return n * 604800;
    if (interval === "1M") return 2592000; // 30d approx — buckets monthly pushes
    return 60;
  };

  var applyPayload = function (payload) {
    candleSeries.setData(payload.candles);
    smaSeries.setData(payload.overlays.sma20);
    emaSeries.setData(payload.overlays.ema20);
    var rsi = payload.overlays.rsi14;
    var last = rsi.length > 0 ? rsi[rsi.length - 1].value : null;
    document.getElementById("rsi").textContent =
      last === null ? "–" : last.toFixed(2);
    var candles = payload.candles;
    lastBucket =
      candles.length > 0 ? candles[candles.length - 1].time : 0;
  };

  var fetchHistory = function () {
    var url =
      "/market/api/kline?symbol=" + state.symbol + "&interval=" + state.interval;
    fetch(url)
      .then(function (r) {
        if (!r.ok) throw new Error("kline " + r.status);
        return r.json();
      })
      .then(applyPayload)
      .catch(function () {
        /* chart stays as-is; next bucket advance retries */
      });
  };

  var scheduleRefetch = function () {
    // Debounce: once per bucket advance, 2s settle.
    if (refetchTimer) return;
    refetchTimer = setTimeout(function () {
      refetchTimer = null;
      fetchHistory();
    }, REFETCH_DELAY);
  };

  var onPush = function (m) {
    if (!sub || m.symbol !== state.symbol) return;
    var sec = intervalSec(state.interval);
    var t = bucket(m.ts, sec);
    candleSeries.update({
      time: t,
      open: +m.data.o,
      high: +m.data.h,
      low: +m.data.l,
      close: +m.data.c,
    });
    if (lastBucket && t > lastBucket) {
      lastBucket = t;
      scheduleRefetch(); // candle closed -> overlays catch up
    }
  };

  var sendSubscribe = function (next) {
    // ORDERING GUARANTEE: unsubscribe strictly precedes subscribe.
    if (sub && ws) {
      ws.send(
        JSON.stringify({
          op: "unsubscribe",
          args: [{ ch: CHANNELS[sub.interval], symbol: sub.symbol }],
        })
      );
    }
    sub = next;
    ws.send(
      JSON.stringify({
        op: "subscribe",
        args: [{ ch: CHANNELS[sub.interval], symbol: sub.symbol }],
      })
    );
  };

  var startPing = function () {
    if (pingTimer) clearInterval(pingTimer);
    // Server drops idle connections: keepalive ping every 20s.
    pingTimer = setInterval(function () {
      if (ws && ws.readyState === 1) {
        ws.send(JSON.stringify({ op: "ping", ping: Math.floor(Date.now() / 1000) }));
      }
    }, 20000);
  };

  var connect = function () {
    ws = new WebSocket(WS_URL);
    ws.onopen = function () {
      retry = 0;
      startPing();
      if (sub) sendSubscribe(sub); // resubscribe after reopen
    };
    ws.onmessage = function (e) {
      onPush(JSON.parse(e.data));
    };
    ws.onclose = function () {
      if (pingTimer) clearInterval(pingTimer);
      setTimeout(connect, backoff());
      retry += 1;
    };
    ws.onerror = function () {
      ws.close();
    };
  };

  var switchTo = function (symbol, interval) {
    state = { symbol: symbol, interval: interval };
    if (ws && ws.readyState === 1) sendSubscribe({ symbol: symbol, interval: interval });
    else sub = { symbol: symbol, interval: interval }; // pending; sent on open
    fetchHistory(); // REST redraw: setData + overlays
  };

  document.querySelectorAll(".pair").forEach(function (btn) {
    btn.addEventListener("click", function () {
      switchTo(btn.dataset.symbol, state.interval);
    });
  });
  document.getElementById("interval").addEventListener("change", function (e) {
    switchTo(state.symbol, e.target.value);
  });

  // Boot: subscribe + load history, one socket for the page lifetime.
  sub = { symbol: state.symbol, interval: state.interval };
  connect();
  fetchHistory();
})();
