// controllers/alerts.js — controller contract under a tiny DOM shim (no jsdom).
//
// The chart library and the REST API are browser concerns (covered by the E2E
// suite); what this test pins is the controller's own observable contract:
// the bell follows the crosshair, the interval guard disables it, Apply writes
// exactly one POST/PUT through the pure cores, and a switch detaches the
// marker handle. Mirrors object-tree.test.js / preference.test.js.
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createBus } from "../../web/market/templates/market/chart-bus.js";
import { createAlerts } from "../../web/market/templates/market/controllers/alerts.js";

// --- minimal DOM shim -------------------------------------------------------
function makeEl(tag) {
  const el = {
    tagName: tag,
    id: "",
    className: "",
    hidden: false,
    disabled: false,
    open: false,
    returnValue: "",
    value: "",
    textContent: "",
    style: {},
    children: [],
    attrs: {},
    _listeners: {},
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    removeAttribute(k) { delete this.attrs[k]; },
    appendChild(c) { this.children.push(c); return c; },
    remove() {},
    addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
    fire(type, ev) { (this._listeners[type] || []).forEach((fn) => fn(ev || {})); },
    showModal() { this.open = true; },
    close(v) { this.open = false; this.returnValue = v || ""; this.fire("close", {}); },
    focus() { globalThis.document.activeElement = this; },
    click() { this.fire("click", { preventDefault() {} }); },
  };
  return el;
}

function makeStore(initial) {
  const state = { ...initial };
  return {
    get: () => state,
    set: (patch) => Object.assign(state, patch),
    subscribe: () => {},
  };
}

function installDom() {
  const chartEl = makeEl("section");
  const dialog = makeEl("dialog");
  const op = makeEl("select");
  const level = makeEl("input");
  const error = makeEl("p");
  const status = makeEl("p");
  const reason = makeEl("p");
  const els = {
    chart: chartEl,
    "alert-dialog": dialog,
    "alert-op": op,
    "alert-level": level,
    "alert-error": error,
    "alert-status": status,
    "alert-interval-reason": reason,
  };
  const prevDoc = globalThis.document;
  const prevLwc = globalThis.LightweightCharts;
  const prevFetch = globalThis.fetch;
  globalThis.document = {
    activeElement: null,
    getElementById: (id) => els[id] || null,
    createElement: makeEl,
    querySelector: (sel) =>
      sel === 'meta[name="csrf-token"]' ? { content: "csrf-abc" } : null,
  };
  const handles = [];
  globalThis.LightweightCharts = {
    createSeriesMarkers(series, list) {
      const h = {
        series, list, detached: false,
        setMarkers(next) { this.list = next; },
        detach() { this.detached = true; },
      };
      handles.push(h);
      return h;
    },
  };
  const requests = [];
  globalThis.fetch = (url, opts) => {
    const method = (opts && opts.method) || "GET";
    requests.push({ url, method, body: opts && opts.body ? JSON.parse(opts.body) : null });
    if (method === "GET") {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ alerts: rows }) });
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ id: 9, condition: JSON.parse(opts.body).condition }),
    });
  };
  let rows = [];
  return {
    els, requests, handles,
    seed(next) { rows = next; },
    restore() {
      globalThis.document = prevDoc;
      globalThis.LightweightCharts = prevLwc;
      globalThis.fetch = prevFetch;
    },
  };
}

function makeHost(candles) {
  let crosshair = null;
  return {
    candles,
    subscribeCrosshairMove(fn) { crosshair = fn; },
    move(param) { if (crosshair) crosshair(param); },
    getCandles: () => candles,
    getCandleSeries: () => ({
      coordinateToPrice: (y) => 200 - y, // 100 at y=100
      priceToCoordinate: (p) => 200 - p,
    }),
  };
}

async function settle() {
  for (let i = 0; i < 8; i += 1) await Promise.resolve();
}

function fixture({ interval = "1h", candles = [{ time: 5, close: 90 }] } = {}) {
  const dom = installDom();
  const bus = createBus();
  const store = makeStore({ symbol: "BTCUSDT", interval });
  const host = makeHost(candles);
  const alerts = createAlerts({
    store,
    bus,
    host,
    config: { urls: { alerts: "/market/api/alerts" } },
  });
  alerts.attach();
  bus.emit("chart:built", {});
  return { dom, bus, store, host, alerts };
}

// --- bell -------------------------------------------------------------------

test("bell follows the crosshair and hides without a point", async () => {
  const f = fixture();
  try {
    const bell = f.dom.els.chart.children.find((c) => c.id === "chart-alert-bell");
    assert.ok(bell, "the bell is appended to #chart");
    f.host.move({ point: { x: 30, y: 100 } });
    assert.strictEqual(bell.hidden, false);
    assert.strictEqual(bell.style.top, "100px");
    assert.match(bell.getAttribute("aria-label"), /100/);
    f.host.move({});
    assert.strictEqual(bell.hidden, true);
  } finally { f.dom.restore(); }
});

test("bell is disabled with a described reason on a non-evaluable interval", async () => {
  const f = fixture({ interval: "3d" });
  try {
    const bell = f.dom.els.chart.children.find((c) => c.id === "chart-alert-bell");
    f.host.move({ point: { x: 10, y: 100 } });
    assert.strictEqual(bell.disabled, true);
    assert.strictEqual(bell.getAttribute("aria-describedby"), "alert-interval-reason");
    assert.match(f.dom.els["alert-interval-reason"].textContent, /3d/);

    f.store.set({ interval: "1h" });
    await f.alerts.refresh(); // main.refresh() on a pair switch
    f.host.move({ point: { x: 10, y: 100 } });
    assert.strictEqual(bell.disabled, false);
    assert.strictEqual(bell.getAttribute("aria-describedby"), undefined);
    assert.strictEqual(f.dom.requests.length, 1, "the 3d fetch is skipped, 1h fetches");
  } finally { f.dom.restore(); }
});

