// Observable UI/config store — node --test (no DOM, no chart lib, no network).
// The store holds UI/config ONLY: candle data lives in chart-host.js (#68).
import test from "node:test";
import assert from "node:assert";
import {
  createStore,
  STORE_KEYS,
} from "../../web/market/templates/market/chart-store.js";

test("get returns the initial config state", () => {
  const store = createStore({
    symbol: "BTCUSDT",
    interval: "1m",
    indicators: ["sma"],
    params: { sma: { sma_len: 20 } },
    smc: { swings: true },
    tool: null,
  });
  assert.deepStrictEqual(store.get(), {
    symbol: "BTCUSDT",
    interval: "1m",
    indicators: ["sma"],
    params: { sma: { sma_len: 20 } },
    styles: undefined,
    smc: { swings: true },
    tool: null,
  });
});

test("set merges a patch in place and keeps the same state reference", () => {
  const store = createStore({ symbol: "BTCUSDT", interval: "1m", tool: null });
  const before = store.get();
  store.set({ interval: "5m" });
  assert.strictEqual(store.get(), before); // same ref, not a copy
  assert.strictEqual(store.get().interval, "5m");
  assert.strictEqual(store.get().symbol, "BTCUSDT"); // untouched keys survive
});

test("subscribe is notified on set and returns an unsubscribe", () => {
  const store = createStore({ symbol: "BTCUSDT", interval: "1m", tool: null });
  const seen = [];
  const unsub = store.subscribe((s) => seen.push(s.interval));
  store.set({ interval: "5m" });
  store.set({ interval: "15m" });
  unsub();
  store.set({ interval: "1h" }); // after unsub: not delivered
  assert.deepStrictEqual(seen, ["5m", "15m"]);
});

test("multiple subscribers each receive the update", () => {
  const store = createStore({ symbol: "BTCUSDT", interval: "1m", tool: null });
  let a = 0;
  let b = 0;
  store.subscribe(() => { a += 1; });
  store.subscribe(() => { b += 1; });
  store.set({ symbol: "ETHUSDT" });
  assert.strictEqual(a, 1);
  assert.strictEqual(b, 1);
});

test("set never admits candle data — the key set is frozen (#68)", () => {
  const store = createStore({ symbol: "BTCUSDT", interval: "1m", tool: null });
  store.set({ candles: [{ time: 1, close: 2 }], symbol: "ETHUSDT" });
  assert.strictEqual(store.get().candles, undefined);
  assert.strictEqual(store.get().symbol, "ETHUSDT");
  // And the constructor drops them too.
  const seeded = createStore({ symbol: "X", interval: "1m", candles: [1, 2] });
  assert.strictEqual(seeded.get().candles, undefined);
});

test("STORE_KEYS is exactly the UI/config vocabulary (7 incl. styles)", () => {
  assert.deepStrictEqual(STORE_KEYS.slice().sort(), [
    "indicators",
    "interval",
    "params",
    "smc",
    "styles",
    "symbol",
    "tool",
  ]);
});

test("styles is a top-level slot, never nested under params", () => {
  const store = createStore({
    symbol: "BTCUSDT",
    interval: "1m",
    params: { sma: { sma_len: 20 } },
    styles: { sma: { color: "#ff0000", lineWidth: 2, precision: 4 } },
  });
  assert.deepStrictEqual(store.get().styles, {
    sma: { color: "#ff0000", lineWidth: 2, precision: 4 },
  });
  // The patch merge keeps styles a top-level key and does not leak into params.
  store.set({ styles: { ema: { color: "#00ff00" } } });
  assert.deepStrictEqual(store.get().styles, { ema: { color: "#00ff00" } });
  assert.deepStrictEqual(store.get().params, { sma: { sma_len: 20 } });
});
