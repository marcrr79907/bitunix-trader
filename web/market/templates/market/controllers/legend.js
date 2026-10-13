// controllers/legend.js — TradingView-style crosshair legend overlay.
//
// DI factory (R14): ``create({store, bus, host, config})``. LEAF module — never
// imports main. Owns the ``.chart-legend`` DOM node and its read-out policy.
//
// SINGLE SOURCE (LC2): this controller only RESHAPES values the host already
// holds — the v5 crosshair ``param.seriesData`` Map (hover) or
// ``host.getSeriesData()``/``getCandles()`` last element (leave). It computes no
// indicator/SMC/candle value; ``changePct`` (close vs the prior close) is the
// only arithmetic, and it operates on server-shaped numbers. The pure formatters
// live in legend-core.js; the DOM writes here are ``textContent`` only.
import * as Core from "../legend-core.js";

// --- pure shapers (DOM-free, unit-tested in tests/js) ------------------------
//
// entries: chart-lib-free [{token,key,place,pane,value}] mapped to each active
// series in host order; the candle at the cursor bar travels alongside. Never
// throws on garbage input.

export function candleFrom(param, candleSeries) {
  const data = param && param.seriesData ? param.seriesData : null;
  if (!data || typeof data.get !== "function") return null;
  return data.get(candleSeries) || null;
}

export function shapeEntries(param, activeSeries, candleSeries) {
  const series = Array.isArray(activeSeries) ? activeSeries : [];
  const data = param && param.seriesData ? param.seriesData : null;
  const read = data && typeof data.get === "function" ? data : null;
  return {
    candle: candleFrom(param, candleSeries),
    entries: series.map(function (a) {
      const point = read ? read.get(a.series) : null;
      return {
        token: a.token,
        key: a.key,
        place: a.place,
        pane: a.pane,
        value: point && typeof point === "object" ? point.value : undefined,
      };
    }),
  };
}

// Close of the candle immediately before ``candle`` in the ascending array.
export function prevClose(candles, candle) {
  const bars = Array.isArray(candles) ? candles : null;
  if (!bars || !candle || typeof candle.time !== "number") return null;
  const i = bars.findIndex(function (b) { return b && b.time === candle.time; });
  if (i <= 0) return null;
  const prev = bars[i - 1];
  return prev ? prev.close : null;
}

// Signed percent change close vs prevClose; placeholder when either is unknown.
export function changePctText(close, prev) {
  const ok = function (v) { return typeof v === "number" && Number.isFinite(v); };
  if (!ok(close) || !ok(prev) || prev === 0) return Core.PLACEHOLDER;
  const pct = ((close - prev) / prev) * 100;
  return (pct > 0 ? "+" : "") + pct.toFixed(2) + "%";
}

// --- controller --------------------------------------------------------------

