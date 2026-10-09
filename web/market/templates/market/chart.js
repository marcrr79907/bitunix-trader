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

  // Read-only test seam: the dev-only E2E asserts the series grows after a
  // left-edge pagination fetch (R8) via evaluate, instead of image diffs.
  window.marketChart = { chart: chart, candleSeries: candleSeries };

  var ws = null;
  var sub = null; // {symbol, interval} pending or active
  var retry = 0;
  var pingTimer = null;
  var refetchTimer = null;
  var lastBucket = 0;

  // Infinite scroll: module-level arrays so older pages can be prepended.
  // The WS live path updates the series directly, so onPush also mirrors the
  // forming candle into these arrays — otherwise a later setData would clobber
  // it (R8: live update not clobbered).
  var allCandles = [];
  var allSma = [];
  var allEma = [];
  var EDGE = 5; // logical bars from the left edge that trigger a load
  var loadingOlder = false;
  var hasMore = true;
  var oldestTime = 0;

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

  // Last element of an array, or undefined (used to mirror the live bar).
  var last = function (arr) {
    return arr.length ? arr[arr.length - 1] : undefined;
  };

  var applyPayload = function (payload) {
    allCandles = payload.candles.slice();
    allSma = payload.overlays.sma20.slice();
    allEma = payload.overlays.ema20.slice();
    candleSeries.setData(allCandles);
    smaSeries.setData(allSma);
    emaSeries.setData(allEma);
    var rsi = payload.overlays.rsi14;
    var lastRsi = rsi.length > 0 ? rsi[rsi.length - 1].value : null;
    document.getElementById("rsi").textContent =
      lastRsi === null ? "–" : lastRsi.toFixed(2);
    lastBucket =
      allCandles.length > 0 ? allCandles[allCandles.length - 1].time : 0;
    // Deliberate anchor reset on every full refetch (bucket close): the loaded
    // window was replaced, so the next left-edge scroll must fetch from its new
    // floor (R8: bucket-close refetch resets anchors).
    oldestTime = allCandles.length > 0 ? allCandles[0].time : 0;
    hasMore = true;
  };

  // Merge older page into a series, deduped by time (existing newer wins).
  var mergeSeries = function (older, existing) {
    var byTime = {};
    var i;
    for (i = 0; i < existing.length; i++) byTime[existing[i].time] = existing[i];
    for (i = 0; i < older.length; i++) {
      if (!(older[i].time in byTime)) byTime[older[i].time] = older[i];
    }
    return Object.keys(byTime)
      .map(function (t) {
        return byTime[t];
      })
      .sort(function (a, b) {
        return a.time - b.time;
      });
  };

  // Fetch one older page before `oldestTime` and prepend it. Single in-flight
  // guard; empty page flips hasMore off.
  var loadOlder = function () {
    if (loadingOlder || !hasMore || !oldestTime) return;
    loadingOlder = true;
    fetch(
      "/market/api/kline?symbol=" + state.symbol + "&interval=" + state.interval +
        "&limit=200&before=" + oldestTime
    )
      .then(function (r) {
        if (!r.ok) throw new Error("kline " + r.status);
        return r.json();
      })
      .then(function (p) {
        if (!p.candles.length) {
          hasMore = false;
          return;
        }
        var range = chart.timeScale().getVisibleLogicalRange();
        var before = allCandles.length;
        allCandles = mergeSeries(p.candles, allCandles);
        allSma = mergeSeries(p.overlays.sma20, allSma);
        allEma = mergeSeries(p.overlays.ema20, allEma);
        var added = allCandles.length - before;
        if (!added) {
          hasMore = false;
          return;
        }
        candleSeries.setData(allCandles);
        smaSeries.setData(allSma);
        emaSeries.setData(allEma);
        // Shift the visible range by the prepended count to hold the viewport
        // (R8: viewport preserved on prepend).
        if (range) {
          chart.timeScale().setVisibleLogicalRange({
            from: range.from + added,
            to: range.to + added,
          });
        }
        oldestTime = allCandles[0].time;
      })
      .catch(function () {
        /* transient: next edge event retries */
      })
      .finally(function () {
        loadingOlder = false;
      });
  };

  chart.timeScale().subscribeVisibleLogicalRangeChange(function (range) {
    if (range && range.from < EDGE) loadOlder();
  });

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
    var bar = {
      time: t,
      open: +m.data.o,
      high: +m.data.h,
      low: +m.data.l,
      close: +m.data.c,
    };
    candleSeries.update(bar);
    // Mirror the live bar into the array so a later prepend/setData keeps it.
    var tip = last(allCandles);
    if (tip && tip.time === t) allCandles[allCandles.length - 1] = bar;
    else if (!tip || t > tip.time) allCandles.push(bar);
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
