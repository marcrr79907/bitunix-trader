// Pure fib-tools-core tests — node --test (no DOM, no chart lib, no network).
//
// Spec chart-drawings R6 (fib_ext/time/zone geometry), design D4 (FIB_EXT_RATIOS
// distinct from FIB_RATIOS), and the "ratio 0 == p2" orientation guard (R11).
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  FIB_EXT_RATIOS,
  fibExtLevels,
  fibTimePath,
  fibZoneBands,
} from "../../web/market/templates/market/fib-tools-core.js";

const SRC = readFileSync(
  fileURLToPath(new URL("../../web/market/templates/market/fib-tools-core.js", import.meta.url)),
  "utf8",
);

const MAP = { x: (t) => t, y: (p) => p };
const SWING = { p1: { time: 10, price: 100 }, p2: { time: 20, price: 200 }, p3: { time: 30, price: 150 } };

function close(actual, expected) {
  assert.ok(Math.abs(actual - expected) < 1e-9, actual + " ~ " + expected);
}

test("FIB_EXT_RATIOS is the six extension ratios (D4)", () => {
  assert.deepStrictEqual(FIB_EXT_RATIOS, [0, 0.618, 1, 1.272, 1.618, 2.618]);
});

test("fibExtLevels: ratio 0 sits on p2's price (anchor), not p1", () => {
  const levels = fibExtLevels(SWING, MAP, [0, 1]);
  assert.deepStrictEqual(levels, [
    { ratio: 0, price: 200, y: 200 },
    { ratio: 1, price: 300, y: 300 },
  ]);
});

test("fibExtLevels: ratio 1 projects beyond p2 on the default ratios", () => {
  const levels = fibExtLevels(SWING, MAP);
  assert.strictEqual(levels.length, 6);
  close(levels[0].price, 200);
  close(levels[2].price, 300); // ratio 1 -> 2*p2 - p1
  close(levels[5].price, 200 + (200 - 100) * 2.618);
});

test("fibExtLevels degrades a missing swing to an empty list", () => {
  assert.deepStrictEqual(fibExtLevels(null, MAP), []);
  assert.deepStrictEqual(fibExtLevels({ p1: { price: 100 } }, MAP), []);
});

test("fibTimePath maps each FIB_RATIOS level to a time and an x", () => {
  const out = fibTimePath(SWING, { x: (t) => t * 2 });
  assert.strictEqual(out.levels.length, 7);
  assert.deepStrictEqual(out.levels[0], { ratio: 0, time: 10, x: 20 });
  assert.deepStrictEqual(out.levels[6], { ratio: 1, time: 20, x: 40 });
});

test("fibTimePath returns null when the two-anchor span is missing", () => {
  assert.strictEqual(fibTimePath({ p1: { time: 10 } }, MAP), null);
  assert.strictEqual(fibTimePath(null, MAP), null);
});

test("fibTimePath leaves x null when the mapper has no bar (off-bar leg)", () => {
  const out = fibTimePath(SWING, { x: () => null });
  assert.ok(out.levels.every((l) => l.x === null));
});

test("fibZoneBands makes consecutive bands with ratio 0 == p2", () => {
  const bands = fibZoneBands(SWING, MAP);
  assert.strictEqual(bands.length, 6);
  assert.strictEqual(bands[0].ratioLo, 0);
  assert.strictEqual(bands[0].priceLo, 200); // ratio 0 == p2
  assert.strictEqual(bands[0].ratioHi, 0.236);
});

test("fibZoneBands skips a band whose y maps off-scale", () => {
  // The ratio-1 level (price 100) has no y -> only its band (0.786->1) drops.
  const bands = fibZoneBands(SWING, { y: (p) => (p === 100 ? null : p) });
  assert.strictEqual(bands.length, 5);
});

test("fib-tools-core is pure and imports drawing-core only", () => {
  assert.ok(/from "\.\/drawing-core\.js"/.test(SRC), "imports drawing-core");
  assert.ok(!/from "(?!\.\/drawing-core\.js)/.test(SRC), "imports nothing else");
  assert.ok(!/document\.|window\.|fetch\(/.test(SRC), "no DOM / no network");
});
