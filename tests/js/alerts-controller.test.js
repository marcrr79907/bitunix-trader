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
    classList: {
      _set: new Set(),
      add(c) { this._set.add(c); },
      remove(c) { this._set.delete(c); },
      contains(c) { return this._set.has(c); },
    },
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
  const cue = makeEl("p");
  cue.hidden = true;
  const confirm = makeEl("p");
  confirm.hidden = true;
  const els = {
    chart: chartEl,
    "alert-dialog": dialog,
    "alert-op": op,
    "alert-level": level,
    "alert-error": error,
    "alert-status": status,
    "alert-interval-reason": reason,
    "alert-cue": cue,
    "alert-confirm": confirm,
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
  // A write hook lets a test simulate a 400 body or a network rejection
  // without touching the GET path the build fetch depends on.
  let onWrite = null;
  globalThis.fetch = (url, opts) => {
    const method = (opts && opts.method) || "GET";
    requests.push({ url, method, body: opts && opts.body ? JSON.parse(opts.body) : null });
    if (method === "GET") {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ alerts: rows }) });
    }
    if (onWrite) return onWrite({ url, method, opts });
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ id: 9, condition: JSON.parse(opts.body).condition }),
    });
  };
  let rows = [];
  return {
    els, requests, handles,
    seed(next) { rows = next; },
    failWrite(fn) { onWrite = fn; },
    restore() {
      globalThis.document = prevDoc;
      globalThis.LightweightCharts = prevLwc;
      globalThis.fetch = prevFetch;
    },
  };
}

function makeHost(candles, scaleWidth) {
  let crosshair = null;
  const series = {
    coordinateToPrice: (y) => 200 - y, // 100 at y=100
    priceToCoordinate: (p) => 200 - p,
  };
  return {
    candles,
    subscribeCrosshairMove(fn) { crosshair = fn; },
    move(param) { if (crosshair) crosshair(param); },
    getCandles: () => candles,
    getCandleSeries: () => series,
    getChart: () => ({
      priceScale: () => ({ width: () => scaleWidth }),
    }),
    setCandles(next) { candles = next; },
  };
}

async function settle() {
  for (let i = 0; i < 8; i += 1) await Promise.resolve();
}

