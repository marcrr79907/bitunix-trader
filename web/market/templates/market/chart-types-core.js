// chart-types-core.js — pure chart-type vocabulary + Heikin Ashi transform.
//
// Framework-free (no DOM, no chart library, no network, no global state),
// mirroring the project's "pure core at the center, adapters at the edges"
// rule. A native ESM module: imported in Node by the tests and in the browser
// by the chart modules (no UMD shim, no window global).
//
// Imports nothing; deterministic; never throws (unknown type/scale, empty or
// malformed candles all degrade to a safe value). The host picks the v5 series
// Ctor from CHART_TYPES and lets this core reshape the candle data.

export const CHART_TYPES = Object.freeze([
  "candles",
  "line",
  "area",
  "heikin-ashi",
]);
export const SCALE_MODES = Object.freeze(["linear", "log", "percentage"]);

// line/area render as a value series; candles/heikin-ashi render OHLC bars.
function isLineLike(type) {
  return type === "line" || type === "area";
}

function isValidType(type) {
  return CHART_TYPES.indexOf(type) !== -1;
}

function isValidScale(mode) {
  return SCALE_MODES.indexOf(mode) !== -1;
}

// One HA bar from the raw OHLC bar and the prior HA bar's open/close.
// `prevHa === null` (first bar) takes the first-bar branch.
function nextHeikinAshi(prevHa, bar) {
  var o = bar.open;
  var h = bar.high;
  var l = bar.low;
  var c = bar.close;
  var haClose = (o + h + l + c) / 4;
  var haOpen = prevHa ? (prevHa.haOpen + prevHa.haClose) / 2 : (o + c) / 2;
  return {
    time: bar.time,
    open: haOpen,
    high: Math.max(h, haOpen, haClose),
    low: Math.min(l, haOpen, haClose),
    close: haClose,
  };
}

// Full recursive HA transform: each bar chains the previous HA open/close.
function heikinAshi(candles) {
  if (!Array.isArray(candles)) return [];
  var out = [];
  var prev = null;
  for (var i = 0; i < candles.length; i++) {
    var ha = nextHeikinAshi(prev, candles[i]);
    out.push(ha);
    prev = { haOpen: ha.open, haClose: ha.close };
  }
  return out;
}

// Type -> series data. candles/heikin-ashi -> OHLC points; line/area ->
// {time,value} with value = close. Unknown type degrades to the candle mapping.
function toChartData(type, candles) {
  if (isLineLike(type)) {
    if (!Array.isArray(candles)) return [];
    return candles.map(function (bar) {
      return { time: bar.time, value: bar.close };
    });
  }
  if (type === "heikin-ashi") return heikinAshi(candles);
  if (!Array.isArray(candles)) return [];
  return candles.map(function (bar) {
    return {
      time: bar.time,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
    };
  });
}

export {
  isLineLike,
  isValidType,
  isValidScale,
  nextHeikinAshi,
  heikinAshi,
  toChartData,
};
