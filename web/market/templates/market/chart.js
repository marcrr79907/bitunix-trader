// Market chart — ADAPTER (DOM + Lightweight Charts + WS + REST).
//
// Consistency rule (issue #68): ONE write path per concern.
//   - history load + pagination prepend -> setData (once / with merge)
//   - live stream (WS push)             -> update() only, never setData
//   - candle close                      -> update() the last point of EVERY
//                                          active overlay/pane series
//   - toggle / indicator change         -> CONFIG change: rebuild + setData
// A toggle is the same class of change as a symbol/interval switch: it refetches
// history and applies it via setData. It is NOT a mid-stream write.
//
// All timeline/ordering math lives in the pure core (chart-core.js); this file
// only renders the server payload {candles, overlays, panes} — never computes
// indicator values (server-side single source).
(function () {
  "use strict";

  var Core = window.ChartCore;
  var SYMBOLS = {{ symbols|safe }};
  var WS_URL = "wss://fapi.bitunix.com/public/";
  var REFETCH_DELAY = 1500;
  var SAVE_DELAY = 500; // debounce for the layout PUT (R5)
  var LAYOUT_URL = "/market/api/layout";

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

  // Static pane registry: token -> placement + series factory. Presentation
  // metadata only; the values come from the server payload. Tokens are the
  // server's param-driven vocabulary: ``sma``/``ema`` carry editable ``_len``
  // (their defaults are 20, so the old ``sma20``/``ema20`` render identically).
  var REGISTRY = {
    sma: { place: "overlay", series: [{ key: "sma", type: "line", color: "#2962ff" }] },
    ema: { place: "overlay", series: [{ key: "ema", type: "line", color: "#ff6d00" }] },
    bollinger: {
      place: "overlay",
      series: [
        { key: "bollinger_upper", type: "line", color: "#7e57c2" },
        { key: "bollinger_middle", type: "line", color: "#7e57c2" },
        { key: "bollinger_lower", type: "line", color: "#7e57c2" },
      ],
    },
    vwap: { place: "overlay", series: [{ key: "vwap", type: "line", color: "#26a69a" }] },
    rsi: {
      place: "pane",
      pane: "rsi",
      series: [{ key: "rsi", type: "line", color: "#ab47bc" }],
    },
    macd: {
      place: "pane",
      pane: "macd",
      series: [
        { key: "macd", type: "line", color: "#2962ff" },
        { key: "signal", type: "line", color: "#ff6d00" },
        { key: "histogram", type: "histogram", color: "#26a69a" },
      ],
    },
    stochastic: {
      place: "pane",
      pane: "stochastic",
      series: [
        { key: "k", type: "line", color: "#2962ff" },
        { key: "d", type: "line", color: "#ff6d00" },
      ],
    },
    atr: { place: "pane", pane: "atr", series: [{ key: "atr", type: "line", color: "#ff6d00" }] },
    volume: {
      place: "pane",
      pane: "volume",
      series: [{ key: "volume", type: "histogram", color: "#26a69a" }],
    },
  };

  // Fixed pane order -> contiguous indices 1..n (index 0 = price scale).
  var PANE_ORDER = ["rsi", "macd", "stochastic", "atr", "volume"];
  var DEFAULT_INDICATORS = ["sma", "ema", "rsi"];

  var toggles = Array.prototype.slice.call(
    document.querySelectorAll(".indicator-toggle"),
  );
  var paramInputs = Array.prototype.slice.call(
    document.querySelectorAll(".indicator-param"),
  );

  // DOM -> {token: {param: number}} for the checked, param-capable overlays.
  var readParams = function () {
    var out = {};
    paramInputs.forEach(function (el) {
      var token = el.dataset.token;
      var n = parseInt(el.value, 10);
      if (!token || isNaN(n) || n < 1) return;
      (out[token] = out[token] || {})[el.dataset.param] = n;
    });
    return out;
  };

  // indicators = ["sma",...]; params = {sma: {sma_len: 20}, ...}. The params
  // only matter for tokens actually selected.
  var buildIndicators = function (indicators, params) {
    return indicators.map(function (token) {
      var entry = { token: token };
      if (params && params[token]) entry.params = params[token];
      return entry;
    });
  };

  var readIndicators = function () {
    if (!toggles.length) return DEFAULT_INDICATORS.slice();
    return toggles
      .filter(function (t) { return t.checked; })
      .map(function (t) { return t.value; });
  };

  // Sync the panel DOM from a layout so a saved set wins over the markup.
  var applyLayout = function (indicators) {
    var tokens = indicators.map(function (i) { return i.token; });
    toggles.forEach(function (t) { t.checked = tokens.indexOf(t.value) !== -1; });
    var params = {};
    indicators.forEach(function (i) {
      if (i.params) params[i.token] = i.params;
    });
    paramInputs.forEach(function (el) {
      var token = el.dataset.token;
      if (params[token] && params[token][el.dataset.param] !== undefined) {
        el.value = params[token][el.dataset.param];
      }
    });
  };

  var state = {
    symbol: SYMBOLS[0],
    interval: "1m",
    indicators: readIndicators(),
    params: readParams(),
  };

  var el = document.getElementById("chart");
  var chart = null;
  var candleSeries = null;
  // Active series descriptors: {token, key, place, pane, series}.
  var activeSeries = [];
  // In-memory series arrays, keyed by dataKey(place,pane,key).
  var seriesData = {};

  // Read-only test seam (DOM assertions, no image diffs). ``ready`` flips true
  // once the async boot has applied the layout and built the chart.
  window.marketChart = { chart: null, candleSeries: null, panes: {}, ready: false };

  var ws = null;
  var sub = null; // {symbol, interval} pending or active
  var retry = 0;
  var pingTimer = null;
  var closeTimer = null;
  var lastBucket = 0;

  var candles = [];
  var EDGE = 5;
  var loadingOlder = false;
  var hasMore = true;

  var dataKey = function (place, pane, key) {
    return place === "overlay" ? "o:" + key : "p:" + pane + ":" + key;
  };

  // Payload -> flat series array for a descriptor (gaps already omitted server-side).
  var seriesFromPayload = function (a, payload) {
    if (a.place === "overlay") {
      return (payload.overlays && payload.overlays[a.key]) || [];
    }
    var pane = payload.panes && payload.panes[a.pane];
    return (pane && pane.series && pane.series[a.key]) || [];
  };

  // RSI text (kept): read the pane's RSI last value, else the legacy overlay.
  var rsiValues = function (payload) {
    if (payload.panes && payload.panes.rsi) return payload.panes.rsi.rsi;
    if (payload.overlays) return payload.overlays.rsi14 || payload.overlays.rsi;
    return null;
  };

  var setRsi = function (values) {
    var last = values && values.length ? values[values.length - 1].value : null;
    document.getElementById("rsi").textContent =
      last === null || last === undefined ? "–" : last.toFixed(2);
  };

  // --- chart build / rebuild (config changes) ---------------------------------

  var buildChart = function () {
    if (chart) chart.remove();
    chart = LightweightCharts.createChart(el, {
      height: 480,
      timeScale: { timeVisible: true },
    });
    candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries);
    activeSeries = [];

    var enabled = state.indicators;
    var isOn = function (token) { return enabled.indexOf(token) !== -1; };
    var addSeries = function (token, paneIndex) {
      REGISTRY[token].series.forEach(function (s) {
        var Ctor =
          s.type === "histogram"
            ? LightweightCharts.HistogramSeries
            : LightweightCharts.LineSeries;
        var series = chart.addSeries(Ctor, { color: s.color }, paneIndex);
        activeSeries.push({
          token: token,
          key: s.key,
          place: REGISTRY[token].place,
          pane: REGISTRY[token].pane,
          series: series,
        });
      });
    };

    Object.keys(REGISTRY).forEach(function (token) {
      if (REGISTRY[token].place === "overlay" && isOn(token)) addSeries(token, 0);
    });
    PANE_ORDER.filter(isOn).forEach(function (token, i) {
      addSeries(token, i + 1);
    });

    // Pane test seam: {paneName: {seriesKey: series}}.
    var panes = {};
    activeSeries.forEach(function (a) {
      if (a.place !== "pane") return;
      (panes[a.pane] = panes[a.pane] || {})[a.key] = a.series;
    });
    window.marketChart.chart = chart;
    window.marketChart.candleSeries = candleSeries;
    window.marketChart.panes = panes;

    chart.timeScale().subscribeVisibleLogicalRangeChange(function (range) {
      if (range && range.from < EDGE) loadOlder();
    });
  };

  var backoff = function () {
    return Math.min(1000 * Math.pow(2, retry), 60000) * (0.5 + Math.random());
  };

  // --- history -----------------------------------------------------------------

  var klineUrl = function (extra) {
    var q = "symbol=" + state.symbol + "&interval=" + state.interval;
    if (state.indicators.length) q += "&indicators=" + state.indicators.join(",");
    // Append editable params so e.g. ``sma_len=50`` reaches the server.
    state.indicators.forEach(function (token) {
      var params = state.params && state.params[token];
      if (!params) return;
      Object.keys(params).forEach(function (key) {
        q += "&" + encodeURIComponent(key) + "=" + encodeURIComponent(params[key]);
      });
    });
    if (extra) q += "&" + extra;
    return "/market/api/kline?" + q;
  };

  var applyHistory = function (payload) {
    // setData is allowed HERE only: full history reset for a config change.
    candles = payload.candles.slice();
    candleSeries.setData(candles);
    activeSeries.forEach(function (a) {
      var arr = seriesFromPayload(a, payload).slice();
      seriesData[dataKey(a.place, a.pane, a.key)] = arr;
      a.series.setData(arr);
    });
    setRsi(rsiValues(payload));
    lastBucket = candles.length ? candles[candles.length - 1].time : 0;
    hasMore = true;
  };

  var fetchHistory = function () {
    fetch(klineUrl())
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
    fetch(klineUrl("limit=200&before=" + before))
      .then(function (r) {
        if (!r.ok) throw new Error("kline " + r.status);
        return r.json();
      })
      .then(function (p) {
        if (!p.candles.length) { hasMore = false; return; }
        var range = chart.timeScale().getVisibleLogicalRange();
        var beforeLen = candles.length;
        candles = Core.mergeCandles(p.candles, candles);
        activeSeries.forEach(function (a) {
          var k = dataKey(a.place, a.pane, a.key);
          seriesData[k] = Core.mergeCandles(seriesFromPayload(a, p), seriesData[k] || []);
          a.series.setData(seriesData[k]);
        });
        var added = candles.length - beforeLen;
        if (!added) { hasMore = false; return; }
        candleSeries.setData(candles);
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
      scheduleCloseRefresh();
    }
  };

  // On candle close, advance the LAST point of every active series via update()
  // (no setData): R6, single-write-path preserved for the live stream.
  var scheduleCloseRefresh = function () {
    if (closeTimer) return;
    closeTimer = setTimeout(function () {
      closeTimer = null;
      fetch(klineUrl("limit=2"))
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (p) {
          if (!p) return;
          activeSeries.forEach(function (a) {
            var pt = Core.lastPoint(seriesFromPayload(a, p));
            if (!pt) return;
            var k = dataKey(a.place, a.pane, a.key);
            Core.upsertCandle(seriesData[k] || (seriesData[k] = []), pt);
            a.series.update(pt); // advance the last point only
          });
          setRsi(rsiValues(p));
        })
        .catch(function () { /* keep current series */ });
    }, REFETCH_DELAY);
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

  // --- layout persistence (R2/R4/R5) ------------------------------------------

  var csrfToken = function () {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  };

  // Fetch and apply the saved layout for ``symbol``/``interval``; fall back to
  // the DOM defaults on any failure (never a blank chart). Resolves either way.
  var loadLayout = function (symbol, interval) {
    var url = LAYOUT_URL + "?symbol=" + encodeURIComponent(symbol)
      + "&interval=" + encodeURIComponent(interval);
    return fetch(url)
      .then(function (r) {
        if (!r.ok) throw new Error("layout " + r.status);
        return r.json();
      })
      .then(function (body) {
        if (!body || !body.indicators) return;
        state.indicators = body.indicators.map(function (i) { return i.token; });
        state.params = readParams(); // panel already synced below
        applyLayout(body.indicators);
        state.params = readParams();
      })
      .catch(function () {
        // Fall back to the DOM defaults already reflected in state.
        state.indicators = readIndicators();
        state.params = readParams();
      });
  };

  // Debounced PUT; the symbol/interval are captured at change time so a racing
  // switch cannot mis-save (R5). A failed save is silent (non-fatal).
  var saveTimer = null;
  var saveLayout = function () {
    if (saveTimer) clearTimeout(saveTimer);
    var symbol = state.symbol;
    var interval = state.interval;
    saveTimer = setTimeout(function () {
      saveTimer = null;
      var payload = {
        symbol: symbol,
        interval: interval,
        indicators: buildIndicators(state.indicators, state.params),
      };
      fetch(LAYOUT_URL, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify(payload),
      }).catch(function () { /* in-session chart unaffected */ });
    }, SAVE_DELAY);
  };

  // --- controls ----------------------------------------------------------------

  // A config change (toggle/param) is legitimate to rebuild (setData path); the
  // live WS stream keeps using update() only.
  var rebuild = function () {
    state.indicators = readIndicators();
    state.params = readParams();
    buildChart();
    fetchHistory();
    saveLayout();
  };

  // Monotonic chart generation: a switch bumps it so a slow boot/switch load
  // for the previous chart cannot clobber the current one.
  var gen = 0;

  var switchTo = function (symbol, interval) {
    var mine = ++gen;
    state.symbol = symbol;
    state.interval = interval;
    lastBucket = 0;
    if (ws && ws.readyState === 1) sendSubscribe({ symbol: symbol, interval: interval });
    else sub = { symbol: symbol, interval: interval };
    // Load THIS chart's layout before history (R4); fallback keeps DOM defaults.
    loadLayout(symbol, interval).then(function () {
      if (mine !== gen) return; // a newer switch won the race
      buildChart();
      fetchHistory();
    });
  };

  document.querySelectorAll(".pair").forEach(function (btn) {
    btn.addEventListener("click", function () {
      switchTo(btn.dataset.symbol, state.interval);
    });
  });
  document.getElementById("interval").addEventListener("change", function (e) {
    switchTo(state.symbol, e.target.value);
  });

  // Toggle = config change -> rebuild the chart and refetch via the history path.
  toggles.forEach(function (t) { t.addEventListener("change", rebuild); });
  paramInputs.forEach(function (el) { el.addEventListener("change", rebuild); });

  // Async boot (R4): layout FIRST, then build + connect + history. On failure
  // the DOM defaults drive the chart — never blank.
  var boot = function () {
    var mine = ++gen;
    loadLayout(state.symbol, state.interval).then(function () {
      if (mine !== gen) return; // a switch raced ahead of boot
      buildChart();
      sub = { symbol: state.symbol, interval: state.interval };
      connect();
      fetchHistory();
      window.marketChart.ready = true;
    });
  };

  boot();
})();
