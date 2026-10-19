// Controller pure-helper tests — node --test (DOM-free helpers only).
//
// The controllers are DI factories whose DOM/chart/REST methods need a browser
// (covered by E2E). The pure mapping helpers they expose have no DOM and are
// unit-tested here, mirroring the Slice 1/2 core-test discipline.
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  buildIndicators,
  settingsFromFields,
  PERIOD_PARAMS,
} from "../../web/market/templates/market/controllers/indicators.js";
import { klineUrlFrom } from "../../web/market/templates/market/controllers/history.js";
import {
  shapeEntries,
  candleFrom,
  changePctText,
  prevClose,
} from "../../web/market/templates/market/controllers/legend.js";
import { resolveToggles } from "../../web/market/templates/market/controllers/smc.js";
import { createBus } from "../../web/market/templates/market/chart-bus.js";

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

test("buildIndicators: 3rd styles arg emits style only for styled tokens", () => {
  const out = buildIndicators(
    ["sma", "rsi"],
    { sma: { sma_len: 50 } },
    { sma: { color: "#ff0000", lineWidth: 2, precision: 4 } },
  );
  assert.deepStrictEqual(out, [
    { token: "sma", params: { sma_len: 50 }, style: { color: "#ff0000", lineWidth: 2, precision: 4 } },
    { token: "rsi" },
  ]);
});

test("buildIndicators: no styles arg keeps entries style-free", () => {
  assert.deepStrictEqual(buildIndicators(["sma"], {}), [{ token: "sma" }]);
});

test("buildIndicators: 4th visible arg emits visible:false only (F2.7 / R4)", () => {
  // Absent = true -> minimal payload (no ``visible`` key), mirroring style.
  assert.deepStrictEqual(
    buildIndicators(["sma", "rsi"], {}, {}, { sma: false }),
    [{ token: "sma", visible: false }, { token: "rsi" }],
  );
  // An explicit true is also dropped (absent means visible).
  assert.deepStrictEqual(buildIndicators(["sma"], {}, {}, { sma: true }), [
    { token: "sma" },
  ]);
  // No visible arg at all keeps entries unchanged (backward compatible).
  assert.deepStrictEqual(buildIndicators(["sma"], {}), [{ token: "sma" }]);
});

test("PERIOD_PARAMS: only param tokens with an editable period", () => {
  assert.deepStrictEqual(PERIOD_PARAMS, { sma: "sma_len", ema: "ema_len" });
});

test("settingsFromFields: coerces string controls into a normalized style", () => {
  const out = settingsFromFields(
    "sma",
    { color: "#ff0000", lineWidth: "3", precision: "5", period: "50" },
    { color: "#2962ff", lineWidth: 1, precision: 2 },
  );
  assert.deepStrictEqual(out.style, { color: "#ff0000", lineWidth: 3, precision: 5 });
  assert.strictEqual(out.period, 50);
});

test("settingsFromFields: empty controls fall back to defaults and clamp", () => {
  const out = settingsFromFields(
    "sma",
    { color: "", lineWidth: "", precision: "", period: "" },
    { color: "#2962ff", lineWidth: 1, precision: 2 },
  );
  assert.deepStrictEqual(out.style, { color: "#2962ff", lineWidth: 1, precision: 2 });
  assert.strictEqual(out.period, null);
});

test("settingsFromFields: out-of-range strings clamp into the frozen shape", () => {
  const out = settingsFromFields(
    "sma",
    { color: "#zzz", lineWidth: "99", precision: "-3", period: "0" },
    { color: "#2962ff", lineWidth: 1, precision: 2 },
  );
  assert.deepStrictEqual(out.style, { color: "#2962ff", lineWidth: 4, precision: 0 });
  assert.strictEqual(out.period, null); // period 0 is not a valid length
});

test("settingsFromFields: period stays null for a token without a param", () => {
  const out = settingsFromFields(
    "rsi",
    { color: "#00ff00", lineWidth: "2", precision: "3", period: "14" },
    { color: "#ab47bc", lineWidth: 1, precision: 2 },
  );
  assert.deepStrictEqual(out.style, { color: "#00ff00", lineWidth: 2, precision: 3 });
  assert.strictEqual(out.period, null);
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

test("klineUrlFrom: styles never leak into the kline query", () => {
  const url = klineUrlFrom(
    {
      symbol: "BTCUSDT",
      interval: "1m",
      indicators: ["sma"],
      params: { sma: { sma_len: 50 } },
      styles: { sma: { color: "#ff0000", lineWidth: 3, precision: 5 } },
    },
    "/market/api/kline",
    "limit=2",
  );
  assert.strictEqual(
    url,
    "/market/api/kline?symbol=BTCUSDT&interval=1m&indicators=sma&sma_len=50&limit=2",
  );
  assert.strictEqual(/color|lineWidth|precision/.test(url), false);
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

// --- SMC persisted toggles (Slice 2 / R7) ------------------------------------

test("resolveToggles: {} means all families ON", () => {
  assert.deepStrictEqual(resolveToggles({}), {
    swings: true,
    structure: true,
    order_blocks: true,
    fvg: true,
    range: true,
    setups: true,
  });
});

test("resolveToggles: an explicit false hides only that family", () => {
  assert.deepStrictEqual(resolveToggles({ range: false }), {
    swings: true,
    structure: true,
    order_blocks: true,
    fvg: true,
    range: false,
    setups: true,
  });
});

test("resolveToggles: a null/garbage payload degrades to all ON", () => {
  const allOn = {
    swings: true,
    structure: true,
    order_blocks: true,
    fvg: true,
    range: true,
    setups: true,
  };
  assert.deepStrictEqual(resolveToggles(null), allOn);
  assert.deepStrictEqual(resolveToggles(undefined), allOn);
  assert.deepStrictEqual(resolveToggles("nope"), allOn);
});

// --- drawings duplicate/restore (F7 S2 / design D6) --------------------------
//
// duplicate/restore MUST reuse the ONE create path (a POST), never a new
// endpoint (#68). A DOM-free shim (null dialogs) + a fetch stub captures the
// POST body; ``drawing:created`` is emitted after the attach (the undo signal).
const { createDrawings } = await import(
  "../../web/market/templates/market/controllers/drawings.js"
);

function drawingsFixture(seedRows) {
  const prevDoc = globalThis.document;
  const prevWin = globalThis.window;
  const prevFetch = globalThis.fetch;
  const posts = [];
  globalThis.document = {
    getElementById: () => null,
    querySelector: () => null,
    documentElement: { style: {} },
  };
  globalThis.window = { marketChart: { drawings: [] } };
  globalThis.fetch = (url, opts) => {
    const method = (opts && opts.method) || "GET";
    if (method === "GET") {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ drawings: seedRows || [] }) });
    }
    const body = JSON.parse((opts && opts.body) || "{}");
    posts.push({ url, method, body });
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ id: 900 + posts.length, kind: body.kind, points: body.points, style: body.style }),
    });
  };
  const bus = createBus();
  const created = [];
  bus.on("drawing:created", (p) => created.push(p));
  const store = makeStore({ symbol: "BTCUSDT", interval: "1m", tool: null });
  const host = { getCandleSeries: () => null };
  const d = createDrawings({ store, bus, host, config: { urls: { drawings: "/market/api/drawings" } } });
  return {
    d, bus, posts, created, store,
    load: () => d.refreshDrawings(),
    restore() {
      if (prevDoc === undefined) delete globalThis.document; else globalThis.document = prevDoc;
      if (prevWin === undefined) delete globalThis.window; else globalThis.window = prevWin;
      if (prevFetch === undefined) delete globalThis.fetch; else globalThis.fetch = prevFetch;
    },
  };
}

