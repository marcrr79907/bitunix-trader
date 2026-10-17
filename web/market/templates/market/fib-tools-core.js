// fib-tools-core.js — pure geometry for the F9 fib instruments (ext/time/zone).
//
// Framework-free (no DOM, no chart library, no network, no global state),
// mirroring drawing-core.js and the project's "pure core at the center, adapters
// at the edges" rule. A native ESM module: imported in Node by the tests and in
// the browser by drawing-tools-core / drawing-primitive.
//
// Reuses FIB_RATIOS from drawing-core.js (fib_time/fib_zone) and adds
// FIB_EXT_RATIOS for fib_ext (D4: extension ≠ retracement). Orientation mirrors
// drawing-core.fibLevels: ratio 0 == p2. Every function is pure and NEVER throws;
// a missing anchor or off-bar mapper degrades to null/[] instead.
import { FIB_RATIOS } from "./drawing-core.js";

// Extension ratios (D4): ratio 0 == p2, ratio 1 projects beyond p2.
var FIB_EXT_RATIOS = [0, 0.618, 1, 1.272, 1.618, 2.618];

function num(v) {
  return typeof v === "number" && isFinite(v) ? v : null;
}

// A price -> y, or null when the mapper has no scale.
function yOf(map, price) {
  if (!map || typeof map.y !== "function") return null;
  var y = map.y(price);
  return y === undefined ? null : y;
}

// The p1/p2 prices, or null when either anchor price is missing/non-numeric.
function swingPrices(points) {
  if (!points || typeof points !== "object") return null;
  var p1 = points.p1;
  var p2 = points.p2;
  if (!p1 || !p2) return null;
  var a = num(p1.price);
  var b = num(p2.price);
  if (a === null || b === null) return null;
  return { p1: a, p2: b };
}

// A 3-point fib_ext swing -> [{ratio, price, y}]. ratio 0 == p2; ratio 1 sits at
// 2*p2 - p1 (the leg projected BEYOND p2); p3 provides x extent only (unused here).
function fibExtLevels(points, map, ratios) {
  try {
    var sp = swingPrices(points);
    if (!sp) return [];
    var rs = ratios || FIB_EXT_RATIOS;
    return rs.map(function (r) {
      var price = sp.p2 + (sp.p2 - sp.p1) * r;
      return { ratio: r, price: price, y: yOf(map, price) };
    });
  } catch (e) {
    return [];
  }
}

// A 2-point span -> {levels:[{ratio, time, x}]} at FIB_RATIOS over the bar span.
// time = p1.time + (p2.time - p1.time) * ratio (ratio 0 == p1 start of the span).
// x is null when the mapper has no bar for that time (the vertical leg is skipped).
function fibTimePath(points, map) {
  try {
    if (!points || !points.p1 || !points.p2) return null;
    var t1 = points.p1.time;
    var t2 = points.p2.time;
    if (typeof t1 !== "number" || typeof t2 !== "number") return null;
    var xOf = map && typeof map.x === "function" ? map.x : null;
    return {
      levels: FIB_RATIOS.map(function (r) {
        var time = t1 + (t2 - t1) * r;
        var x = xOf ? xOf(time) : null;
        return { ratio: r, time: time, x: x === undefined ? null : x };
      }),
    };
  } catch (e) {
    return null;
  }
}

// A 2-point span -> [{ratioLo, ratioHi, priceLo, priceHi, yLo, yHi}] between
// consecutive FIB_RATIOS levels (ratio 0 == p2). A band whose either y maps
// off-scale (null) is skipped, never coerced to 0.
function fibZoneBands(points, map) {
  try {
    var sp = swingPrices(points);
    if (!sp) return [];
    var levels = FIB_RATIOS.map(function (r) {
      return { ratio: r, price: sp.p2 + (sp.p1 - sp.p2) * r };
    });
    var bands = [];
    for (var i = 0; i < levels.length - 1; i++) {
      var lo = yOf(map, levels[i].price);
      var hi = yOf(map, levels[i + 1].price);
      if (lo === null || hi === null) continue;
      bands.push({
        ratioLo: levels[i].ratio,
        ratioHi: levels[i + 1].ratio,
        priceLo: levels[i].price,
        priceHi: levels[i + 1].price,
        yLo: lo,
        yHi: hi,
      });
    }
    return bands;
  } catch (e) {
    return [];
  }
}

export { FIB_EXT_RATIOS, fibExtLevels, fibTimePath, fibZoneBands };
