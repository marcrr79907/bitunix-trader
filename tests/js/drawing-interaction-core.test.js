// Pure interaction-core tests — node --test (no DOM, no chart lib, no network).
//
// The core owns drawing geometry for selection/drag: per-kind handles, a
// pointer->grab resolver (handles win over body), and a pure drag transform.
// A pixel map is stubbed; the identity map makes data and pixels equal so the
// expectations stay obvious.
import test from "node:test";
import assert from "node:assert";
import * as core from "../../web/market/templates/market/drawing-interaction-core.js";

const ident = {
  x: (t) => t,
  y: (p) => p,
  time: (px) => px,
  price: (py) => py,
};

const trendline = () => ({
  id: 1,
  kind: "trendline",
  points: { p1: { time: 10, price: 1 }, p2: { time: 20, price: 2 } },
});

// --- frozen constants --------------------------------------------------------

test("HANDLE_RADIUS and BODY_RADIUS are frozen", () => {
  assert.strictEqual(core.HANDLE_RADIUS, 6);
  assert.strictEqual(core.BODY_RADIUS, 4);
});

// --- handlesFor --------------------------------------------------------------

test("handlesFor hline returns one price handle at x 0", () => {
  assert.deepStrictEqual(core.handlesFor("hline", { price: 50 }, ident), [
    { id: "price", x: 0, y: 50 },
  ]);
});

test("handlesFor trendline returns p1 and p2", () => {
  assert.deepStrictEqual(
    core.handlesFor("trendline", { p1: { time: 10, price: 1 }, p2: { time: 20, price: 2 } }, ident),
    [
      { id: "p1", x: 10, y: 1 },
      { id: "p2", x: 20, y: 2 },
    ],
  );
});

test("handlesFor fib returns p1 and p2", () => {
  assert.deepStrictEqual(
    core.handlesFor("fib", { p1: { time: 10, price: 1 }, p2: { time: 20, price: 2 } }, ident),
    [
      { id: "p1", x: 10, y: 1 },
      { id: "p2", x: 20, y: 2 },
    ],
  );
});

test("handlesFor rect returns the four corners", () => {
  assert.deepStrictEqual(
    core.handlesFor("rect", { p1: { time: 10, price: 1 }, p2: { time: 20, price: 2 } }, ident),
    [
      { id: "tl", x: 10, y: 1 },
      { id: "tr", x: 20, y: 1 },
      { id: "bl", x: 10, y: 2 },
      { id: "br", x: 20, y: 2 },
    ],
  );
});

test("handlesFor text returns the anchor", () => {
  assert.deepStrictEqual(core.handlesFor("text", { time: 7, price: 3, text: "n" }, ident), [
    { id: "anchor", x: 7, y: 3 },
  ]);
});

test("handlesFor resolves 1 / 2 / 2 / 4 / 1 per kind", () => {
  const pts = { time: 7, price: 3, p1: { time: 10, price: 1 }, p2: { time: 20, price: 2 } };
  assert.strictEqual(core.handlesFor("hline", { price: 50 }, ident).length, 1);
  assert.strictEqual(core.handlesFor("trendline", pts, ident).length, 2);
  assert.strictEqual(core.handlesFor("fib", pts, ident).length, 2);
  assert.strictEqual(core.handlesFor("rect", pts, ident).length, 4);
  assert.strictEqual(core.handlesFor("text", pts, ident).length, 1);
});

test("handlesFor omits an off-bar anchor", () => {
  const map = { ...ident, x: (t) => (t === 20 ? null : t) };
  const hs = core.handlesFor("trendline", { p1: { time: 10, price: 1 }, p2: { time: 20, price: 2 } }, map);
  assert.strictEqual(hs.length, 1);
  assert.strictEqual(hs[0].id, "p1");
});

test("handlesFor never throws on malformed input", () => {
  assert.deepStrictEqual(core.handlesFor("nope", {}, ident), []);
  assert.doesNotThrow(() => core.handlesFor("rect", {}, ident));
});

// --- grabHandle --------------------------------------------------------------

test("grabHandle prefers a handle over the body", () => {
  const row = { id: 7, kind: "rect", points: { p1: { time: 10, price: 10 }, p2: { time: 100, price: 90 } } };
  // (12,12) is ~2.8px from the tl corner (10,10) but also inside the body.
  assert.deepStrictEqual(core.grabHandle([row], 12, 12, ident), { id: 7, target: 0 });
});

