// Pure drawing-click-flow-core tests — node --test (pure core, no DOM).
//
// Spec design D6 / Interfaces: the ONE 1/2/3-click state machine. It is keyed by
// clicksFor(kind), returns the kind-shaped points on the final click, signals a
// dialog need for text/callout, and resets a half-collected draft on a tool switch.
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createFlow } from "../../web/market/templates/market/drawing-click-flow-core.js";

const SRC = readFileSync(
  fileURLToPath(new URL("../../web/market/templates/market/drawing-click-flow-core.js", import.meta.url)),
  "utf8",
);

const at = (time, price) => ({ time: time, price: price });

test("a 2-click kind stays pending then yields {p1,p2} on the second click", () => {
  const flow = createFlow();
  assert.deepStrictEqual(flow.collect("ray", at(1, 10)), { status: "pending" });
  assert.ok(flow.active());
  const out = flow.collect("ray", at(2, 20));
  assert.strictEqual(out.status, "ready");
  assert.strictEqual(out.kind, "ray");
  assert.deepStrictEqual(out.points, { p1: at(1, 10), p2: at(2, 20) });
  assert.strictEqual(flow.active(), false);
});

test("a 3-click kind yields {p1,p2,p3} only on the third click", () => {
  for (const kind of ["channel", "fib_ext"]) {
    const flow = createFlow();
    assert.deepStrictEqual(flow.collect(kind, at(1, 10)), { status: "pending" });
    assert.deepStrictEqual(flow.collect(kind, at(2, 20)), { status: "pending" });
    const out = flow.collect(kind, at(3, 30));
    assert.strictEqual(out.status, "ready", kind);
    assert.deepStrictEqual(out.points, { p1: at(1, 10), p2: at(2, 20), p3: at(3, 30) });
  }
});

test("a 1-click kind finalizes immediately with its shaped point", () => {
  const flow = createFlow();
  assert.deepStrictEqual(flow.collect("vline", at(7, 99)), {
    status: "ready", kind: "vline", points: { time: 7 },
  });
  const flow2 = createFlow();
  assert.deepStrictEqual(flow2.collect("price", at(7, 99)), {
    status: "ready", kind: "price", points: { price: 99 },
  });
});

test("existing kinds resolve their counts and shapes (D6: one machine)", () => {
  const hline = createFlow();
  assert.deepStrictEqual(hline.collect("hline", at(1, 10)), {
    status: "ready", kind: "hline", points: { price: 10 },
  });

  const trend = createFlow();
  trend.collect("trendline", at(1, 10));
  assert.deepStrictEqual(trend.collect("trendline", at(2, 20)).points, {
    p1: at(1, 10), p2: at(2, 20),
  });

  const pos = createFlow();
  pos.collect("position", at(1, 10));
  pos.collect("position", at(2, 20));
  assert.deepStrictEqual(pos.collect("position", at(3, 30)).points, {
    entry: at(1, 10), stop: 20, take_profit: 30,
  });
});

test("text and callout signal a dialog need on their final click", () => {
  const text = createFlow();
  const t = text.collect("text", at(1, 10));
  assert.strictEqual(t.status, "dialog");
  assert.strictEqual(t.kind, "text");
  assert.deepStrictEqual(t.points, { time: 1, price: 10 });

  const callout = createFlow();
  callout.collect("callout", at(1, 10));
  const c = callout.collect("callout", at(2, 20));
  assert.strictEqual(c.status, "dialog");
  assert.strictEqual(c.kind, "callout");
  assert.deepStrictEqual(c.points, { p1: at(1, 10), p2: at(2, 20) });
});

test("a tool switch mid-collection drops the half-built draft", () => {
  const flow = createFlow();
  flow.collect("ray", at(1, 10)); // half a ray
  // Switching to channel starts a NEW draft, not a continuation of the ray.
  assert.deepStrictEqual(flow.collect("channel", at(2, 20)), { status: "pending" });
  assert.deepStrictEqual(flow.collect("channel", at(3, 30)), { status: "pending" });
  const out = flow.collect("channel", at(4, 40));
  assert.deepStrictEqual(out.points, { p1: at(2, 20), p2: at(3, 30), p3: at(4, 40) });
});

test("cancel drops the draft and the next click starts fresh", () => {
  const flow = createFlow();
  flow.collect("ray", at(1, 10));
  assert.strictEqual(flow.active(), true);
  flow.cancel();
  assert.strictEqual(flow.active(), false);
  // The next ray click is a first anchor, not a second.
  assert.deepStrictEqual(flow.collect("ray", at(9, 90)), { status: "pending" });
  assert.deepStrictEqual(flow.collect("ray", at(9, 91)).points, { p1: at(9, 90), p2: at(9, 91) });
});

test("reset clears an active draft (alias of cancel)", () => {
  const flow = createFlow();
  flow.collect("fib_time", at(1, 10));
  assert.strictEqual(flow.active(), true);
  flow.reset();
  assert.strictEqual(flow.active(), false);
});

test("collect degrades a null point and an unknown kind, never throws", () => {
  const flow = createFlow();
  assert.strictEqual(flow.collect("ray", null), null);
  assert.strictEqual(flow.collect("nope", at(1, 2)), null);
  assert.strictEqual(flow.active(), false);
});

test("drawing-click-flow-core is pure and imports cores only", () => {
  assert.ok(/from "\.\/drawing-tools-core\.js"/.test(SRC), "imports drawing-tools-core");
  assert.ok(!/from "(?!\.\/(drawing-tools-core|position-core)\.js)/.test(SRC), "no non-core imports");
  assert.ok(!/document\.|window\.|fetch\(/.test(SRC), "no DOM / no network");
});
