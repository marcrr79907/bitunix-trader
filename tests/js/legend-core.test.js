// Pure legend-formatter tests — node --test (no DOM, no chart lib, no network).
//
// legend-core is a pure read-through: it only formats server-shaped values and
// recomputes nothing (no window/EMA/RSI/ATR math). See specs/chart-legend.
import test from "node:test";
import assert from "node:assert";
import * as core from "../../web/market/templates/market/legend-core.js";

test("DECIMALS is a frozen token->decimals map with the spec values", () => {
  assert.ok(Object.isFrozen(core.DECIMALS));
  assert.deepStrictEqual(
    { ...core.DECIMALS },
    {
      sma: 2,
      ema: 2,
      bollinger_upper: 2,
      bollinger_middle: 2,
      bollinger_lower: 2,
      vwap: 2,
      rsi: 2,
      stochastic_k: 2,
      stochastic_d: 2,
      atr: 2,
      macd: 4,
      macd_signal: 4,
      macd_histogram: 4,
      volume: 0,
    },
  );
  assert.strictEqual(core.PLACEHOLDER, "\u2013");
});

test("formatValue: known token uses its decimals", () => {
  assert.strictEqual(core.formatValue("macd", 1.23456), "1.2346");
  assert.strictEqual(core.formatValue("volume", 1234.9), "1235");
  assert.strictEqual(core.formatValue("sma", 42.1), "42.10");
});

test("formatValue: unknown token falls back to 2 decimals", () => {
  assert.strictEqual(core.formatValue("mystery", 50000.5), "50000.50");
});

test("formatValue: null/undefined/NaN -> placeholder, never throws", () => {
  assert.strictEqual(core.formatValue("sma", null), core.PLACEHOLDER);
  assert.strictEqual(core.formatValue("sma", undefined), core.PLACEHOLDER);
  assert.strictEqual(core.formatValue("sma", NaN), core.PLACEHOLDER);
  assert.strictEqual(core.formatValue("sma", "not-a-number"), core.PLACEHOLDER);
});

test("formatOhlc: strings plus signed direction", () => {
  assert.deepStrictEqual(core.formatOhlc({ open: 100, high: 110, low: 90, close: 105 }), {
    open: "100.00",
    high: "110.00",
    low: "90.00",
    close: "105.00",
    dir: "up",
  });
  assert.strictEqual(core.formatOhlc({ open: 105, high: 110, low: 90, close: 100 }).dir, "dn");
  assert.strictEqual(core.formatOhlc({ open: 100, high: 110, low: 90, close: 100 }).dir, "flat");
});

test("formatOhlc: missing candle -> placeholder strings, dir flat, no throw", () => {
  assert.deepStrictEqual(core.formatOhlc(null), {
    open: core.PLACEHOLDER,
    high: core.PLACEHOLDER,
    low: core.PLACEHOLDER,
    close: core.PLACEHOLDER,
    dir: "flat",
  });
  assert.deepStrictEqual(core.formatOhlc({ open: 1 }), {
    open: "1.00",
    high: core.PLACEHOLDER,
    low: core.PLACEHOLDER,
    close: core.PLACEHOLDER,
    dir: "flat",
  });
});

test("rows: assembles ohlc + one row per entry with label and formatted value", () => {
  const entries = [
    { token: "sma", key: "sma", place: "overlay", pane: undefined, value: 42.1 },
    { token: "rsi", key: "rsi", place: "pane", pane: "rsi", value: 55.555 },
  ];
  const activeSeries = [
    { token: "sma", key: "sma", place: "overlay", params: { sma_len: 20 } },
    { token: "rsi", key: "rsi", place: "pane", pane: "rsi" },
  ];
  const out = core.rows(entries, activeSeries, {
    open: 100,
    high: 110,
    low: 90,
    close: 105,
  });
  assert.deepStrictEqual(out.ohlc, {
    open: "100.00",
    high: "110.00",
    low: "90.00",
    close: "105.00",
    dir: "up",
  });
  assert.deepStrictEqual(out.series, [
    {
      token: "sma",
      key: "sma",
      place: "overlay",
      pane: undefined,
      label: "SMA 20",
      value: "42.10",
    },
    {
      token: "rsi",
      key: "rsi",
      place: "pane",
      pane: "rsi",
      label: "RSI",
      value: "55.55",
    },
  ]);
});

test("rows: unknown token -> 2-decimal fallback and bare label", () => {
  const out = core.rows(
    [{ token: "mystery", key: "mystery", place: "overlay", value: 50000.5 }],
    [],
    null,
  );
  assert.strictEqual(out.series[0].value, "50000.50");
  assert.strictEqual(out.series[0].label, "MYSTERY");
});

test("rows: missing value -> placeholder; empty entries -> empty series", () => {
  const out = core.rows(
    [{ token: "sma", key: "sma", place: "overlay", value: undefined }],
    [],
    null,
  );
  assert.strictEqual(out.series[0].value, core.PLACEHOLDER);
  assert.deepStrictEqual(core.rows([], [], null).series, []);
});

test("rows: deterministic (deep-equal across calls)", () => {
  const entries = [{ token: "macd", key: "macd", place: "pane", pane: "macd", value: 1.2345 }];
  const candle = { open: 1, high: 2, low: 0.5, close: 1.5 };
  const a = core.rows(entries, [], candle);
  const b = core.rows(entries, [], candle);
  assert.deepStrictEqual(a, b);
});

test("lastValues: recomputes o:/p: dataKey and reads the last element", () => {
  const activeSeries = [
    { token: "sma", key: "sma", place: "overlay" },
    { token: "rsi", key: "rsi", place: "pane", pane: "rsi" },
  ];
  const seriesData = {
    "o:sma": [{ time: 1, value: 10 }, { time: 2, value: 20 }],
    "p:rsi:rsi": [{ time: 1, value: 40 }, { time: 2, value: 55 }],
  };
  const candles = [{ time: 1 }, { time: 2, close: 5 }];
  assert.deepStrictEqual(core.lastValues(activeSeries, seriesData, candles), {
    candle: { time: 2, close: 5 },
    entries: [
      { key: "sma", value: 20 },
      { key: "rsi", value: 55 },
    ],
  });
});

test("lastValues: missing series -> null value; empty inputs -> null candle, no entries", () => {
  const out = core.lastValues([{ token: "sma", key: "sma", place: "overlay" }], {}, []);
  assert.strictEqual(out.candle, null);
  assert.deepStrictEqual(out.entries, [{ key: "sma", value: null }]);
  assert.deepStrictEqual(core.lastValues(null, null, null), { candle: null, entries: [] });
});

test("core never throws on garbage input", () => {
  assert.doesNotThrow(() => core.formatValue(null, {}));
  assert.doesNotThrow(() => core.formatOhlc(undefined));
  assert.doesNotThrow(() => core.rows(undefined, undefined, undefined));
  assert.doesNotThrow(() => core.lastValues(undefined, undefined, undefined));
});
