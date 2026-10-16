// drawing-interaction-core.js — pure geometry for drawing selection + drag.
//
// Framework-free: no DOM, no chart library, no network, no global state. A
// native ESM module imported in Node by the tests and in the browser by the
// interaction controller. Geometry helpers are reused from the sibling pure
// core so the two never drift.
//
// ``map`` is ``{x(time), y(price), time(px), price(py)}``; ``x``/``y`` map data
// to pixels and ``time``/``price`` are their inverses. Any may return null when
// a value has no bar / no scale — every consumer keeps the OLD component on a
// null conversion so a drag can never emit null (which the API would 400).
import { hitTest } from "./drawing-core.js";

const HANDLE_RADIUS = 6;
const BODY_RADIUS = 4;

// An anchor -> pixel, or null when off-bar/off-scale.
function anchorPx(p, map) {
  if (!p) return null;
  const x = map.x(p.time);
  const y = map.y(p.price);
  if (x === null || y === null || x === undefined || y === undefined) return null;
  return { x: x, y: y };
}

// --- handlesFor --------------------------------------------------------------

// Handle positions per kind: hline 1; trendline/fib 2; rect 4 corners; text 1.
// Off-bar anchors are omitted (never null), so a caller can hit-test directly.
function handlesFor(kind, points, map) {
  try {
    if (!points || !map) return [];
    const out = [];
    const add = function (id, x, y) {
      if (x !== null && y !== null && x !== undefined && y !== undefined) {
        out.push({ id: id, x: x, y: y });
      }
    };
    if (kind === "hline") {
      add("price", 0, map.y(points.price));
    } else if (kind === "trendline" || kind === "fib") {
      const a = anchorPx(points.p1, map);
      const b = anchorPx(points.p2, map);
      if (a) add("p1", a.x, a.y);
      if (b) add("p2", b.x, b.y);
    } else if (kind === "rect") {
      const c = rectCorners(points, map);
      if (c) c.forEach(function (h) { add(h.id, h.x, h.y); });
    } else if (kind === "text") {
      add("anchor", map.x(points.time), map.y(points.price));
    }
    return out;
  } catch (e) {
    return [];
  }
}

// The four rect corners (tl,tr,bl,br) in pixel space, or null if a corner is
// off-bar. Order is fixed so a handle index maps to a corner deterministically.
function rectCorners(points, map) {
  const a = anchorPx(points.p1, map);
  const b = anchorPx(points.p2, map);
  if (!a || !b) return null;
  const left = Math.min(a.x, b.x);
  const right = Math.max(a.x, b.x);
  const top = Math.min(a.y, b.y);
  const bottom = Math.max(a.y, b.y);
  return [
    { id: "tl", x: left, y: top },
    { id: "tr", x: right, y: top },
    { id: "bl", x: left, y: bottom },
    { id: "br", x: right, y: bottom },
  ];
}

// --- hit-testing -------------------------------------------------------------

// A pointer (x,y) -> {id, target} for the TOPMOST drawing, or null on a miss.
// Handles win over the body: a handle pass over every row runs first, then a
// body pass. Within each pass the last row (top of the draw order) wins.
function grabHandle(rows, x, y, map, radius) {
  try {
    if (!Array.isArray(rows)) return null;
    const r = radius === undefined || radius === null ? HANDLE_RADIUS : radius;
    for (let i = rows.length - 1; i >= 0; i--) {
      const row = rows[i];
      if (!row) continue;
      const idx = hitTest(handlesFor(row.kind, row.points, map), x, y, r);
      if (idx !== -1) return { id: row.id, target: idx };
    }
    for (let j = rows.length - 1; j >= 0; j--) {
      const row = rows[j];
      if (!row) continue;
      if (bodyHit(row, x, y, map)) return { id: row.id, target: "body" };
    }
    return null;
  } catch (e) {
    return null;
  }
}

// Per-kind body proximity (BODY_RADIUS unless noted).
function bodyHit(row, x, y, map) {
  const p = row.points || {};
  if (row.kind === "hline") {
    const y2 = map.y(p.price);
    return y2 !== null && y2 !== undefined && Math.abs(y - y2) <= BODY_RADIUS;
  }
  if (row.kind === "trendline" || row.kind === "fib") {
    const a = anchorPx(p.p1, map);
    const b = anchorPx(p.p2, map);
    if (!a || !b) return false;
    return pointSegDist(x, y, a, b) <= BODY_RADIUS;
  }
  if (row.kind === "rect") {
    const c = rectCorners(p, map);
    if (!c) return false;
    const left = c[0].x - BODY_RADIUS;
    const right = c[1].x + BODY_RADIUS;
    const top = c[0].y - BODY_RADIUS;
    const bottom = c[2].y + BODY_RADIUS;
    return x >= left && x <= right && y >= top && y <= bottom;
  }
  if (row.kind === "text") {
    const a = anchorPx({ time: p.time, price: p.price }, map);
    if (!a) return false;
    const dx = a.x - x;
    const dy = a.y - y;
    return dx * dx + dy * dy <= BODY_RADIUS * BODY_RADIUS;
  }
  return false;
}

