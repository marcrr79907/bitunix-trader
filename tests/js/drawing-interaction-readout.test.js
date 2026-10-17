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

// F6 UI #192: a drag frame at 60fps must not rewrite the aria-live region on
// every frame. N drag updates inside one animation frame coalesce to ONE DOM
// write; the drag-end (persist:true) flushes the final value immediately.
function countingFixture() {
  const chartEl = makeEl();
  const readout = makeEl();
  let text = "";
  let writes = 0;
  Object.defineProperty(readout, "textContent", {
    get: () => text,
    set: (v) => { text = v; writes += 1; },
  });
  Object.defineProperty(readout, "writes", { get: () => writes });
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

function withRaf(fn) {
  const prev = globalThis.requestAnimationFrame;
  const queued = [];
  globalThis.requestAnimationFrame = (cb) => { queued.push(cb); return queued.length; };
  try {
    return fn(() => { queued.splice(0).forEach((cb) => cb()); });
  } finally {
    if (prev === undefined) delete globalThis.requestAnimationFrame;
    else globalThis.requestAnimationFrame = prev;
  }
}

test("N drag frames in one animation frame write the position readout once (#192)", () => {
  const f = countingFixture();
  try {
    withRaf((flush) => {
      f.bus.emit("drawings:changed", { rows: [POSITION] });
      f.bus.emit("drawing:selected", { id: 7 });
      const base = f.readout.writes; // the selection write is immediate
      for (let i = 0; i < 20; i++) {
        const stop = 90 + i; // a distinct drag frame each time
        f.bus.emit("drawing:changed", {
          id: 7,
          points: { entry: { time: 10, price: 100 }, stop, take_profit: 120 },
          persist: false,
        });
      }
      assert.strictEqual(f.readout.writes, base, "no per-frame DOM write before the frame");
      flush();
      assert.strictEqual(f.readout.writes, base + 1, "20 drag frames coalesce to one write");
      // The last frame (i=19) has stop=109: short, risk 9, reward -20 -> rr -2.22.
      assert.strictEqual(f.readout.textContent, "R:R -2.22", "the coalesced write is the last value");
    });
  } finally { f.restore(); }
});

test("the drag-end write (persist:true) flushes immediately (#192)", () => {
  const f = countingFixture();
  try {
    withRaf(() => {
      f.bus.emit("drawings:changed", { rows: [POSITION] });
      f.bus.emit("drawing:selected", { id: 7 });
      f.bus.emit("drawing:changed", {
        id: 7,
        points: { entry: { time: 10, price: 100 }, stop: 95, take_profit: 120 },
        persist: false,
      });
      const before = f.readout.writes;
      f.bus.emit("drawing:changed", {
        id: 7,
        points: { entry: { time: 10, price: 100 }, stop: 80, take_profit: 120 },
        persist: true, // endDrag: the final value MUST be written now
      });
      assert.strictEqual(f.readout.writes, before + 1, "the drag-end writes immediately");
      // entry=100, stop=80, tp=120 -> long, risk 20, reward 20, rr 1.
      assert.strictEqual(f.readout.textContent, "R:R 1.00");
    });
  } finally { f.restore(); }
});