// --- dialog -----------------------------------------------------------------

test("Apply creates one price alert through the cores", async () => {
  const f = fixture({ candles: [{ time: 5, close: 90 }] });
  try {
    f.host.move({ point: { x: 10, y: 100 } }); // price 100, above close 90
    const bell = f.dom.els.chart.children.find((c) => c.id === "chart-alert-bell");
    bell.click();
    const dialog = f.dom.els["alert-dialog"];
    assert.strictEqual(dialog.open, true);
    assert.strictEqual(f.dom.els["alert-level"].value, "100");
    assert.strictEqual(f.dom.els["alert-op"].value, "above");

    dialog.returnValue = "ok";
    dialog.close("ok");
    await settle();

    const posts = f.dom.requests.filter((r) => r.method === "POST");
    assert.strictEqual(posts.length, 1);
    assert.strictEqual(posts[0].url, "/market/api/alerts");
    assert.deepStrictEqual(posts[0].body.condition, { type: "price", op: "above", level: 100 });
    assert.strictEqual(posts[0].body.symbol, "BTCUSDT");
    assert.strictEqual(posts[0].body.interval, "1h");
  } finally { f.dom.restore(); }
});

test("a nearby price rule is edited with PUT instead of a duplicate POST", async () => {
  const f = fixture();
  f.dom.seed([
    { id: 7, condition: { type: "price", op: "above", level: 100.5 }, is_active: true, last_fired_at: null },
  ]);
  try {
    await settle(); // the build fetch populates the rules
    f.host.move({ point: { x: 10, y: 100 } }); // price 100 -> 0.5px from 100.5
    const bell = f.dom.els.chart.children.find((c) => c.id === "chart-alert-bell");
    bell.click();
    f.dom.els["alert-dialog"].close("ok");
    await settle();

    assert.strictEqual(f.dom.requests.filter((r) => r.method === "POST").length, 0);
    const puts = f.dom.requests.filter((r) => r.method === "PUT");
    assert.strictEqual(puts.length, 1);
    assert.strictEqual(puts[0].url, "/market/api/alerts/7");
  } finally { f.dom.restore(); }
});

test("an invalid level writes nothing and keeps the dialog open", async () => {
  const f = fixture();
  try {
    f.host.move({ point: { x: 10, y: 100 } });
    const bell = f.dom.els.chart.children.find((c) => c.id === "chart-alert-bell");
    bell.click();
    f.dom.els["alert-level"].value = "abc";
    f.dom.els["alert-dialog"].close("ok");
    await settle();
    assert.strictEqual(f.dom.requests.filter((r) => r.method !== "GET").length, 0);
    assert.strictEqual(f.dom.els["alert-dialog"].open, true);
    assert.notStrictEqual(f.dom.els["alert-error"].hidden, true);
  } finally { f.dom.restore(); }
});

test("Cancel writes nothing and returns focus to #chart", async () => {
  const f = fixture();
  try {
    f.host.move({ point: { x: 10, y: 100 } });
    const bell = f.dom.els.chart.children.find((c) => c.id === "chart-alert-bell");
    bell.click();
    f.dom.els["alert-dialog"].close("cancel");
    await settle();
    assert.strictEqual(f.dom.requests.filter((r) => r.method !== "GET").length, 0);
    assert.strictEqual(globalThis.document.activeElement, f.dom.els.chart);
  } finally { f.dom.restore(); }
});

// --- markers ----------------------------------------------------------------

test("markers are created from the armed/fired rules and anchored on the newest candle", async () => {
  const f = fixture();
  f.dom.seed([
    { id: 1, condition: { type: "price", op: "above", level: 100 }, is_active: true, last_fired_at: 5 },
    { id: 2, condition: { type: "price", op: "below", level: 80 }, is_active: true, last_fired_at: null },
  ]);
  try {
    await settle();
    const h = f.dom.handles[0];
    assert.ok(h, "a marker handle is created");
    assert.strictEqual(h.list.length, 2);
    assert.strictEqual(h.list[0].text, "F 100");
    assert.strictEqual(h.list[1].time, 5, "armed anchors on the newest candle time");
  } finally { f.dom.restore(); }
});

test("clearForSwitch detaches the marker handle and clears the bell", async () => {
  const f = fixture();
  try {
    await settle();
    f.host.move({ point: { x: 10, y: 100 } });
    f.alerts.clearForSwitch();
    assert.strictEqual(f.dom.handles[0].detached, true);
    const bell = f.dom.els.chart.children.find((c) => c.id === "chart-alert-bell");
    assert.strictEqual(bell.hidden, true);
  } finally { f.dom.restore(); }
});

// --- layering guard ---------------------------------------------------------

test("controllers/smc.js carries no alert token", () => {
  // The design's "smc.js byte-untouched" proof at test level: markers live in
  // alerts.js only, so the served SMC controller must never grow the word.
  const here = fileURLToPath(import.meta.url);
  const path = here.replace(/tests\/js\/[^/]+$/, "web/market/templates/market/controllers/smc.js");
  assert.doesNotMatch(readFileSync(path, "utf8"), /alert/i);
});
