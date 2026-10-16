// controllers/smc.js — SMC overlay fetch, primitive, markers, toggles.
//
// DI factory (R14): ``create({store, bus, host, config})``. LEAF module — never
// imports main. The overlay renders on a series PRIMITIVE (its own canvas
// layer) — never via setData/update — so #68 single-write-path stays intact.
// Geometry comes from the pure smc-overlay-core.js; this controller fetches and
// maps coords. ``smcGen`` guards a stale SMC fetch; a toggle re-renders from the
// already-fetched payload with NO refetch (R7).
import * as Smc from "../smc-overlay-core.js";

const MAP_WIDTH_REF = { width: 0 }; // live canvas width, refreshed each draw
const RAY_WIDTH = 40; // px length of a BOS/CHoCH ray
const FVG_HALF_WIDTH = 6; // px half-width of an FVG box

// Theme-aware swing connector (D3): read the resolved token from the shell so
// light (dark text) and dark (#8b949e) both stay legible on the canvas. Falls
// back to the light literal (#616161, 6.2:1 on white) if the var is absent.
function connectorColor() {
  try {
    const v = getComputedStyle(document.documentElement)
      .getPropertyValue("--chart-connector")
      .trim();
    return v || "#616161";
  } catch (_e) {
    return "#616161";
  }
}

// DOM -> {family: bool} for the SMC overlay (absent element => all ON).
export function readSmc() {
  const out = {};
  document.querySelectorAll(".smc-toggle").forEach(function (el) {
    out[el.dataset.family] = el.checked;
  });
  return out;
}

// Persisted map ({family: bool}) -> a COMPLETE {family: bool} map with an
// absent/invalid family defaulting to ON (R7: `{}` means all ON). Pure, so the
// boot restore path is node-testable without a DOM.
export function resolveToggles(saved) {
  const out = {};
  Smc.FAMILIES.forEach(function (f) {
    out[f] = !saved || typeof saved !== "object" ? true : saved[f] !== false;
  });
  return out;
}