test("drawing:duplicate clones kind/points/style into ONE POST, no offset (D6/Q4)", async () => {
  const f = drawingsFixture([{ id: 7, kind: "hline", points: { price: 100 }, style: { color: "#111" } }]);
  try {
    await f.load();
    f.bus.emit("drawing:duplicate", { id: 7 });
    assert.strictEqual(f.posts.length, 1, "duplicate is one POST");
    assert.strictEqual(f.posts[0].method, "POST");
    assert.deepStrictEqual(f.posts[0].body.points, { price: 100 });
    assert.strictEqual(f.posts[0].body.kind, "hline");
    assert.deepStrictEqual(f.posts[0].body.style, { color: "#111" });
  } finally { f.restore(); }
});

test("drawing:restore re-POSTs the committed before row (undo of a delete)", async () => {
  const f = drawingsFixture([]);
  try {
    f.bus.emit("drawing:restore", { row: { kind: "trendline", points: { p1: 1, p2: 2 }, style: {} } });
    // The POST is issued synchronously on the emit; the response resolves async.
    await Promise.resolve();
    assert.strictEqual(f.posts.length, 1);
    assert.strictEqual(f.posts[0].method, "POST");
    assert.strictEqual(f.posts[0].body.kind, "trendline");
    assert.deepStrictEqual(f.posts[0].body.points, { p1: 1, p2: 2 });
  } finally { f.restore(); }
});

test("drawing:created is emitted after a create (the undo signal)", async () => {
  const f = drawingsFixture([]);
  try {
    f.bus.emit("drawing:restore", { row: { kind: "hline", points: { price: 5 }, style: {} } });
    for (let i = 0; i < 5; i += 1) await Promise.resolve();
    assert.strictEqual(f.created.length, 1, "create completion is published");
    assert.strictEqual(f.created[0].kind, "hline");
    assert.strictEqual(f.created[0].id, 901);
  } finally { f.restore(); }
});

test("a duplicate of an unknown id POSTs nothing", async () => {
  const f = drawingsFixture([{ id: 7, kind: "hline", points: {}, style: {} }]);
  try {
    await f.load();
    f.bus.emit("drawing:duplicate", { id: 404 });
    assert.deepStrictEqual(f.posts, []);
  } finally { f.restore(); }
});

// --- drawings click flow (F9 S3b / design D6) --------------------------------
//
// The 1/2/3-click machine moved into the pure drawing-click-flow-core; the
// controller is now a thin delegate. These tests pin the CONTROLLER contract:
// clicks -> exactly ONE POST with the kind-shaped points, a dialog for
// text/callout, and cancel on tool switch / Escape / symbol switch.
function drawingsClickFixture() {
  const prevDoc = globalThis.document;
  const prevWin = globalThis.window;
  const prevFetch = globalThis.fetch;
  const prevGcs = globalThis.getComputedStyle;
  const posts = [];
  const dialog = makeEl("dialog");
  dialog.showModal = () => { dialog.open = true; };
  dialog.returnValue = "";
  const input = { value: "" };
  const chartEl = makeEl("div");
  globalThis.document = {
    getElementById: (id) => {
      if (id === "text-dialog") return dialog;
      if (id === "text-dialog-input") return input;
      if (id === "chart") return chartEl;
      return null;
    },
    querySelector: () => null,
    documentElement: { style: {} },
  };
  globalThis.getComputedStyle = () => ({ getPropertyValue: () => "" });
  globalThis.window = { marketChart: { drawings: [] } };
  globalThis.fetch = (url, opts) => {
    const method = (opts && opts.method) || "GET";
    const body = JSON.parse((opts && opts.body) || "{}");
    if (method !== "GET") posts.push({ url, method, body });
    if (method === "GET") {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ drawings: [] }) });
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ id: 900 + posts.length, kind: body.kind, points: body.points, style: body.style }),
    });
  };
  const bus = createBus();
  const store = makeStore({ symbol: "BTCUSDT", interval: "1m", tool: null });
  const host = { getCandleSeries: () => ({ coordinateToPrice: (y) => y }) };
  const d = createDrawings({ store, bus, host, config: { urls: { drawings: "/market/api/drawings" } } });
  return {
    d, bus, posts, store, dialog, input, chartEl,
    tool: (kind) => store.set({ tool: kind }),
    click(time, price) { d.onChartClick({ time, point: { y: price } }); },
    closeDialog(text) {
      dialog.returnValue = "ok";
      input.value = text;
      dialog.fire("close", {});
    },
    restore() {
      if (prevDoc === undefined) delete globalThis.document; else globalThis.document = prevDoc;
      if (prevWin === undefined) delete globalThis.window; else globalThis.window = prevWin;
      if (prevFetch === undefined) delete globalThis.fetch; else globalThis.fetch = prevFetch;
      if (prevGcs === undefined) delete globalThis.getComputedStyle; else globalThis.getComputedStyle = prevGcs;
    },
  };
}

test("a 1-click kind (hline) POSTs its price on the first click", () => {
  const f = drawingsClickFixture();
  try {
    f.tool("hline");
    f.click(undefined, 42);
    assert.strictEqual(f.posts.length, 1);
    assert.strictEqual(f.posts[0].body.kind, "hline");
    assert.deepStrictEqual(f.posts[0].body.points, { price: 42 });
  } finally { f.restore(); }
});

test("a 2-click kind (ray) POSTs once, after the second click", () => {
  const f = drawingsClickFixture();
  try {
    f.tool("ray");
    f.click(1, 10);
    assert.deepStrictEqual(f.posts, [], "the first click only sets an anchor");
    f.click(2, 20);
    assert.strictEqual(f.posts.length, 1);
    assert.strictEqual(f.posts[0].body.kind, "ray");
    assert.deepStrictEqual(f.posts[0].body.points, {
      p1: { time: 1, price: 10 }, p2: { time: 2, price: 20 },
    });
  } finally { f.restore(); }
});

