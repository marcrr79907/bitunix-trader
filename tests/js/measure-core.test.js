// Pure measure-core tests — node --test (no DOM, no chart lib, no network).
//
// Spec chart-measure R2: measure(a, b, interval) -> the five measurement fields,
// computed by the pure core that reuses intervalSeconds from chart-core.js
// (single source). Deltas keep their sign; time fields are null when either
// point is off-bar. Source-scan proves purity + the single-source import.
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { measure, formatMeasure } from "../../web/market/templates/market/measure-core.js";

const SRC = readFileSync(
  fileURLToPath(new URL("../../web/market/templates/market/measure-core.js", import.meta.url)),
  "utf8",
);

test("measure reports the five fields for a known long move", () => {
  const a = { time: 1000, price: 100 };
  const b = { time: 1060, price: 150 };
  const m = measure(a, b, "1m");
  assert.deepStrictEqual(m, {
    priceDelta: 50,
    pricePct: 50,
    timeDelta: 60,
    bars: 1,
    candles: 1,
  });
});

test("measure keeps negative deltas (direction by sign)", () => {
  const a = { time: 1060, price: 100 };
  const b = { time: 1000, price: 50 };
  const m = measure(a, b, "1m");
  assert.strictEqual(m.priceDelta, -50);
  assert.strictEqual(m.pricePct, -50);
  assert.strictEqual(m.timeDelta, -60);
  assert.strictEqual(m.bars, -1);
  assert.strictEqual(m.candles, -1);
});

test("bars === candles === round(timeDelta / interval) identity", () => {
  const a = { time: 0, price: 1 };
  const b = { time: 5400, price: 2 };
  const m = measure(a, b, "1h");
  const iv = 3600;
  assert.strictEqual(m.bars, Math.round(m.timeDelta / iv));
  assert.strictEqual(m.candles, m.bars);
  assert.strictEqual(m.bars, 2);
});

test("interval accepts a string and an equivalent seconds number", () => {
  const a = { time: 0, price: 1 };
  const b = { time: 120, price: 2 };
  const fromString = measure(a, b, "1m");
  const fromSeconds = measure(a, b, 60);
  assert.strictEqual(fromString.bars, 2);
  assert.deepStrictEqual(fromString, fromSeconds);
});

test("off-bar time (null) degrades timeDelta/bars/candles to null only", () => {
  const m = measure({ time: null, price: 100 }, { time: 1000, price: 150 }, "1m");
  assert.strictEqual(m.priceDelta, 50);
  assert.strictEqual(m.pricePct, 50);
  assert.strictEqual(m.timeDelta, null);
  assert.strictEqual(m.bars, null);
  assert.strictEqual(m.candles, null);
});

test("missing price degrades priceDelta/pricePct to null", () => {
  const m = measure({ time: 1, price: null }, { time: 2, price: 150 }, "1m");
  assert.strictEqual(m.priceDelta, null);
  assert.strictEqual(m.pricePct, null);
  assert.strictEqual(m.timeDelta, 1);
});

test("measure never throws on missing points or interval", () => {
  assert.deepStrictEqual(measure(null, null, "1m"), {
    priceDelta: null,
    pricePct: null,
    timeDelta: null,
    bars: null,
    candles: null,
  });
  assert.deepStrictEqual(measure(undefined, { time: 1, price: 1 }, undefined), {
    priceDelta: null,
    pricePct: null,
    timeDelta: null,
    bars: null,
    candles: null,
  });
});

test("formatMeasure renders signed display strings", () => {
  assert.deepStrictEqual(
    formatMeasure({ priceDelta: 1.5, pricePct: 1.5, timeDelta: 90, bars: 2 }),
    { price: "+1.50", pct: "+1.50%", time: "+90s", bars: "+2" },
  );
  assert.deepStrictEqual(
    formatMeasure({ priceDelta: -1.5, pricePct: -1.5, timeDelta: -90, bars: -2 }),
    { price: "-1.50", pct: "-1.50%", time: "-90s", bars: "-2" },
  );
});

test("formatMeasure renders an em dash for off-value fields", () => {
  assert.deepStrictEqual(
    formatMeasure({ priceDelta: null, pricePct: null, timeDelta: null, bars: null }),
    { price: "\u2014", pct: "\u2014", time: "\u2014", bars: "\u2014" },
  );
  assert.strictEqual(formatMeasure(null).price, "\u2014");
});

test("measure-core is pure and imports intervalSeconds from chart-core", () => {
  assert.ok(SRC.includes('from "./chart-core.js"'), "imports chart-core");
  assert.ok(SRC.includes("intervalSeconds"), "uses intervalSeconds");
  assert.ok(!/document\.|window\.|Math\.pow/.test(SRC), "no DOM / no window / no pow");
});
