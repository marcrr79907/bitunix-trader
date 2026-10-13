// controllers/history.js — REST history load + left-edge pagination.
//
// DI factory (R14): ``create({store, bus, host, config})``. LEAF module — never
// imports main. Owns ``klineUrl``/``fetchHistory``/``loadOlder``/``applyHistory``.
// The #68 write path: history/config -> host.setCandles + series setData; the
// live stream (controllers/stream.js) uses update() only.
import * as Core from "../chart-core.js";

// URLs are built here so the (symbol, interval, params, extra) window lives in
// one place; the entry owns the base paths via ``config.urls``.
export function klineUrlFrom(state, base, extra) {
  let q = "symbol=" + state.symbol + "&interval=" + state.interval;
  if (state.indicators.length) q += "&indicators=" + state.indicators.join(",");
  // Append editable params so e.g. ``sma_len=50`` reaches the server.
  state.indicators.forEach(function (token) {
    const params = state.params && state.params[token];
    if (!params) return;
    Object.keys(params).forEach(function (key) {
      q += "&" + encodeURIComponent(key) + "=" + encodeURIComponent(params[key]);
    });
  });
  if (extra) q += "&" + extra;
  return base + "?" + q;
}

export function createHistory({ store, bus, host, config }) {
  const state = store.get();
  const EDGE = 5;
  let loadingOlder = false;
  let hasMore = true;

  function klineUrl(extra) {
    return klineUrlFrom(state, config.urls.kline, extra);
  }

  function applyHistory(payload) {
    // setData is allowed HERE only: full history reset for a config change.
    // The host owns the candle array + the single write path (#68).
    host.setCandles(payload.candles.slice());
    const seriesData = host.getSeriesData();
    host.getActiveSeries().forEach(function (a) {
      const arr = host.seriesFromPayload(a, payload).slice();
      seriesData[host.dataKey(a.place, a.pane, a.key)] = arr;
      a.series.setData(arr);
    });
    host.setRsi(host.rsiValues(payload));
    const candles = host.getCandles();
    host.setLastBucket(candles.length ? candles[candles.length - 1].time : 0);
    hasMore = true;
    bus.emit("history:loaded", { candles: candles });
  }

  function fetchHistory() {
    // limit=HISTORY_LIMIT so the history window matches the SMC window (R8).
    fetch(klineUrl("limit=" + config.historyLimit))
      .then(function (r) {
        if (!r.ok) throw new Error("kline " + r.status);
        return r.json();
      })
      .then(applyHistory)
      .catch(function () { /* chart stays; nothing to do */ });
  }

  // Pagination (setData with merge; viewport preserved). Triggered by the
  // visible-range subscription main wires in buildChart.
  function loadOlder() {
    if (loadingOlder || !hasMore || !host.getCandles().length) return;
    loadingOlder = true;
    const candles = host.getCandles();
    const before = candles[0].time;
    fetch(klineUrl("limit=200&before=" + before))
      .then(function (r) {
        if (!r.ok) throw new Error("kline " + r.status);
        return r.json();
      })
      .then(function (p) {
        if (!p.candles.length) { hasMore = false; return; }
        const range = host.getChart().timeScale().getVisibleLogicalRange();
        const current = host.getCandles();
        const beforeLen = current.length;
        const merged = Core.mergeCandles(p.candles, current);
        const seriesData = host.getSeriesData();
        host.getActiveSeries().forEach(function (a) {
          const k = host.dataKey(a.place, a.pane, a.key);
          seriesData[k] = Core.mergeCandles(host.seriesFromPayload(a, p), seriesData[k] || []);
          a.series.setData(seriesData[k]);
        });
        const added = merged.length - beforeLen;
        if (!added) { hasMore = false; return; }
        host.setCandles(merged); // candle setData last (original order)
        if (range) {
          host.getChart().timeScale().setVisibleLogicalRange({
            from: range.from + added,
            to: range.to + added,
          });
        }
      })
      .catch(function () { /* transient */ })
      .finally(function () { loadingOlder = false; });
  }

  // Visible range -> left edge -> paginate. Wired by main after build.
  function onVisibleRange(range) {
    if (range && range.from < EDGE) loadOlder();
  }

  return { fetchHistory, loadOlder, onVisibleRange, applyHistory };
}
