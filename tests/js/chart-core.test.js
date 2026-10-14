// Pure core tests — node --test (no DOM, no chart lib, no network).
import test from "node:test";
import assert from "node:assert";
import * as core from "../../web/market/templates/market/chart-core.js";

test("bucketTime: intraday floors to the interval", () => {
  // 2026-10-10 00:00:30 UTC -> 5m bucket
  const ts = Date.UTC(2026, 9, 10, 0, 0, 30);
  assert.strictEqual(core.bucketTime(ts, "5m"), Math.floor(ts / 1000 / 300) * 300);
  assert.strictEqual(core.bucketTime(ts, "1h"), Math.floor(ts / 1000 / 3600) * 3600);
});

test("bucketTime: 1d floors to UTC midnight", () => {
  const ts = Date.UTC(2026, 9, 10, 13, 37, 0);
  assert.strictEqual(core.bucketTime(ts, "1d"), Date.UTC(2026, 9, 10) / 1000);
});

test("bucketTime: 1w aligns to Monday (t % 604800 == 345600)", () => {
  // Real BitUnix 1w candle time: 1790553600 => 2026-09-28 (Mon) 00:00
  const real = 1790553600 * 1000;
  const b = core.bucketTime(real, "1w");
  assert.strictEqual(b, 1790553600);
  assert.strictEqual(b % 604800, 345600);
  // A Thursday in the same week buckets back to that Monday
  const thu = Date.UTC(2026, 9, 1, 12, 0, 0); // 2026-10-01 Thu
  const bthu = core.bucketTime(thu, "1w");
  const d = new Date(bthu * 1000);
  assert.strictEqual(d.getUTCDay(), 1); // Monday
});

test("bucketTime: 1M aligns to calendar month start", () => {
  // Real BitUnix 1M candle time: 1788220800 => 2026-09-01
  assert.strictEqual(core.bucketTime(1788220800 * 1000, "1M"), 1788220800);
  const mid = Date.UTC(2026, 8, 17, 5, 0, 0);
  assert.strictEqual(core.bucketTime(mid, "1M"), Date.UTC(2026, 8, 1) / 1000);
});

test("upsertCandle: same bucket replaces in place", () => {
  const arr = [{ time: 100, close: 1 }];
  core.upsertCandle(arr, { time: 100, close: 2 });
  assert.strictEqual(arr.length, 1);
  assert.strictEqual(arr[0].close, 2);
});

test("upsertCandle: newer appends, older ignored", () => {
  const arr = [{ time: 100, close: 1 }];
  core.upsertCandle(arr, { time: 200, close: 2 });
  assert.strictEqual(arr.length, 2);
  core.upsertCandle(arr, { time: 50, close: 9 });
  assert.strictEqual(arr.length, 2);
  assert.deepStrictEqual(arr.map((c) => c.time), [100, 200]);
});

test("upsertCandle: never duplicates time", () => {
  const arr = [];
  core.upsertCandle(arr, { time: 100 });
  core.upsertCandle(arr, { time: 100 });
  core.upsertCandle(arr, { time: 100 });
  assert.strictEqual(arr.length, 1);
});

test("mergeCandles: union ascending, existing wins on dup", () => {
  const older = [{ time: 1, v: "old" }, { time: 2, v: "old2" }];
  const existing = [{ time: 2, v: "new2" }, { time: 3, v: "new3" }];
  const merged = core.mergeCandles(older, existing);
  assert.deepStrictEqual(merged.map((c) => c.time), [1, 2, 3]);
  assert.strictEqual(merged.find((c) => c.time === 2).v, "new2");
});

test("lastPoint: last or undefined", () => {
  assert.strictEqual(core.lastPoint([]), undefined);
  assert.deepStrictEqual(core.lastPoint([{ t: 1 }, { t: 2 }]), { t: 2 });
});

test("isFrameForChannel: exact-channel truth table", () => {
  const ch = "market_kline_5min";
  // Same channel → true
  assert.strictEqual(core.isFrameForChannel({ ch }, ch), true);
  // Foreign channel → false
  assert.strictEqual(core.isFrameForChannel({ ch: "market_kline_1min" }, ch), false);
  // Missing / null / empty ch → false (fail closed)
  assert.strictEqual(core.isFrameForChannel({}, ch), false);
  assert.strictEqual(core.isFrameForChannel({ ch: null }, ch), false);
  assert.strictEqual(core.isFrameForChannel({ ch: "" }, ch), false);
  // Null / undefined frame → false
  assert.strictEqual(core.isFrameForChannel(null, ch), false);
  assert.strictEqual(core.isFrameForChannel(undefined, ch), false);
  // Missing / empty expectedChannel → false
  assert.strictEqual(core.isFrameForChannel({ ch }, undefined), false);
  assert.strictEqual(core.isFrameForChannel({ ch }, ""), false);
});

test("isFrameForChannel: pure, deterministic, never throws", () => {
  const frame = { ch: "market_kline_5min" };
  const before = JSON.stringify(frame);
  assert.strictEqual(core.isFrameForChannel(frame, "market_kline_5min"), true);
  assert.strictEqual(core.isFrameForChannel(frame, "market_kline_5min"), true);
  assert.strictEqual(JSON.stringify(frame), before, "input must not mutate");
  // Malformed shapes must not throw
  assert.doesNotThrow(() => core.isFrameForChannel(123, "market_kline_5min"));
  assert.doesNotThrow(() => core.isFrameForChannel({}, {}));
});
