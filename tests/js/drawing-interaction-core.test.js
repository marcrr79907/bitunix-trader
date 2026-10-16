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