test("grabHandle falls back to the body", () => {
  const row = { id: 7, kind: "rect", points: { p1: { time: 10, price: 10 }, p2: { time: 100, price: 90 } } };
  assert.deepStrictEqual(core.grabHandle([row], 55, 50, ident), { id: 7, target: "body" });
});

test("grabHandle returns null on a miss", () => {
  const row = trendline();
  assert.strictEqual(core.grabHandle([row], 5000, 5000, ident), null);
});

test("grabHandle hits an hline body along the line and its handle at x 0", () => {
  const row = { id: 3, kind: "hline", points: { price: 50 } };
  assert.deepStrictEqual(core.grabHandle([row], 400, 51, ident), { id: 3, target: "body" });
  assert.deepStrictEqual(core.grabHandle([row], 0, 50, ident), { id: 3, target: 0 });
});

test("grabHandle picks the topmost shape", () => {
  const a = { id: 1, kind: "hline", points: { price: 50 } };
  const b = { id: 2, kind: "hline", points: { price: 50 } };
  assert.deepStrictEqual(core.grabHandle([a, b], 400, 50, ident), { id: 2, target: "body" });
});

test("grabHandle never throws on malformed input", () => {
  assert.strictEqual(core.grabHandle([], 0, 0, ident), null);
  assert.doesNotThrow(() => core.grabHandle([null, {}], 0, 0, ident));
});

// --- applyDrag: body translate ----------------------------------------------

test("applyDrag body translates a trendline and does not mutate the row", () => {
  const row = trendline();
  assert.deepStrictEqual(core.applyDrag(row, "body", 5, 5, ident), {
    p1: { time: 15, price: 6 },
    p2: { time: 25, price: 7 },
  });
  assert.deepStrictEqual(row.points, { p1: { time: 10, price: 1 }, p2: { time: 20, price: 2 } });
});

test("applyDrag hline body moves price only, never adds time", () => {
  assert.deepStrictEqual(core.applyDrag({ kind: "hline", points: { price: 50 } }, "body", 999, 10, ident), {
    price: 60,
  });
});

test("applyDrag text body translates the anchor and keeps the label", () => {
  assert.deepStrictEqual(
    core.applyDrag({ kind: "text", points: { time: 5, price: 3, text: "n" } }, "body", 2, 4, ident),
    { time: 7, price: 7, text: "n" },
  );
});

test("applyDrag rect body shifts both corners", () => {
  assert.deepStrictEqual(
    core.applyDrag({ kind: "rect", points: { p1: { time: 10, price: 1 }, p2: { time: 20, price: 2 } } }, "body", 3, 4, ident),
    { p1: { time: 13, price: 5 }, p2: { time: 23, price: 6 } },
  );
});

// --- applyDrag: single anchor ------------------------------------------------

test("applyDrag moves only the grabbed trendline anchor", () => {
  assert.deepStrictEqual(core.applyDrag(trendline(), 1, 3, 4, ident), {
    p1: { time: 10, price: 1 },
    p2: { time: 23, price: 6 },
  });
});

test("applyDrag hline handle moves price", () => {
  assert.deepStrictEqual(core.applyDrag({ kind: "hline", points: { price: 50 } }, 0, 5, -5, ident), {
    price: 45,
  });
});

test("applyDrag rect corner keeps the opposite corner fixed", () => {
  const row = { kind: "rect", points: { p1: { time: 10, price: 1 }, p2: { time: 20, price: 2 } } };
  // tl (index 0) moves by (-5,-3): tl pixel (10,1) -> (5,-2); br stays.
  assert.deepStrictEqual(core.applyDrag(row, 0, -5, -3, ident), {
    p1: { time: 5, price: -2 },
    p2: { time: 20, price: 2 },
  });
});

// --- applyDrag: null inverse + determinism ----------------------------------

test("applyDrag keeps the old component when the inverse is null", () => {
  const map = { ...ident, price: () => null };
  assert.deepStrictEqual(core.applyDrag(trendline(), "body", 5, 5, map), {
    p1: { time: 15, price: 1 },
    p2: { time: 25, price: 2 },
  });
});