test("a 3-click kind (channel) POSTs once, after the third click", () => {
  const f = drawingsClickFixture();
  try {
    f.tool("channel");
    f.click(1, 10);
    f.click(2, 20);
    assert.deepStrictEqual(f.posts, []);
    f.click(3, 30);
    assert.strictEqual(f.posts.length, 1);
    assert.strictEqual(f.posts[0].body.kind, "channel");
    assert.deepStrictEqual(f.posts[0].body.points, {
      p1: { time: 1, price: 10 }, p2: { time: 2, price: 20 }, p3: { time: 3, price: 30 },
    });
  } finally { f.restore(); }
});

test("position still collects entry/stop/tp and POSTs ONE drawing", () => {
  const f = drawingsClickFixture();
  try {
    f.tool("position");
    f.click(1, 10);
    f.click(2, 20);
    assert.deepStrictEqual(f.posts, []);
    f.click(3, 30);
    assert.strictEqual(f.posts.length, 1);
    assert.strictEqual(f.posts[0].body.kind, "position");
    assert.deepStrictEqual(f.posts[0].body.points, {
      entry: { time: 1, price: 10 }, stop: 20, take_profit: 30,
    });
    // The style is the DERIVED direction colour, not Draw.defaultStyle("position").
    assert.strictEqual(typeof f.posts[0].body.style.color, "string");
    assert.strictEqual(f.posts[0].body.style.lineWidth, 1);
  } finally { f.restore(); }
});

test("a position's derived colour follows the direction (long vs short)", () => {
  const long = drawingsClickFixture();
  try {
    long.tool("position");
    long.click(1, 10);
    long.click(2, 5);
    long.click(3, 30);
  } finally { long.restore(); }
  const longColor = long.posts[0].body.style.color;
  const short = drawingsClickFixture();
  try {
    short.tool("position");
    short.click(1, 10);
    short.click(2, 20);
    short.click(3, 5);
    assert.strictEqual(short.posts.length, 1);
  } finally { short.restore(); }
  assert.notStrictEqual(short.posts[0].body.style.color, longColor);
});

test("a tool switch drops the half-collected draft", () => {
  const f = drawingsClickFixture();
  try {
    f.tool("ray");
    f.click(1, 10);
    f.tool("trendline");
    f.click(2, 20);
    assert.deepStrictEqual(f.posts, [], "the ray anchor must not become the trendline p1");
    f.click(3, 30);
    assert.strictEqual(f.posts.length, 1);
    assert.strictEqual(f.posts[0].body.kind, "trendline");
    assert.deepStrictEqual(f.posts[0].body.points.p1, { time: 2, price: 20 });
  } finally { f.restore(); }
});

test("Escape cancels a half-collected draft (no POST)", () => {
  const f = drawingsClickFixture();
  try {
    f.tool("position");
    f.click(1, 10);
    f.click(2, 20);
    f.chartEl.fire("keydown", { key: "Escape", preventDefault() {} });
    f.click(3, 30);
    assert.deepStrictEqual(f.posts, [], "the draft was cancelled, not resumed");
    f.click(4, 40);
    f.click(5, 50);
    assert.strictEqual(f.posts.length, 1, "a fresh 3-click draft finalizes");
    assert.deepStrictEqual(f.posts[0].body.points.entry, { time: 3, price: 30 });
  } finally { f.restore(); }
});

test("clearForSwitch cancels the draft and the next symbol starts fresh", () => {
  const f = drawingsClickFixture();
  try {
    f.tool("ray");
    f.click(1, 10);
    f.d.clearForSwitch();
    f.tool("ray");
    f.click(2, 20);
    assert.deepStrictEqual(f.posts, []);
    f.click(3, 30);
    assert.strictEqual(f.posts.length, 1);
    assert.deepStrictEqual(f.posts[0].body.points.p1, { time: 2, price: 20 });
  } finally { f.restore(); }
});

test("text opens #text-dialog and merges the typed text into ONE POST", () => {
  const f = drawingsClickFixture();
  try {
    f.tool("text");
    f.click(1, 10);
    assert.deepStrictEqual(f.posts, []);
    assert.strictEqual(f.dialog.open, true, "the text dialog opens");
    f.closeDialog("hello");
    assert.strictEqual(f.posts.length, 1);
    assert.strictEqual(f.posts[0].body.kind, "text");
    assert.deepStrictEqual(f.posts[0].body.points, { time: 1, price: 10, text: "hello" });
  } finally { f.restore(); }
});

test("callout collects 2 points then merges the dialog text into ONE POST", () => {
  const f = drawingsClickFixture();
  try {
    f.tool("callout");
    f.click(1, 10);
    assert.strictEqual(f.dialog.open, undefined, "the dialog waits for the second click");
    f.click(2, 20);
    assert.strictEqual(f.dialog.open, true);
    f.closeDialog("watch this");
    assert.strictEqual(f.posts.length, 1);
    assert.strictEqual(f.posts[0].body.kind, "callout");
    assert.deepStrictEqual(f.posts[0].body.points, {
      p1: { time: 1, price: 10 }, p2: { time: 2, price: 20 }, text: "watch this",
    });
  } finally { f.restore(); }
});

test("a cancelled dialog POSTs nothing and drops the pending shape", () => {
  const f = drawingsClickFixture();
  try {
    f.tool("callout");
    f.click(1, 10);
    f.click(2, 20);
    f.dialog.returnValue = "cancel";
    f.dialog.fire("close", {});
    assert.deepStrictEqual(f.posts, []);
  } finally { f.restore(); }
});

test("a 2-click kind ignores an off-bar click (no time)", () => {
  const f = drawingsClickFixture();
  try {
    f.tool("ray");
    f.click(null, 10);
    assert.deepStrictEqual(f.posts, []);
    f.click(2, 20);
    assert.deepStrictEqual(f.posts, [], "the off-bar click must not have set the anchor");
    f.click(3, 30);
    assert.strictEqual(f.posts.length, 1);
    assert.deepStrictEqual(f.posts[0].body.points.p1, { time: 2, price: 20 });
  } finally { f.restore(); }
});

test("measure is ephemeral and never POSTs through the click flow", () => {
  const f = drawingsClickFixture();
  try {
    f.tool("measure");
    f.click(1, 10);
    assert.deepStrictEqual(f.posts, []);
  } finally { f.restore(); }
});

//
// The controller's chart peers need a browser (E2E), but its gesture +
// ephemeral-readout contract is DOM + a stubbed host/series: it owns the
// ``#chart`` pointer listeners guarded by ``state.tool==="measure"`` and writes
// the ``#measure-readout`` textContent via the pure measure-core. A hand-rolled
// shim (no jsdom) keeps the test framework-free.
const { createMeasure } = await import(
  "../../web/market/templates/market/controllers/measure.js"
);

function makeEl(tag) {
  const el = {
    tagName: tag,
    _listeners: {},
    style: {},
    textContent: "",
    setAttribute() {},
    addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
    removeEventListener() {},
    getBoundingClientRect() { return { left: 0, top: 0 }; },
    setPointerCapture() {},
    releasePointerCapture() {},
    hasPointerCapture() { return false; },
    fire(type, ev) { (this._listeners[type] || []).forEach((fn) => fn(ev)); },
  };
  return el;
}

