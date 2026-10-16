// drawing-primitive render contract — node --test (canvas stub, no browser).
//
// F5 S3 (R6 delta): a drawing with ``visible:false`` MUST render NOTHING (the
// primitive stays attached) and its ``autoscaleInfo`` MUST return null so a
// hidden full-width ray does not influence autoscale. Geometry comes from the
// pure drawing-core; here we drive renderShape with a recording ctx stub.
import test from "node:test";
import assert from "node:assert";
import {
  renderShape,
  makeDrawingPrimitive,
} from "../../web/market/templates/market/drawing-primitive.js";

function recordingCtx() {
  const calls = [];
  const ctx = {
    calls,
    save: () => calls.push("save"),
    restore: () => calls.push("restore"),
    beginPath: () => calls.push("beginPath"),
    moveTo: () => calls.push("moveTo"),
    lineTo: () => calls.push("lineTo"),
    stroke: () => calls.push("stroke"),
    strokeRect: () => calls.push("strokeRect"),
    fillRect: () => calls.push("fillRect"),
    fillText: () => calls.push("fillText"),
    arc: () => calls.push("arc"),
    fill: () => calls.push("fill"),
    font: "",
    strokeStyle: "",
    fillStyle: "",
    lineWidth: 1,
    globalAlpha: 1,
  };
  return ctx;
}

const MAP = { x: (t) => t, y: (p) => p };
const HLINE = { id: 1, kind: "hline", points: { price: 100 }, style: { color: "#2962ff", lineWidth: 1 } };

test("renderShape draws a visible shape (baseline)", () => {
  const ctx = recordingCtx();
  renderShape(ctx, { width: 100, height: 100 }, HLINE, MAP, false);
  assert.ok(ctx.calls.includes("stroke"), "a visible hline strokes");
});

test("renderShape early-returns blank when visible === false (R6)", () => {
  const ctx = recordingCtx();
  const hidden = { ...HLINE, visible: false };
  renderShape(ctx, { width: 100, height: 100 }, hidden, MAP, false);
  // No draw calls at all — only the save/restore scaffold.
  assert.deepStrictEqual(ctx.calls, ["save", "restore"]);
});

test("renderShape still draws when visible is absent or true", () => {
  const ctx = recordingCtx();
  renderShape(ctx, { width: 100, height: 100 }, { ...HLINE, visible: true }, MAP, false);
  assert.ok(ctx.calls.includes("stroke"));
});

test("autoscaleInfo is null when the drawing is hidden (R6)", () => {
  const visible = makeDrawingPrimitive(HLINE, {});
  assert.deepStrictEqual(visible.autoscaleInfo(), {
    priceRange: { minValue: 100, maxValue: 100 },
  });
  const hidden = makeDrawingPrimitive({ ...HLINE, visible: false }, {});
  assert.strictEqual(hidden.autoscaleInfo(), null);
});

// --- position render (F6 R6) -------------------------------------------------

const POSITION = {
  id: 9,
  kind: "position",
  points: { entry: { time: 10, price: 50 }, stop: 45, take_profit: 60 },
  style: { color: "#26a69a", lineWidth: 1 },
};

test("renderShape draws a position via position-core (zones + levels + R:R)", () => {
  const ctx = recordingCtx();
  renderShape(ctx, { width: 300, height: 300 }, POSITION, MAP, false);
  // Two filled bands (risk + reward) and three level strokes.
  assert.ok(ctx.calls.filter((c) => c === "fillRect").length >= 2, "risk + reward bands");
  assert.ok(ctx.calls.filter((c) => c === "stroke").length >= 3, "three level lines");
  // The LONG/SHORT label + the R:R figure are written as text (not colour-only).
  assert.ok(ctx.calls.filter((c) => c === "fillText").length >= 2, "label + R:R");
});

test("renderShape position degrades (no throw) when the entry is off-bar", () => {
  const ctx = recordingCtx();
  const map = { x: () => null, y: (p) => p };
  assert.doesNotThrow(() =>
    renderShape(ctx, { width: 300, height: 300 }, POSITION, map, false),
  );
  assert.strictEqual(ctx.calls.filter((c) => c === "fillRect").length, 0, "no box off-bar");
});

test("renderShape position draws nothing when hidden (R6)", () => {
  const ctx = recordingCtx();
  renderShape(ctx, { width: 300, height: 300 }, { ...POSITION, visible: false }, MAP, false);
  assert.deepStrictEqual(ctx.calls, ["save", "restore"]);
});

test("autoscaleInfo of a position includes stop and take_profit (R6)", () => {
  const prim = makeDrawingPrimitive(POSITION, {});
  assert.deepStrictEqual(prim.autoscaleInfo(), {
    priceRange: { minValue: 45, maxValue: 60 },
  });
});

test("autoscaleInfo of a hidden position is null (R6)", () => {
  const prim = makeDrawingPrimitive({ ...POSITION, visible: false }, {});
  assert.strictEqual(prim.autoscaleInfo(), null);
});
