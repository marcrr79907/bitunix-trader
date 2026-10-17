// drawing-tools-core.js — pure descriptor map for the eight F9 drawing kinds.
//
// Framework-free (no DOM, no chart library, no network, no global state),
// mirroring drawing-core.js and the project's "pure core at the center, adapters
// at the edges" rule. Native ESM: imported in Node by the tests and in the
// browser by drawing-core / drawing-primitive / drawing-interaction-core.
//
// Each kind is ONE descriptor {clicks, style, path, handles, bodyHit, drag} so
// the existing cores dispatch with a single guard (design D2) and never grow an
// if/else chain. Fib geometry delegates to fib-tools-core. Every entry point is
// pure and NEVER throws; a null row / off-bar map degrades to null/[]/false.
import { FIB_RATIOS } from "./drawing-core.js";
import { FIB_EXT_RATIOS, fibExtLevels, fibTimePath, fibZoneBands } from "./fib-tools-core.js";

const NEW_KINDS = [
  "ray", "vline", "channel", "price", "callout", "fib_ext", "fib_time", "fib_zone",
];
const COLORS = {
  ray: "#ff6d00", vline: "#2962ff", channel: "#26a69a", price: "#ef5350",
  callout: "#e6edf3", fib_ext: "#7e57c2", fib_time: "#7e57c2", fib_zone: "#7e57c2",
};
const R = 4; // body hit radius (px), mirrors drawing-interaction-core BODY_RADIUS

// --- helpers ----------------------------------------------------------------

// Anchor {time,price} -> {x,y}, or null when off-bar / off-scale.
function P(p, map) {
  if (!p || !map) return null;
  const x = map.x(p.time);
  const y = map.y(p.price);
  return x === null || y === null || x === undefined || y === undefined ? null : { x: x, y: y };
}

// Shortest distance from a point to a segment [a,b]; Infinity when an end is null.
function d2seg(px, py, a, b) {
  if (!a || !b) return Infinity;
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const l2 = dx * dx + dy * dy;
  if (l2 === 0) return Math.hypot(px - a.x, py - a.y);
  let t = ((px - a.x) * dx + (py - a.y) * dy) / l2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (a.x + t * dx), py - (a.y + t * dy));
}

const near = (px, py, segs) => segs.some((s) => d2seg(px, py, s[0], s[1]) <= R);
const nearPt = (px, py, a) => (a ? Math.hypot(a.x - px, a.y - py) <= R : false);
const onAxis = (a, b) => a !== null && a !== undefined && Math.abs(a - b) <= R;

// base pixel + delta -> mapped value, keeping ``old`` on a null conversion.
function mv(px, d, inv, old) {
  if (px === null || px === undefined) return old;
  const n = inv(px + d);
  return n === null || n === undefined ? old : n;
}

// Move one anchor by a pixel delta (both components).
function dragA(o, pts, id, dx, dy, map) {
  const p = pts[id];
  if (!p) return;
  o[id] = {
    time: mv(map.x(p.time), dx, map.time, p.time),
    price: mv(map.y(p.price), dy, map.price, p.price),
  };
}

const clone = (pts) => JSON.parse(JSON.stringify(pts || {}));

// --- handle / drag factories for the anchor kinds ---------------------------

// Handles for a fixed anchor id list; off-bar anchors are omitted.
const handlesOf = (ids) => (pts, map) => {
  const out = [];
  ids.forEach((id) => { const h = P(pts[id], map); if (h) out.push({ id: id, x: h.x, y: h.y }); });
  return out;
};

// Drag: "body" translates every anchor; a known anchor id moves only itself.
const dragOf = (ids) => (pts, target, dx, dy, map) => {
  const o = clone(pts);
  if (target === "body") ids.forEach((id) => dragA(o, pts, id, dx, dy, map));
  else if (ids.indexOf(target) !== -1) dragA(o, pts, target, dx, dy, map);
  return o;
};

// --- per-kind geometry ------------------------------------------------------

// A ray: p1 -> p2 extended to the map's right edge (slope preserved).
function rayPath(row, map) {
  const a = P(row.points.p1, map);
  const b = P(row.points.p2, map);
  const right = map.right;
  if (!a || !b || typeof right !== "number" || b.x === a.x) return { a: a, b: b };
  const slope = (b.y - a.y) / (b.x - a.x);
  return { a: a, b: { x: right, y: a.y + slope * (right - a.x) } };
}

const vlinePath = (row, map) => ({ x: map.x(row.points.time) });
const pricePath = (row, map) => ({ y: map.y(row.points.price), price: row.points.price });

// Two parallel lines: base p1->p2 plus an offset line through p3 (d = p3 + p2-p1).
function channelPath(row, map) {
  const a = P(row.points.p1, map);
  const b = P(row.points.p2, map);
  const c = P(row.points.p3, map);
  const d = a && b && c ? { x: c.x + (b.x - a.x), y: c.y + (b.y - a.y) } : null;
  return { a: a, b: b, c: c, d: d };
}

const calloutPath = (row, map) => ({
  a: P(row.points.p1, map), b: P(row.points.p2, map), text: row.points.text,
});

const fibExtPath = (row, map) => ({
  x1: map.x(row.points.p1 && row.points.p1.time),
  x2: map.x(row.points.p2 && row.points.p2.time),
  levels: fibExtLevels(row.points, map, FIB_EXT_RATIOS),
});

const fibTimePathFor = (row, map) => fibTimePath(row.points, map);

const fibZonePath = (row, map) => ({
  x1: map.x(row.points.p1 && row.points.p1.time),
  x2: map.x(row.points.p2 && row.points.p2.time),
  bands: fibZoneBands(row.points, map, FIB_RATIOS),
});