function makeStore(initial) {
  const state = { ...initial };
  const listeners = [];
  return {
    get: () => state,
    set: (patch) => { Object.assign(state, patch); listeners.slice().forEach((fn) => fn(state)); },
    subscribe: (fn) => { listeners.push(fn); },
  };
}

// A series stub: maps price<->px and records every primitive attach/detach +
// each requestUpdate (so we can assert #68). One per chart build.
function makeSeries(chart) {
  return {
    _prim: null,
    attaches: 0,
    updates: 0,
    attachPrimitive(prim) {
      this._prim = prim;
      this.attaches += 1;
      const seriesRef = this;
      prim.attached({
        chart: chart,
        series: this,
        requestUpdate() { seriesRef.updates += 1; },
      });
    },
    detachPrimitive(prim) { if (this._prim === prim) this._prim = null; },
    priceToCoordinate(p) { return p; },
    coordinateToPrice(y) { return y; },
    setData() { throw new Error("measure must never call setData"); },
    update() { throw new Error("measure must never call update"); },
  };
}

// A host stub: the chart maps time<->px; ``swap()`` models a chart REBUILD
// (buildChart recreates the candle series) so a controller's rebuild behaviour
// is testable (#188). ``_series`` always resolves to the current series.
function makeHost() {
  const chart = { timeScale() { return { timeToCoordinate: (t) => t, coordinateToTime: (x) => x }; } };
  let series = makeSeries(chart);
  const host = {
    getChart: () => chart,
    getCandleSeries: () => series,
    swap() { series = makeSeries(chart); return series; },
  };
  Object.defineProperty(host, "_series", { get: () => series });
  return host;
}

function measureFixture(tool = "measure") {
  const chartEl = makeEl("section");
  const readout = makeEl("p");
  const prev = globalThis.document;
  globalThis.document = {
    getElementById: (id) => (id === "chart" ? chartEl : id === "measure-readout" ? readout : null),
  };
  const store = makeStore({ tool: tool, interval: "1m", symbol: "BTCUSDT" });
  const host = makeHost();
  const bus = { on() {}, emit() {} };
  const m = createMeasure({ store, bus, host, config: {} });
  m.attach();
  return { m, store, host, bus, chartEl, readout, restore: () => { globalThis.document = prev; } };
}

function ev(x, y) {
  return { clientX: x, clientY: y, pointerId: 1, button: 0, preventDefault() {}, stopPropagation() {} };
}

test("measure drag → readout DOM, one primitive, no setData/update (R1/R2/R3)", () => {
  const f = measureFixture();
  try {
    f.chartEl.fire("pointerdown", ev(10, 100));
    f.chartEl.fire("pointermove", ev(50, 120));
    assert.strictEqual(f.host._series.attaches, 1, "one primitive attached while measuring");
    assert.ok(f.host._series.updates > 0, "redraw via requestUpdate (#68)");
    // The readout carries the price/time/bar figures from measure-core.
    assert.match(f.readout.textContent, /\d/);
    assert.notStrictEqual(f.readout.textContent, "");
    // The primitive never moves the scale and never writes series data.
    assert.strictEqual(f.host._series._prim.autoscaleInfo(), null);
  } finally { f.restore(); }
});

test("a new measure replaces the old (one primitive, not two) (R1)", () => {
  const f = measureFixture();
  try {
    f.chartEl.fire("pointerdown", ev(10, 100));
    f.chartEl.fire("pointermove", ev(50, 120));
    f.chartEl.fire("pointerup", ev(50, 120));
    f.chartEl.fire("pointerdown", ev(20, 80));
    f.chartEl.fire("pointermove", ev(60, 90));
    assert.strictEqual(f.host._series.attaches, 1, "the primitive is attached exactly once");
    assert.ok(f.host._series._prim, "a primitive remains after the second gesture");
  } finally { f.restore(); }
});

test("Escape cancels the measurement and clears the readout (R4)", () => {
  const f = measureFixture();
  try {
    f.chartEl.fire("pointerdown", ev(10, 100));
    f.chartEl.fire("pointermove", ev(50, 120));
    f.chartEl.fire("keydown", { key: "Escape", preventDefault() {}, stopPropagation() {} });
    assert.strictEqual(f.host._series._prim, null, "the primitive is detached on Escape");
    assert.strictEqual(f.readout.textContent, "");
  } finally { f.restore(); }
});

test("changing the tool away from measure clears (R4)", () => {
  const f = measureFixture();
  try {
    f.chartEl.fire("pointerdown", ev(10, 100));
    f.chartEl.fire("pointermove", ev(50, 120));
    f.store.set({ tool: "hline" });
    assert.strictEqual(f.host._series._prim, null);
    assert.strictEqual(f.readout.textContent, "");
  } finally { f.restore(); }
});

test("clearForSwitch detaches the primitive and clears the readout (R4)", () => {
  const f = measureFixture();
  try {
    f.chartEl.fire("pointerdown", ev(10, 100));
    f.chartEl.fire("pointermove", ev(50, 120));
    f.m.clearForSwitch();
    assert.strictEqual(f.host._series._prim, null);
    assert.strictEqual(f.readout.textContent, "");
  } finally { f.restore(); }
});

test("no pointerdown starts a measurement when the tool is not measure (R1)", () => {
  const f = measureFixture("hline");
  try {
    f.chartEl.fire("pointerdown", ev(10, 100));
    f.chartEl.fire("pointermove", ev(50, 120));
    assert.strictEqual(f.host._series.attaches, 0, "the gesture is guarded on state.tool");
  } finally { f.restore(); }
});

test("measure re-attaches to the NEW series after a rebuild (#188)", () => {
  // An interval-only switch rebuilds the chart but does not clear the measure;
  // attach() (called on every buildChart) MUST move the primitive to the new
  // series, never leave it on the destroyed one.
  const f = measureFixture();
  try {
    f.chartEl.fire("pointerdown", ev(10, 100));
    f.chartEl.fire("pointermove", ev(50, 120));
    const prim = f.host._series._prim;
    assert.ok(prim, "a primitive is attached while measuring");
    const oldSeries = f.host._series;
    const newSeries = f.host.swap(); // buildChart recreates the candle series
    f.m.attach(); // main calls attach() after every build
    assert.strictEqual(oldSeries._prim, null, "detached from the destroyed series");
    assert.strictEqual(newSeries._prim, prim, "attached to the NEW series");
    assert.notStrictEqual(f.readout.textContent, "", "the readout survives the rebuild");
  } finally { f.restore(); }
});

test("measure attach() is a no-op with no active measurement (#188/R1)", () => {
  // Triangulation: a rebuild with nothing measured attaches nothing.
  const f = measureFixture();
  try {
    f.host.swap();
    f.m.attach();
    assert.strictEqual(f.host._series.attaches, 0, "no phantom primitive on rebuild");
  } finally { f.restore(); }
});