test("applyDrag hline keeps price when the y axis is off-scale", () => {
  const map = { ...ident, y: () => null };
  assert.deepStrictEqual(core.applyDrag({ kind: "hline", points: { price: 50 } }, "body", 0, 10, map), {
    price: 50,
  });
});

test("applyDrag is deterministic and never mutates its input", () => {
  const row = { kind: "fib", points: { p1: { time: 10, price: 1 }, p2: { time: 20, price: 2 } } };
  const before = JSON.parse(JSON.stringify(row));
  const a = core.applyDrag(row, 0, 3, 3, ident);
  const b = core.applyDrag(row, 0, 3, 3, ident);
  assert.deepStrictEqual(a, b);
  assert.deepStrictEqual(row, before);
});

test("applyDrag never throws on malformed input", () => {
  assert.doesNotThrow(() => core.applyDrag({}, "body", 1, 1, ident));
  assert.doesNotThrow(() => core.applyDrag({ kind: "trendline" }, 0, 1, 1, ident));
  assert.doesNotThrow(() => core.applyDrag(null, "body", 1, 1, ident));
});

// --- position kind (F6 R10) --------------------------------------------------

const position = () => ({
  id: 9,
  kind: "position",
  points: { entry: { time: 10, price: 50 }, stop: 45, take_profit: 60 },
});

test("handlesFor position returns the 4 handles (entry anchor + 3 levels)", () => {
  // entry anchor at the entry column; levels on the right edge (BOX_WIDTH=120).
  assert.deepStrictEqual(core.handlesFor("position", position().points, ident), [
    { id: "entry", x: 10, y: 50 },
    { id: "entry_price", x: 130, y: 50 },
    { id: "stop", x: 130, y: 45 },
    { id: "take_profit", x: 130, y: 60 },
  ]);
});

test("handlesFor resolves 1 / 2 / 2 / 4 / 1 / 4 per kind", () => {
  const pts = { time: 7, price: 3, p1: { time: 10, price: 1 }, p2: { time: 20, price: 2 } };
  assert.strictEqual(core.handlesFor("hline", { price: 50 }, ident).length, 1);
  assert.strictEqual(core.handlesFor("trendline", pts, ident).length, 2);
  assert.strictEqual(core.handlesFor("fib", pts, ident).length, 2);
  assert.strictEqual(core.handlesFor("rect", pts, ident).length, 4);
  assert.strictEqual(core.handlesFor("text", pts, ident).length, 1);
  assert.strictEqual(core.handlesFor("position", position().points, ident).length, 4);
});

test("handlesFor position omits everything when the entry is off-bar", () => {
  const map = { ...ident, x: () => null };
  assert.deepStrictEqual(core.handlesFor("position", position().points, map), []);
});

test("bodyHit position covers the entry->stop and entry->tp band", () => {
  const row = position();
  // Inside the box (x within [left,right], y between stop and tp).
  assert.strictEqual(core.bodyHit(row, 60, 52, ident), true);
  // x to the right of the box -> miss.
  assert.strictEqual(core.bodyHit(row, 400, 52, ident), false);
  // y above the highest level (tp 60) -> miss.
  assert.strictEqual(core.bodyHit(row, 60, 200, ident), false);
});

test("applyDrag position moves ONLY the dragged stop level", () => {
  const row = position();
  const out = core.applyDrag(row, 2, 0, -5, ident); // index 2 = stop
  assert.deepStrictEqual(out, {
    entry: { time: 10, price: 50 },
    stop: 40,
    take_profit: 60,
  });
  // input untouched (never mutates).
  assert.deepStrictEqual(row.points, { entry: { time: 10, price: 50 }, stop: 45, take_profit: 60 });
});

test("applyDrag position moves ONLY the dragged take_profit level", () => {
  assert.deepStrictEqual(core.applyDrag(position(), 3, 0, 7, ident), {
    entry: { time: 10, price: 50 },
    stop: 45,
    take_profit: 67,
  });
});

test("applyDrag position body shifts all three levels + the anchor column", () => {
  assert.deepStrictEqual(core.applyDrag(position(), "body", 3, 4, ident), {
    entry: { time: 13, price: 54 },
    stop: 49,
    take_profit: 64,
  });
});

test("applyDrag position entry_price level moves only the entry price", () => {
  assert.deepStrictEqual(core.applyDrag(position(), 1, 0, -2, ident), {
    entry: { time: 10, price: 48 },
    stop: 45,
    take_profit: 60,
  });
});

