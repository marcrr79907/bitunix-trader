// Market chart — ADAPTER (DOM + Lightweight Charts + WS + REST).
//
// Consistency rule (issue #68): ONE write path per concern.
//   - history load + pagination prepend -> setData (once / with merge)
//   - live stream (WS push)             -> update() only, never setData
//   - candle close                      -> update() the last overlay point
// All timeline/ordering math lives in the pure core (chart-core.js).
(function () {
  "use strict";

  var Core = window.ChartCore;
  var SYMBOLS = {{ symbols|safe }};
  var WS_URL = "wss://fapi.bitunix.com/public/";
  var REFETCH_DELAY = 1500;

  // REST interval -> BitUnix WS channel (live-verified 2026-10-08).
  var CHANNELS = {
    "1m": "market_kline_1min", "5m": "market_kline_5min",
    "15m": "market_kline_15min", "30m": "market_kline_30min",
    "1h": "market_kline_60min", "2h": "market_kline_2h",
    "4h": "market_kline_4h", "6h": "market_kline_6h",
    "8h": "market_kline_8h", "12h": "market_kline_12h",
    "1d": "market_kline_1day", "3d": "market_kline_3day",
    "1w": "market_kline_1week", "1M": "market_kline_1month",
  };

  var state = { symbol: SYMBOLS[0], interval: "1m" };

  var chart = LightweightCharts.createChart(document.getElementById("chart"), {
    height: 480,
    timeScale: { timeVisible: true },
  });
  var candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries);
  var smaSeries = chart.addSeries(LightweightCharts.LineSeries, { color: "#2962ff" });
  var emaSeries = chart.addSeries(LightweightCharts.LineSeries, { color: "#ff6d00" });

  // Read-only test seam (DOM assertions, no image diffs).
  window.marketChart = { chart: chart, candleSeries: candleSeries };

  var ws = null;
  var sub = null; // {symbol, interval} pending or active
  var retry = 0;
  var pingTimer = null;
  var closeTimer = null;
  var lastBucket = 0;

  // In-memory series (single source for the adapter's writes).
  var candles = [];
  var sma = [];
  var ema = [];
  var EDGE = 5;
  var loadingOlder = false;
  var hasMore = true;

  var backoff = function () {
    return Math.min(1000 * Math.pow(2, retry), 60000) * (0.5 + Math.random());
  };

  var setRsi = function (value) {
    document.getElementById("rsi").textContent =
      value === null || value === undefined ? "–" : value.toFixed(2);
  };

  // --- history -----------------------------------------------------------------

  var applyHistory = function (payload) {
    // setData is allowed HERE only: full history reset for a symbol/interval.
    candles = payload.candles.slice();
    sma = payload.overlays.sma20.slice();
    ema = payload.overlays.ema20.slice();
    candleSeries.setData(candles);
    smaSeries.setData(sma);
    emaSeries.setData(ema);
    var rsi = payload.overlays.rsi14;
    setRsi(rsi.length ? rsi[rsi.length - 1].value : null);
    lastBucket = candles.length ? candles[candles.length - 1].time : 0;
    hasMore = true;
  };

  var fetchHistory = function () {
    fetch("/market/api/kline?symbol=" + state.symbol + "&interval=" + state.interval)
      .then(function (r) {
        if (!r.ok) throw new Error("kline " + r.status);
        return r.json();
      })
      .then(applyHistory)
      .catch(function () { /* chart stays; nothing to do */ });
  };

  // --- pagination (setData with merge; viewport preserved) ---------------------

  var loadOlder = function () {
    if (loadingOlder || !hasMore || !candles.length) return;
    loadingOlder = true;
    var before = candles[0].time;
    fetch("/market/api/kline?symbol=" + state.symbol + "&interval=" + state.interval +
          "&limit=200&before=" + before)
      .then(function (r) {
        if (!r.ok) throw new Error("kline " + r.status);
        return r.json();
      })
      .then(function (p) {
        if (!p.candles.length) { hasMore = false; return; }
        var range = chart.timeScale().getVisibleLogicalRange();
        var beforeLen = candles.length;
        candles = Core.mergeCandles(p.candles, candles);
        sma = Core.mergeCandles(p.overlays.sma20, sma);
        ema = Core.mergeCandles(p.overlays.ema20, ema);
        var added = candles.length - beforeLen;
        if (!added) { hasMore = false; return; }
        candleSeries.setData(candles);
        smaSeries.setData(sma);
        emaSeries.setData(ema);
        if (range) {
          chart.timeScale().setVisibleLogicalRange({
            from: range.from + added,
            to: range.to + added,
          });
        }
      })
      .catch(function () { /* transient */ })
      .finally(function () { loadingOlder = false; });
  };

  chart.timeScale().subscribeVisibleLogicalRangeChange(function (range) {
    if (range && range.from < EDGE) loadOlder();
  });

  // --- live stream (update only) ----------------------------------------------

  var onPush = function (m) {
    if (!sub || m.symbol !== state.symbol) return;
    var t = Core.bucketTime(m.ts, state.interval);
    var bar = {
      time: t,
      open: +m.data.o, high: +m.data.h, low: +m.data.l, close: +m.data.c,
    };
    Core.upsertCandle(candles, bar);
    candleSeries.update(bar); // the ONLY live candle write

    if (t > lastBucket) {
      lastBucket = t; // monotonic: a closed candle advanced the bucket
      scheduleCloseOverlay();
    }
  };

  // On candle close, refresh the overlays' last point via update() (no setData).
  var scheduleCloseOverlay = function () {
    if (closeTimer) return;
    closeTimer = setTimeout(function () {
      closeTimer = null;
      fetch("/market/api/kline?symbol=" + state.symbol + "&interval=" + state.interval +
            "&limit=2")
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (p) {
          if (!p) return;
          updateLastOverlay(smaSeries, sma, p.overlays.sma20);
          updateLastOverlay(emaSeries, ema, p.overlays.ema20);
          var rsi = p.overlays.rsi14;
          if (rsi.length) setRsi(rsi[rsi.length - 1].value);
        })
        .catch(function () { /* keep current overlays */ });
    }, REFETCH_DELAY);
  };

  var updateLastOverlay = function (series, arr, points) {
    var pt = Core.lastPoint(points);
    if (!pt) return;
    Core.upsertCandle(arr, pt);
    series.update(pt); // update the last overlay point, never setData mid-stream
  };

  // --- websocket ---------------------------------------------------------------

  var sendSubscribe = function (next) {
    if (sub && ws) {
      ws.send(JSON.stringify({
        op: "unsubscribe", args: [{ ch: CHANNELS[sub.interval], symbol: sub.symbol }],
      }));
    }
    sub = next;
    ws.send(JSON.stringify({
      op: "subscribe", args: [{ ch: CHANNELS[next.interval], symbol: next.symbol }],
    }));
  };

  var startPing = function () {
    if (pingTimer) clearInterval(pingTimer);
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
      if (sub) sendSubscribe(sub);
    };
    ws.onmessage = function (e) { onPush(JSON.parse(e.data)); };
    ws.onclose = function () {
      if (pingTimer) clearInterval(pingTimer);
      setTimeout(connect, backoff());
      retry += 1;
    };
    ws.onerror = function () { ws.close(); };
  };

  // --- controls ----------------------------------------------------------------

  var switchTo = function (symbol, interval) {
    state = { symbol: symbol, interval: interval };
    lastBucket = 0;
    if (ws && ws.readyState === 1) sendSubscribe({ symbol: symbol, interval: interval });
    else sub = { symbol: symbol, interval: interval };
    fetchHistory(); // full reset for the new series
  };

  document.querySelectorAll(".pair").forEach(function (btn) {
    btn.addEventListener("click", function () {
      switchTo(btn.dataset.symbol, state.interval);
    });
  });
  document.getElementById("interval").addEventListener("change", function (e) {
    switchTo(state.symbol, e.target.value);
  });

  sub = { symbol: state.symbol, interval: state.interval };
  connect();
  fetchHistory();
})();