// F6 UI #192: the aria-live readout MUST NOT be rewritten on every pointermove.
// N moves inside one animation frame coalesce to a SINGLE DOM write; the final
// write on pointerup still happens. rAF is shimmed so a frame is flushed on cue.
function withRaf(fn) {
  const prev = globalThis.requestAnimationFrame;
  const queued = [];
  globalThis.requestAnimationFrame = (cb) => { queued.push(cb); return queued.length; };
  try {
    return fn(() => { const q = queued.splice(0); q.forEach((cb) => cb()); });
  } finally {
    if (prev === undefined) delete globalThis.requestAnimationFrame;
    else globalThis.requestAnimationFrame = prev;
  }
}

function countingEl(tag) {
  const el = makeEl(tag);
  let text = "";
  let writes = 0;
  Object.defineProperty(el, "textContent", {
    get: () => text,
    set: (v) => { text = v; writes += 1; },
  });
  Object.defineProperty(el, "writes", { get: () => writes });
  return el;
}

test("measure: N pointermoves in one frame write the live region once (#192)", () => {
  const prevDoc = globalThis.document;
  const chartEl = makeEl("section");
  const readout = countingEl("p");
  globalThis.document = {
    getElementById: (id) => (id === "chart" ? chartEl : id === "measure-readout" ? readout : null),
  };
  try {
    withRaf((flush) => {
      const store = makeStore({ tool: "measure", interval: "1m", symbol: "BTCUSDT" });
      const host = makeHost();
      const m = createMeasure({ store, bus: { on() {}, emit() {} }, host, config: {} });
      m.attach();
      chartEl.fire("pointerdown", ev(10, 100));
      const base = readout.writes; // the pointerdown write is immediate (first point)
      for (let i = 0; i < 20; i++) chartEl.fire("pointermove", ev(10 + i, 100 + i));
      assert.strictEqual(readout.writes, base, "no per-move DOM write before the frame");
      flush();
      assert.strictEqual(readout.writes, base + 1, "20 moves coalesce to one write");
      assert.match(readout.textContent, /\d/, "the coalesced write carries a real figure");
    });
  } finally { globalThis.document = prevDoc; }
});

test("measure: pointerup flushes the final readout write immediately (#192)", () => {
  const prevDoc = globalThis.document;
  const chartEl = makeEl("section");
  const readout = countingEl("p");
  globalThis.document = {
    getElementById: (id) => (id === "chart" ? chartEl : id === "measure-readout" ? readout : null),
  };
  try {
    withRaf(() => {
      const store = makeStore({ tool: "measure", interval: "1m", symbol: "BTCUSDT" });
      const host = makeHost();
      const m = createMeasure({ store, bus: { on() {}, emit() {} }, host, config: {} });
      m.attach();
      chartEl.fire("pointerdown", ev(10, 100));
      chartEl.fire("pointermove", ev(60, 140));
      const before = readout.writes;
      chartEl.fire("pointerup", ev(60, 140)); // no frame flushed first
      assert.strictEqual(readout.writes, before + 1, "pointerup writes the final value");
      assert.match(readout.textContent, /\d/);
    });
  } finally { globalThis.document = prevDoc; }
});


// F6 UI #193 (R9): the measure stroke reads the shell --accent token, not a
// literal, so the light theme stays on-palette. Drive the primitive's renderer
// directly with a token shim + a recording ctx.
function renderMeasurePrim(ctx) {
  return (prim) =>
    prim.paneViews()[0].renderer().draw({
      useMediaCoordinateSpace: (cb) => cb({ context: ctx, mediaSize: { width: 300, height: 300 } }),
    });
}

// --- F7 S3: context menu controller (design §c / R1-R5) ----------------------
//
// The controller owns the ``#chart`` contextmenu listener, the hit-test (the
// pure grabHandle/pointerRows/localPoint reused verbatim), the JS-built
// role="menu" DOM and the ACTION dispatch. A hand-rolled DOM shim (no jsdom)
// keeps it framework-free; the bus is real so the emitted commands are asserted.
const { createContextMenu } = await import(
  "../../web/market/templates/market/controllers/context-menu.js"
);

function menuEl(tag) {
  const el = {
    tagName: tag,
    children: [],
    attrs: {},
    style: {},
    dataset: {},
    _listeners: {},
    textContent: "",
    parentNode: null,
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    hasAttribute(k) { return k in this.attrs; },
    appendChild(c) { c.parentNode = this; this.children.push(c); return c; },
    remove() {
      if (!this.parentNode) return;
      const i = this.parentNode.children.indexOf(this);
      if (i !== -1) this.parentNode.children.splice(i, 1);
      this.parentNode = null;
    },
    contains(node) {
      if (node === this) return true;
      return this.children.some((c) => c.contains(node));
    },
    addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
    focus() { globalThis.document.activeElement = this; },
    getBoundingClientRect() { return { left: 0, top: 0, width: 800, height: 600 }; },
    fire(type, ev) { (this._listeners[type] || []).forEach((fn) => fn(ev || {})); },
  };
  return el;
}

function menuFixture(rows, onAddAlert) {
  const prevDoc = globalThis.document;
  const body = menuEl("body");
  const chart = menuEl("section");
  const docListeners = {};
  globalThis.document = {
    activeElement: null,
    body,
    getElementById: (id) => (id === "chart" ? chart : null),
    createElement: menuEl,
    addEventListener(type, fn) { (docListeners[type] = docListeners[type] || []).push(fn); },
    removeEventListener() {},
    fireDoc(type, ev) { (docListeners[type] || []).forEach((fn) => fn(ev || {})); },
  };
  const store = makeStore({ scaleMode: "linear", indicators: ["sma"], tool: null });
  const host = makeHost();
  const bus = createBus();
  const emitted = [];
  ["drawing:delete", "drawing:duplicate", "scale:changed", "indicator:changed", "drawing:selected"]
    .forEach((e) => bus.on(e, (p) => emitted.push({ event: e, payload: p })));
  const cm = createContextMenu({ store, bus, host, config: {}, onAddAlert });
  cm.attach();
  if (rows) bus.emit("drawings:changed", { rows });
  return {
    cm, store, host, bus, emitted, body, chart,
    restore() { globalThis.document = prevDoc; },
  };
}

function menuNode(body) {
  return body.children.find((c) => c.getAttribute("role") === "menu") || null;
}

function ctxEv(x, y) {
  let prevented = false;
  return { clientX: x, clientY: y, button: 2, preventDefault() { prevented = true; }, _prevented: () => prevented };
}

const HLINE_ROW = { id: 7, kind: "hline", points: { price: 100 }, style: {} };