// --- body-hit strategies ----------------------------------------------------

const segHit = (pathFn) => (pts, x, y, map) => {
  const v = pathFn({ points: pts }, map);
  return near(x, y, [[v.a, v.b]]);
};

// --- descriptors ------------------------------------------------------------

const TOOL_SPECS = {
  ray: {
    clicks: 2, style: { color: COLORS.ray, lineWidth: 1 }, path: rayPath,
    handles: handlesOf(["p1", "p2"]),
    bodyHit: segHit(rayPath),
    drag: dragOf(["p1", "p2"]),
  },
  vline: {
    clicks: 1, style: { color: COLORS.vline, lineWidth: 1 }, path: vlinePath,
    handles: (pts, map) => {
      const x = map.x(pts.time);
      return x === null || x === undefined ? [] : [{ id: "time", x: x, y: 0 }];
    },
    bodyHit: (pts, x, y, map) => onAxis(map.x(pts.time), x),
    drag: (pts, target, dx, dy, map) => ({ time: mv(map.x(pts.time), dx, map.time, pts.time) }),
  },
  channel: {
    clicks: 3, style: { color: COLORS.channel, lineWidth: 1 }, path: channelPath,
    handles: handlesOf(["p1", "p2", "p3"]),
    bodyHit: (pts, x, y, map) => {
      const v = channelPath({ points: pts }, map);
      return near(x, y, [[v.a, v.b], [v.c, v.d]]);
    },
    drag: dragOf(["p1", "p2", "p3"]),
  },
  price: {
    clicks: 1, style: { color: COLORS.price, lineWidth: 1 }, path: pricePath,
    handles: (pts, map) => {
      const y = map.y(pts.price);
      return y === null || y === undefined ? [] : [{ id: "price", x: 0, y: y }];
    },
    bodyHit: (pts, x, y, map) => onAxis(map.y(pts.price), y),
    drag: (pts, target, dx, dy, map) => ({ price: mv(map.y(pts.price), dy, map.price, pts.price) }),
  },
  callout: {
    clicks: 2, style: { color: COLORS.callout, lineWidth: 1 }, path: calloutPath,
    handles: handlesOf(["p1", "p2"]),
    bodyHit: (pts, x, y, map) => {
      const a = P(pts.p1, map);
      const b = P(pts.p2, map);
      return nearPt(x, y, a) || nearPt(x, y, b) || near(x, y, [[a, b]]);
    },
    drag: dragOf(["p1", "p2"]),
  },
  fib_ext: {
    clicks: 3, style: { color: COLORS.fib_ext, lineWidth: 1 }, path: fibExtPath,
    handles: handlesOf(["p1", "p2", "p3"]),
    bodyHit: (pts, x, y, map) => {
      const v = fibExtPath({ points: pts }, map);
      const segs = [];
      v.levels.forEach((l) => {
        if (l.y !== null && l.y !== undefined) segs.push([{ x: v.x1, y: l.y }, { x: v.x2, y: l.y }]);
      });
      return near(x, y, segs) || nearPt(x, y, P(pts.p3, map));
    },
    drag: dragOf(["p1", "p2", "p3"]),
  },
  fib_time: {
    clicks: 2, style: { color: COLORS.fib_time, lineWidth: 1 }, path: fibTimePathFor,
    handles: handlesOf(["p1", "p2"]),
    bodyHit: (pts, x, y, map) => {
      const v = fibTimePath(pts, map);
      return !!v && v.levels.some((l) => onAxis(l.x, x));
    },
    drag: dragOf(["p1", "p2"]),
  },
  fib_zone: {
    clicks: 2, style: { color: COLORS.fib_zone, lineWidth: 1 }, path: fibZonePath,
    handles: handlesOf(["p1", "p2"]),
    bodyHit: (pts, x, y, map) => {
      const v = fibZonePath({ points: pts }, map);
      return v.bands.some((b) => {
        const top = Math.min(b.yLo, b.yHi) - R;
        const bottom = Math.max(b.yLo, b.yHi) + R;
        return x >= v.x1 - R && x <= v.x2 + R && y >= top && y <= bottom;
      });
    },
    drag: dragOf(["p1", "p2"]),
  },
};

// --- public dispatch (one guard per existing core) --------------------------

const specOf = (kind) => TOOL_SPECS[kind] || null;

function clicksFor(kind) {
  const s = specOf(kind);
  return s ? s.clicks : 0;
}

function defaultToolStyle(kind) {
  const s = specOf(kind);
  const base = s ? s.style : { color: COLORS.ray, lineWidth: 1 };
  return { color: base.color, lineWidth: base.lineWidth };
}

function toolPath(kind, row, map) {
  try {
    const s = specOf(kind);
    return s && row && map ? s.path(row, map) : null;
  } catch (e) { return null; }
}

function toolHandles(kind, points, map) {
  try {
    const s = specOf(kind);
    return s && points && map ? s.handles(points, map) : [];
  } catch (e) { return []; }
}

function toolBodyHit(kind, points, x, y, map) {
  try {
    const s = specOf(kind);
    return !!(s && points && map && s.bodyHit(points, x, y, map));
  } catch (e) { return false; }
}

function toolDrag(kind, points, target, dx, dy, map) {
  try {
    const s = specOf(kind);
    return s && points && map ? s.drag(points, target, dx, dy, map) : points || {};
  } catch (e) { return points || {}; }
}

export {
  NEW_KINDS, TOOL_SPECS, clicksFor, defaultToolStyle,
  toolPath, toolHandles, toolBodyHit, toolDrag,
};
