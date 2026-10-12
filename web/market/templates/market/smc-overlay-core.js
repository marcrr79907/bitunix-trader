// smc-overlay-core.js — pure mapping for the SMC overlay payload.
//
// Framework-free (no DOM, no chart library, no network, no SMC math),
// mirroring drawing-core.js / chart-core.js and the project's "pure core at
// the center, adapters at the edges" rule. Loads in Node via CommonJS and in
// the browser via window.SmcOverlayCore (UMD shim at the bottom).
//
// SINGLE SOURCE (R10): src/smc/ computes every swing, zone, range and setup;
// this file only RESHAPES the server payload into draw descriptors. It never
// recomputes SMC. The adapter (chart.js) owns the chart and the v5 primitives.
(function (root) {
  "use strict";

  // Element families, in draw/render order (mirrors the frozen payload keys).
  var FAMILIES = [
    "swings",
    "structure",
    "order_blocks",
    "fvg",
    "range",
    "setups",
  ];

  var COLORS = {
    swings: { high: "#ef5350", low: "#26a69a" },
    structure: { bullish: "#2962ff", bearish: "#ff6d00" },
    order_blocks: { bullish: "#26a69a", bearish: "#ef5350" },
    fvg: { bullish: "#26a69a", bearish: "#ef5350" },
    range: "#7e57c2",
    setups: { long: "#26a69a", short: "#ef5350" },
  };

  function isArray(v) {
    return Array.isArray(v);
  }

  // --- normalization ----------------------------------------------------------

  // A payload (frozen API shape) -> normalized object with camelCase keys.
  // Never throws: null / garbage degrades to the empty shape. Unknown keys are
  // dropped (only the six families + symbol/interval survive).
  function fromApi(payload) {
    var p = payload && typeof payload === "object" ? payload : {};
    return {
      symbol: p.symbol || null,
      interval: p.interval || null,
      swings: isArray(p.swings) ? p.swings : [],
      structure: isArray(p.structure) ? p.structure : [],
      orderBlocks: isArray(p.order_blocks) ? p.order_blocks : [],
      fvgs: isArray(p.fvgs) ? p.fvgs : [],
      range: p.range && typeof p.range === "object" ? p.range : null,
      setups: isArray(p.setups) ? p.setups : [],
    };
  }

  // --- toggles ----------------------------------------------------------------

  // Enabled families. Absent / empty toggles mean all ON (R7); only an explicit
  // `false` hides a family.
  function visibleFamilies(toggles) {
    if (!toggles || typeof toggles !== "object") return FAMILIES.slice();
    return FAMILIES.filter(function (f) {
      return toggles[f] !== false;
    });
  }

  // --- coordinate mapping -----------------------------------------------------

  // Default mapper: identity (descriptors carry data coords; the adapter maps
  // data -> pixels at draw time). A supplied map may return null for an
  // off-series value, and the affected record is dropped (R6: never throws).
  function defaultMap() {
    return {
      x: function (t) {
        return t;
      },
      y: function (p) {
        return p;
      },
    };
  }

  function off(v) {
    return v === null || v === undefined;
  }

  // --- per-family descriptor builders -----------------------------------------

  function swingDescriptors(rows, map) {
    var out = [];
    rows.forEach(function (s) {
      var x = map.x(s.time);
      var y = map.y(s.price);
      if (off(x) || off(y)) return;
      out.push({
        kind: s.kind,
        time: s.time,
        price: s.price,
        label: s.label === undefined ? null : s.label,
        color: COLORS.swings[s.kind] || COLORS.swings.low,
        x: x,
        y: y,
      });
    });
    return out;
  }

  function structureDescriptors(rows, map) {
    var out = [];
    rows.forEach(function (e) {
      var x = map.x(e.time);
      var y = map.y(e.price);
      if (off(x) || off(y)) return;
      out.push({
        kind: e.kind,
        time: e.time,
        price: e.price,
        direction: e.direction,
        trend: e.trend,
        label: e.kind === "bos" ? "BOS" : "CHoCH",
        color: COLORS.structure[e.direction] || COLORS.structure.bullish,
        x: x,
        y: y,
      });
    });
    return out;
  }

  function orderBlockDescriptors(rows, map) {
    var out = [];
    rows.forEach(function (ob) {
      var x1 = map.x(ob.time);
      var x2 = map.x(ob.anchor_time);
      var yTop = map.y(ob.top);
      var yBottom = map.y(ob.bottom);
      if (off(x1) || off(x2) || off(yTop) || off(yBottom)) return;
      out.push({
        kind: ob.kind,
        time: ob.time,
        anchorTime: ob.anchor_time,
        top: ob.top,
        bottom: ob.bottom,
        color: COLORS.order_blocks[ob.kind] || COLORS.order_blocks.bullish,
        x1: x1,
        x2: x2,
        yTop: yTop,
        yBottom: yBottom,
      });
    });
    return out;
  }

  function fvgDescriptors(rows, map) {
    var out = [];
    rows.forEach(function (g) {
      var x = map.x(g.time);
      var yTop = map.y(g.top);
      var yBottom = map.y(g.bottom);
      if (off(x) || off(yTop) || off(yBottom)) return;
      out.push({
        kind: g.kind,
        time: g.time,
        top: g.top,
        bottom: g.bottom,
        color: COLORS.fvg[g.kind] || COLORS.fvg.bullish,
        x: x,
        yTop: yTop,
        yBottom: yBottom,
      });
    });
    return out;
  }

  // The premium (equilibrium..high) + discount (low..equilibrium) bands. Null
  // range, or any off-scale band price, drops the whole band set (R6).
  function rangeDescriptor(range, map) {
    if (!range) return null;
    var yHigh = map.y(range.high);
    var yLow = map.y(range.low);
    var yEq = map.y(range.equilibrium);
    if (off(yHigh) || off(yLow) || off(yEq)) return null;
    return {
      high: range.high,
      low: range.low,
      equilibrium: range.equilibrium,
      time: range.time,
      color: COLORS.range,
      yHigh: yHigh,
      yLow: yLow,
      yEquilibrium: yEq,
    };
  }

  // --- public mapping ---------------------------------------------------------

  // payload + toggles (+ optional {x,y} map) -> per-family draw descriptors.
  // Pure; off-series legs are dropped instead of thrown. Families that are
  // toggled off (or absent in the payload) yield [] / null.
  function descriptors(payload, toggles, map) {
    var n = fromApi(payload);
    var on = {};
    visibleFamilies(toggles).forEach(function (f) {
      on[f] = true;
    });
    var m = map && typeof map.x === "function" && typeof map.y === "function"
      ? map
      : defaultMap();
    return {
      swings: on.swings ? swingDescriptors(n.swings, m) : [],
      structure: on.structure ? structureDescriptors(n.structure, m) : [],
      order_blocks: on.order_blocks ? orderBlockDescriptors(n.orderBlocks, m) : [],
      fvg: on.fvg ? fvgDescriptors(n.fvgs, m) : [],
      range: on.range ? rangeDescriptor(n.range, m) : null,
      setups: on.setups ? n.setups.slice() : [],
    };
  }

  // setups -> createSeriesMarkers array: belowBar long / aboveBar short (R6).
  function setupMarkers(payload, toggles) {
    var n = fromApi(payload);
    if (visibleFamilies(toggles).indexOf("setups") === -1) return [];
    return n.setups.map(function (s) {
      var long = s.direction === "long";
      return {
        time: s.time,
        position: long ? "belowBar" : "aboveBar",
        color: long ? COLORS.setups.long : COLORS.setups.short,
        shape: long ? "arrowUp" : "arrowDown",
        text: (long ? "L " : "S ") + s.score + "/4",
      };
    });
  }

  // Parity (R9): drawn-record count per family, honoring the toggles.
  function counts(payload, toggles) {
    var d = descriptors(payload, toggles);
    return {
      swings: d.swings.length,
      structure: d.structure.length,
      order_blocks: d.order_blocks.length,
      fvg: d.fvg.length,
      range: d.range ? 1 : 0,
      setups: d.setups.length,
    };
  }

  var api = {
    FAMILIES: FAMILIES,
    COLORS: COLORS,
    fromApi: fromApi,
    visibleFamilies: visibleFamilies,
    descriptors: descriptors,
    setupMarkers: setupMarkers,
    counts: counts,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api; // Node
  }
  if (root) {
    root.SmcOverlayCore = api; // browser
  }
})(typeof window !== "undefined" ? window : null);
