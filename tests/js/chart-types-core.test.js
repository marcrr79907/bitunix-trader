// Pure core tests — node --test (no DOM, no chart lib, no network).
// chart-types-core.js: chart type vocabulary, Heikin Ashi transform, type→data
// mapping. Imports nothing, deterministic, never throws (CS1).
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import * as core from "../../web/market/templates/market/chart-types-core.js";

// Hand-computed fixture. HA formulas (CS1):
//   haClose=(o+h+l+c)/4; haOpen = i===0 ? (o+c)/2 : (prevHaOpen+prevHaClose)/2;
//   haHigh=max(h,haOpen,haClose); haLow=min(l,haOpen,haClose); time preserved.
//   bar0 {o:10,h:12,l:9,c:11}  -> open 10.5, high 12,   low 9,  close 10.5
//   bar1 {o:11,h:13,l:10,c:12} -> open 10.5, high 13,   low 10, close 11.5
//   bar2 {o:12,h:14,l:11,c:13} -> open 11,   high 14,   low 11, close 12.5
const BAR0 = { time: 100, open: 10, high: 12, low: 9, close: 11 };
const BAR1 = { time: 200, open: 11, high: 13, low: 10, close: 12 };
const BAR2 = { time: 300, open: 12, high: 14, low: 11, close: 13 };

test("CHART_TYPES / SCALE_MODES: frozen vocabularies", () => {
  assert.deepStrictEqual([...core.CHART_TYPES], [
    "candles",
    "line",
    "area",
    "heikin-ashi",
  ]);
  assert.deepStrictEqual([...core.SCALE_MODES], ["linear", "log", "percentage"]);
  assert.ok(Object.isFrozen(core.CHART_TYPES), "CHART_TYPES frozen");
  assert.ok(Object.isFrozen(core.SCALE_MODES), "SCALE_MODES frozen");
});

test("isLineLike: line/area true, candles/heikin-ashi false", () => {
  assert.strictEqual(core.isLineLike("line"), true);
  assert.strictEqual(core.isLineLike("area"), true);
  assert.strictEqual(core.isLineLike("candles"), false);
  assert.strictEqual(core.isLineLike("heikin-ashi"), false);
});

test("isValidType / isValidScale: known true, unknown false", () => {
  assert.strictEqual(core.isValidType("candles"), true);
  assert.strictEqual(core.isValidType("heikin-ashi"), true);
  assert.strictEqual(core.isValidType("notreal"), false);
  assert.strictEqual(core.isValidScale("log"), true);
  assert.strictEqual(core.isValidScale("percentage"), true);
  assert.strictEqual(core.isValidScale("bogus"), false);
});

test("heikinAshi: exact 2-bar recursive fixture", () => {
  const out = core.heikinAshi([BAR0, BAR1]);
  assert.deepStrictEqual(out, [
    { time: 100, open: 10.5, high: 12, low: 9, close: 10.5 },
    { time: 200, open: 10.5, high: 13, low: 10, close: 11.5 },
  ]);
});

test("heikinAshi: 3-bar chain keeps recursing from prior HA bar", () => {
  const out = core.heikinAshi([BAR0, BAR1, BAR2]);
  assert.deepStrictEqual(out[2], {
    time: 300,
    open: 11, // (prevHaOpen 10.5 + prevHaClose 11.5) / 2
    high: 14,
    low: 11,
    close: 12.5, // (12+14+11+13)/4
  });
});

test("heikinAshi: single candle uses the first-bar branch", () => {
  const out = core.heikinAshi([BAR0]);
  assert.strictEqual(out[0].open, 10.5); // (o+c)/2, NOT (prev+prev)/2
  assert.strictEqual(out[0].close, 10.5);
  assert.strictEqual(out[0].time, 100);
});

test("heikinAshi: empty and non-array return [] without throwing", () => {
  assert.deepStrictEqual(core.heikinAshi([]), []);
  assert.deepStrictEqual(core.heikinAshi(null), []);
  assert.deepStrictEqual(core.heikinAshi(undefined), []);
});

test("heikinAshi: malformed bars return safe output, never throw", () => {
  const out = core.heikinAshi([{}, { time: 7 }]);
  assert.strictEqual(out.length, 2);
  assert.strictEqual(out[1].time, 7);
});

test("nextHeikinAshi: matches the last bar of heikinAshi", () => {
  const [, second] = core.heikinAshi([BAR0, BAR1]);
  const prevHa = { haOpen: 10.5, haClose: 10.5 }; // prior HA bar state
  assert.deepStrictEqual(core.nextHeikinAshi(prevHa, BAR1), second);
});

test("nextHeikinAshi: null prevHa takes the first-bar branch", () => {
  assert.deepStrictEqual(core.nextHeikinAshi(null, BAR0), core.heikinAshi([BAR0])[0]);
});

test("toChartData: line/area map to {time,value} with value = close", () => {
  assert.deepStrictEqual(core.toChartData("line", [BAR0, BAR1]), [
    { time: 100, value: 11 },
    { time: 200, value: 12 },
  ]);
  assert.deepStrictEqual(core.toChartData("area", [BAR0]), [{ time: 100, value: 11 }]);
});

test("toChartData: candles map to OHLC points (5 keys)", () => {
  assert.deepStrictEqual(core.toChartData("candles", [BAR0]), [
    { time: 100, open: 10, high: 12, low: 9, close: 11 },
  ]);
});

test("toChartData: heikin-ashi equals the HA transform", () => {
  assert.deepStrictEqual(
    core.toChartData("heikin-ashi", [BAR0, BAR1]),
    core.heikinAshi([BAR0, BAR1])
  );
});

test("toChartData: unknown type degrades to candle mapping, no throw", () => {
  assert.deepStrictEqual(core.toChartData("notreal", [BAR0]), [
    { time: 100, open: 10, high: 12, low: 9, close: 11 },
  ]);
});

test("toChartData: empty / non-array return [] without throwing", () => {
  assert.deepStrictEqual(core.toChartData("line", []), []);
  assert.deepStrictEqual(core.toChartData("candles", []), []);
  assert.deepStrictEqual(core.toChartData("line", null), []);
});

test("determinism and non-mutation: input candles stay untouched", () => {
  const input = [BAR0, BAR1];
  const snapshot = JSON.parse(JSON.stringify(input));
  const a = core.heikinAshi(input);
  const b = core.heikinAshi(input);
  assert.deepStrictEqual(a, b);
  assert.deepStrictEqual(input, snapshot);
});

test("purity: the module imports nothing", () => {
  const src = readFileSync(
    fileURLToPath(new URL("../../web/market/templates/market/chart-types-core.js", import.meta.url)),
    "utf8"
  );
  assert.doesNotMatch(src, /^\s*import\b/m, "no ESM import");
  assert.doesNotMatch(src, /\brequire\s*\(/, "no CommonJS require");
});
