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
import { positionBox } from "./position-core.js";

// Price range so a full-width ray / rect / position box is not clipped (R6).
function priceRangeFor(row) {
  const prices = [];
  if (typeof row.points.price === "number") prices.push(row.points.price);
  // F6 (R6): a position's stop/take_profit levels must be in range too.
  if (typeof row.points.stop === "number") prices.push(row.points.stop);
  if (typeof row.points.take_profit === "number") prices.push(row.points.take_profit);
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
  // F5 S3 (R6): a hidden drawing stays attached but draws NOTHING. Reveal is a
  // requestUpdate only (the primitive reads ``row.visible`` live each render).
  if (row.visible === false) {
    ctx.restore();
    return;
  }
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
  } else if (kind === "position") {
    renderPosition(ctx, row, map);
  }
  if (selected) drawHandles(ctx, row, map);
  ctx.restore();
}

// F6 (R6): a position box — a risk zone (entry->stop) and a reward zone
// (entry->take_profit), three level lines with labels, and a LONG/SHORT label +
// arrow + R:R text. Geometry comes from position-core.positionBox; a null box
// (off-bar entry) skips every leg. NOT colour-only: the label + arrow carry the
// direction as text (design-system R6/R9).
function renderPosition(ctx, row, map) {
  const box = positionBox(row.points, map);
  if (!box) return;
  const fill = function (band, color) {
    if (band.top === null || band.bottom === null) return;
    ctx.globalAlpha = 0.15;
    ctx.fillStyle = color;
    ctx.fillRect(box.left, band.top, box.right - box.left, band.bottom - band.top);
    ctx.globalAlpha = 1;
  };
  fill(box.riskBand, "#ef5350"); // risk (entry -> stop)
  fill(box.rewardBand, "#26a69a"); // reward (entry -> tp)
  ctx.strokeStyle = row.style.color || "#787b86";
  ctx.fillStyle = row.style.color || "#787b86";
  ctx.font = "11px sans-serif";
  box.levels.forEach(function (l) {
    if (l.y === null || l.y === undefined) return;
    ctx.beginPath();
    ctx.moveTo(box.left, l.y);
    ctx.lineTo(box.right, l.y);
    ctx.stroke();
    ctx.fillText(l.label + " " + l.price, box.left + 2, l.y - 2);
  });
  const dir = box.long ? "LONG" : "SHORT";
  const arrow = box.long ? "\u25b2" : "\u25bc";
  ctx.fillText(arrow + " " + dir, box.left + 2, box.rewardBand.top - 4);
  if (box.rr !== null && box.rr !== undefined) {
    ctx.fillText("R:R " + box.rr.toFixed(2), box.left + 2, box.riskBand.bottom + 12);
  }
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
    // Force a redraw after a live row/selection change — the v5 primitive's
    // requestUpdate only (never setData/update: #68). No-op before attach.
    requestUpdate: function () { if (c.requestUpdate) c.requestUpdate(); },
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
    // F5 S3 (R6): a hidden full-width ray MUST NOT influence autoscale.
    autoscaleInfo: function () {
      return row.visible === false ? null : priceRangeFor(row);
    },
  };
}

export { renderShape, makeDrawingPrimitive };