function pointSegDist(px, py, a, b) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len2 = dx * dx + dy * dy;
  if (len2 === 0) return Math.hypot(px - a.x, py - a.y);
  let t = ((px - a.x) * dx + (py - a.y) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (a.x + t * dx), py - (a.y + t * dy));
}

// --- applyDrag ---------------------------------------------------------------

// Move a whole body or a single anchor by a pixel delta. Returns FRESH points
// (never mutates ``row``); a null inverse keeps the old component.
function applyDrag(row, target, dxPx, dyPx, map) {
  try {
    const points = (row && row.points) || {};
    const out = JSON.parse(JSON.stringify(points));
    const kind = row && row.kind;

    if (kind === "hline") {
      out.price = moveValue(map.y(points.price), dyPx, map.price, points.price);
      return out;
    }
    if (kind === "trendline" || kind === "fib") {
      if (!hasAnchor(points, "p1") && !hasAnchor(points, "p2")) return out;
      if (target === "body") {
        moveAnchor(out, points, "p1", dxPx, dyPx, map);
        moveAnchor(out, points, "p2", dxPx, dyPx, map);
      } else {
        moveAnchor(out, points, target === 1 ? "p2" : "p1", dxPx, dyPx, map);
      }
      return out;
    }
    if (kind === "rect") {
      if (target === "body") {
        moveAnchor(out, points, "p1", dxPx, dyPx, map);
        moveAnchor(out, points, "p2", dxPx, dyPx, map);
      } else {
        dragRectCorner(out, points, target, dxPx, dyPx, map);
      }
      return out;
    }
    if (kind === "text") {
      out.time = moveValue(map.x(points.time), dxPx, map.time, points.time);
      out.price = moveValue(map.y(points.price), dyPx, map.price, points.price);
      return out;
    }
    return out;
  } catch (e) {
    return (row && row.points) || {};
  }
}

// Translate one anchor by a pixel delta (both components).
function moveAnchor(out, points, key, dx, dy, map) {
  const p = points[key];
  if (!p) return;
  out[key] = {
    time: moveValue(map.x(p.time), dx, map.time, p.time),
    price: moveValue(map.y(p.price), dy, map.price, p.price),
  };
}

// Corner index (0..3 = tl,tr,bl,br) -> which anchor owns x / y at that corner.
// The opposite corner stays fixed because only that corner's components change.
function dragRectCorner(out, points, index, dx, dy, map) {
  const a = anchorPx(points.p1, map);
  const b = anchorPx(points.p2, map);
  if (!a || !b) return;
  const leftIsP1 = a.x <= b.x;
  const topIsP1 = a.y <= b.y;
  const wide = index === 1 || index === 3; // tr / br use the right edge
  const tall = index === 2 || index === 3; // bl / br use the bottom edge
  const xAnchor = wide ? (leftIsP1 ? "p2" : "p1") : leftIsP1 ? "p1" : "p2";
  const yAnchor = tall ? (topIsP1 ? "p2" : "p1") : topIsP1 ? "p1" : "p2";
  const cx = wide ? Math.max(a.x, b.x) : Math.min(a.x, b.x);
  const cy = tall ? Math.max(a.y, b.y) : Math.min(a.y, b.y);
  const newTime = map.time(cx + dx);
  const newPrice = map.price(cy + dy);
  if (newTime !== null && newTime !== undefined) out[xAnchor].time = newTime;
  if (newPrice !== null && newPrice !== undefined) out[yAnchor].price = newPrice;
}

// base pixel + delta -> mapped value, keeping ``old`` on a null conversion.
function moveValue(basePx, delta, inverse, old) {
  if (basePx === null || basePx === undefined) return old;
  const next = inverse(basePx + delta);
  if (next === null || next === undefined) return old;
  return next;
}

function hasAnchor(points, key) {
  return !!points[key] && typeof points[key].time !== "undefined";
}

export { HANDLE_RADIUS, BODY_RADIUS, handlesFor, grabHandle, applyDrag };
