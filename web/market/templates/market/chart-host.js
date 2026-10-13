// chart-host.js — the ONLY LightweightCharts construction surface.
//
// Encapsulates LightweightCharts 5.2.0 (createChart / addSeries / panes) and
// OWNS the candle series data (#68 single-write-path: history -> setData, live
// -> update(), config rebuild -> setData). UI/config state lives in
// chart-store.js; the host never reads the store.
//
// Static presentation registry (token -> placement + series factory). Values
// come from the server payload; the host only maps them onto chart series.
import * as Core from "./chart-core.js";

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

export function createHost() {
  let chart = null;
  let candleSeries = null;
  let activeSeries = [];
  let panes = {};
  let candles = [];
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

  function addSeries(token, paneIndex) {
    REGISTRY[token].series.forEach(function (s) {
      const Ctor =
        s.type === "histogram"
          ? LightweightCharts.HistogramSeries
          : LightweightCharts.LineSeries;
      const series = chart.addSeries(Ctor, { color: s.color }, paneIndex);
      activeSeries.push({
        token: token,
        key: s.key,
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
    chart = LightweightCharts.createChart(el, {
      height: 480,
      timeScale: { timeVisible: true },
    });
    candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries);
    activeSeries = [];

    const enabled = state.indicators;
    const isOn = function (token) { return enabled.indexOf(token) !== -1; };

    Object.keys(REGISTRY).forEach(function (token) {
      if (REGISTRY[token].place === "overlay" && isOn(token)) addSeries(token, 0);
    });
    PANE_ORDER.filter(isOn).forEach(function (token, i) {
      addSeries(token, i + 1);
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
    if (chart) chart.remove();
    chart = null;
    candleSeries = null;
    activeSeries = [];
    panes = {};
  }

  // --- accessors --------------------------------------------------------------

  function getChart() { return chart; }
  function getCandleSeries() { return candleSeries; }
  function getActiveSeries() { return activeSeries; }
  function getPanes() { return panes; }
  function getCandles() { return candles; }

  // Overlay/pane series arrays (NOT candles) shared by history + stream so the
  // single-write-path bookkeeping stays in one place. Returned by reference.
  function getSeriesData() { return seriesData; }

  // Last live bucket (UNIX seconds). History resets it; the stream advances it.
  function getLastBucket() { return lastBucket; }
  function setLastBucket(t) { lastBucket = t; }

  // Candle data write path (#68). History/config -> setData; live -> update().
  function setCandles(arr) {
    candles = arr;
    if (candleSeries) candleSeries.setData(candles);
  }

  function updateCandle(bar) {
    Core.upsertCandle(candles, bar);
    if (candleSeries) candleSeries.update(bar); // the ONLY live candle write
  }

  // --- coordinate converters (scales / crosshair) -----------------------------

  function timeToCoordinate(time) {
    return chart ? chart.timeScale().timeToCoordinate(time) : null;
  }
  function priceToCoordinate(price) {
    return candleSeries ? candleSeries.priceToCoordinate(price) : null;
  }
  function coordinateToPrice(y) {
    return candleSeries ? candleSeries.coordinateToPrice(y) : null;
  }
  function coordinateToTime(x) {
    return chart ? chart.timeScale().coordinateToTime(x) : null;
  }

  function subscribeClick(fn) {
    if (chart) chart.subscribeClick(fn);
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
    dataKey,
    seriesFromPayload,
    rsiValues,
    setRsi,
    timeToCoordinate,
    priceToCoordinate,
    coordinateToPrice,
    coordinateToTime,
    subscribeClick,
    subscribeVisibleRange,
  };
}
