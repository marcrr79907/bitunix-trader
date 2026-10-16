// drawing-core.js — pure geometry + serialization for chart drawings.
//
// Framework-free (no DOM, no chart library, no network, no global state),
// mirroring chart-core.js and the project's "pure core at the center, adapters
// at the edges" rule. A native ESM module: imported in Node by the tests and in
// the browser by the chart modules (no UMD shim, no window global).
//
// The adapter (chart.js) owns the chart, the fetch/DOM, and the v5 primitives;
// it delegates every coordinate/geometry/round-trip decision here so the logic
// is deterministically testable without a canvas.

// Mirrors Drawing.Kind on the server (the model is the source of truth).
var DRAWING_KINDS = ["hline", "trendline", "fib", "rect", "text"];

// Default fib ratios (TradingView's seven) and per-kind style seed.
var FIB_RATIOS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
var COLORS = {
  hline: "#2962ff",
  trendline: "#ff6d00",
  fib: "#7e57c2",
  rect: "#26a69a",
  text: "#e6edf3",
};

function defaultStyle(kind) {
  if (kind === "fib") return { color: COLORS.fib, lineWidth: 1, levels: FIB_RATIOS.slice() };
  if (kind === "rect") return { color: COLORS.rect, lineWidth: 1, fill: true };
  if (kind === "text") return { color: COLORS.text, fontSize: 14 };
  return { color: COLORS[kind] || COLORS.hline, lineWidth: 1 };
}

// --- serialization (API shape <-> in-memory) --------------------------------

// A persisted row -> in-memory shape, or null for an unknown kind (skip it).
// F5 (R2/R4): carries the persisted ``visible``/``locked`` flags; absent →
// visible / unlocked (the model defaults).
function fromApi(row) {
  if (!row || DRAWING_KINDS.indexOf(row.kind) === -1) return null;
  return {
    id: row.id,
    kind: row.kind,
    points: row.points || {},
    style: row.style || {},
    visible: row.visible !== false,
    locked: row.locked === true,
  };
}

// A drawn shape -> the POST body (server validates symbol/interval).
function toApi(kind, points, style) {
  return { kind: kind, points: points, style: style };
}

// --- click -> data point ----------------------------------------------------

// A chart click param -> {time, price}, or null when no bar sits under the
// cursor (time undefined / null). ``priceAt`` maps a pixel y to a price.
function pointFromParam(param, priceAt) {
  if (!param || param.time === undefined || param.time === null) return null;
  if (!param.point) return null;
  var price = priceAt(param.point.y);
  if (price === null || price === undefined) return null;
  return { time: param.time, price: price };
}

// --- per-kind path builders (map -> pixel geometry) -------------------------
//
// ``map`` is ``{x(time), y(price)}``; each may return null when the value has
// no bar / no scale, and the builders degrade (null leg) instead of throwing.

function hlinePath(d, map) {
  return { y: map.y(d.points.price) };
}

function trendlinePath(d, map) {
  var p1 = d.points.p1;
  var p2 = d.points.p2;
  var a = anchor(p1, map);
  var b = anchor(p2, map);
  return { a: a, b: b };
}

function anchor(p, map) {
  if (!p) return null;
  var x = map.x(p.time);
  var y = map.y(p.price);
  if (x === null || y === null || x === undefined || y === undefined) return null;
  return { x: x, y: y };
}

// Interpolate price levels between two anchors; ratio 0 == p2, ratio 1 == p1
// (the standard retracement orientation: level 0 sits on the latest anchor).
function fibLevels(price1, price2, ratios) {
  var rs = ratios || FIB_RATIOS;
  return rs.map(function (r) {
    return { ratio: r, price: price2 + (price1 - price2) * r };
  });
}

function fibPath(d, map, ratios) {
  var p1 = d.points.p1;
  var p2 = d.points.p2;
  return {
    x1: map.x(p1.time),
    x2: map.x(p2.time),
    levels: fibLevels(p1.price, p2.price, ratios).map(function (l) {
      return { ratio: l.ratio, price: l.price, y: map.y(l.price) };
    }),
  };
}

// Two corners -> a normalized pixel box (any corner order), or null if either
// corner is off the axis/scale.
function rectPath(d, map) {
  var a = anchor(d.points.p1, map);
  var b = anchor(d.points.p2, map);
  if (!a || !b) return null;
  return {
    left: Math.min(a.x, b.x),
    top: Math.min(a.y, b.y),
    width: Math.abs(a.x - b.x),
    height: Math.abs(a.y - b.y),
  };
}

function textPath(d, map) {
  return { x: map.x(d.points.time), y: map.y(d.points.price), text: d.points.text };
}

// --- hit-test (panel delete is primary; this is for future canvas selection) -

// Index of the nearest {x,y} within ``radius`` px, or -1 on a miss.
function hitTest(items, x, y, radius) {
  var best = -1;
  var bestD = radius * radius;
  for (var i = 0; i < items.length; i++) {
    var dx = items[i].x - x;
    var dy = items[i].y - y;
    var d2 = dx * dx + dy * dy;
    if (d2 <= bestD) {
      bestD = d2;
      best = i;
    }
  }
  return best;
}

export {
  DRAWING_KINDS,
  FIB_RATIOS,
  defaultStyle,
  fromApi,
  toApi,
  pointFromParam,
  hlinePath,
  trendlinePath,
  fibLevels,
  fibPath,
  rectPath,
  textPath,
  hitTest,
};
