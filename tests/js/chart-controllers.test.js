// Controller pure-helper tests — node --test (DOM-free helpers only).
//
// The controllers are DI factories whose DOM/chart/REST methods need a browser
// (covered by E2E). The pure mapping helpers they expose have no DOM and are
// unit-tested here, mirroring the Slice 1/2 core-test discipline.
import test from "node:test";
import assert from "node:assert";
import { buildIndicators } from "../../web/market/templates/market/controllers/indicators.js";
import { klineUrlFrom } from "../../web/market/templates/market/controllers/history.js";
import {
  shapeEntries,
  candleFrom,
  changePctText,
  prevClose,
} from "../../web/market/templates/market/controllers/legend.js";

test("buildIndicators: token-only entries when no params", () => {
  assert.deepStrictEqual(buildIndicators(["sma", "rsi"], {}), [
    { token: "sma" },
    { token: "rsi" },
  ]);
});

test("buildIndicators: params attach only to selected tokens", () => {
  const out = buildIndicators(["sma", "rsi"], { sma: { sma_len: 50 } });
  assert.deepStrictEqual(out, [
    { token: "sma", params: { sma_len: 50 } },
    { token: "rsi" },
  ]);
});

test("klineUrlFrom: symbol+interval+indicators+params+extra", () => {
  const url = klineUrlFrom(
    {
      symbol: "BTCUSDT",
      interval: "5m",
      indicators: ["sma"],
      params: { sma: { sma_len: 50 } },
    },
    "/market/api/kline",
    "limit=2",
  );
  assert.strictEqual(
    url,
    "/market/api/kline?symbol=BTCUSDT&interval=5m&indicators=sma&sma_len=50&limit=2",
  );
});

test("klineUrlFrom: no indicators -> no indicators/params segments", () => {
  const url = klineUrlFrom(
    { symbol: "ETHUSDT", interval: "1m", indicators: [], params: {} },
    "/market/api/kline",
    "limit=200",
  );
  assert.strictEqual(
    url,
    "/market/api/kline?symbol=ETHUSDT&interval=1m&limit=200",
  );
});

// --- legend controller pure helpers (Slice 2) --------------------------------
//
// The legend is a pure read-through: these helpers only RESHAPE the v5
// crosshair ``param.seriesData`` Map (series -> point) into chart-lib-free
// {token,key,place,pane,value} entries plus the candle at the cursor. No
// recompute, no DOM — so they are unit-tested here without a browser.

const SMA_SERIES = { id: "sma" };
const RSI_SERIES = { id: "rsi" };
const CANDLE_SERIES = { id: "candles" };
const ACTIVE = [
  { token: "sma", key: "sma", place: "overlay", pane: undefined, series: SMA_SERIES },
  { token: "rsi", key: "rsi", place: "pane", pane: "rsi", series: RSI_SERIES },
];

function seriesMap(pairs) {
  return { seriesData: new Map(pairs) };
}

test("shapeEntries: maps each active series point to a chart-lib-free entry", () => {
  const candle = { time: 2, open: 100, high: 110, low: 90, close: 105 };
  const param = seriesMap([
    [CANDLE_SERIES, candle],
    [SMA_SERIES, { time: 2, value: 42.1 }],
    [RSI_SERIES, { time: 2, value: 55.5 }],
  ]);
  const out = shapeEntries(param, ACTIVE, CANDLE_SERIES);
  assert.strictEqual(out.candle, candle);
  assert.deepStrictEqual(out.entries, [
    { token: "sma", key: "sma", place: "overlay", pane: undefined, value: 42.1 },
    { token: "rsi", key: "rsi", place: "pane", pane: "rsi", value: 55.5 },
  ]);
});

test("shapeEntries: series absent from the Map -> value undefined (no throw)", () => {
  const candle = { time: 3, open: 1, high: 2, low: 0.5, close: 1.5 };
  const param = seriesMap([[CANDLE_SERIES, candle]]);
  const out = shapeEntries(param, ACTIVE, CANDLE_SERIES);
  assert.deepStrictEqual(out.entries, [
    { token: "sma", key: "sma", place: "overlay", pane: undefined, value: undefined },
    { token: "rsi", key: "rsi", place: "pane", pane: "rsi", value: undefined },
  ]);
  assert.strictEqual(out.candle, candle);
});

test("shapeEntries: garbage inputs degrade to null candle + no throw", () => {
  // No param Map, but active series present -> one undefined-valued entry each.
  assert.deepStrictEqual(shapeEntries(undefined, ACTIVE, CANDLE_SERIES), {
    candle: null,
    entries: [
      { token: "sma", key: "sma", place: "overlay", pane: undefined, value: undefined },
      { token: "rsi", key: "rsi", place: "pane", pane: "rsi", value: undefined },
    ],
  });
  // No active series -> empty entries regardless of the Map.
  assert.deepStrictEqual(shapeEntries(seriesMap([]), undefined, undefined), {
    candle: null,
    entries: [],
  });
});

test("candleFrom: reads the candle series point, else null", () => {
  const candle = { time: 9, open: 1, high: 2, low: 0.5, close: 1.5 };
  assert.strictEqual(
    candleFrom(seriesMap([[CANDLE_SERIES, candle]]), CANDLE_SERIES),
    candle,
  );
  assert.strictEqual(candleFrom(seriesMap([]), CANDLE_SERIES), null);
  assert.strictEqual(candleFrom(undefined, undefined), null);
});

test("prevClose: close of the candle immediately before the cursor bar", () => {
  const candles = [
    { time: 1, close: 10 },
    { time: 2, close: 20 },
    { time: 3, close: 30 },
  ];
  assert.strictEqual(prevClose(candles, { time: 3, close: 30 }), 20);
  assert.strictEqual(prevClose(candles, { time: 1, close: 10 }), null); // first bar
  assert.strictEqual(prevClose([], { time: 5 }), null);
  assert.strictEqual(prevClose(undefined, undefined), null);
});

test("changePctText: signed percent vs prevClose, placeholder when unknown", () => {
  assert.strictEqual(changePctText(105, 100), "+5.00%");
  assert.strictEqual(changePctText(95, 100), "-5.00%");
  assert.strictEqual(changePctText(100, 100), "0.00%");
  assert.strictEqual(changePctText(105, null), "\u2013");
  assert.strictEqual(changePctText(null, 100), "\u2013");
});
