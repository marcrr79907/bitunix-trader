// drawing-primitive.js — the v5 drawing renderer, extracted from drawings.js.
//
// Owns ONLY canvas drawing for one shape + its LightweightCharts v5 primitive
// wrapper (paneViews / autoscaleInfo / lifecycle). Geometry comes from the pure
// drawing-core.js; handles for a selected shape come from drawing-interaction-core.js.
// A selected shape draws a thicker stroke plus its per-kind handle dots. The
// primitive reads ``isSelected`` LIVE on every render, so a selection change
// needs no re-attach (R6/#68: redraw via ``requestUpdate`` only).
import * as Draw from "./drawing-core.js";
import { handlesFor, HANDLE_RADIUS } from "./drawing-interaction-core.js";

// Price range so a full-width ray / rect is not clipped on pan/zoom (R6).
function priceRangeFor(row) {
  const prices = [];
  if (typeof row.points.price === "number") prices.push(row.points.price);
  ["p1", "p2"].forEach(function (k) {
    const p = row.points[k];
    if (p && typeof p.price === "number") prices.push(p.price);
  });
  if (!prices.length) return null;
  return {
    priceRange: {
      minValue: Math.min.apply(null, prices),
      maxValue: Math.max.apply(null, prices),
    },
  };
}

// Pure canvas draws for one shape. ``map`` = {x(time), y(price)}; null means
// off-bar / off-scale and the leg is skipped rather than thrown (R6). When
// ``selected``, strokes are thicker and the per-kind handle dots are drawn.
function renderShape(ctx, size, row, map, selected) {
  const kind = row.kind;
  ctx.save();
  ctx.strokeStyle = ctx.fillStyle = row.style.color || "#2962ff";
  ctx.lineWidth = (row.style.lineWidth || 1) + (selected ? 2 : 0);
  if (kind === "hline") {
    const y = map.y(row.points.price);
    if (y !== null && y !== undefined) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(size.width, y); ctx.stroke();
    }
  } else if (kind === "trendline") {
    const t = Draw.trendlinePath(row, map);
    if (t.a && t.b) {
      ctx.beginPath(); ctx.moveTo(t.a.x, t.a.y); ctx.lineTo(t.b.x, t.b.y); ctx.stroke();
    }
  } else if (kind === "fib") {
    const f = Draw.fibPath(row, map, row.style.levels);
    ctx.font = "11px sans-serif";
    f.levels.forEach(function (l) {
      if (l.y === null || l.y === undefined) return;
      ctx.beginPath(); ctx.moveTo(f.x1, l.y); ctx.lineTo(f.x2, l.y); ctx.stroke();
      ctx.fillText(l.ratio + "  " + l.price, f.x1, l.y - 2);
    });
  } else if (kind === "rect") {
    const r = Draw.rectPath(row, map);
    if (r) {
      if (row.style.fill) {
        ctx.globalAlpha = 0.15;
        ctx.fillRect(r.left, r.top, r.width, r.height);
        ctx.globalAlpha = 1;
      }
      ctx.strokeRect(r.left, r.top, r.width, r.height);
    }
  } else if (kind === "text") {
    const tx = Draw.textPath(row, map);
    if (tx.x !== null && tx.x !== undefined && tx.y !== null && tx.y !== undefined) {
      ctx.font = (row.style.fontSize || 14) + "px sans-serif";
      ctx.fillText(tx.text, tx.x, tx.y);
    }
  }
  if (selected) drawHandles(ctx, row, map);
  ctx.restore();
}

// The per-kind handle dots for a selected shape (skip any off-bar anchor).
function drawHandles(ctx, row, map) {
  ctx.fillStyle = "#ffffff";
  ctx.strokeStyle = row.style.color || "#2962ff";
  ctx.lineWidth = 1;
  handlesFor(row.kind, row.points, map).forEach(function (h) {
    ctx.beginPath();
    ctx.arc(h.x, h.y, HANDLE_RADIUS / 2, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  });
}

// One v5 ISeriesPrimitive per drawing (paneViews + autoscaleInfo + lifecycle).
// ``selection`` is an object with an ``isSelected(row)`` predicate (or boolean),
// read live each render so toggling selection never needs a re-attach.
function makeDrawingPrimitive(row, selection) {
  const sel = selection || {};
  const isSelected = function () {
    const s = sel.isSelected;
    return typeof s === "function" ? !!s(row) : !!s;
  };
  const c = { chart: null, series: null, requestUpdate: null };
  const map = {
    x: function (time) { return c.chart ? c.chart.timeScale().timeToCoordinate(time) : null; },
    y: function (price) { return c.series ? c.series.priceToCoordinate(price) : null; },
  };
  return {
    attached: function (p) { c.chart = p.chart; c.series = p.series; c.requestUpdate = p.requestUpdate; },
    detached: function () { c.chart = null; c.series = null; },
    paneViews: function () {
      return [{
        renderer: function () {
          return {
            draw: function (target) {
              target.useMediaCoordinateSpace(function (scope) {
                renderShape(scope.context, scope.mediaSize, row, map, isSelected());
              });
            },
          };
        },
      }];
    },
    autoscaleInfo: function () { return priceRangeFor(row); },
  };
}

export { renderShape, makeDrawingPrimitive };