test("contextmenu on a drawing row opens a role=menu with Delete then Duplicate (R2/R4)", () => {
  const f = menuFixture([HLINE_ROW]);
  try {
    const ev = ctxEv(300, 100);
    f.chart.fire("contextmenu", ev);
    assert.strictEqual(ev._prevented(), true, "default context menu prevented");
    const menu = menuNode(f.body);
    assert.ok(menu, "a role=menu node is appended");
    assert.strictEqual(menu.getAttribute("aria-label") != null, true);
    const labels = menu.children.map((c) => c.textContent);
    assert.deepStrictEqual(labels, ["Delete", "Duplicate"]);
    assert.strictEqual(menu.children.every((c) => c.getAttribute("role") === "menuitem"), true);
    assert.strictEqual(menu.children[0].getAttribute("aria-keyshortcuts"), "Delete");
    // The hit resolved the row: selection is announced on the bus.
    const sel = f.emitted.find((e) => e.event === "drawing:selected");
    assert.deepStrictEqual(sel.payload, { id: 7 });
  } finally { f.restore(); }
});

test("contextmenu on an empty chart offers Add indicator then Add alert (R1/#235)", () => {
  const f = menuFixture([]);
  try {
    f.chart.fire("contextmenu", ctxEv(300, 400));
    const menu = menuNode(f.body);
    assert.ok(menu);
    assert.deepStrictEqual(menu.children.map((c) => c.textContent), ["Add indicator", "Add alert"]);
    const sel = f.emitted.find((e) => e.event === "drawing:selected");
    assert.deepStrictEqual(sel.payload, { id: null });
  } finally { f.restore(); }
});

test("reset-scale appears non-linear and is absent linear (R1)", () => {
  const f = menuFixture([]);
  try {
    f.store.set({ scaleMode: "log" });
    f.chart.fire("contextmenu", ctxEv(300, 400));
    assert.deepStrictEqual(
      menuNode(f.body).children.map((c) => c.textContent),
      ["Reset scale", "Add indicator", "Add alert"],
    );
    // Close, then flip linear: no reset-scale.
    globalThis.document.fireDoc("pointerdown", { target: menuEl("div") });
    f.store.set({ scaleMode: "linear" });
    f.chart.fire("contextmenu", ctxEv(300, 400));
    assert.deepStrictEqual(
      menuNode(f.body).children.map((c) => c.textContent),
      ["Add indicator", "Add alert"],
    );
  } finally { f.restore(); }
});

test("Delete item emits drawing:delete with the hit id (R4)", () => {
  const f = menuFixture([HLINE_ROW]);
  try {
    f.chart.fire("contextmenu", ctxEv(300, 100));
    menuNode(f.body).children[0].fire("click");
    const del = f.emitted.find((e) => e.event === "drawing:delete");
    assert.deepStrictEqual(del.payload, { id: 7 });
    assert.strictEqual(menuNode(f.body), null, "menu closes after activation");
    assert.strictEqual(globalThis.document.activeElement, f.chart, "focus returns to #chart");
  } finally { f.restore(); }
});

test("Duplicate item emits drawing:duplicate with the hit id (R4)", () => {
  const f = menuFixture([HLINE_ROW]);
  try {
    f.chart.fire("contextmenu", ctxEv(300, 100));
    menuNode(f.body).children[1].fire("click");
    const dup = f.emitted.find((e) => e.event === "drawing:duplicate");
    assert.deepStrictEqual(dup.payload, { id: 7 });
  } finally { f.restore(); }
});

test("reset-scale item sets linear + emits scale:changed, never a PUT (R4/#68)", () => {
  const f = menuFixture([]);
  try {
    f.store.set({ scaleMode: "percentage" });
    f.chart.fire("contextmenu", ctxEv(300, 400));
    menuNode(f.body).children[0].fire("click");
    assert.strictEqual(f.store.get().scaleMode, "linear");
    const ev = f.emitted.find((e) => e.event === "scale:changed");
    assert.deepStrictEqual(ev.payload, { mode: "linear" });
  } finally { f.restore(); }
});

test("add-indicator reuses the F5 seam: store membership + indicator:changed (R4)", () => {
  const f = menuFixture([]);
  try {
    f.chart.fire("contextmenu", ctxEv(300, 400));
    menuNode(f.body).children[0].fire("click");
    assert.deepStrictEqual(f.store.get().indicators, ["sma", "ema"]);
    assert.ok(f.emitted.some((e) => e.event === "indicator:changed"));
  } finally { f.restore(); }
});

test("Add alert calls the injected callback and never emits a new bus event (#235)", () => {
  // F10 UI #235: the menu is the non-pointer entry point. It mirrors the
  // onIndicatorSettings precedent — an injected callback, NO new bus event.
  let calls = 0;
  const f = menuFixture([], () => { calls += 1; });
  try {
    f.chart.fire("contextmenu", ctxEv(300, 400));
    menuNode(f.body).children[1].fire("click"); // Add indicator, then Add alert
    assert.strictEqual(calls, 1, "the alerts callback ran exactly once");
    assert.deepStrictEqual(f.emitted.map((e) => e.event), ["drawing:selected"]);
  } finally { f.restore(); }
});

test("Add alert is reachable from the keyboard-opened menu too (#235)", () => {
  // Shift+F10 / ContextMenu open the same model, so the keyboard user reaches
  // the item with no pointer crosshair at all.
  let calls = 0;
  const f = menuFixture([], () => { calls += 1; });
  try {
    f.chart.fire("keydown", keyOpen("ContextMenu"));
    const menu = menuNode(f.body);
    const item = menu.children.find((c) => c.textContent === "Add alert");
    assert.ok(item, "the keyboard menu offers Add alert");
    item.fire("click");
    assert.strictEqual(calls, 1);
  } finally { f.restore(); }
});

test("Escape closes the menu and returns focus to #chart (R3)", () => {
  const f = menuFixture([HLINE_ROW]);
  try {
    f.chart.fire("contextmenu", ctxEv(300, 100));
    const menu = menuNode(f.body);
    menu.fire("keydown", { key: "Escape", preventDefault() {} });
    assert.strictEqual(menuNode(f.body), null);
    assert.strictEqual(globalThis.document.activeElement, f.chart);
  } finally { f.restore(); }
});

test("outside pointerdown closes the menu (R3)", () => {
  const f = menuFixture([HLINE_ROW]);
  try {
    f.chart.fire("contextmenu", ctxEv(300, 100));
    assert.ok(menuNode(f.body));
    globalThis.document.fireDoc("pointerdown", { target: menuEl("span") });
    assert.strictEqual(menuNode(f.body), null);
  } finally { f.restore(); }
});

test("ArrowDown then End then Home rove focus across items (R3)", () => {
  const f = menuFixture([HLINE_ROW]);
  try {
    f.store.set({ scaleMode: "log" }); // 3 items: delete, duplicate, reset-scale
    f.chart.fire("contextmenu", ctxEv(300, 100));
    const menu = menuNode(f.body);
    const items = menu.children;
    assert.strictEqual(globalThis.document.activeElement, items[0], "first item focused on open");
    assert.strictEqual(items[0].getAttribute("tabindex"), "0");
    menu.fire("keydown", { key: "ArrowDown", preventDefault() {} });
    assert.strictEqual(globalThis.document.activeElement, items[1]);
    menu.fire("keydown", { key: "End", preventDefault() {} });
    assert.strictEqual(globalThis.document.activeElement, items[2]);
    menu.fire("keydown", { key: "Home", preventDefault() {} });
    assert.strictEqual(globalThis.document.activeElement, items[0]);
  } finally { f.restore(); }
});

