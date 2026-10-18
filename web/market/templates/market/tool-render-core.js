// tool-render-core.js — canvas drawing for the eight F9 kinds (extracted from
// drawing-primitive.js to keep that module under the 300-line ceiling).
//
// Takes a 2D context + geometry from the PURE drawing-tools-core; no DOM, no
// chart library, no network of its own. Nothing here is colour-only: ratio/price
// labels carry the meaning (design-system R6). Off-bar legs are skipped, never
// thrown. (Canvas access lives here, not in the pure geometry core.)
import * as Tools from "./drawing-tools-core.js";
import { token } from "./theme-core.js";

// R2 #223: ONE label font + a contrasting halo (a bare fillText vanished).
const LABEL_FONT = "11px sans-serif";

function label(ctx, text, x, y, font) {
  const fill = ctx.fillStyle;
  ctx.font = font || LABEL_FONT;
  // The halo is the page background token; the text keeps the row/palette colour.
  ctx.strokeStyle = token("--bg", "#0e1117");
  ctx.lineWidth = 3;
  ctx.strokeText(text, x, y);
  ctx.strokeStyle = fill;
  ctx.lineWidth = 1;
  ctx.fillText(text, x, y);
}

// R2 #223: callout = connector leg + arrowhead at ``a`` + a rounded balloon
// around the text at ``b``. Pure canvas; no new palette (inherits the row style).
function drawCallout(ctx, p) {
  ctx.beginPath(); ctx.moveTo(p.a.x, p.a.y); ctx.lineTo(p.b.x, p.b.y); ctx.stroke();
  const ang = Math.atan2(p.b.y - p.a.y, p.b.x - p.a.x);
  const head = 8;
  ctx.beginPath();
  ctx.moveTo(p.a.x, p.a.y);
  ctx.lineTo(p.a.x + Math.cos(ang + 0.4) * head, p.a.y + Math.sin(ang + 0.4) * head);
  ctx.moveTo(p.a.x, p.a.y);
  ctx.lineTo(p.a.x + Math.cos(ang - 0.4) * head, p.a.y + Math.sin(ang - 0.4) * head);
  ctx.stroke();
  const text = String(p.text == null ? "" : p.text);
  const stroke = ctx.strokeStyle;
  const w = ctx.measureText ? ctx.measureText(text).width : text.length * 6;
  const x = p.b.x + 6, y = p.b.y - 20;
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(x, y, w + 12, 20, 4);
  else ctx.rect(x, y, w + 12, 20);
  // A surface-filled balloon keeps the text legible (the row colour is the text).
  ctx.fillStyle = token("--surface", "#1c2230");
  ctx.fill();
  ctx.fillStyle = stroke;
  ctx.stroke();
  ctx.fillText(text, x + 6, y + 14);
}

// F9 S3 (R6): the canvas switch for the eight new kinds. Geometry comes from
// drawing-tools-core.toolPath (pure); nothing here is colour-only — ratio/price
// labels carry the meaning (design-system R6). Off-bar legs are skipped, never
// thrown. Canvas access lives here, not in the pure core.
function renderTool(ctx, size, row, map) {
  const kind = row.kind;
  const p = Tools.toolPath(kind, row, map);
  if (!p) return;
  if (kind === "ray") {
    if (p.a && p.b) {
      ctx.beginPath(); ctx.moveTo(p.a.x, p.a.y); ctx.lineTo(p.b.x, p.b.y); ctx.stroke();
    }
  } else if (kind === "vline") {
    if (p.x !== null && p.x !== undefined) {
      ctx.beginPath(); ctx.moveTo(p.x, 0); ctx.lineTo(p.x, size.height); ctx.stroke();
    }
  } else if (kind === "channel") {
    [[p.a, p.b], [p.c, p.d]].forEach(function (seg) {
      if (seg[0] && seg[1]) {
        ctx.beginPath(); ctx.moveTo(seg[0].x, seg[0].y); ctx.lineTo(seg[1].x, seg[1].y); ctx.stroke();
      }
    });
  } else if (kind === "price") {
    if (p.y !== null && p.y !== undefined) {
      ctx.beginPath(); ctx.moveTo(0, p.y); ctx.lineTo(size.width, p.y); ctx.stroke();
      // R2 #223: right-axis tag, formatted like the axis (never String(raw)).
      const fmt = map && typeof map.format === "function" ? map.format : String;
      ctx.textAlign = "right";
      label(ctx, fmt(p.price), size.width - 4, p.y - 4);
      ctx.textAlign = "left";
    }
  } else if (kind === "callout") {
    // R2 #223: a balloon + an arrowhead, not a bare line.
    if (p.a && p.b) drawCallout(ctx, p);
  } else if (kind === "fib_ext") {
    // #216: an off-bar x anchor skips the whole body (never coerce null -> 0).
    if (p.x1 === null || p.x1 === undefined || p.x2 === null || p.x2 === undefined) return;
    (p.levels || []).forEach(function (l) {
      if (l.y === null || l.y === undefined) return;
      ctx.beginPath(); ctx.moveTo(p.x1, l.y); ctx.lineTo(p.x2, l.y); ctx.stroke();
      label(ctx, l.ratio + "  " + l.price, p.x1, l.y - 2);
    });
  } else if (kind === "fib_time") {
    ((p && p.levels) || []).forEach(function (l) {
      if (l.x === null || l.x === undefined) return;
      ctx.beginPath(); ctx.moveTo(l.x, 0); ctx.lineTo(l.x, size.height); ctx.stroke();
      label(ctx, String(l.ratio), l.x + 2, 12);
    });
  } else if (kind === "fib_zone") {
    // #216: an off-bar x anchor or an off-scale level skips the band entirely.
    if (p.x1 === null || p.x1 === undefined || p.x2 === null || p.x2 === undefined) return;
    (p.bands || []).forEach(function (b) {
      if (b.yLo === null || b.yLo === undefined
        || b.yHi === null || b.yHi === undefined) return;
      const top = Math.min(b.yLo, b.yHi);
      ctx.globalAlpha = 0.15;
      ctx.fillRect(p.x1, top, p.x2 - p.x1, Math.abs(b.yHi - b.yLo));
      ctx.globalAlpha = 1;
      ctx.strokeRect(p.x1, top, p.x2 - p.x1, Math.abs(b.yHi - b.yLo));
      label(ctx, b.ratioLo + "-" + b.ratioHi, p.x1 + 2, top - 2);
    });
  }
}

export { LABEL_FONT, label, renderTool };
