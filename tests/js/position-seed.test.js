// controllers/position-seed.js — seed button state + setup cache (F6 UI #194).
// node --test, DOM shim (no jsdom). The button is disabled until ``smc:loaded``
// provides a setup; re-enabled when one arrives; a click copies the most recent
// setup's levels VERBATIM into the onSeed callback.
import test from "node:test";
import assert from "node:assert";
const { createPositionSeed } = await import(
  "../../web/market/templates/market/controllers/position-seed.js"
);

function makeEl() {
  return {
    _listeners: {},
    disabled: false,
    addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
    click() { (this._listeners.click || []).forEach((fn) => fn({})); },
  };
}

function makeBus() {
  const handlers = {};
  return {
    on(type, fn) { (handlers[type] = handlers[type] || []).push(fn); },
    emit(type, payload) { (handlers[type] || []).forEach((fn) => fn(payload)); },
  };
}

function fixture() {
  const button = makeEl();
  const prev = globalThis.document;
  globalThis.document = {
    getElementById: (id) => (id === "position-seed" ? button : null),
  };
  const bus = makeBus();
  const seeded = [];
  const seed = createPositionSeed({ bus, onSeed: (points) => seeded.push(points) });
  return {
    button,
    bus,
    seeded,
    seed,
    restore: () => { globalThis.document = prev; },
  };
}

const SETUP = { time: 100, entry: 50, stop: 45, take_profit: 60, direction: "long" };

test("seed button starts disabled before any setup arrives (#194)", () => {
  const f = fixture();
  try {
    assert.strictEqual(f.button.disabled, true, "no setup -> the seed is disabled");
  } finally { f.restore(); }
});

test("smc:loaded with a setup enables the seed; empty re-disables it (#194)", () => {
  const f = fixture();
  try {
    f.bus.emit("smc:loaded", { payload: { setups: [SETUP] } });
    assert.strictEqual(f.button.disabled, false, "a setup enables the seed");
    f.bus.emit("smc:loaded", { payload: { setups: [] } });
    assert.strictEqual(f.button.disabled, true, "an empty payload re-disables it");
  } finally { f.restore(); }
});

test("clicking the enabled seed copies the most recent setup verbatim (#194)", () => {
  const f = fixture();
  try {
    const older = { time: 90, entry: 40, stop: 35, take_profit: 55 };
    f.bus.emit("smc:loaded", { payload: { setups: [older, SETUP] } });
    f.button.click();
    assert.deepStrictEqual(f.seeded, [
      { entry: { time: 100, price: 50 }, stop: 45, take_profit: 60 },
    ]);
  } finally { f.restore(); }
});

test("clicking with no setup is a no-op (never seeds) (#194)", () => {
  const f = fixture();
  try {
    f.button.click(); // still disabled / no setup
    assert.deepStrictEqual(f.seeded, []);
  } finally { f.restore(); }
});