export function createLegend({ store, bus, host }) {
  const state = store.get();
  const container = document.getElementById("chart");
  if (!container) return { render: function () {}, root: null };

  // Inject the overlay once. a11y: role=status; aria-live starts polite (idle)
  // and flips to off while hovering so screen readers are never flooded
  // per-mousemove (LC5).
  const root = document.createElement("div");
  root.className = "chart-legend";
  root.setAttribute("role", "status");
  root.setAttribute("aria-live", "polite");
  root.setAttribute("aria-label", "Chart legend");

  const ohlcEl = document.createElement("div");
  ohlcEl.className = "lg-ohlc num";
  const ohlcVals = document.createElement("span");
  ohlcVals.className = "lg-ohlc-vals";
  const chgEl = document.createElement("span");
  chgEl.className = "lg-chg";
  ohlcEl.appendChild(ohlcVals);
  ohlcEl.appendChild(chgEl);
  root.appendChild(ohlcEl);
  container.appendChild(root);

  const rowByKey = {}; // key -> {row, token, val}
  let frame = null;
  let pending = null;
  let hovering = false;
  let idleTimer = null;

  function activeEnriched() {
    const params = state.params || {};
    return host.getActiveSeries().map(function (a) {
      return {
        token: a.token,
        key: a.key,
        place: a.place,
        pane: a.pane,
        params: params[a.token],
      };
    });
  }

  // Hover rows come straight from the crosshair Map; idle rows from the host's
  // last-value bookkeeping (LC3). Both feed the same formatter/render path.
  function idleModel() {
    const active = activeEnriched();
    const last = Core.lastValues(active, host.getSeriesData(), host.getCandles());
    const byKey = {};
    active.forEach(function (a) { byKey[a.key] = a; });
    const entries = last.entries.map(function (e) {
      const a = byKey[e.key] || {};
      return { token: a.token, key: e.key, place: a.place, pane: a.pane, value: e.value };
    });
    return { model: Core.rows(entries, active, last.candle), candle: last.candle };
  }

  function rowFor(key) {
    if (rowByKey[key]) return rowByKey[key];
    const row = document.createElement("div");
    row.className = "lg-row";
    const token = document.createElement("span");
    token.className = "lg-token";
    const val = document.createElement("span");
    val.className = "lg-val num";
    row.appendChild(token);
    row.appendChild(val);
    root.appendChild(row);
    rowByKey[key] = { row: row, token: token, val: val };
    return rowByKey[key];
  }

  // Paint is textContent-only; called at most once per animation frame.
  function paint(model, candle) {
    const o = model.ohlc;
    const closeNum = candle && typeof candle.close === "number" ? candle.close : null;
    const prev = prevClose(host.getCandles(), candle);
    const text = "O " + o.open + "  H " + o.high + "  L " + o.low + "  C " + o.close;
    ohlcVals.textContent = text;
    chgEl.textContent = changePctText(closeNum, prev);
    chgEl.className = "lg-chg " + o.dir;

    const seen = {};
    model.series.forEach(function (s) {
      seen[s.key] = true;
      const node = rowFor(s.key);
      node.token.textContent = s.label;
      node.val.textContent = s.value;
    });
    // Drop rows for series no longer active (config change).
    Object.keys(rowByKey).forEach(function (key) {
      if (seen[key]) return;
      rowByKey[key].row.remove();
      delete rowByKey[key];
    });
  }

  // rAF coalescing: keep at most one pending frame (LC3).
  function schedule(model, candle) {
    pending = { model: model, candle: candle };
    if (frame !== null) return;
    frame = requestAnimationFrame(function () {
      frame = null;
      const p = pending;
      pending = null;
      if (p) paint(p.model, p.candle);
    });
  }

  function setHovering(next) {
    if (next === hovering) return;
    hovering = next;
    if (idleTimer) { clearTimeout(idleTimer); idleTimer = null; }
    if (next) {
      root.setAttribute("aria-live", "off"); // never announce per mousemove
    } else {
      // Idle summary: one polite announcement once movement settles (LC5).
      idleTimer = setTimeout(function () {
        idleTimer = null;
        root.setAttribute("aria-live", "polite");
      }, 300);
    }
  }

  function onMove(param) {
    const hasPoint = !!(param && param.point);
    setHovering(hasPoint);
    if (hasPoint) {
      const snap = shapeEntries(param, host.getActiveSeries(), host.getCandleSeries());
      schedule(Core.rows(snap.entries, activeEnriched(), snap.candle), snap.candle);
    } else {
      renderIdle();
    }
  }

  function renderIdle() {
    const m = idleModel();
    schedule(m.model, m.candle);
  }

  // The chart is recreated on every build(), so the crosshair handler must be
  // re-bound to the NEW chart each ``chart:built`` (the old one dies with
  // chart.remove()). Idle snapshot refreshes on the data events that can change
  // the last value (LC4/LC6).
  bus.on("chart:built", function () {
    host.subscribeCrosshairMove(onMove);
    setHovering(false);
    renderIdle();
  });
  bus.on("history:loaded", function () { if (!hovering) renderIdle(); });
  bus.on("candle:closed", function () { if (!hovering) renderIdle(); });

  return { root: root, renderIdle: renderIdle, onMove: onMove };
}
