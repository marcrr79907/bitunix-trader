// Controller pure-helper tests — node --test (DOM-free helpers only).
//
// The controllers are DI factories whose DOM/chart/REST methods need a browser
// (covered by E2E). The pure mapping helpers they expose have no DOM and are
// unit-tested here, mirroring the Slice 1/2 core-test discipline.
import test from "node:test";
import assert from "node:assert";
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

// --- measure controller (F6 S3 / R1-R4) --------------------------------------
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

// F6 UI #193 (R9): the measure stroke reads the shell --accent token, not a
// literal, so the light theme stays on-palette. Drive the primitive's renderer
// directly with a token shim + a recording ctx.
function renderMeasurePrim(ctx) {
  return (prim) =>
    prim.paneViews()[0].renderer().draw({
      useMediaCoordinateSpace: (cb) => cb({ context: ctx, mediaSize: { width: 300, height: 300 } }),
    });
}

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
