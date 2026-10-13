// main.js — ALL chart orchestration + boot()/switchTo().
//
// Owns the store/bus/host + the controller instances and the async sequencing:
// layout -> build (reattach drawings/SMC) -> drawings fetch -> SMC fetch ->
// history, with ``ready`` after history. The ``gen`` race guard invalidates a
// slow boot/switch for a previous key. Controllers never import main; commands
// travel the bus (config:changed / indicator:changed).
//
// R18 seam: ``window.marketChart`` (8 keys) + ``window.SmcOverlayCore``.
import * as Smc from "./smc-overlay-core.js";
import { createStore } from "./chart-store.js";
import { createBus } from "./chart-bus.js";
import { createHost } from "./chart-host.js";
import {
  createIndicators,
  readIndicators,
  readParams,
} from "./controllers/indicators.js";
import { createHistory } from "./controllers/history.js";
import { createStream } from "./controllers/stream.js";
import { createDrawings } from "./controllers/drawings.js";
import { createSmc, readSmc } from "./controllers/smc.js";
import { createToolbar } from "./controllers/toolbar.js";
import { createLegend } from "./controllers/legend.js";

export function boot(config) {
  // Sanctioned test seam (R18): the E2E reads window.SmcOverlayCore.setupMarkers.
  window.SmcOverlayCore = Smc;

  // Observable UI/config state (chart-store.js). Candle data never enters the
  // store (#68) — it lives in the host.
  const store = createStore({
    symbol: config.symbols[0],
    interval: "1m",
    indicators: readIndicators(),
    params: readParams(),
    styles: {}, // per-token presentation style (F2.4; loaded from layout, never in params)
    smc: readSmc(), // session-only SMC family toggles (R7)
    tool: null, // active drawing tool ("hline"|"trendline"|"fib"|"rect"|"text")
  });
  const state = store.get();
  const bus = createBus();
  const host = createHost();

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

  const indicators = createIndicators({ store, bus, config });
  const history = createHistory({ store, bus, host, config });
  const stream = createStream({ store, bus, host, config });
  const drawings = createDrawings({ store, bus, host, config });
  const smc = createSmc({ store, bus, host, config });
  const toolbar = createToolbar({ store, bus, config });
  // Read-only legend overlay: re-subscribes on chart:built internally, so no
  // buildChart change is needed (design: keeps main wiring to +1 line).
  createLegend({ store, bus, host, config });

  // Monotonic chart generation: a switch bumps it so a slow boot/switch load
  // for the previous chart cannot clobber the current one.
  let gen = 0;

  // chart-host.js is the ONLY LightweightCharts construction surface; it writes
  // the {chart,candleSeries,panes} seam in place.
  function buildChart() {
    const built = host.build(state);
    // Drawings + SMC live on the primitive layer (own canvas), so a rebuild must
    // re-attach them — no series setData/update involved (#68 preserved).
    drawings.attachAllDrawings();
    smc.attachSmcLayer();
    host.subscribeClick(drawings.onChartClick);
    host.subscribeVisibleRange(history.onVisibleRange);
    bus.emit("chart:built", {
      chart: built.chart,
      candleSeries: built.candleSeries,
      panes: host.getPanes(),
    });
  }

  // A config change (toggle/param) is legitimate to rebuild (setData path); the
  // live WS stream keeps using update() only.
  function rebuild() {
    const r = indicators.readState();
    state.indicators = r.indicators;
    state.params = r.params;
    buildChart();
    history.fetchHistory();
    indicators.saveLayout();
  }

  function switchTo(symbol, interval) {
    const mine = ++gen;
    state.symbol = symbol;
    state.interval = interval;
    // Clear the previous key's drawings + SMC immediately: shapes/primitives/
    // markers never cross keys (R7/R8). The bumps invalidate in-flight fetches.
    drawings.clearForSwitch();
    smc.clearForSwitch();
    host.setLastBucket(0);
    stream.subscribe({ symbol: symbol, interval: interval });
    // Load THIS chart's layout first (R4), then build + attach its drawings
    // (R7: layout -> build -> drawings -> attach). A failed drawings fetch is
    // non-fatal (resolves with []) so the chart still renders.
    indicators.loadLayout(symbol, interval).then(function () {
      if (mine !== gen) return; // a newer switch won the race
      buildChart();
      return drawings.refreshDrawings();
    }).then(function () {
      if (mine !== gen) return;
      return smc.loadSmc(); // SMC for the new key, before history (R8)
    }).then(function () {
      if (mine !== gen) return;
      history.fetchHistory(); // same (symbol, interval, limit) window as SMC
    });
  }

  // Commands travel the bus (chart-bus.js) so main owns orchestration: the
  // config:changed command switches, indicator:changed rebuilds (config change
  // -> setData path; the live WS stream keeps update() only).
  bus.on("config:changed", function (p) {
    // Persist a genuine interval change only (mirrors saveLayout); a pair
    // switch keeps the same interval and must not PUT.
    if (p.interval !== state.interval) savePreference(p.interval);
    switchTo(p.symbol, p.interval);
  });
  bus.on("indicator:changed", rebuild);

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  // Debounced preference PUT on interval change (R10), mirroring saveLayout.
  // A failed save is silent — the in-session chart is unaffected.
  let savePrefTimer = null;
  function savePreference(interval) {
    if (savePrefTimer) clearTimeout(savePrefTimer);
    savePrefTimer = setTimeout(function () {
      savePrefTimer = null;
      fetch(config.urls.preference, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify({ interval: interval }),
      }).catch(function () { /* non-fatal */ });
    }, config.saveDelay);
  }

  // Fetch the saved interval before boot; any failure (or a miss) falls back to
  // "1m" so the chart is never blank and boot is never blocked (R10).
  function loadPreference() {
    return fetch(config.urls.preference)
      .then(function (r) {
        if (!r.ok) throw new Error("preference " + r.status);
        return r.json();
      })
      .then(function (body) { return (body && body.interval) || "1m"; })
      .catch(function () { return "1m"; });
  }

  // Async boot (R4/R7/R10): preference -> layout -> build -> connect ->
  // drawings -> history, all sequential so no two API fetches race the session
  // (the E2E live server is single-session). The saved interval is applied
  // BEFORE the first build; a failed/empty fetch falls back to "1m". A failed
  // drawings fetch is non-fatal. ``ready`` flips only after the drawings
  // resolve so tests can read the seam deterministically.
  function start() {
    loadPreference().then(function (interval) {
      if (gen !== 0) return; // a switch raced ahead of boot — it owns the chart
      const mine = ++gen;
      state.interval = interval;
      toolbar.setInterval(interval);
      return indicators.loadLayout(state.symbol, state.interval).then(function () {
        if (mine !== gen) return; // a switch raced ahead of boot
        buildChart();
        stream.connect({ symbol: state.symbol, interval: state.interval });
        return drawings.refreshDrawings();
      }).then(function () {
        if (mine !== gen) return;
        return smc.loadSmc(); // attach the SMC layer before history (R8 ordering)
      }).then(function () {
        if (mine !== gen) return;
        history.fetchHistory();
        window.marketChart.ready = true;
        bus.emit("ready");
      });
    });
  }

  start();
}