test("the contextmenu listener binds exactly once across attach() calls (R2)", () => {
  const f = menuFixture([]);
  try {
    f.cm.attach();
    f.cm.attach();
    assert.strictEqual(f.chart._listeners.contextmenu.length, 1);
  } finally { f.restore(); }
});

test("clearForSwitch closes an open menu (R4)", () => {
  const f = menuFixture([HLINE_ROW]);
  try {
    f.chart.fire("contextmenu", ctxEv(300, 100));
    assert.ok(menuNode(f.body));
    f.cm.clearForSwitch();
    assert.strictEqual(menuNode(f.body), null);
  } finally { f.restore(); }
});

// --- F7 UI #204: keyboard-open path (Shift+F10 / ContextMenu) ----------------

function keyOpen(key, opts) {
  let prevented = false;
  return Object.assign(
    { key, shiftKey: false, preventDefault() { prevented = true; }, _prevented: () => prevented },
    opts,
  );
}

test("#chart advertises a menu popup (aria-haspopup, F7 UI #204)", () => {
  const html = readFileSync(
    fileURLToPath(new URL("../../web/market/templates/market/chart.html", import.meta.url)),
    "utf8",
  );
  assert.match(html, /id="chart"[^>]*aria-haspopup="menu"/, "chart.html #chart carries aria-haspopup");
});

test("Shift+F10 on #chart opens the menu at the selected drawing (F7 UI #204)", () => {
  const f = menuFixture([HLINE_ROW]);
  try {
    f.chart.getBoundingClientRect = () => ({ left: 40, top: 20 });
    f.bus.emit("drawing:selected", { id: 7 });
    const e = keyOpen("F10", { shiftKey: true });
    f.chart.fire("keydown", e);
    assert.strictEqual(e._prevented(), true, "the native key is consumed");
    const menu = menuNode(f.body);
    assert.ok(menu, "Shift+F10 opens the menu");
    assert.deepStrictEqual(menu.children.map((c) => c.textContent), ["Delete", "Duplicate"]);
    // hline handle at price 100 -> local (0,100); rect (40,20) -> client (40,120).
    assert.strictEqual(menu.style.left, "40px");
    assert.strictEqual(menu.style.top, "120px");
  } finally { f.restore(); }
});

test("ContextMenu key with nothing selected opens at the chart rect+8 (F7 UI #204)", () => {
  const f = menuFixture([]);
  try {
    f.chart.getBoundingClientRect = () => ({ left: 40, top: 20 });
    const e = keyOpen("ContextMenu");
    f.chart.fire("keydown", e);
    assert.strictEqual(e._prevented(), true);
    const menu = menuNode(f.body);
    assert.ok(menu);
    assert.deepStrictEqual(menu.children.map((c) => c.textContent), ["Add indicator", "Add alert"]);
    assert.strictEqual(menu.style.left, "48px");
    assert.strictEqual(menu.style.top, "28px");
  } finally { f.restore(); }
});

test("a bare F10 (no Shift) does not open the menu (F7 UI #204)", () => {
  const f = menuFixture([HLINE_ROW]);
  try {
    const e = keyOpen("F10");
    f.chart.fire("keydown", e);
    assert.strictEqual(menuNode(f.body), null);
    assert.notStrictEqual(e._prevented(), true);
  } finally { f.restore(); }
});

test("an item without a shortcut omits aria-keyshortcuts (F7 UI #206)", () => {
  // The model yields keyshortcut:"" for Duplicate/Add indicator; writing it
  // verbatim leaves an empty (misleading) attribute. Omit it entirely.
  const f = menuFixture([HLINE_ROW]);
  try {
    f.chart.fire("contextmenu", ctxEv(300, 100));
    const items = menuNode(f.body).children;
    assert.strictEqual(items[0].getAttribute("aria-keyshortcuts"), "Delete");
    assert.strictEqual(
      items[1].hasAttribute("aria-keyshortcuts"),
      false,
      "an empty shortcut must not be written",
    );
  } finally { f.restore(); }
});

test("measure stroke paints with the resolved --accent token, not a literal (R9)", () => {
  const f = measureFixture();
  const prevDoc = globalThis.document;
  const prevGcs = globalThis.getComputedStyle;
  const strokes = [];
  const ctx = {
    save() {}, restore() {}, setLineDash() {}, beginPath() {}, moveTo() {}, lineTo() {},
    stroke() { strokes.push(ctx.strokeStyle); }, fillRect() {}, fillText() {},
    set strokeStyle(v) { this._s = v; }, get strokeStyle() { return this._s; },
    set fillStyle(v) {},
    font: "", lineWidth: 1, globalAlpha: 1,
  };
  try {
    f.chartEl.fire("pointerdown", ev(10, 100));
    f.chartEl.fire("pointermove", ev(50, 120));
    // Override the token shim AFTER the fixture installed its document stub.
    globalThis.document = { ...prevDoc, documentElement: {} };
    globalThis.getComputedStyle = () => ({ getPropertyValue: (n) => (n === "--accent" ? "#0969da" : "") });
    renderMeasurePrim(ctx)(f.host._series._prim);
    assert.ok(strokes.includes("#0969da"), `measure stroke uses --accent: ${strokes}`);
    assert.ok(!strokes.includes("#2962ff"), "measure literal must not be painted");
  } finally {
    if (prevDoc === undefined) delete globalThis.document; else globalThis.document = prevDoc;
    if (prevGcs === undefined) delete globalThis.getComputedStyle; else globalThis.getComputedStyle = prevGcs;
    f.restore();
  }
});