test("applyDrag position entry anchor moves the entry (time + price)", () => {
  assert.deepStrictEqual(core.applyDrag(position(), 0, 4, -2, ident), {
    entry: { time: 14, price: 48 },
    stop: 45,
    take_profit: 60,
  });
});

test("applyDrag position keeps a level when the y inverse is null", () => {
  const map = { ...ident, price: () => null };
  assert.deepStrictEqual(core.applyDrag(position(), 2, 0, -5, map), {
    entry: { time: 10, price: 50 },
    stop: 45,
    take_profit: 60,
  });
});

test("grabHandle resolves a position level handle", () => {
  // stop handle sits at (right=130, y=45).
  assert.deepStrictEqual(core.grabHandle([position()], 130, 45, ident), { id: 9, target: 2 });
});

// --- F9 kinds: handlesFor / bodyHit / applyDrag dispatch (F9 S3 R10) ----------

const F9_POINTS = {
  ray: { p1: { time: 0, price: 0 }, p2: { time: 10, price: 10 } },
  vline: { time: 42 },
  channel: { p1: { time: 0, price: 0 }, p2: { time: 10, price: 10 }, p3: { time: 0, price: 20 } },
  price: { price: 50 },
  callout: { p1: { time: 0, price: 0 }, p2: { time: 10, price: 10 }, text: "OB" },
  fib_ext: { p1: { time: 0, price: 0 }, p2: { time: 10, price: 10 }, p3: { time: 20, price: 20 } },
  fib_time: { p1: { time: 0, price: 0 }, p2: { time: 10, price: 10 } },
  fib_zone: { p1: { time: 0, price: 0 }, p2: { time: 10, price: 10 } },
};
const F9_COUNT = {
  ray: 2, callout: 2, fib_time: 2, fib_zone: 2, channel: 3, fib_ext: 3, vline: 1, price: 1,
};

test("handlesFor resolves the F9 per-kind counts 2/2/2/2/3/3/1/1 (F9 S3 R10)", () => {
  for (const kind of Object.keys(F9_COUNT)) {
    assert.strictEqual(
      core.handlesFor(kind, F9_POINTS[kind], ident).length,
      F9_COUNT[kind],
      kind,
    );
  }
});

test("applyDrag moves ONLY the dragged F9 anchor (channel p3) (F9 S3 R10)", () => {
  const row = { kind: "channel", points: F9_POINTS.channel };
  const out = core.applyDrag(row, 2, 3, 4, ident); // index 2 = p3
  assert.deepStrictEqual(out.p1, { time: 0, price: 0 });
  assert.deepStrictEqual(out.p2, { time: 10, price: 10 });
  assert.deepStrictEqual(out.p3, { time: 3, price: 24 });
});

test("applyDrag F9 body translates every anchor (fib_ext) (F9 S3 R10)", () => {
  const out = core.applyDrag({ kind: "fib_ext", points: F9_POINTS.fib_ext }, "body", 2, 3, ident);
  assert.deepStrictEqual(out.p1, { time: 2, price: 3 });
  assert.deepStrictEqual(out.p2, { time: 12, price: 13 });
  assert.deepStrictEqual(out.p3, { time: 22, price: 23 });
});

test("applyDrag vline moves time only and adds no price (F9 S3 R10)", () => {
  assert.deepStrictEqual(
    core.applyDrag({ kind: "vline", points: { time: 42 } }, "body", 5, 9, ident),
    { time: 47 },
  );
});

test("applyDrag price moves price only and adds no time (F9 S3 R10)", () => {
  assert.deepStrictEqual(
    core.applyDrag({ kind: "price", points: { price: 50 } }, "body", 7, 5, ident),
    { price: 55 },
  );
});

test("bodyHit dispatches F9 kinds to the descriptor (ray/price) (F9 S3 R10)", () => {
  assert.strictEqual(core.bodyHit({ kind: "ray", points: F9_POINTS.ray }, 500, 500, {
    ...ident, right: 1000,
  }), true);
  assert.strictEqual(core.bodyHit({ kind: "price", points: { price: 50 } }, 999, 51, ident), true);
  assert.strictEqual(core.bodyHit({ kind: "price", points: { price: 50 } }, 999, 90, ident), false);
});
