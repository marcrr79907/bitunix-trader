// chart-host-candles.js — the host-layer candle channel (DEBT-5 / #146).
//
// Owns the candle SERIES, the raw candle array, and the incremental Heikin
// Ashi state. Split out of chart-host.js so the candle write path (#68:
// history/config -> setData, live -> update only) lives in one focused module
// under the ~300-line ceiling.
//
// The HA transform itself stays in the pure core (chart-types-core.js); this
// module only owns the series handle and the state that chains live bars.
import * as Core from "./chart-core.js";
import * as Types from "./chart-types-core.js";

// Candle-series Ctor per chart type (F8). HA has no v5 series (D2) — it wraps
// the transform over CandlestickSeries. Unknown type degrades to candles.
const CANDLE_CTORS = {
  candles: "CandlestickSeries",
  "heikin-ashi": "CandlestickSeries",
  line: "LineSeries",
  area: "AreaSeries",
};

// Candle factory: owns the series, the raw array and the incremental HA state.
// ``getCandleSeries``/``getCandles`` return the LIVE references (never copies).
export function createCandles(chart, chartType) {
  const ctor = LightweightCharts[CANDLE_CTORS[chartType] || CANDLE_CTORS.candles];
  let series = chart ? chart.addSeries(ctor) : null;
  const type = chartType;
  let candles = [];
  // HA live state: the HA of the last WRITTEN bar and the state after the
  // second-to-last bar (the chain a forming same-bucket replace needs). Both
  // reset on setCandles.
  let lastHa = null;
  let prevHa = null;
  let lastBarTime = 0;

  // Candle data write path (#68). History/config -> setData; live -> update().
  // HA (F8) transforms both paths; state resets on a fresh history page.
  function setCandles(arr) {
    candles = arr;
    prevHa = null;
    lastHa = null;
    lastBarTime = 0;
    if (!series) return;
    if (type === "heikin-ashi") {
      const out = Types.heikinAshi(candles);
      series.setData(out);
      const n = out.length;
      lastHa = n ? { haOpen: out[n - 1].open, haClose: out[n - 1].close } : null;
      prevHa = n > 1 ? { haOpen: out[n - 2].open, haClose: out[n - 2].close } : null;
      lastBarTime = n ? out[n - 1].time : 0;
    } else {
      series.setData(candles);
    }
  }

  function updateCandle(bar) {
    Core.upsertCandle(candles, bar);
    if (!series) return;
    if (type === "heikin-ashi") {
      // A same-bucket replace chains from the last CLOSED bar's HA (``prevHa``);
      // a new bar chains from the current bar's HA (``lastHa``). ``prevHa`` MUST
      // advance only when the previous bar CLOSES — otherwise repeated same-bucket
      // ticks chain the forming bar onto an old version of ITSELF and drift.
      // Either way: update() only (#68).
      const sameBucket = bar.time === lastBarTime;
      const base = sameBucket ? prevHa : lastHa;
      const ha = Types.nextHeikinAshi(base, bar);
      series.update(ha);
      if (!sameBucket) prevHa = lastHa;
      lastHa = { haOpen: ha.open, haClose: ha.close };
      lastBarTime = bar.time;
    } else {
      series.update(bar); // the ONLY live candle write
    }
  }

  function getCandleSeries() { return series; }
  function getCandles() { return candles; }
  function remove() { series = null; candles = []; }

  return { getCandleSeries, getCandles, setCandles, updateCandle, remove };
}