// --- F9 R2 (#222): a pending draft is VISIBLE + the cursor is a crosshair ----
//
// A 2/3-click draft used to draw nothing until the final click: the user clicked
// into a void. The controller now attaches a TRANSIENT preview primitive after
// every pending click (a primitive + requestUpdate, never a POST, #68), and
// #chart shows a crosshair while a tool is active.
function draftsPreviewFixture() {
  const prevDoc = globalThis.document;
  const prevWin = globalThis.window;
  const prevFetch = globalThis.fetch;
  const prevGcs = globalThis.getComputedStyle;
  const attached = [];
  const posts = [];
  const chartEl = makeEl("div");
  globalThis.document = {
    getElementById: (id) => (id === "chart" ? chartEl : null),
    querySelector: () => null,
    documentElement: { style: {} },
  };
  globalThis.getComputedStyle = () => ({ getPropertyValue: () => "" });
  globalThis.window = { marketChart: { drawings: [] } };
  globalThis.fetch = (url, opts) => {
    const method = (opts && opts.method) || "GET";
    const body = JSON.parse((opts && opts.body) || "{}");
    if (method !== "GET") posts.push({ url, method, body });
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ drawings: [], id: 1, kind: body.kind, points: body.points }),
    });
  };
  const chart = { timeScale: () => ({ timeToCoordinate: (t) => t }) };
  const series = {
    // Mirror v5: attaching hands the primitive its chart/series/requestUpdate.
    attachPrimitive(prim) {
      attached.push(prim);
      prim.attached({ chart: chart, series: series, requestUpdate() {} });
    },
    detachPrimitive() {},
    coordinateToPrice: (y) => y,
    priceToCoordinate: (p) => p,
  };
  const bus = createBus();
  const store = makeStore({ symbol: "BTCUSDT", interval: "1m", tool: null });
  const host = { getChart: () => chart, getCandleSeries: () => series };
  const d = createDrawings({ store, bus, host, config: { urls: { drawings: "/market/api/drawings" } } });
  return {
    d, store, chartEl, attached, posts,
    tool: (kind) => store.set({ tool: kind }),
    click(time, price) { d.onChartClick({ time, point: { y: price } }); },
    restore() {
      if (prevDoc === undefined) delete globalThis.document; else globalThis.document = prevDoc;
      if (prevWin === undefined) delete globalThis.window; else globalThis.window = prevWin;
      if (prevFetch === undefined) delete globalThis.fetch; else globalThis.fetch = prevFetch;
      if (prevGcs === undefined) delete globalThis.getComputedStyle; else globalThis.getComputedStyle = prevGcs;
    },
  };
}

test("the first click of a channel attaches a preview primitive, no POST (#222)", () => {
  const f = draftsPreviewFixture();
  try {
    f.tool("channel");
    f.click(1, 10);
    assert.strictEqual(f.attached.length, 1, "a preview primitive is attached");
    assert.deepStrictEqual(f.posts, [], "a pending draft never POSTs");
    // The preview row carries the first anchor and renders a stroke/point.
    const drawn = [];
    const ctx = {
      save() {}, restore() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {},
      arc(x, y) { drawn.push({ x, y }); }, fill() {}, setLineDash() {},
      strokeRect() {}, fillRect() {}, fillText() {},
      strokeStyle: "", fillStyle: "", lineWidth: 1, globalAlpha: 1, font: "",
    };
    f.attached[0].paneViews()[0].renderer().draw({
      useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width: 100, height: 100 } }),
    });
    assert.deepStrictEqual(drawn, [{ x: 1, y: 10 }], "the first anchor is drawn at its pixel");
  } finally { f.restore(); }
});

test("#chart shows a crosshair cursor while a tool is active (#222)", () => {
  const f = draftsPreviewFixture();
  try {
    assert.strictEqual(f.chartEl.style.cursor, "", "no tool -> no cursor override");
    f.tool("ray");
    assert.strictEqual(f.chartEl.style.cursor, "crosshair");
    f.tool(null);
    assert.strictEqual(f.chartEl.style.cursor, "", "the cursor is restored");
  } finally { f.restore(); }
});

test("the draft preview never moves the price scale (#222/#68)", () => {
  const f = draftsPreviewFixture();
  try {
    f.tool("channel");
    f.click(1, 10);
    assert.strictEqual(f.attached[0].autoscaleInfo(), null, "a preview must not rescale");
  } finally { f.restore(); }
});


// --- symbol picker: follow/unfollow toggle (F11 A-S4 / R19) ------------------
//
// The listbox rows are JS-built, so this drives the real controller with a
// minimal DOM shim. It proves the ONE thing a static markup test cannot: a
// followed symbol can be UNfollowed again (the button is never disabled) and
// the request method flips POST -> DELETE.
const { createSymbolPicker } = await import(
  "../../web/market/templates/market/controllers/symbol-picker.js"
);

function pickerFixture(watchlist) {
  const prevDoc = globalThis.document;
  const prevFetch = globalThis.fetch;
  const calls = [];

  function makeNode(tag) {
    return {
      tagName: tag,
      children: [],
      dataset: {},
      attributes: {},
      textContent: "",
      hidden: true,
      id: "",
      type: "",
      className: "",
      _handlers: {},
      appendChild(child) { this.children.push(child); return child; },
      setAttribute(name, value) { this.attributes[name] = value; },
      removeAttribute(name) { delete this.attributes[name]; },
      addEventListener(name, fn) { this._handlers[name] = fn; },
      contains() { return false; },
      querySelectorAll(sel) {
        return this.children.filter((c) => c.attributes.role === "option");
      },
      scrollIntoView() {},
    };
  }

  const input = makeNode("input");
  const list = makeNode("ul");
  const status = makeNode("p");

  globalThis.document = {
    getElementById(id) {
      if (id === "symbol-search") return input;
      if (id === "symbol-results") return list;
      if (id === "symbol-status") return status;
      return null;
    },
    querySelector: () => ({ content: "tok" }),
    createElement: makeNode,
    addEventListener() {},
  };

  globalThis.fetch = (url, opts) => {
    const method = (opts && opts.method) || "GET";
    calls.push({ url, method });
    const body =
      url.indexOf("symbols") !== -1
        ? { symbols: ["BTCUSDT", "ETHUSDT"] }
        : { symbols: watchlist };
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  };

  const picker = createSymbolPicker({
    store: { get: () => ({ interval: "1m" }) },
    bus: { emit() {} },
    config: {
      symbols: ["BTCUSDT"],
      saveDelay: 0,
      urls: { symbols: "/market/api/symbols", watchlist: "/market/api/watchlist" },
    },
  });

  return {
    picker, calls, input, list,
    restore() {
      if (prevDoc === undefined) delete globalThis.document; else globalThis.document = prevDoc;
      if (prevFetch === undefined) delete globalThis.fetch; else globalThis.fetch = prevFetch;
    },
  };
}

test("symbol picker: a followed symbol can be unfollowed (DELETE, not disabled)", async () => {
  const f = pickerFixture(["BTCUSDT"]);
  try {
    await f.picker.refresh();
    f.input._handlers.input.call(f.input, {});
    const options = f.list.querySelectorAll("option");
    const btc = options.find((o) => o.dataset.symbol === "BTCUSDT");
    const button = btc.children[1];

    assert.strictEqual(button.disabled, undefined, "follow button is never disabled");
    assert.strictEqual(button.attributes["aria-pressed"], "true", "starts followed");

    f.calls.length = 0;
    const clickHandler = button._handlers.click;
    assert.ok(clickHandler, "a click handler is attached to the follow button");
    clickHandler({ stopPropagation() {} });
    await Promise.resolve();
    await Promise.resolve();

    assert.deepStrictEqual(
      f.calls.map((c) => c.method),
      ["DELETE"],
      "unfollow issues DELETE",
    );
    assert.ok(
      f.calls[0].url.endsWith("/BTCUSDT"),
      "DELETE targets the symbol path",
    );
  } finally {
    f.restore();
  }
});
