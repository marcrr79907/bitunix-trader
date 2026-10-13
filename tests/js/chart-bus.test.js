// Tiny event bus — node --test (no DOM, no deps).
import test from "node:test";
import assert from "node:assert";
import { createBus, EVENTS } from "../../web/market/templates/market/chart-bus.js";

test("on + emit delivers the payload to every listener", () => {
  const bus = createBus();
  const got = [];
  bus.on("chart:built", (p) => got.push(p));
  bus.on("chart:built", (p) => got.push(p.id));
  bus.emit("chart:built", { id: 7 });
  assert.deepStrictEqual(got, [{ id: 7 }, 7]);
});

test("off removes only the given listener", () => {
  const bus = createBus();
  const a = [];
  const b = [];
  const fa = (p) => a.push(p);
  const fb = (p) => b.push(p);
  bus.on("ready", fa);
  bus.on("ready", fb);
  bus.off("ready", fa);
  bus.emit("ready");
  assert.deepStrictEqual(a, []);
  assert.deepStrictEqual(b, [undefined]); // fb still subscribed
});

test("emit with no listeners is a no-op and events stay isolated", () => {
  const bus = createBus();
  let calls = 0;
  bus.on("a", () => { calls += 1; });
  bus.emit("b", 1); // nobody on b
  bus.emit("a");
  assert.strictEqual(calls, 1);
});

test("emitting inside a listener does not corrupt the listener list", () => {
  const bus = createBus();
  const seen = [];
  bus.on("x", () => {
    seen.push("first");
    bus.off("x", second); // mutate the list mid-emit
  });
  const second = () => seen.push("second");
  bus.on("x", second);
  bus.emit("x");
  bus.emit("x");
  assert.deepStrictEqual(seen, ["first", "second", "first"]);
});

test("EVENTS freezes the command/notification names", () => {
  assert.strictEqual(EVENTS.configChanged, "config:changed");
  assert.strictEqual(EVENTS.indicatorChanged, "indicator:changed");
  assert.strictEqual(EVENTS.ready, "ready");
  assert.ok(Object.isFrozen(EVENTS));
});