export function createSmc({ store, bus, host, config }) {
  const state = store.get();
  const smcToggles = Array.prototype.slice.call(
    document.querySelectorAll(".smc-toggle"),
  );

  let smcBody = null; // raw fetched payload (R9: window.marketChart.smc)
  let smcPrim = null; // the attached ISeriesPrimitive (canvas families)
  let smcMarkers = null; // the createSeriesMarkers handle (setups)
  let smcGen = 0; // monotonic guard against a stale SMC fetch
  const smcCtx = { chart: null, series: null, requestUpdate: null };

  function smcUrl() {
    const q = "symbol=" + encodeURIComponent(state.symbol)
      + "&interval=" + encodeURIComponent(state.interval)
      + "&limit=" + config.historyLimit;
    return config.urls.smc + "?" + q;
  }

  // {x(time), y(price)} over the LIVE chart; each may return null off-series.
  function smcMap() {
    return {
      x: function (time) {
        return smcCtx.chart ? smcCtx.chart.timeScale().timeToCoordinate(time) : null;
      },
      y: function (price) {
        return smcCtx.series ? smcCtx.series.priceToCoordinate(price) : null;
      },
    };
  }

  // Price range so bands / rays are not clipped on pan/zoom (R6 autoscaleInfo).
  function smcPriceRange() {
    const prices = [];
    const push = function (v) { if (typeof v === "number") prices.push(v); };
    const d = Smc.descriptors(smcBody, state.smc);
    d.swings.forEach(function (s) { push(s.price); });
    d.structure.forEach(function (s) { push(s.price); });
    d.order_blocks.forEach(function (o) { push(o.top); push(o.bottom); });
    d.fvg.forEach(function (f) { push(f.top); push(f.bottom); });
    if (d.range) { push(d.range.high); push(d.range.low); }
    if (!prices.length) return null;
    return {
      priceRange: {
        minValue: Math.min.apply(null, prices),
        maxValue: Math.max.apply(null, prices),
      },
    };
  }

  // Pure canvas draw for the enabled canvas families. ``map`` null-guards every
  // coordinate: an off-series leg is skipped, never thrown (R6).
  function renderSmc(ctx, map) {
    const d = Smc.descriptors(smcBody, state.smc, map);
    ctx.save();
    ctx.lineWidth = 1;

    // Premium (equilibrium..high) + discount (low..equilibrium) bands + eq line.
    if (d.range) {
      ctx.globalAlpha = 0.08;
      ctx.fillStyle = d.range.color;
      ctx.fillRect(0, d.range.yHigh, MAP_WIDTH_REF.width, d.range.yEquilibrium - d.range.yHigh);
      ctx.fillRect(0, d.range.yEquilibrium, MAP_WIDTH_REF.width, d.range.yLow - d.range.yEquilibrium);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = d.range.color;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(0, d.range.yEquilibrium);
      ctx.lineTo(MAP_WIDTH_REF.width, d.range.yEquilibrium);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Order-block rects (time -> anchor_time, top -> bottom).
    d.order_blocks.forEach(function (ob) {
      const left = Math.min(ob.x1, ob.x2);
      const width = Math.abs(ob.x2 - ob.x1);
      const top = Math.min(ob.yTop, ob.yBottom);
      const height = Math.abs(ob.yBottom - ob.yTop);
      ctx.globalAlpha = 0.15;
      ctx.fillStyle = ob.color;
      ctx.fillRect(left, top, width, height);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = ob.color;
      ctx.strokeRect(left, top, width, height);
    });

    // FVG rects (middle candle span; draw a fixed-width box centred on x).
    d.fvg.forEach(function (g) {
      const top = Math.min(g.yTop, g.yBottom);
      const height = Math.abs(g.yBottom - g.yTop);
      ctx.globalAlpha = 0.15;
      ctx.fillStyle = g.color;
      ctx.fillRect(g.x - FVG_HALF_WIDTH, top, FVG_HALF_WIDTH * 2, height);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = g.color;
      ctx.strokeRect(g.x - FVG_HALF_WIDTH, top, FVG_HALF_WIDTH * 2, height);
    });

    // Swing zig-zag polyline + pivot labels (label-less first swing still draws).
    // The connector color is theme-aware (D3): dark #8b949e, light #616161
    // (both clear the WCAG 1.4.11 non-text floor of 3:1 on their canvas).
    ctx.strokeStyle = connectorColor();
    ctx.beginPath();
    let started = false;
    d.swings.forEach(function (s) {
      if (!started) { ctx.moveTo(s.x, s.y); started = true; }
      else { ctx.lineTo(s.x, s.y); }
    });
    ctx.stroke();
    ctx.font = "10px sans-serif";
    d.swings.forEach(function (s) {
      ctx.fillStyle = s.color;
      ctx.beginPath();
      ctx.arc(s.x, s.y, 2, 0, Math.PI * 2);
      ctx.fill();
      if (s.label) ctx.fillText(s.label, s.x + 3, s.y - 3);
    });

    // BOS / CHoCH short horizontal ray at price + text.
    ctx.font = "10px sans-serif";
    d.structure.forEach(function (e) {
      ctx.strokeStyle = e.color;
      ctx.fillStyle = e.color;
      ctx.beginPath();
      ctx.moveTo(e.x, e.y);
      ctx.lineTo(Math.min(e.x + RAY_WIDTH, MAP_WIDTH_REF.width), e.y);
      ctx.stroke();
      ctx.fillText(e.label, e.x + 3, e.y - 3);
    });

    ctx.restore();
  }

  // One v5 ISeriesPrimitive renders ALL enabled canvas families (fewest
  // attach/detach cycles). Rebuilt on every buildChart via attachSmcLayer().
  function makeSmcPrimitive() {
    return {
      attached: function (params) {
        smcCtx.chart = params.chart;
        smcCtx.series = params.series;
        smcCtx.requestUpdate = params.requestUpdate;
      },
      detached: function () {
        smcCtx.chart = null;
        smcCtx.series = null;
        smcCtx.requestUpdate = null;
      },
      paneViews: function () {
        return [
          {
            renderer: function () {
              return {
                draw: function (target) {
                  if (!smcBody) return;
                  target.useMediaCoordinateSpace(function (scope) {
                    MAP_WIDTH_REF.width = scope.mediaSize.width;
                    renderSmc(scope.context, smcMap());
                  });
                },
              };
            },
          },
        ];
      },
      autoscaleInfo: smcPriceRange,
    };
  }

  // (Re)attach the SMC primitive + markers onto the CURRENT candleSeries.
  // Called from buildChart (A3 order: layout -> build -> reattach) and after a
  // fetch. Always tears the previous layer down first (no leak, R6/R7).
  function attachSmcLayer() {
    const candleSeries = host.getCandleSeries();
    if (smcPrim && candleSeries) candleSeries.detachPrimitive(smcPrim);
    smcPrim = null;
    if (smcMarkers) {
      smcMarkers.detach();
      smcMarkers = null;
    }
    if (!candleSeries || !smcBody) {
      window.marketChart.smc = smcBody;
      return;
    }
    smcPrim = makeSmcPrimitive();
    candleSeries.attachPrimitive(smcPrim);
    smcMarkers = LightweightCharts.createSeriesMarkers(
      candleSeries,
      Smc.setupMarkers(smcBody, state.smc),
    );
    window.marketChart.smc = smcBody;
    window.marketChart.smcCounts = Smc.counts(smcBody, state.smc);
    bus.emit("smc:loaded", { payload: smcBody });
  }

  // Fetch the SMC payload for the ACTIVE key; a failed fetch is non-fatal.
  function loadSmc() {
    const mine = ++smcGen;
    return fetch(smcUrl())
      .then(function (r) {
        if (!r.ok) throw new Error("smc " + r.status);
        return r.json();
      })
      .then(function (body) {
        if (mine !== smcGen) return;
        smcBody = body;
        attachSmcLayer();
      })
      .catch(function () {
        if (mine !== smcGen) return;
        smcBody = null;
        attachSmcLayer();
      });
  }

  // Toggle -> re-render from the already-fetched payload; NO refetch (R7).
  function refreshSmc() {
    state.smc = readSmc();
    window.marketChart.smcToggles = state.smc;
    bus.emit("smc:toggles", { families: state.smc });
    if (smcCtx.requestUpdate) smcCtx.requestUpdate();
    if (smcMarkers) smcMarkers.setMarkers(Smc.setupMarkers(smcBody, state.smc));
    window.marketChart.smcCounts = smcBody ? Smc.counts(smcBody, state.smc) : null;
  }

  // Boot restore (R7): apply the persisted toggles to the checkboxes and render
  // from the (already fetched or empty) payload WITHOUT emitting ``smc:toggles``
  // — restoring is not a user change, so it must not trigger a save.
  function applyToggles(saved) {
    const resolved = resolveToggles(saved);
    state.smc = resolved;
    window.marketChart.smcToggles = resolved;
    smcToggles.forEach(function (el) {
      if (el.dataset.family in resolved) el.checked = resolved[el.dataset.family];
    });
    if (smcCtx.requestUpdate) smcCtx.requestUpdate();
    if (smcMarkers) smcMarkers.setMarkers(Smc.setupMarkers(smcBody, resolved));
    window.marketChart.smcCounts = smcBody ? Smc.counts(smcBody, resolved) : null;
  }

  // Called by main on switchTo: clear the previous key's layer immediately
  // (primitives/markers never cross keys) and invalidate any in-flight fetch.
  function clearForSwitch() {
    smcBody = null;
    smcGen++;
    attachSmcLayer();
  }

  smcToggles.forEach(function (t) { t.addEventListener("change", refreshSmc); });

  return { loadSmc, attachSmcLayer, refreshSmc, clearForSwitch, applyToggles };
}
