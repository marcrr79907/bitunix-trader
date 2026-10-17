// Pure drawing geometry tests — node --test (no DOM, no chart lib, no network).
import test from "node:test";
import assert from "node:assert";
import * as core from "../../web/market/templates/market/drawing-core.js";

// A coordinate mapper stub: identity-ish, so expected pixels are obvious.
const mapper = (x, y) => ({ x: () => x, y: () => y });

test("DRAWING_KINDS exposes the six kinds", () => {
  assert.deepStrictEqual(
    core.DRAWING_KINDS.slice().sort(),
    ["fib", "hline", "position", "rect", "text", "trendline"],
  );
});

test("hlinePath maps price to y, ignores time", () => {
  const d = { kind: "hline", points: { price: 50 } };
  assert.deepStrictEqual(core.hlinePath(d, { x: () => 1, y: (p) => p * 2 }), {
    y: 100,
  });
});

test("hlinePath returns null y when price is off-scale", () => {
  const d = { kind: "hline", points: { price: 50 } };
  assert.deepStrictEqual(core.hlinePath(d, { x: () => 1, y: () => null }), {
    y: null,
  });
});

test("trendlinePath maps both anchors", () => {
  const d = {
    kind: "trendline",
    points: { p1: { time: 10, price: 1 }, p2: { time: 20, price: 2 } },
  };
  const out = core.trendlinePath(d, {
    x: (t) => t * 10,
    y: (p) => p * 100,
  });
  assert.deepStrictEqual(out, { a: { x: 100, y: 100 }, b: { x: 200, y: 200 } });
});

test("trendlinePath null-guards each off-bar leg without throwing", () => {
  const d = {
    kind: "trendline",
    points: { p1: { time: 10, price: 1 }, p2: { time: 20, price: 2 } },
  };
  // p2's time has no bar on the axis -> that leg is skipped (null), not a throw.
  const out = core.trendlinePath(d, { x: (t) => (t === 20 ? null : t), y: (p) => p });
  assert.deepStrictEqual(out, { a: { x: 10, y: 1 }, b: null });
});

test("fibLevels interpolates between the two anchors", () => {
  const levels = core.fibLevels(100, 200, [0, 0.5, 1]);
  assert.deepStrictEqual(levels, [
    { ratio: 0, price: 200 },
    { ratio: 0.5, price: 150 },
    { ratio: 1, price: 100 },
  ]);
});

test("fibLevels handles a downward swing", () => {
  const levels = core.fibLevels(200, 100, [0, 1]);
  assert.deepStrictEqual(levels, [
    { ratio: 0, price: 100 },
    { ratio: 1, price: 200 },
  ]);
});

test("fibPath emits a y per level and the anchor x range", () => {
  const d = {
    kind: "fib",
    points: { p1: { time: 10, price: 100 }, p2: { time: 20, price: 200 } },
  };
  const out = core.fibPath(d, { x: (t) => t, y: (p) => p }, [0, 1]);
  assert.strictEqual(out.x1, 10);
  assert.strictEqual(out.x2, 20);
  assert.deepStrictEqual(out.levels, [
    { ratio: 0, price: 200, y: 200 },
    { ratio: 1, price: 100, y: 100 },
  ]);
});

test("rectPath normalizes two corners into a box (any order)", () => {
  const d = {
    kind: "rect",
    points: { p1: { time: 20, price: 5 }, p2: { time: 10, price: 50 } },
  };
  const out = core.rectPath(d, { x: (t) => t, y: (p) => p });
  assert.deepStrictEqual(out, { left: 10, top: 5, width: 10, height: 45 });
});

test("rectPath returns null when a corner is off-bar", () => {
  const d = {
    kind: "rect",
    points: { p1: { time: 20, price: 5 }, p2: { time: 10, price: 50 } },
  };
  assert.strictEqual(core.rectPath(d, { x: () => null, y: (p) => p }), null);
});

test("textPath maps the anchor and carries the label", () => {
  const d = {
    kind: "text",
    points: { time: 7, price: 3, text: "OB" },
  };
  assert.deepStrictEqual(core.textPath(d, { x: (t) => t, y: (p) => p * 2 }), {
    x: 7,
    y: 6,
    text: "OB",
  });
});

test("hitTest returns the nearest anchor within the radius", () => {
  const items = [
    { x: 10, y: 10 },
    { x: 100, y: 100 },
  ];
  // (12,11) is ~2.2px from the first, far from the second.
  assert.strictEqual(core.hitTest(items, 12, 11, 5), 0);
  // Too far from anything -> miss.
  assert.strictEqual(core.hitTest(items, 50, 50, 5), -1);
});

test("pointFromParam converts a click to {time, price}", () => {
  const param = { time: 1700000000, point: { x: 5, y: 42 } };
  assert.deepStrictEqual(core.pointFromParam(param, () => 99.5), {
    time: 1700000000,
    price: 99.5,
  });
});

test("pointFromParam returns null with no bar under the cursor", () => {
  const param = { time: undefined, point: { x: 5, y: 42 } };
  assert.strictEqual(core.pointFromParam(param, () => 99.5), null);
});

test("fromApi normalizes a row and rejects an unknown kind", () => {
  assert.deepStrictEqual(
    core.fromApi({ id: 3, kind: "rect", points: { p1: {} }, style: {} }),
    { id: 3, kind: "rect", points: { p1: {} }, style: {}, visible: true, locked: false },
  );
  assert.strictEqual(core.fromApi({ id: 4, kind: "nope" }), null);
  assert.strictEqual(core.fromApi(null), null);
});

test("fromApi accepts a position row and keeps its points (F6)", () => {
  const points = { entry: { time: 1700000000, price: 50000 }, stop: 49000, take_profit: 52000 };
  assert.deepStrictEqual(
    core.fromApi({ id: 9, kind: "position", points: points, style: {} }),
    { id: 9, kind: "position", points: points, style: {}, visible: true, locked: false },
  );
});

test("fromApi carries visible/locked flags (absent -> visible, unlocked)", () => {
  // Explicit flags pass through.
  assert.deepStrictEqual(
    core.fromApi({ id: 5, kind: "hline", points: { price: 1 }, style: {}, visible: false, locked: true }),
    { id: 5, kind: "hline", points: { price: 1 }, style: {}, visible: false, locked: true },
  );
  // Absent flags default to visible/unlocked (R4: persistent model).
  const noFlags = core.fromApi({ id: 6, kind: "hline", points: { price: 1 }, style: {} });
  assert.strictEqual(noFlags.visible, true);
  assert.strictEqual(noFlags.locked, false);
});

test("toApi builds the POST body shape", () => {
  assert.deepStrictEqual(core.toApi("hline", { price: 1 }, { color: "#f00" }), {
    kind: "hline",
    points: { price: 1 },
    style: { color: "#f00" },
  });
});

test("defaultStyle carries a color per kind and a fib level set", () => {
  assert.strictEqual(core.defaultStyle("hline").color, "#2962ff");
  assert.deepStrictEqual(core.defaultStyle("fib").levels, [
    0, 0.236, 0.382, 0.5, 0.618, 0.786, 1,
  ]);
  assert.strictEqual(core.defaultStyle("rect").fill, true);
});

test("defaultStyle gives position a color + lineWidth (F6)", () => {
  const style = core.defaultStyle("position");
  assert.strictEqual(typeof style.color, "string");
  assert.match(style.color, /^#[0-9a-f]{6}$/i);
  assert.strictEqual(style.lineWidth, 1);
});
