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
  var Draw = window.DrawingCore;
  var Smc = window.SmcOverlayCore;
  var SYMBOLS = {{ symbols|safe }};
  var WS_URL = "wss://fapi.bitunix.com/public/";
  var REFETCH_DELAY = 1500;
  var SAVE_DELAY = 500; // debounce for the layout PUT (R5)
  var LAYOUT_URL = "/market/api/layout";
  var DRAWINGS_URL = "/market/api/drawings";
  // Shared history/SMC window (R8): both requests use ``limit=HISTORY_LIMIT`` so
  // the SMC bar indices align with ``candles[-HISTORY_LIMIT:]``.
  var HISTORY_LIMIT = 200;

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
  // SMC family checkboxes (R7); session-only, no persistence.
  var smcToggles = Array.prototype.slice.call(
    document.querySelectorAll(".smc-toggle"),
  );

  // DOM -> {family: bool} for the SMC overlay (absent element => all ON).
  var readSmc = function () {
    var out = {};
    smcToggles.forEach(function (el) { out[el.dataset.family] = el.checked; });
    return out;
  };

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
    smc: readSmc(), // session-only SMC family toggles (R7)
    tool: null, // active drawing tool ("hline"|"trendline"|"fib"|"rect"|"text")
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
  window.marketChart = {
    chart: null,
    candleSeries: null,
    panes: {},
    ready: false,
    drawings: [],
    smc: null, // R9 seam: the fetched SMC payload (deep-equals the response)
    smcCounts: null,
    smcToggles: null, // R7 seam: {family: bool}
  };
  window.marketChart.smcToggles = state.smc;

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

    // Drawings live on the primitive layer (own canvas), so a rebuild must
    // re-attach them — no series setData/update involved (#68 preserved).
    attachAllDrawings();
    // SMC overlay lives on the same primitive layer; re-attach after a rebuild
    // (the previous chart's primitives are gone with chart.remove()).
    attachSmcLayer();
    chart.subscribeClick(onChartClick);

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
    // limit=HISTORY_LIMIT so the history window matches the SMC window (R8).
    fetch(klineUrl("limit=" + HISTORY_LIMIT))
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

  // --- drawings (R6/R7) --------------------------------------------------------
  //
  // Drawings render on a series PRIMITIVE (its own canvas layer) — never via
  // setData/update — so the #68 single-write-path stays intact. Geometry comes
  // from the pure drawing-core.js; this adapter only maps coordinates, fetches,
  // and owns the DOM.

  var drawingListEl = document.getElementById("drawing-list");
  var drawToolButtons = Array.prototype.slice.call(
    document.querySelectorAll(".draw-tool"),
  );
  var cancelToolButton = document.querySelector(".draw-cancel");
  var textDialog = document.getElementById("text-dialog");
  var textDialogInput = document.getElementById("text-dialog-input");

  var currentDrawings = []; // rows loaded for the active (symbol, interval)
  var attached = []; // [{id, prim}] — the primitives currently on the series
  var drawGen = 0; // monotonic guard against a stale drawings fetch
  var pendingAnchor = null; // first click of a two-point drawing

  var enc = encodeURIComponent;

  // Price range so a full-width ray / rect is not clipped on pan/zoom (R6).
  var priceRangeFor = function (row) {
    var prices = [];
    if (typeof row.points.price === "number") prices.push(row.points.price);
    ["p1", "p2"].forEach(function (k) {
      var p = row.points[k];
      if (p && typeof p.price === "number") prices.push(p.price);
    });
    if (!prices.length) return null;
    return {
      priceRange: {
        minValue: Math.min.apply(null, prices),
        maxValue: Math.max.apply(null, prices),
      },
    };
  };

  // Pure canvas draws for one shape. ``map`` = {x(time), y(price)}; null means
  // off-bar / off-scale and the leg is skipped rather than thrown (R6).
  var renderShape = function (ctx, size, row, map) {
    var color = row.style.color || "#2962ff";
    var width = row.style.lineWidth || 1;
    var kind = row.kind;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = width;

    if (kind === "hline") {
      var y = map.y(row.points.price);
      if (y !== null && y !== undefined) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(size.width, y);
        ctx.stroke();
      }
    } else if (kind === "trendline") {
      var t = Draw.trendlinePath(row, map);
      if (t.a && t.b) {
        ctx.beginPath();
        ctx.moveTo(t.a.x, t.a.y);
        ctx.lineTo(t.b.x, t.b.y);
        ctx.stroke();
      }
    } else if (kind === "fib") {
      var f = Draw.fibPath(row, map, row.style.levels);
      ctx.font = "11px sans-serif";
      f.levels.forEach(function (l) {
        if (l.y === null || l.y === undefined) return;
        ctx.beginPath();
        ctx.moveTo(f.x1, l.y);
        ctx.lineTo(f.x2, l.y);
        ctx.stroke();
        ctx.fillText(l.ratio + "  " + l.price, f.x1, l.y - 2);
      });
    } else if (kind === "rect") {
      var r = Draw.rectPath(row, map);
      if (r) {
        if (row.style.fill) {
          ctx.globalAlpha = 0.15;
          ctx.fillRect(r.left, r.top, r.width, r.height);
          ctx.globalAlpha = 1;
        }
        ctx.strokeRect(r.left, r.top, r.width, r.height);
      }
    } else if (kind === "text") {
      var tx = Draw.textPath(row, map);
      if (tx.x !== null && tx.x !== undefined && tx.y !== null && tx.y !== undefined) {
        ctx.font = (row.style.fontSize || 14) + "px sans-serif";
        ctx.fillText(tx.text, tx.x, tx.y);
      }
    }
    ctx.restore();
  };

  // One v5 ISeriesPrimitive per drawing (paneViews + autoscaleInfo + lifecycle).
  var makeDrawingPrimitive = function (row) {
    var ctx = { chart: null, series: null, requestUpdate: null };
    var map = {
      x: function (time) {
        return ctx.chart ? ctx.chart.timeScale().timeToCoordinate(time) : null;
      },
      y: function (price) {
        return ctx.series ? ctx.series.priceToCoordinate(price) : null;
      },
    };
    return {
      attached: function (params) {
        ctx.chart = params.chart;
        ctx.series = params.series;
        ctx.requestUpdate = params.requestUpdate;
      },
      detached: function () {
        ctx.chart = null;
        ctx.series = null;
      },
      paneViews: function () {
        return [
          {
            renderer: function () {
              return {
                draw: function (target) {
                  target.useMediaCoordinateSpace(function (scope) {
                    renderShape(scope.context, scope.mediaSize, row, map);
                  });
                },
              };
            },
          },
        ];
      },
      autoscaleInfo: function () {
        return priceRangeFor(row);
      },
    };
  };

  var renderDrawingList = function () {
    if (!drawingListEl) return;
    drawingListEl.textContent = "";
    currentDrawings.forEach(function (row) {
      var li = document.createElement("li");
      var label = row.kind + " #" + row.id;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "drawing-del";
      btn.dataset.id = row.id;
      btn.textContent = "× " + label;
      btn.addEventListener("click", function () { deleteDrawing(row.id); });
      li.appendChild(btn);
      drawingListEl.appendChild(li);
    });
  };

  // Re-attach every loaded drawing to the CURRENT candleSeries (used after a
  // rebuild and after a load). Always rebuilds the primitive list (R7). Before
  // the first buildChart (candleSeries === null) it only publishes the seam and
  // list; buildChart re-attaches once the series exists.
  var attachAllDrawings = function () {
    attached.forEach(function (p) {
      if (candleSeries) candleSeries.detachPrimitive(p.prim);
    });
    attached = [];
    if (candleSeries) {
      currentDrawings.forEach(function (row) {
        var prim = makeDrawingPrimitive(row);
        candleSeries.attachPrimitive(prim);
        attached.push({ id: row.id, prim: prim });
      });
    }
    window.marketChart.drawings = currentDrawings.slice();
    renderDrawingList();
  };

  var loadDrawings = function (symbol, interval) {
    var mine = ++drawGen;
    var url = DRAWINGS_URL + "?symbol=" + enc(symbol) + "&interval=" + enc(interval);
    return fetch(url)
      .then(function (r) {
        if (!r.ok) throw new Error("drawings " + r.status);
        return r.json();
      })
      .then(function (body) {
        if (mine !== drawGen) return;
        currentDrawings = (body.drawings || []).map(Draw.fromApi).filter(Boolean);
        attachAllDrawings();
      })
      .catch(function () {
        // A failed fetch is non-fatal: the chart renders with no drawings (R7).
        if (mine !== drawGen) return;
        currentDrawings = [];
        attachAllDrawings();
      });
  };

  // Load the active key's drawings then attach them to the CURRENT series
  // (called AFTER buildChart, per R7: layout -> build -> drawings -> attach).
  var refreshDrawings = function () {
    return loadDrawings(state.symbol, state.interval);
  };

  var createDrawing = function (kind, points, style) {
    var body = {
      symbol: state.symbol,
      interval: state.interval,
      kind: kind,
      points: points,
      style: style,
    };
    fetch(DRAWINGS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify(body),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("drawings " + r.status);
        return r.json();
      })
      .then(function (saved) {
        var row = Draw.fromApi({
          id: saved.id,
          kind: saved.kind,
          points: saved.points,
          style: saved.style,
        });
        if (!row) return;
        currentDrawings.push(row);
        attachAllDrawings();
      })
      .catch(function () { /* in-session create failed; nothing to do */ });
  };

  var deleteDrawing = function (id) {
    fetch(DRAWINGS_URL + "/" + id, {
      method: "DELETE",
      headers: { "X-CSRFToken": csrfToken() },
    })
      .then(function () {
        currentDrawings = currentDrawings.filter(function (d) { return d.id !== id; });
        attachAllDrawings();
      })
      .catch(function () { /* keep the row on a failed delete */ });
  };

  var syncToolButtons = function () {
    drawToolButtons.forEach(function (btn) {
      var on = btn.dataset.kind === state.tool;
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      btn.classList.toggle("active", on);
    });
    if (el) el.classList.toggle("drawing", !!state.tool);
  };

  // A chart click in tool mode -> create a shape. hline needs only a price;
  // two-point kinds collect an anchor then a second click; text opens a dialog.
  var onChartClick = function (param) {
    if (!state.tool || !param || !param.point || !candleSeries) return;
    var price = candleSeries.coordinateToPrice(param.point.y);
    if (price === null || price === undefined) return;
    var kind = state.tool;

    if (kind === "hline") {
      createDrawing("hline", { price: price }, Draw.defaultStyle("hline"));
      return;
    }
    if (param.time === undefined || param.time === null) return; // off-bar anchor
    if (kind === "text") {
      pendingAnchor = { time: param.time, price: price };
      if (textDialog) {
        textDialogInput.value = "";
        textDialog.showModal();
      } else {
        createDrawing("text", { time: param.time, price: price, text: "note" },
          Draw.defaultStyle("text"));
        pendingAnchor = null;
      }
      return;
    }
    // trendline | fib | rect: first click sets the anchor, second finalizes.
    if (pendingAnchor === null) {
      pendingAnchor = { time: param.time, price: price };
      return;
    }
    createDrawing(
      kind,
      { p1: pendingAnchor, p2: { time: param.time, price: price } },
      Draw.defaultStyle(kind),
    );
    pendingAnchor = null;
  };

  drawToolButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var kind = btn.dataset.kind;
      state.tool = state.tool === kind ? null : kind;
      pendingAnchor = null;
      syncToolButtons();
    });
  });
  if (cancelToolButton) {
    cancelToolButton.addEventListener("click", function () {
      state.tool = null;
      pendingAnchor = null;
      syncToolButtons();
    });
  }
  if (textDialog) {
    textDialog.addEventListener("close", function () {
      var text = (textDialogInput.value || "").trim();
      if (textDialog.returnValue === "ok" && pendingAnchor && text) {
        createDrawing(
          "text",
          { time: pendingAnchor.time, price: pendingAnchor.price, text: text },
          Draw.defaultStyle("text"),
        );
      }
      pendingAnchor = null;
      textDialogInput.value = "";
    });
  }

  // --- SMC overlay (R6/R7/R8/R9) ----------------------------------------------
  //
  // The overlay renders on a series PRIMITIVE (its own canvas layer) — never via
  // setData/update — so #68 single-write-path stays intact. Geometry comes from
  // the pure smc-overlay-core.js; this adapter only fetches and maps coords.
  // Setups use ONE createSeriesMarkers handle on candleSeries, recreated on
  // every buildChart (A3 draw teardown precedent, no leak).

  var smcBody = null; // raw fetched payload (R9: window.marketChart.smc)
  var smcPrim = null; // the attached ISeriesPrimitive (canvas families)
  var smcMarkers = null; // the createSeriesMarkers handle (setups)
  var smcGen = 0; // monotonic guard against a stale SMC fetch
  var smcCtx = { chart: null, series: null, requestUpdate: null };
  var MAP_WIDTH = 0; // live canvas width, refreshed each draw
  var RAY_WIDTH = 40; // px length of a BOS/CHoCH ray
  var FVG_HALF_WIDTH = 6; // px half-width of an FVG box

  var smcUrl = function () {
    var q = "symbol=" + encodeURIComponent(state.symbol)
      + "&interval=" + encodeURIComponent(state.interval)
      + "&limit=" + HISTORY_LIMIT;
    return "/market/api/smc?" + q;
  };

  // {x(time), y(price)} over the LIVE chart; each may return null off-series.
  var smcMap = function () {
    return {
      x: function (time) {
        return smcCtx.chart ? smcCtx.chart.timeScale().timeToCoordinate(time) : null;
      },
      y: function (price) {
        return smcCtx.series ? smcCtx.series.priceToCoordinate(price) : null;
      },
    };
  };

  // Price range so bands / rays are not clipped on pan/zoom (R6 autoscaleInfo).
  var smcPriceRange = function () {
    var prices = [];
    var push = function (v) { if (typeof v === "number") prices.push(v); };
    var d = Smc.descriptors(smcBody, state.smc);
    d.swings.forEach(function (s) { push(s.price); });
    d.structure.forEach(function (s) { push(s.price); });
    d.order_blocks.forEach(function (o) { push(o.top); push(o.bottom); });
    d.fvg.forEach(function (f) { push(f.top); push(f.bottom); });
    if (d.range) { push(d.range.high); push(d.range.low); }
    if (!prices.length) return null;
    return {
      priceRange: {
        minValue: Math.min.apply(null, prices),
        maxValue: Math.max.apply(null, prices),
      },
    };
  };

  // Pure canvas draw for the enabled canvas families. ``map`` null-guards every
  // coordinate: an off-series leg is skipped, never thrown (R6).
  var renderSmc = function (ctx, map) {
    var d = Smc.descriptors(smcBody, state.smc, map);
    ctx.save();
    ctx.lineWidth = 1;

    // Premium (equilibrium..high) + discount (low..equilibrium) bands + eq line.
    if (d.range) {
      ctx.globalAlpha = 0.08;
      ctx.fillStyle = d.range.color;
      // premium band (equilibrium..high)
      ctx.fillRect(0, d.range.yHigh, MAP_WIDTH, d.range.yEquilibrium - d.range.yHigh);
      // discount band (low..equilibrium)
      ctx.fillRect(0, d.range.yEquilibrium, MAP_WIDTH, d.range.yLow - d.range.yEquilibrium);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = d.range.color;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(0, d.range.yEquilibrium);
      ctx.lineTo(MAP_WIDTH, d.range.yEquilibrium);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Order-block rects (time -> anchor_time, top -> bottom).
    d.order_blocks.forEach(function (ob) {
      var left = Math.min(ob.x1, ob.x2);
      var width = Math.abs(ob.x2 - ob.x1);
      var top = Math.min(ob.yTop, ob.yBottom);
      var height = Math.abs(ob.yBottom - ob.yTop);
      ctx.globalAlpha = 0.15;
      ctx.fillStyle = ob.color;
      ctx.fillRect(left, top, width, height);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = ob.color;
      ctx.strokeRect(left, top, width, height);
    });

    // FVG rects (middle candle span; draw a fixed-width box centred on x).
    d.fvg.forEach(function (g) {
      var top = Math.min(g.yTop, g.yBottom);
      var height = Math.abs(g.yBottom - g.yTop);
      ctx.globalAlpha = 0.15;
      ctx.fillStyle = g.color;
      ctx.fillRect(g.x - FVG_HALF_WIDTH, top, FVG_HALF_WIDTH * 2, height);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = g.color;
      ctx.strokeRect(g.x - FVG_HALF_WIDTH, top, FVG_HALF_WIDTH * 2, height);
    });

    // Swing zig-zag polyline + pivot labels (label-less first swing still draws).
    ctx.strokeStyle = "#9e9e9e";
    ctx.beginPath();
    var started = false;
    d.swings.forEach(function (s) {
      if (!started) { ctx.moveTo(s.x, s.y); started = true; }
      else { ctx.lineTo(s.x, s.y); }
    });
    ctx.stroke();
    ctx.font = "10px sans-serif";
    d.swings.forEach(function (s) {
      ctx.fillStyle = s.color;
      ctx.beginPath();
      ctx.arc(s.x, s.y, 2, 0, Math.PI * 2);
      ctx.fill();
      if (s.label) ctx.fillText(s.label, s.x + 3, s.y - 3);
    });

    // BOS / CHoCH short horizontal ray at price + text.
    ctx.font = "10px sans-serif";
    d.structure.forEach(function (e) {
      ctx.strokeStyle = e.color;
      ctx.fillStyle = e.color;
      ctx.beginPath();
      ctx.moveTo(e.x, e.y);
      ctx.lineTo(Math.min(e.x + RAY_WIDTH, MAP_WIDTH), e.y);
      ctx.stroke();
      ctx.fillText(e.label, e.x + 3, e.y - 3);
    });

    ctx.restore();
  };

  // One v5 ISeriesPrimitive renders ALL enabled canvas families (fewest
  // attach/detach cycles). Rebuilt on every buildChart via attachSmcLayer().
  var makeSmcPrimitive = function () {
    return {
      attached: function (params) {
        smcCtx.chart = params.chart;
        smcCtx.series = params.series;
        smcCtx.requestUpdate = params.requestUpdate;
      },
      detached: function () {
        smcCtx.chart = null;
        smcCtx.series = null;
        smcCtx.requestUpdate = null;
      },
      paneViews: function () {
        return [
          {
            renderer: function () {
              return {
                draw: function (target) {
                  if (!smcBody) return;
                  target.useMediaCoordinateSpace(function (scope) {
                    MAP_WIDTH = scope.mediaSize.width;
                    renderSmc(scope.context, smcMap());
                  });
                },
              };
            },
          },
        ];
      },
      autoscaleInfo: smcPriceRange,
    };
  };

  // (Re)attach the SMC primitive + markers onto the CURRENT candleSeries.
  // Called from buildChart (A3 order: layout -> build -> reattach) and after a
  // fetch. Always tears the previous layer down first (no leak, R6/R7).
  var attachSmcLayer = function () {
    if (smcPrim && candleSeries) candleSeries.detachPrimitive(smcPrim);
    smcPrim = null;
    if (smcMarkers) {
      smcMarkers.detach();
      smcMarkers = null;
    }
    if (!candleSeries || !smcBody) {
      window.marketChart.smc = smcBody;
      return;
    }
    smcPrim = makeSmcPrimitive();
    candleSeries.attachPrimitive(smcPrim);
    smcMarkers = LightweightCharts.createSeriesMarkers(
      candleSeries,
      Smc.setupMarkers(smcBody, state.smc),
    );
    window.marketChart.smc = smcBody;
    window.marketChart.smcCounts = Smc.counts(smcBody, state.smc);
  };

  // Fetch the SMC payload for the ACTIVE key; a failed fetch is non-fatal.
  var loadSmc = function () {
    var mine = ++smcGen;
    return fetch(smcUrl())
      .then(function (r) {
        if (!r.ok) throw new Error("smc " + r.status);
        return r.json();
      })
      .then(function (body) {
        if (mine !== smcGen) return;
        smcBody = body;
        attachSmcLayer();
      })
      .catch(function () {
        if (mine !== smcGen) return;
        smcBody = null;
        attachSmcLayer();
      });
  };

  // Toggle -> re-render from the already-fetched payload; NO refetch (R7).
  var refreshSmc = function () {
    state.smc = readSmc();
    window.marketChart.smcToggles = state.smc;
    if (smcCtx.requestUpdate) smcCtx.requestUpdate();
    if (smcMarkers) smcMarkers.setMarkers(Smc.setupMarkers(smcBody, state.smc));
    window.marketChart.smcCounts = smcBody ? Smc.counts(smcBody, state.smc) : null;
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
    state.tool = null;
    pendingAnchor = null;
    syncToolButtons();
    currentDrawings = []; // clear immediately: shapes never cross keys (R7)
    drawGen++; // invalidate any in-flight drawings fetch for the old key
    // Clear the previous key's SMC layer immediately: primitives/markers never
    // cross keys. smcGen++ invalidates any in-flight SMC fetch (R8).
    smcBody = null;
    smcGen++;
    attachSmcLayer();
    lastBucket = 0;
    if (ws && ws.readyState === 1) sendSubscribe({ symbol: symbol, interval: interval });
    else sub = { symbol: symbol, interval: interval };
    // Load THIS chart's layout first (R4), then build + attach its drawings
    // (R7: layout -> build -> drawings -> attach). A failed drawings fetch is
    // non-fatal (resolves with []) so the chart still renders.
    loadLayout(symbol, interval).then(function () {
      if (mine !== gen) return; // a newer switch won the race
      buildChart();
      return refreshDrawings();
    }).then(function () {
      if (mine !== gen) return;
      return loadSmc(); // SMC for the new key, before history (R8)
    }).then(function () {
      if (mine !== gen) return;
      fetchHistory(); // same (symbol, interval, limit) window as the SMC request
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
  // SMC family toggle -> re-render from the fetched payload; NO refetch (R7).
  smcToggles.forEach(function (t) { t.addEventListener("change", refreshSmc); });

  // Async boot (R4/R7): layout -> build -> connect -> drawings -> history, all
  // sequential so no two API fetches race the session (the E2E live server is
  // single-session). A failed drawings fetch is non-fatal. ``ready`` flips only
  // after the drawings resolve so tests can read the seam deterministically.
  var boot = function () {
    var mine = ++gen;
    loadLayout(state.symbol, state.interval).then(function () {
      if (mine !== gen) return; // a switch raced ahead of boot
      buildChart();
      sub = { symbol: state.symbol, interval: state.interval };
      connect();
      return refreshDrawings();
    }).then(function () {
      if (mine !== gen) return;
      return loadSmc(); // attach the SMC layer before history (R8 ordering)
    }).then(function () {
      if (mine !== gen) return;
      fetchHistory();
      window.marketChart.ready = true;
    });
  };

  boot();
})();
