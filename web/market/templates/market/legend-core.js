// legend-core.js — pure legend formatters for the market chart.
//
// Framework-free (no DOM, no chart library, no network, no globals) mirroring
// chart-core.js / drawing-core.js / smc-overlay-core.js. A native ESM module:
// imported in Node by the tests and in the browser by the legend controller.
//
// SINGLE SOURCE (LC2): this file only FORMATS server-shaped values. It imports
// nothing and defines no indicator/window/EMA/RSI/ATR math. The only arithmetic
// is the candle open-vs-close direction.
export const DECIMALS = Object.freeze({
  sma: 2,
  ema: 2,
  bollinger_upper: 2,
  bollinger_middle: 2,
  bollinger_lower: 2,
  vwap: 2,
  rsi: 2,
  stochastic_k: 2,
  stochastic_d: 2,
  atr: 2,
  macd: 4,
  macd_signal: 4,
  macd_histogram: 4,
  volume: 0,
});

export const PLACEHOLDER = "\u2013"; // en dash

function isNum(v) {
  return typeof v === "number" && Number.isFinite(v);
}

// token -> fixed decimals (2-decimal fallback). null/undefined/NaN/non-number
// -> placeholder. Never throws.
export function formatValue(token, value) {
  if (!isNum(value)) return PLACEHOLDER;
  const decimals = DECIMALS[token];
  return value.toFixed(typeof decimals === "number" ? decimals : 2);
}

// Candle -> {open,high,low,close,dir}; all strings. dir is the signed direction
// of close vs open ("up"|"dn"|"flat"); a missing leg -> placeholder, dir "flat".
export function formatOhlc(candle) {
  const c = candle && typeof candle === "object" ? candle : {};
  const dir = isNum(c.close) && isNum(c.open)
    ? c.close > c.open
      ? "up"
      : c.close < c.open
        ? "dn"
        : "flat"
    : "flat";
  return {
    open: formatValue("ohlc", c.open),
    high: formatValue("ohlc", c.high),
    low: formatValue("ohlc", c.low),
    close: formatValue("ohlc", c.close),
    dir: dir,
  };
}

// entries: chart-lib-free [{token,key,place,pane,value}]
// activeSeries: host.getActiveSeries() enriched with an optional {params}
// label: TOKEN uppercase + first numeric param (e.g. "SMA 20")
export function rows(entries, activeSeries, candle) {
  const list = Array.isArray(entries) ? entries : [];
  const series = Array.isArray(activeSeries) ? activeSeries : [];
  return {
    ohlc: formatOhlc(candle),
    series: list.map(function (e) {
      const entry = e && typeof e === "object" ? e : {};
      const token = entry.token === undefined || entry.token === null ? entry.key : entry.token;
      return {
        token: entry.token,
        key: entry.key,
        place: entry.place,
        pane: entry.pane,
        label: labelFor(token, series),
        value: formatValue(entry.token, entry.value),
      };
    }),
  };
}

function labelFor(token, activeSeries) {
  const name = token === undefined || token === null ? "" : String(token).toUpperCase();
  const match = activeSeries.find(function (a) {
    return a && (a.token === token || a.key === token);
  });
  const params = match && match.params && typeof match.params === "object" ? match.params : null;
  if (params) {
    const values = Object.keys(params).map(function (k) {
      return params[k];
    });
    for (let i = 0; i < values.length; i += 1) {
      if (isNum(values[i])) return name + " " + values[i];
    }
  }
  return name;
}

// Not-hovering fallback: last candle + each active series' last value. Recomputes
// the o:/p: dataKey locally so the core stays chart-lib-free. Never throws.
export function lastValues(activeSeries, seriesData, candles) {
  const series = Array.isArray(activeSeries) ? activeSeries : [];
  const data = seriesData && typeof seriesData === "object" ? seriesData : {};
  const bars = Array.isArray(candles) && candles.length ? candles : null;
  return {
    candle: bars ? bars[bars.length - 1] : null,
    entries: series.map(function (a) {
      const place = a && a.place;
      const key = a && a.key;
      const dk = place === "overlay" ? "o:" + key : "p:" + (a && a.pane) + ":" + key;
      const arr = data[dk];
      const last = Array.isArray(arr) && arr.length ? arr[arr.length - 1] : null;
      return { key: key, value: last ? last.value : null };
    }),
  };
}
