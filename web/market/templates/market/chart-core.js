// chart-core.js — pure timeline/series math for the market chart.
//
// Framework-free (no DOM, no chart library, no network, no global state),
// mirroring the project's "pure core at the center, adapters at the edges"
// rule (see src/ vs web/). Loads in Node via CommonJS and in the browser via
// window.ChartCore from this single source (UMD shim at the bottom).
//
// The adapter (chart.js) owns DOM/chart/WS/REST and delegates every timeline or
// ordering decision here, so the logic is deterministically testable.
(function (root) {
  "use strict";

  var MONTH = "1M";
  var WEEK_SECONDS = 604800;
  // BitUnix aligns weekly candles to Monday 00:00 UTC (epoch was a Thursday).
  var MONDAY_OFFSET = 345600;

  function intervalSeconds(interval) {
    var unit = interval.slice(-1);
    var n = parseInt(interval, 10);
    if (unit === "m") return n * 60;
    if (unit === "h") return n * 3600;
    if (unit === "d") return n * 86400;
    if (interval === MONTH) return 2592000; // unused for bucketing (calendar path)
    if (unit === "w") return n * WEEK_SECONDS;
    return 60;
  }

  // UNIX-seconds start of the candle bucket for `tsMs`, aligned as the exchange
  // aligns it. 1w -> Monday 00:00 UTC; 1M -> calendar month start; else floor.
  function bucketTime(tsMs, interval) {
    if (interval === MONTH) {
      var d = new Date(tsMs);
      return Math.floor(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1) / 1000);
    }
    var sec = intervalSeconds(interval);
    var bucket = Math.floor(Math.floor(tsMs / 1000) / sec) * sec;
    if (interval.slice(-1) === "w") bucket += MONDAY_OFFSET; // weeks align to Monday
    return bucket;
  }

  // In-place, monotonic, deduped upsert. Replaces the current last bar on the
  // same time, appends when newer, ignores strictly-older bars.
  function upsertCandle(candles, bar) {
    var n = candles.length;
    if (n === 0 || bar.time > candles[n - 1].time) {
      candles.push(bar);
    } else if (bar.time === candles[n - 1].time) {
      candles[n - 1] = bar;
    }
    // else: older -> ignored (never reorder or duplicate)
    return candles;
  }

  // Pagination merge: union deduped by time, ascending, existing wins on dup.
  function mergeCandles(older, existing) {
    var byTime = {};
    var i;
    for (i = 0; i < older.length; i++) byTime[older[i].time] = older[i];
    for (i = 0; i < existing.length; i++) byTime[existing[i].time] = existing[i];
    return Object.keys(byTime)
      .map(function (t) {
        return byTime[t];
      })
      .sort(function (a, b) {
        return a.time - b.time;
      });
  }

  function lastPoint(series) {
    return series.length ? series[series.length - 1] : undefined;
  }

  var api = {
    intervalSeconds: intervalSeconds,
    bucketTime: bucketTime,
    upsertCandle: upsertCandle,
    mergeCandles: mergeCandles,
    lastPoint: lastPoint,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api; // Node
  }
  if (root) {
    root.ChartCore = api; // browser
  }
})(typeof window !== "undefined" ? window : null);
