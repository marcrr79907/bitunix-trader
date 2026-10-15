// chart-host.js — the ONLY LightweightCharts construction surface.
//
// Encapsulates LightweightCharts 5.2.0 (createChart / addSeries / panes) and
// owns the chart/panes/scale lifecycle. The candle channel (#68 single-write-
// path: history/config -> setData, live -> update()) lives in the delegated
// chart-host-candles.js module. UI/config state lives in chart-store.js; the
// host never reads the store.
//
// Static presentation registry (token -> placement + series factory). Values
// come from the server payload; the host only maps them onto chart series.
// The candle channel (series, raw array, HA state) lives in chart-host-candles.
import * as Types from "./chart-types-core.js";
import { createCandles } from "./chart-host-candles.js";
import { optionsFor, prefersDark, resolve as resolveTheme } from "./theme-core.js";

export const REGISTRY = {
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
export const PANE_ORDER = ["rsi", "macd", "stochastic", "atr", "volume"];

// scaleMode -> LightweightCharts.PriceScaleMode member. The SYMBOL is read at
// call time (never a magic number); unknown -> Normal (CS2 fallback).
const SCALE_MODES = {
  linear: "Normal",
  log: "Logarithmic",
  percentage: "Percentage",
};

export function createHost() {
  let chart = null;
  let candleSeries = null;
  let activeSeries = [];
  let panes = {};
  // The candle channel (series, raw array, HA state) is owned by the delegated
  // module; ``candles`` holds that module handle.
  let candles = null;
  // F8: the live scale mode (applied in build; scale is an applyOptions option,
  // never a data write).
  let scaleMode = "linear";
  // Overlay/pane series arrays keyed by dataKey() — the indicator series data
  // (NOT candles). Shared by the history (setData) and stream (last-point
  // update) paths so the #68 single-write-path keeps one bookkeeping array.
  let seriesData = {};
  // Last live bucket (UNIX seconds) already applied by the stream; advanced on
  // history load + live push so a new-bucket push can be detected.
  let lastBucket = 0;

  // --- payload <-> series mapping ---------------------------------------------

  function dataKey(place, pane, key) {
    return place === "overlay" ? "o:" + key : "p:" + pane + ":" + key;
  }

  // Payload -> flat series array for a descriptor (gaps already omitted server-side).
  function seriesFromPayload(a, payload) {
    if (a.place === "overlay") {
      return (payload.overlays && payload.overlays[a.key]) || [];
    }
    const pane = payload.panes && payload.panes[a.pane];
    return (pane && pane.series && pane.series[a.key]) || [];
  }

  // RSI text (kept): read the pane's RSI last value, else the legacy overlay.
  function rsiValues(payload) {
    if (payload.panes && payload.panes.rsi) return payload.panes.rsi.rsi;
    if (payload.overlays) return payload.overlays.rsi14 || payload.overlays.rsi;
    return null;
  }

  function setRsi(values) {
    const last = values && values.length ? values[values.length - 1].value : null;
    document.getElementById("rsi").textContent =
      last === null || last === undefined ? "–" : last.toFixed(2);
  }

  // --- construction -----------------------------------------------------------

  // One series per registry entry. ``style`` (F2.5) is presentation-only:
  // color/lineWidth at construction, precision as the series priceFormat.
  // Absent style → the registry default color, width 1 (no priceFormat forced).
  function addSeries(token, paneIndex, style) {
    const s = style || {};
    REGISTRY[token].series.forEach(function (entry) {
      const Ctor =
        entry.type === "histogram"
          ? LightweightCharts.HistogramSeries
          : LightweightCharts.LineSeries;
      const series = chart.addSeries(
        Ctor,
        { color: s.color || entry.color, lineWidth: s.lineWidth || 1 },
        paneIndex,
      );
      if (typeof s.precision === "number") {
        // ``Number("1e-" + n)`` is exactly representable; ``Math.pow(10, -n)``
        // is not (V8-version-dependent: 10**-5 -> 0.000009999999999999999 on
        // some Node builds), which would break the priceFormat minMove.
        series.applyOptions({
          priceFormat: {
            precision: s.precision,
            minMove: Number("1e-" + s.precision),
          },
        });
      }
      activeSeries.push({
        token: token,
        key: entry.key,
        place: REGISTRY[token].place,
        pane: REGISTRY[token].pane,
        series: series,
      });
    });
  }

  // (Re)build the chart for the given config state. Returns the live handles;
  // writes the frozen seam (window.marketChart.{chart,candleSeries,panes}).
  function build(state) {
    const el = document.getElementById("chart");
    if (chart) chart.remove();
    // Born themed (theme-core owns the tables; R14 size). state.theme is RESOLVED.
    const theme = optionsFor(state.theme ?? resolveTheme("system", prefersDark()));
    chart = LightweightCharts.createChart(el, {
      ...theme,
      autoSize: true,
      timeScale: { ...theme.timeScale, timeVisible: true },
    });
    const type = Types.isValidType(state.chartType) ? state.chartType : "candles";
    scaleMode = Types.isValidScale(state.scaleMode) ? state.scaleMode : "linear";
    candles = createCandles(chart, type);
    candleSeries = candles.getCandleSeries();
    // F8: re-apply the scale after createChart (a fresh chart has the default
    // scale); an applyOptions option, never a data write (#68).
    applyScale();
    activeSeries = [];

    const enabled = state.indicators;
    const styles = state.styles || {};
    const isOn = function (token) { return enabled.indexOf(token) !== -1; };

    Object.keys(REGISTRY).forEach(function (token) {
      if (REGISTRY[token].place === "overlay" && isOn(token)) {
        addSeries(token, 0, styles[token]);
      }
    });
    PANE_ORDER.filter(isOn).forEach(function (token, i) {
      addSeries(token, i + 1, styles[token]);
    });

    // Pane test seam: {paneName: {seriesKey: series}}.
    panes = {};
    activeSeries.forEach(function (a) {
      if (a.place !== "pane") return;
      (panes[a.pane] = panes[a.pane] || {})[a.key] = a.series;
    });
    window.marketChart.chart = chart;
    window.marketChart.candleSeries = candleSeries;
    window.marketChart.panes = panes;

    return { chart, candleSeries, activeSeries };
  }

  function remove() {
    if (candles) candles.remove();
    if (chart) chart.remove();
    chart = null;
    candles = null;
    candleSeries = null;
    activeSeries = [];
    panes = {};
  }

  // --- accessors --------------------------------------------------------------

  function getChart() { return chart; }
  function getCandleSeries() { return candles ? candles.getCandleSeries() : null; }
  function getActiveSeries() { return activeSeries; }
  function getPanes() { return panes; }
  function getCandles() { return candles ? candles.getCandles() : []; }

  // Overlay/pane series arrays (NOT candles) shared by history + stream so the
  // single-write-path bookkeeping stays in one place. Returned by reference.
  function getSeriesData() { return seriesData; }

  // Last live bucket (UNIX seconds). History resets it; the stream advances it.
  function getLastBucket() { return lastBucket; }
  function setLastBucket(t) { lastBucket = t; }

  // --- scale mode (F8) --------------------------------------------------------

  // Theme setter (CT5): option-only, no data write (#68). No-op before a chart.
  function setTheme(resolved) {
    if (!chart) return;
    chart.applyOptions(optionsFor(resolved));
  }

  // Map the UI vocab to the v5 PriceScaleMode SYMBOL and apply it to the right
  // price scale. Option-only: never setData/update (#68). Unknown -> Normal.
  function applyScale() {
    if (!chart) return;
    const member = SCALE_MODES[scaleMode] || "Normal";
    chart.priceScale("right").applyOptions({
      mode: LightweightCharts.PriceScaleMode[member],
    });
  }

  // Public scale setter (option-only; no rebuild, no refetch). Invalid input
  // degrades to linear without throwing (CS2).
  function setScaleMode(mode, _autoScale) {
    scaleMode = Types.isValidScale(mode) ? mode : "linear";
    applyScale();
  }

  // Candle data write path (#68) — delegated to the candle module (setData for
  // history/config, update() for live; HA state resets on a fresh history page).
  function setCandles(arr) {
    if (candles) candles.setCandles(arr);
  }

  function updateCandle(bar) {
    if (candles) candles.updateCandle(bar);
  }

  function subscribeClick(fn) {
    if (chart) chart.subscribeClick(fn);
  }
  // Crosshair is host-owned (R14); mirror subscribeClick's null guard. Because
  // build() recreates the chart, consumers MUST re-subscribe after chart:built.
  function subscribeCrosshairMove(fn) {
    if (chart) chart.subscribeCrosshairMove(fn);
  }
  function subscribeVisibleRange(fn) {
    if (chart) chart.timeScale().subscribeVisibleLogicalRangeChange(fn);
  }

  return {
    build,
    remove,
    getChart,
    getCandleSeries,
    getActiveSeries,
    getPanes,
    getCandles,
    getSeriesData,
    getLastBucket,
    setLastBucket,
    setCandles,
    updateCandle,
    setScaleMode,
    setTheme,
    dataKey,
    seriesFromPayload,
    rsiValues,
    setRsi,
    subscribeClick,
    subscribeCrosshairMove,
    subscribeVisibleRange,
  };
}
