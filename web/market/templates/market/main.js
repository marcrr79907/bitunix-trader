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
import { createDrawingInteraction } from "./controllers/drawing-interaction.js";
import { createSmc, readSmc } from "./controllers/smc.js";
import { createToolbar } from "./controllers/toolbar.js";
import { createDrawToolbar } from "./controllers/draw-toolbar.js";
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
    smc: readSmc(), // SMC family toggles (persisted user-global, R7)
    scaleMode: "linear", // F8 price-scale option (persistence is Slice 3)
    chartType: "candles", // F8 candle-series Ctor (persistence is Slice 3)
    theme: "system", // resolved theme (light/dark) after boot; pref "system" default
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
  const drawingInteraction = createDrawingInteraction({ store, bus, host, config });
  const smc = createSmc({ store, bus, host, config });
  // Theme (R27/CT2/CT3): the toolbar resolves + writes ``data-theme``, then
  // calls this callback (NO bus event — R20). Live flip is option-only (#68);
  // only a user change persists (boot has its own restore path).
  const toolbar = createToolbar({
    store,
    bus,
    config,
    onTheme: function (p) {
      state.theme = p.resolved;
      host.setTheme(p.resolved);
      savePreference({ theme: p.pref });
    },
  });
  // F5 S2: the vertical drawing toolbar writes ``store.tool`` (the legacy
  // ``.draw-tool`` command); drawings reacts via store.subscribe.
  createDrawToolbar({ store, bus, config });
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
    // The #chart container survives a rebuild; bind() is idempotent (first build
    // binds, later builds are no-ops). Drawings re-attach above.
    drawingInteraction.attach();
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
  let savedChartType = state.chartType;
  function rebuild() {
    const r = indicators.readState();
    state.indicators = r.indicators;
    state.params = r.params;
    buildChart();
    history.fetchHistory();
    indicators.saveLayout();
    // A chart-type change reuses this rebuild command (CS5); persist the type
    // only when it actually changed (CS6 "only the changed field").
    if (state.chartType !== savedChartType) {
      savedChartType = state.chartType;
      savePreference({ chart_type: state.chartType });
    }
  }

  function switchTo(symbol, interval) {
    const mine = ++gen;
    const symbolChanged = symbol !== state.symbol;
    state.symbol = symbol;
    state.interval = interval;
    // Drawings are per SYMBOL (R1/R7): clear + reload ONLY when the symbol
    // changed; an interval-only switch keeps the shapes attached with no
    // refetch (buildChart re-attaches them). SMC is per (symbol, interval), so
    // it always clears. The bumps invalidate in-flight fetches.
    if (symbolChanged) drawings.clearForSwitch();
    smc.clearForSwitch();
    // R14: a symbol switch clears selection with the drawings; an interval-only
    // switch keeps it (the drawings stay attached, #68).
    if (symbolChanged) drawingInteraction.clearForSwitch();
    host.setLastBucket(0);
    stream.subscribe({ symbol: symbol, interval: interval });
    // Load THIS chart's layout first (R4), then build + attach its drawings
    // (R7: layout -> build -> drawings -> attach). A failed drawings fetch is
    // non-fatal (resolves with []) so the chart still renders.
    indicators.loadLayout(symbol, interval).then(function () {
      if (mine !== gen) return; // a newer switch won the race
      buildChart();
      if (!symbolChanged) return; // interval-only: drawings stay, no refetch
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
    if (p.interval !== state.interval) savePreference({ interval: p.interval });
    switchTo(p.symbol, p.interval);
  });
  bus.on("indicator:changed", rebuild);
  // R7: a family toggle is a user change — re-render already happens in the
  // controller; main only persists the full family map (debounced, partial PUT).
  bus.on("smc:toggles", function (p) {
    savePreference({ smc: p.families });
  });
  // F8: a scale change is a host price-scale OPTION only — no rebuild, no
  // fetchHistory (#68 held). The store already holds the new mode. Persist it
  // (debounced, changed field only).
  bus.on("scale:changed", function () {
    host.setScaleMode(state.scaleMode);
    savePreference({ scale_mode: state.scaleMode });
  });

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  // Debounced preference PUT (R10/CS6), mirroring saveLayout. Each call merges
  // only its patch into the pending body, so two quick changes coalesce into one
  // PUT that still carries just the changed fields. A failed save is silent —
  // the in-session chart is unaffected.
  let savePrefTimer = null;
  let savePrefPending = null;
  function savePreference(patch) {
    savePrefPending = Object.assign(savePrefPending || {}, patch);
    if (savePrefTimer) clearTimeout(savePrefTimer);
    savePrefTimer = setTimeout(function () {
      savePrefTimer = null;
      const body = savePrefPending;
      savePrefPending = null;
      fetch(config.urls.preference, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify(body),
      }).catch(function () { /* non-fatal */ });
    }, config.saveDelay);
  }

  // Fetch the saved preference before boot; any failure (or a miss) falls back
  // to the defaults so the chart is never blank and boot is never blocked
  // (R10/CS6).
  function loadPreference() {
    return fetch(config.urls.preference)
      .then(function (r) {
        if (!r.ok) throw new Error("preference " + r.status);
        return r.json();
      })
      .then(function (body) {
        return {
          interval: (body && body.interval) || "1m",
          scaleMode: (body && body.scale_mode) || "linear",
          chartType: (body && body.chart_type) || "candles",
          theme: (body && body.theme) || "system",
          smc: (body && body.smc) || {}, // R7: persisted family toggles
        };
      })
      .catch(function () {
        return {
          interval: "1m",
          scaleMode: "linear",
          chartType: "candles",
          theme: "system",
          smc: {},
        };
      });
  }

  // Async boot (R4/R7/R10): preference -> layout -> build -> connect ->
  // drawings -> history, all sequential so no two API fetches race the session
  // (the E2E live server is single-session). The saved interval is applied
  // BEFORE the first build; a failed/empty fetch falls back to "1m". A failed
  // drawings fetch is non-fatal. ``ready`` flips only after the drawings
  // resolve so tests can read the seam deterministically.
  function start() {
    loadPreference().then(function (pref) {
      if (gen !== 0) return; // a switch raced ahead of boot — it owns the chart
      const mine = ++gen;
      // Apply the restored scale/type BEFORE the first build (CS6): the host
      // picks the series Ctor and price-scale mode from state.
      state.scaleMode = pref.scaleMode;
      state.chartType = pref.chartType;
      savedChartType = pref.chartType;
      state.interval = pref.interval;
      // Apply the restored theme BEFORE the first build (CT6): setTheme writes
      // ``data-theme`` (shell tokens) and returns the RESOLVED value that makes
      // ``build()`` born themed.
      state.theme = toolbar.setTheme(pref.theme);
      toolbar.setInterval(pref.interval);
      toolbar.setScaleMode(pref.scaleMode);
      toolbar.setChartType(pref.chartType);
      // R7: apply the persisted SMC family toggles to the checkboxes BEFORE the
      // first SMC render (no emit — restore is not a user change).
      smc.applyToggles(pref.smc);
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
