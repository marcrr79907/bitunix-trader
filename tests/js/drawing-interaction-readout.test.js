// Position R:R readout (F6 / design-system R6) — node --test, DOM shim.
//
// The selected position's R:R MUST live in an ``aria-live`` DOM node (the canvas
// text stays as visual reinforcement). The interaction controller owns the
// selection + drag path, so it writes that node from the pure position-core.
// A hand-rolled shim (no jsdom) keeps the test framework-free.
import test from "node:test";
import assert from "node:assert";
const { createDrawingInteraction } = await import(
  "../../web/market/templates/market/controllers/drawing-interaction.js"
);
const { createBus } = await import(
  "../../web/market/templates/market/chart-bus.js"
);

function makeEl() {
  return {
    _listeners: {},
    textContent: "",
    hasAttribute() { return false; },
    setAttribute() {},
    addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
    getBoundingClientRect() { return { left: 0, top: 0 }; },
  };
}

function makeStore() {
  const state = { tool: null };
  return { get: () => state };
}

function fixture() {
  const chartEl = makeEl();
  const readout = makeEl();
  const prev = globalThis.document;
  globalThis.document = {
    getElementById: (id) => (id === "chart" ? chartEl : id === "position-readout" ? readout : null),
  };
  const bus = createBus();
  createDrawingInteraction({
    store: makeStore(),
    bus,
    host: { getChart: () => null, getCandleSeries: () => null },
    config: {},
  });
  return { bus, readout, restore: () => { globalThis.document = prev; } };
}

const POSITION = {
  id: 7,
  kind: "position",
  points: { entry: { time: 10, price: 100 }, stop: 90, take_profit: 120 },
  style: {},
};

test("selecting a position writes its R:R to the aria-live readout (R6)", () => {
  const f = fixture();
  try {
    f.bus.emit("drawings:changed", { rows: [POSITION] });
    f.bus.emit("drawing:selected", { id: 7 });
    // entry=100, stop=90, tp=120 -> risk 10, reward 20, rr 2.
    assert.strictEqual(f.readout.textContent, "R:R 2.00");
  } finally { f.restore(); }
});

test("selecting a non-position clears the position readout (R6)", () => {
  const f = fixture();
  try {
    const hline = { id: 8, kind: "hline", points: { price: 100 }, style: {} };
    f.bus.emit("drawings:changed", { rows: [POSITION, hline] });
    f.bus.emit("drawing:selected", { id: 7 });
    assert.strictEqual(f.readout.textContent, "R:R 2.00");
    f.bus.emit("drawing:selected", { id: 8 });
    assert.strictEqual(f.readout.textContent, "", "a non-position clears the R:R");
  } finally { f.restore(); }
});

test("deselecting clears the readout (R6)", () => {
  const f = fixture();
  try {
    f.bus.emit("drawings:changed", { rows: [POSITION] });
    f.bus.emit("drawing:selected", { id: 7 });
    f.bus.emit("drawing:selected", { id: null });
    assert.strictEqual(f.readout.textContent, "");
  } finally { f.restore(); }
});

test("dragging the selected position refreshes the R:R (R6/R10)", () => {
  const f = fixture();
  try {
    f.bus.emit("drawings:changed", { rows: [POSITION] });
    f.bus.emit("drawing:selected", { id: 7 });
    assert.strictEqual(f.readout.textContent, "R:R 2.00");
    // The drag moves stop 90 -> 95 (risk 5, reward 20, rr 4).
    f.bus.emit("drawing:changed", {
      id: 7,
      points: { entry: { time: 10, price: 100 }, stop: 95, take_profit: 120 },
      persist: false,
    });
    assert.strictEqual(f.readout.textContent, "R:R 4.00");
  } finally { f.restore(); }
});
