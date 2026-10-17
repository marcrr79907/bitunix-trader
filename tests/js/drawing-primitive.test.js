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
    fills: [], // fillStyle captured at each fillRect (F6 UI #193 zone colours)
    save: () => calls.push("save"),
    restore: () => calls.push("restore"),
    beginPath: () => calls.push("beginPath"),
    moveTo: () => calls.push("moveTo"),
    lineTo: () => calls.push("lineTo"),
    stroke: () => calls.push("stroke"),
    strokeRect: () => calls.push("strokeRect"),
    fillRect: () => { calls.push("fillRect"); ctx.fills.push(ctx.fillStyle); },
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

// --- position zone colours read shell tokens (F6 UI #193 / R9) ----------------

function withTokens(values, fn) {
  const prevDoc = globalThis.document;
  const prevGcs = globalThis.getComputedStyle;
  globalThis.document = { documentElement: {} };
  globalThis.getComputedStyle = () => ({
    getPropertyValue: (n) => values[n] || "",
  });
  try {
    return fn();
  } finally {
    if (prevDoc === undefined) delete globalThis.document;
    else globalThis.document = prevDoc;
    if (prevGcs === undefined) delete globalThis.getComputedStyle;
    else globalThis.getComputedStyle = prevGcs;
  }
}

test("position zones paint with the resolved --dn/--up tokens, not literals (R9)", () => {
  // Deliberately NON-standard token values so a hard-coded literal fails.
  const ctx = recordingCtx();
  withTokens({ "--dn": "#cf222e", "--up": "#1a7f37", "--muted": "#57606a" }, () => {
    renderShape(ctx, { width: 300, height: 300 }, POSITION, MAP, false);
  });
  assert.ok(ctx.fills.includes("#cf222e"), `risk uses --dn: ${ctx.fills}`);
  assert.ok(ctx.fills.includes("#1a7f37"), `reward uses --up: ${ctx.fills}`);
  assert.ok(!ctx.fills.includes("#ef5350"), "risk literal must not be painted");
  assert.ok(!ctx.fills.includes("#26a69a"), "reward literal must not be painted");
});

test("position zones fall back to the literals with no DOM (R9)", () => {
  const ctx = recordingCtx();
  renderShape(ctx, { width: 300, height: 300 }, POSITION, MAP, false);
  assert.ok(ctx.fills.includes("#ef5350"), `risk fallback: ${ctx.fills}`);
  assert.ok(ctx.fills.includes("#26a69a"), `reward fallback: ${ctx.fills}`);
});

// --- F9 kinds render dispatch (F9 S3 R6) -------------------------------------

const MAPR = { x: (t) => t, y: (p) => p, right: 1000 };

// One representative row per F9 kind.
const F9_ROWS = {
  ray: { kind: "ray", points: { p1: { time: 0, price: 0 }, p2: { time: 10, price: 10 } } },
  vline: { kind: "vline", points: { time: 42 } },
  channel: {
    kind: "channel",
    points: { p1: { time: 0, price: 0 }, p2: { time: 10, price: 10 }, p3: { time: 0, price: 20 } },
  },
  price: { kind: "price", points: { price: 50 } },
  callout: {
    kind: "callout",
    points: { p1: { time: 0, price: 0 }, p2: { time: 10, price: 10 }, text: "OB" },
  },
  fib_ext: {
    kind: "fib_ext",
    points: { p1: { time: 0, price: 0 }, p2: { time: 10, price: 10 }, p3: { time: 20, price: 20 } },
  },
  fib_time: { kind: "fib_time", points: { p1: { time: 0 }, p2: { time: 10 } } },
  fib_zone: {
    kind: "fib_zone",
    points: { p1: { time: 0, price: 0 }, p2: { time: 10, price: 10 } },
  },
};

test("renderShape dispatches each F9 kind to renderTool without throwing (R6)", () => {
  for (const kind of Object.keys(F9_ROWS)) {
    const ctx = recordingCtx();
    const row = { ...F9_ROWS[kind], style: { color: "#2962ff", lineWidth: 1 } };
    assert.doesNotThrow(
      () => renderShape(ctx, { width: 300, height: 300 }, row, MAPR, false),
      kind,
    );
    const draws = ctx.calls.filter((c) => c === "stroke" || c === "fillRect" || c === "fillText");
    assert.ok(draws.length > 0, `${kind} draws something`);
  }
});

test("renderShape honours the hidden rule for F9 kinds too (R6)", () => {
  for (const kind of Object.keys(F9_ROWS)) {
    const ctx = recordingCtx();
    const row = { ...F9_ROWS[kind], visible: false, style: {} };
    renderShape(ctx, { width: 300, height: 300 }, row, MAPR, false);
    assert.deepStrictEqual(ctx.calls, ["save", "restore"], kind);
  }
});

test("price/ray/vline/channel are distinguished by shape (strokes) (R6)", () => {
  for (const kind of ["ray", "vline", "channel", "price"]) {
    const ctx = recordingCtx();
    renderShape(ctx, { width: 300, height: 300 }, { ...F9_ROWS[kind], style: {} }, MAPR, false);
    assert.ok(ctx.calls.filter((c) => c === "stroke").length > 0, kind);
  }
});

test("price draws a right-axis price label, not colour alone (R6/design-system)", () => {
  const ctx = recordingCtx();
  renderShape(ctx, { width: 300, height: 300 }, { ...F9_ROWS.price, style: {} }, MAPR, false);
  assert.ok(ctx.calls.includes("fillText"), "price carries a text label");
});

test("fib_ext/fib_time/fib_zone show ratio labels (R6/design-system)", () => {
  for (const kind of ["fib_ext", "fib_time", "fib_zone"]) {
    const ctx = recordingCtx();
    renderShape(ctx, { width: 300, height: 300 }, { ...F9_ROWS[kind], style: {} }, MAPR, false);
    assert.ok(ctx.calls.includes("fillText"), `${kind} shows ratio labels`);
  }
});

test("callout draws its text balloon (R6/design-system)", () => {
  const ctx = recordingCtx();
  renderShape(ctx, { width: 300, height: 300 }, { ...F9_ROWS.callout, style: {} }, MAPR, false);
  assert.ok(ctx.calls.includes("fillText"), "callout shows its text");
});

test("autoscaleInfo of a channel/fib_ext includes p3 (R6)", () => {
  const channel = { kind: "channel", points: {
    p1: { time: 0, price: 0 }, p2: { time: 10, price: 10 }, p3: { time: 20, price: 99 } } };
  assert.deepStrictEqual(makeDrawingPrimitive(channel, {}).autoscaleInfo(), {
    priceRange: { minValue: 0, maxValue: 99 },
  });
  const fibExt = { kind: "fib_ext", points: {
    p1: { time: 0, price: 5 }, p2: { time: 10, price: 10 }, p3: { time: 20, price: 42 } } };
  assert.deepStrictEqual(makeDrawingPrimitive(fibExt, {}).autoscaleInfo(), {
    priceRange: { minValue: 5, maxValue: 42 },
  });
});

test("autoscaleInfo of a price drawing includes its price (R6)", () => {
  const prim = makeDrawingPrimitive({ kind: "price", points: { price: 50 } }, {});
  assert.deepStrictEqual(prim.autoscaleInfo(), {
    priceRange: { minValue: 50, maxValue: 50 },
  });
});
