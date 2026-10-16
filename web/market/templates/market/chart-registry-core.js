// chart-registry-core.js — pure static presentation registry (F5 S1, R14).
//
// Framework-free (no DOM, no chart library, no network, no global state),
// mirroring the project's "pure core at the center, adapters at the edges"
// rule. A native ESM module: imported in Node by the tests and in the browser
// by the chart modules (no UMD shim, no window global).
//
// Moved verbatim out of ``chart-host.js`` so the host stays under the R14
// ceiling while it gains ``setSeriesVisible`` (design D1). The host and the
// indicators controller are the two importers.
//
// NOTE the required rename: the price-scale map is ``PRICE_SCALE_MODES``, NOT
// ``SCALE_MODES`` — ``chart-types-core.js`` already exports an ARRAY under the
// latter name, and both cores are imported together. An exported-name clash
// would silently shadow one of them.

// token -> placement + series factory. Values come from the server payload; the
// host only maps them onto chart series.
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
// Named PRICE_SCALE_MODES to avoid the chart-types-core.SCALE_MODES clash.
export const PRICE_SCALE_MODES = {
  linear: "Normal",
  log: "Logarithmic",
  percentage: "Percentage",
};
