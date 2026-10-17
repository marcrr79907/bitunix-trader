// position-draft-core tests — node --test (pure: no DOM, no imports).
//
// F6 D6: the 3-click position collector (entry -> stop -> take_profit). The
// controller owns createDrawing; this pure state machine only accumulates a
// draft and can CANCEL it (Escape, R6). Extracted so it is unit-testable and
// drawings.js stays within the 300-line ceiling.
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createDraft } from "../../web/market/templates/market/position-draft-core.js";

const SRC = readFileSync(
  fileURLToPath(new URL("../../web/market/templates/market/position-draft-core.js", import.meta.url)),
  "utf8",
);

test("collect returns null until the three clicks are complete", () => {
  const d = createDraft();
  assert.strictEqual(d.collect({ time: 1, price: 100 }), null);
  assert.strictEqual(d.collect({ time: 1, price: 90 }), null);
});

test("collect finalizes entry/stop/take_profit on the third click", () => {
  const d = createDraft();
  d.collect({ time: 5, price: 100 });
  d.collect({ time: 5, price: 90 });
  const points = d.collect({ time: 5, price: 120 });
  assert.deepStrictEqual(points, {
    entry: { time: 5, price: 100 },
    stop: 90,
    take_profit: 120,
  });
});

test("cancel drops the pending draft; the next click starts fresh", () => {
  const d = createDraft();
  d.collect({ time: 5, price: 100 }); // entry
  d.collect({ time: 5, price: 90 }); // stop
  assert.strictEqual(d.active(), true);
  d.cancel();
  assert.strictEqual(d.active(), false);
  // A subsequent click begins a NEW draft (entry), not a stop for the dead one.
  assert.strictEqual(d.collect({ time: 9, price: 50 }), null);
  assert.deepStrictEqual(d.collect({ time: 9, price: 40 }), null);
  assert.deepStrictEqual(d.collect({ time: 9, price: 60 }), {
    entry: { time: 9, price: 50 },
    stop: 40,
    take_profit: 60,
  });
});

test("a finalized draft resets active() (the next click starts fresh)", () => {
  const d = createDraft();
  d.collect({ time: 1, price: 10 });
  d.collect({ time: 1, price: 5 });
  d.collect({ time: 1, price: 20 });
  assert.strictEqual(d.active(), false);
});

test("collect degrades a null point without throwing", () => {
  const d = createDraft();
  assert.strictEqual(d.collect(null), null);
  assert.strictEqual(d.active(), false);
});

test("position-draft-core is pure (no DOM, no imports)", () => {
  assert.ok(!/\bimport\b/.test(SRC), "no imports");
  assert.ok(!/document\.|window\./.test(SRC), "no DOM / no window");
});