function fixture({ interval = "1h", candles = [{ time: 5, close: 90 }], scaleWidth = 64 } = {}) {
  const dom = installDom();
  const bus = createBus();
  const store = makeStore({ symbol: "BTCUSDT", interval });
  const host = makeHost(candles, scaleWidth);
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

test("bell stays focusable with a described reason on a non-evaluable interval (#234)", async () => {
  const f = fixture({ interval: "3d" });
  try {
    const bell = f.dom.els.chart.children.find((c) => c.id === "chart-alert-bell");
    f.host.move({ point: { x: 10, y: 100 } });
    // A native ``disabled`` button leaves the tab order, so its reason is never
    // announced. It must stay focusable and inert instead.
    assert.notStrictEqual(bell.disabled, true);
    assert.strictEqual(bell.getAttribute("aria-disabled"), "true");
    assert.strictEqual(bell.getAttribute("aria-describedby"), "alert-interval-reason");
    assert.match(f.dom.els["alert-interval-reason"].textContent, /3d/);

    bell.click();
    assert.strictEqual(f.dom.els["alert-dialog"].open, false, "the action is skipped");

    f.store.set({ interval: "1h" });
    await f.alerts.refresh(); // main.refresh() on a pair switch
    f.host.move({ point: { x: 10, y: 100 } });
    assert.strictEqual(bell.getAttribute("aria-disabled"), undefined);
    assert.strictEqual(bell.getAttribute("aria-describedby"), undefined);
    assert.strictEqual(f.dom.requests.length, 1, "the 3d fetch is skipped, 1h fetches");
  } finally { f.dom.restore(); }
});

test("the bell is offset by the price-scale width so it clears the axis (#234)", async () => {
  const f = fixture({ scaleWidth: 64 });
  try {
    const bell = f.dom.els.chart.children.find((c) => c.id === "chart-alert-bell");
    assert.strictEqual(bell.style.right, "72px", "64px axis + the 8px gap");
  } finally { f.dom.restore(); }
});

test("a stale bell hides when the pointer leaves it after the crosshair cleared (#234)", async () => {
  const f = fixture();
  try {
    const bell = f.dom.els.chart.children.find((c) => c.id === "chart-alert-bell");
    f.host.move({ point: { x: 10, y: 100 } });
    assert.strictEqual(bell.hidden, false);
    bell.fire("pointerenter", { type: "pointerenter" });
    f.host.move({}); // LWC clears the crosshair while the pointer is on the bell
    assert.strictEqual(bell.hidden, false, "the bell must survive the hover");
    bell.fire("pointerleave", { type: "pointerleave" });
    assert.strictEqual(bell.hidden, true, "leaving a stale bell hides it");
  } finally { f.dom.restore(); }
});

test("the dialog names the alert a near rule would update (#234)", async () => {
  const f = fixture();
  f.dom.seed([
    { id: 7, condition: { type: "price", op: "above", level: 100.5 }, is_active: true, last_fired_at: null },
  ]);
  try {
    await settle();
    f.host.move({ point: { x: 10, y: 100 } }); // 0.5px from 100.5
    const bell = f.dom.els.chart.children.find((c) => c.id === "chart-alert-bell");
    bell.click();
    const cue = f.dom.els["alert-cue"];
    assert.strictEqual(cue.hidden, false);
    assert.match(cue.textContent, /Updates the existing 100\.5 alert/);
  } finally { f.dom.restore(); }
});

test("a successful Apply flashes a visible confirmation (#234)", async () => {
  const f = fixture();
  try {
    f.host.move({ point: { x: 10, y: 100 } });
    const bell = f.dom.els.chart.children.find((c) => c.id === "chart-alert-bell");
    bell.click();
    f.dom.els["alert-dialog"].close("ok");
    await settle();
    const confirm = f.dom.els["alert-confirm"];
    assert.strictEqual(confirm.hidden, false);
    assert.strictEqual(confirm.textContent, "Alert at 100 armed");
  } finally { f.dom.restore(); }
});

test("armed markers re-anchor when a candle closes (#234)", async () => {
  const f = fixture({ candles: [{ time: 5, close: 90 }] });
  f.dom.seed([
    { id: 1, condition: { type: "price", op: "above", level: 100 }, is_active: true, last_fired_at: null },
  ]);
  try {
    await settle();
    assert.strictEqual(f.dom.handles[0].list[0].time, 5);
    f.host.setCandles([{ time: 5, close: 90 }, { time: 60, close: 95 }]);
    f.bus.emit("candle:closed", { time: 60 });
    assert.strictEqual(f.dom.handles[0].list[0].time, 60, "re-anchored on the closed candle");
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

// --- F10 UI #233: a failed Apply must be visible ----------------------------
//
// Apply runs in the dialog's ``close`` handler, so the dialog is already shut
// when the request resolves. Writing the error into the (closed) dialog is
// zero feedback: every failure must re-open it with the message, keeping the
// level the user typed.

test("a 400 response re-opens the dialog with the server error visible (#233)", async () => {
  const f = fixture();
  f.dom.failWrite(() =>
    Promise.resolve({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ error: "invalid condition" }),
    }),
  );
  try {
    f.host.move({ point: { x: 10, y: 100 } });
    const bell = f.dom.els.chart.children.find((c) => c.id === "chart-alert-bell");
    bell.click();
    f.dom.els["alert-level"].value = "123.5";
    f.dom.els["alert-dialog"].close("ok");
    await settle();

    assert.strictEqual(f.dom.requests.filter((r) => r.method === "POST").length, 1);
    assert.strictEqual(f.dom.els["alert-dialog"].open, true, "the dialog re-opens");
    assert.strictEqual(f.dom.els["alert-error"].hidden, false);
    assert.strictEqual(f.dom.els["alert-error"].textContent, "invalid condition");
    assert.strictEqual(f.dom.els["alert-level"].value, "123.5", "the typed level is kept");
    assert.strictEqual(globalThis.document.activeElement, f.dom.els["alert-level"]);
  } finally { f.dom.restore(); }
});

test("a network rejection re-opens the dialog with the error visible (#233)", async () => {
  const f = fixture();
  f.dom.failWrite(() => Promise.reject(new Error("offline")));
  try {
    f.host.move({ point: { x: 10, y: 100 } });
    const bell = f.dom.els.chart.children.find((c) => c.id === "chart-alert-bell");
    bell.click();
    f.dom.els["alert-dialog"].close("ok");
    await settle();

    assert.strictEqual(f.dom.els["alert-dialog"].open, true);
    assert.strictEqual(f.dom.els["alert-error"].hidden, false);
    assert.match(f.dom.els["alert-error"].textContent, /Network error/);
  } finally { f.dom.restore(); }
});

// --- F10 UI #235: a non-pointer entry point --------------------------------
//
// The bell only appears on a real crosshair point, so a keyboard user never
// reaches it. ``openFromLastClose`` seeds the dialog from the newest candle
// close, with no cursor at all.

test("openFromLastClose seeds the dialog from the last close without a crosshair (#235)", async () => {
  const f = fixture({ candles: [{ time: 1, close: 90 }, { time: 5, close: 137.25 }] });
  try {
    await settle();
    f.alerts.openFromLastClose();
    assert.strictEqual(f.dom.els["alert-dialog"].open, true, "the dialog opens");
    assert.strictEqual(f.dom.els["alert-level"].value, "137.25");
    // opFor(137.25, 137.25) -> "above" (at/above the close).
    assert.strictEqual(f.dom.els["alert-op"].value, "above");
  } finally { f.dom.restore(); }
});

test("openFromLastClose does nothing without candles or on an ineligible interval (#235)", async () => {
  const empty = fixture({ candles: [] });
  try {
    empty.alerts.openFromLastClose();
    assert.strictEqual(empty.dom.els["alert-dialog"].open, false, "no price to seed from");
  } finally { empty.dom.restore(); }

  const ineligible = fixture({ interval: "3d" });
  try {
    ineligible.alerts.openFromLastClose();
    assert.strictEqual(ineligible.dom.els["alert-dialog"].open, false);
  } finally { ineligible.dom.restore(); }
});

// --- F10 UI #232: theme-aware marker colors --------------------------------
//
// The core's literals are a fallback; the controller resolves the shell tokens
// at RENDER time. A theme flip is option-only, so the controller must also be
// told to re-render — otherwise the markers keep the previous palette.

function withTokens(values) {
  const prev = globalThis.getComputedStyle;
  globalThis.getComputedStyle = () => ({
    getPropertyValue: (name) => values[name] || "",
  });
  return () => {
    if (prev === undefined) delete globalThis.getComputedStyle;
    else globalThis.getComputedStyle = prev;
  };
}

const THEMED_ROWS = [
  { id: 1, condition: { type: "price", op: "above", level: 100 }, is_active: true, last_fired_at: 5 },
  { id: 2, condition: { type: "price", op: "below", level: 80 }, is_active: true, last_fired_at: null },
];

test("markers paint with the resolved --alert-armed/--dn tokens, not literals (#232)", async () => {
  const f = fixture();
  f.dom.seed(THEMED_ROWS);
  globalThis.document.documentElement = {};
  const restoreTokens = withTokens({ "--alert-armed": "#aaaaaa", "--dn": "#bbbbbb" });
  try {
    await settle();
    const h = f.dom.handles[0];
    assert.strictEqual(h.list[0].color, "#bbbbbb", "fired uses --dn");
    assert.strictEqual(h.list[1].color, "#aaaaaa", "armed uses --alert-armed");
  } finally { restoreTokens(); f.dom.restore(); }
});

test("a theme change re-renders the markers with the new tokens (#232)", async () => {
  const f = fixture();
  f.dom.seed(THEMED_ROWS);
  globalThis.document.documentElement = {};
  let restoreTokens = withTokens({ "--alert-armed": "#aaaaaa", "--dn": "#bbbbbb" });
  try {
    await settle();
    const h = f.dom.handles[0];
    assert.strictEqual(h.list[0].color, "#bbbbbb");

    restoreTokens();
    restoreTokens = withTokens({ "--alert-armed": "#cccccc", "--dn": "#dddddd" });
    f.alerts.refreshTheme(); // main's onTheme calls this after host.setTheme

    assert.strictEqual(f.dom.handles.length, 1, "the same marker handle is reused");
    assert.strictEqual(h.list[0].color, "#dddddd", "fired re-rendered");
    assert.strictEqual(h.list[1].color, "#cccccc", "armed re-rendered");
  } finally { restoreTokens(); f.dom.restore(); }
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

test("bell is a keyboard-reachable native button (R1)", async () => {
  // A native <button type="button"> is Tab-focusable and Enter/Space activate
  // it (no keydown handler needed); this pins that it stays a real button, not
  // a clickable <div>.
  const f = fixture();
  try {
    const bell = f.dom.els.chart.children.find((c) => c.id === "chart-alert-bell");
    assert.strictEqual(String(bell.tagName).toLowerCase(), "button", "the bell is a <button>");
    assert.strictEqual(bell.type, "button", "type=button avoids form submit");
    assert.ok(bell.getAttribute("aria-label"), "it has an accessible name");
    f.host.move({ point: { x: 30, y: 100 } });
    assert.strictEqual(bell.hidden, false, "reachable when the crosshair has a point");
  } finally { f.dom.restore(); }
});
