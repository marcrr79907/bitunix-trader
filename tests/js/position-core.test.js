// Pure position-core tests — node --test (no DOM, no chart lib, no network).
//
// Spec chart-drawings R5 (levels schema), R6 (risk/reward zones), R10 (4 handles)
// and the smc-signals R3 R:R mirror. The core is pure and imports nothing.
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  BOX_WIDTH,
  levelsFrom,
  riskReward,
  positionBox,
  positionHandles,
  defaultPositionStyle,
} from "../../web/market/templates/market/position-core.js";

const SRC = readFileSync(
  fileURLToPath(new URL("../../web/market/templates/market/position-core.js", import.meta.url)),
  "utf8",
);

const MAP = { x: (t) => t, y: (p) => p };
const LONG = { entry: { time: 10, price: 100 }, stop: 90, take_profit: 120 };
const SHORT = { entry: { time: 10, price: 100 }, stop: 110, take_profit: 80 };

test("BOX_WIDTH is the 120px box width", () => {
  assert.strictEqual(BOX_WIDTH, 120);
});

test("levelsFrom returns the normalized long shape", () => {
  assert.deepStrictEqual(levelsFrom(LONG), {
    entry: 100,
    stop: 90,
    takeProfit: 120,
    long: true,
  });
});

test("levelsFrom flags a short (stop above entry)", () => {
  assert.deepStrictEqual(levelsFrom(SHORT), {
    entry: 100,
    stop: 110,
    takeProfit: 80,
    long: false,
  });
});

test("levelsFrom returns null on invalid or missing levels", () => {
  assert.strictEqual(levelsFrom(null), null);
  assert.strictEqual(levelsFrom({}), null);
  assert.strictEqual(levelsFrom({ entry: { price: 100 }, stop: "x", take_profit: 1 }), null);
  assert.strictEqual(levelsFrom({ entry: { price: null }, stop: 1, take_profit: 2 }), null);
  assert.strictEqual(levelsFrom({ entry: { price: 100 }, stop: 90 }), null);
});

test("riskReward for a long mirrors smc-signals R3", () => {
  // entry=100, stop=95, tp=115 -> risk 5, reward 15, rr 3 (smc R3 scenario).
  assert.deepStrictEqual(riskReward(100, 95, 115), { risk: 5, reward: 15, rr: 3 });
});

test("riskReward mirrors for a short", () => {
  // short entry=100, stop=110, tp=80 -> risk 10, reward 20, rr 2.
  assert.deepStrictEqual(riskReward(100, 110, 80), { risk: 10, reward: 20, rr: 2 });
});

test("riskReward is null rr and zero risk when entry === stop", () => {
  const out = riskReward(100, 100, 120);
  assert.strictEqual(out.rr, null);
  assert.strictEqual(out.risk, 0);
});

test("riskReward degrades non-numeric inputs without throwing", () => {
  assert.deepStrictEqual(riskReward(null, 90, 120), { risk: null, reward: null, rr: null });
});

test("positionBox returns a normalized risk + reward box", () => {
  assert.deepStrictEqual(positionBox(LONG, MAP), {
    left: 10,
    right: 130,
    riskBand: { top: 90, bottom: 100 },
    rewardBand: { top: 100, bottom: 120 },
    levels: [
      { id: "entry", price: 100, y: 100, label: "Entry" },
      { id: "stop", price: 90, y: 90, label: "SL" },
      { id: "take_profit", price: 120, y: 120, label: "TP" },
    ],
    rr: 2,
    long: true,
  });
});

test("positionBox normalizes a short box (bands still top<bottom)", () => {
  const box = positionBox(SHORT, MAP);
  assert.deepStrictEqual(box.riskBand, { top: 100, bottom: 110 });
  assert.deepStrictEqual(box.rewardBand, { top: 80, bottom: 100 });
  assert.strictEqual(box.long, false);
  assert.strictEqual(box.right, 130);
});

test("positionBox is null when the entry x is off-bar", () => {
  assert.strictEqual(positionBox(LONG, { x: () => null, y: (p) => p }), null);
});

test("positionHandles returns 4 handles (entry anchor + 3 levels)", () => {
  assert.deepStrictEqual(positionHandles(LONG, MAP), [
    { id: "entry", x: 10, y: 100 },
    { id: "entry_price", x: 130, y: 100 },
    { id: "stop", x: 130, y: 90 },
    { id: "take_profit", x: 130, y: 120 },
  ]);
});

test("positionHandles omits a level whose y is off-scale", () => {
  const out = positionHandles(LONG, { x: (t) => t, y: (p) => (p === 90 ? null : p) });
  assert.deepStrictEqual(out.map((h) => h.id), ["entry", "entry_price", "take_profit"]);
});

test("positionHandles is empty when the entry x is off-bar", () => {
  assert.deepStrictEqual(positionHandles(LONG, { x: () => null, y: (p) => p }), []);
});

test("defaultPositionStyle returns a color + lineWidth shape", () => {
  const style = defaultPositionStyle();
  assert.strictEqual(style.lineWidth, 1);
  assert.strictEqual(typeof style.color, "string");
});

test("defaultPositionStyle distinguishes long from short", () => {
  assert.notStrictEqual(
    defaultPositionStyle(LONG).color,
    defaultPositionStyle(SHORT).color,
  );
});

test("position-core is pure (no DOM, no imports)", () => {
  assert.ok(!/\bimport\b/.test(SRC), "no imports");
  assert.ok(!/document\.|window\.|Math\.pow/.test(SRC), "no DOM / no window / no pow");
});
