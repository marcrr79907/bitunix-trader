// position-core.js — pure geometry + R:R math for the position instrument.
//
// Framework-free (no DOM, no chart library, no network, no global state, no
// imports at all), mirroring drawing-core.js and the project's "pure core at
// the center, adapters at the edges" rule. A native ESM module: imported in
// Node by the tests and in the browser by drawing-primitive / interaction.
//
// A persisted position carries {entry:{time,price}, stop:number,
// take_profit:number} (spec chart-drawings R5, D6). The R:R derivation mirrors
// smc-signals R3 (long (tp-entry)/(entry-stop); short mirrored) so the client
// never recomputes SMC levels — it only re-derives R:R while the user drags.
// Every function is pure and NEVER throws; an off-value input degrades to null.

// px width of a position box, drawn right from the entry column.
var BOX_WIDTH = 120;

var COLORS = { long: "#26a69a", short: "#ef5350", none: "#787b86" };

function num(v) {
  return typeof v === "number" && isFinite(v) ? v : null;
}

// {entry:{time,price}, stop, take_profit} -> {entry, stop, takeProfit, long},
// or null when an entry price / level is missing or non-numeric.
// long = stop < entry (direction by level order).
function levelsFrom(points) {
  if (!points || typeof points !== "object") return null;
  var entry = points.entry;
  if (!entry || typeof entry !== "object") return null;
  var e = num(entry.price);
  var stop = num(points.stop);
  var tp = num(points.take_profit);
  if (e === null || stop === null || tp === null) return null;
  return { entry: e, stop: stop, takeProfit: tp, long: stop < e };
}

// Long  (stop < entry): risk = entry-stop, reward = tp-entry.
// Short (stop > entry): risk = stop-entry, reward = entry-tp.   [mirrors smc R3]
// rr is null when entry === stop (degenerate, never divide by zero).
function riskReward(entry, stop, tp) {
  var e = num(entry);
  var s = num(stop);
  var t = num(tp);
  if (e === null || s === null || t === null) return { risk: null, reward: null, rr: null };
  var long = s < e;
  var risk = long ? e - s : s - e;
  var reward = long ? t - e : e - t;
  return { risk: risk, reward: reward, rr: risk === 0 ? null : reward / risk };
}

// A normalized pixel box for a position, or null when the entry x is off-bar.
// ``map`` is {x(time), y(price)}; either may return null and the box degrades.
function positionBox(points, map) {
  var lv = levelsFrom(points);
  if (!lv || !map) return null;
  var left = map.x(points.entry.time);
  if (left === null || left === undefined) return null;
  var yEntry = map.y(lv.entry);
  var yStop = map.y(lv.stop);
  var yTp = map.y(lv.takeProfit);
  var rr = riskReward(lv.entry, lv.stop, lv.takeProfit).rr;
  return {
    left: left,
    right: left + BOX_WIDTH,
    riskBand: { top: Math.min(yEntry, yStop), bottom: Math.max(yEntry, yStop) },
    rewardBand: { top: Math.min(yEntry, yTp), bottom: Math.max(yEntry, yTp) },
    levels: [
      { id: "entry", price: lv.entry, y: yEntry, label: "Entry" },
      { id: "stop", price: lv.stop, y: yStop, label: "SL" },
      { id: "take_profit", price: lv.takeProfit, y: yTp, label: "TP" },
    ],
    rr: rr,
    long: lv.long,
  };
}

// Four handles (R10): the entry anchor at the entry column plus the stop,
// take_profit and entry-price level handles on the right edge. Off-bar/off-scale
// entries are omitted (never null), so a caller can hit-test directly.
function positionHandles(points, map) {
  try {
    var lv = levelsFrom(points);
    if (!lv || !map) return [];
    var left = map.x(points.entry.time);
    if (left === null || left === undefined) return [];
    var right = left + BOX_WIDTH;
    var out = [];
    var add = function (id, x, y) {
      if (x !== null && y !== null && x !== undefined && y !== undefined) {
        out.push({ id: id, x: x, y: y });
      }
    };
    var yEntry = map.y(lv.entry);
    add("entry", left, yEntry);
    add("entry_price", right, yEntry);
    add("stop", right, map.y(lv.stop));
    add("take_profit", right, map.y(lv.takeProfit));
    return out;
  } catch (e) {
    return [];
  }
}

// Seed style. Direction color is presentation-only (R6/R9: the render always
// draws a LONG/SHORT text label + arrow, so color is never the sole cue).
function defaultPositionStyle(points) {
  var lv = points ? levelsFrom(points) : null;
  var key = lv === null ? "none" : lv.long ? "long" : "short";
  return { color: COLORS[key], lineWidth: 1 };
}

export {
  BOX_WIDTH,
  levelsFrom,
  riskReward,
  positionBox,
  positionHandles,
  defaultPositionStyle,
};
