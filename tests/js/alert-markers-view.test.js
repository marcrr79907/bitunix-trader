// alert-markers-view — the DOM/LWC adapter for alert markers + the live summary.
//
// Extracted from controllers/alerts.js to hold the 300-line ceiling. What it
// pins is the adapter contract only: one reused marker handle (never a second
// createSeriesMarkers), the newest-candle anchor, the token-resolved colors,
// the aria-live summary, and the short-lived visible confirmation after Apply.
import test from "node:test";
import assert from "node:assert";
import { createMarkersView } from "../../web/market/templates/market/alert-markers-view.js";

function makeStatus() {
  return { textContent: "" };
}

function installLwc() {
  const prev = globalThis.LightweightCharts;
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
  return { handles, restore() { globalThis.LightweightCharts = prev; } };
}

function withTokens(values) {
  const prev = globalThis.getComputedStyle;
  globalThis.getComputedStyle = () => ({
    getPropertyValue: (name) => values[name] || "",
  });
  const prevDoc = globalThis.document;
  globalThis.document = { documentElement: {} };
  return () => {
    globalThis.document = prevDoc;
    if (prev === undefined) delete globalThis.getComputedStyle;
    else globalThis.getComputedStyle = prev;
  };
}

function makeHost(candles) {
  const series = { id: "candles" };
  return { candles, getCandles: () => candles, getCandleSeries: () => series };
}

const RULES = [
  { condition: { level: 100 }, is_active: true, last_fired_at: 5 },
  { condition: { level: 80 }, is_active: true, last_fired_at: null },
];

test("render creates one handle, reuses it, and anchors armed on the newest candle", () => {
  const lwc = installLwc();
  const restoreTokens = withTokens({ "--alert-armed": "#aaa", "--dn": "#bbb" });
  try {
    const status = makeStatus();
    const view = createMarkersView({ host: makeHost([{ time: 1 }, { time: 9 }]), statusEl: status });
    view.render(RULES);
    assert.strictEqual(lwc.handles.length, 1);
    assert.strictEqual(lwc.handles[0].list[1].time, 9);
    assert.strictEqual(lwc.handles[0].list[1].color, "#aaa");
    assert.strictEqual(status.textContent, "2 alerts: 1 fired, 1 armed");

    view.render(RULES);
    assert.strictEqual(lwc.handles.length, 1, "the handle is reused, never recreated");
  } finally { restoreTokens(); lwc.restore(); }
});

test("clear empties the markers and announces the empty state", () => {
  const lwc = installLwc();
  try {
    const status = makeStatus();
    const view = createMarkersView({ host: makeHost([{ time: 9 }]), statusEl: status });
    view.render(RULES);
    view.clear();
    assert.deepStrictEqual(lwc.handles[0].list, []);
    assert.strictEqual(status.textContent, "No alerts on this chart");
  } finally { lwc.restore(); }
});

test("detach lets the dead handle go so a rebuild never reuses it", () => {
  const lwc = installLwc();
  try {
    const view = createMarkersView({ host: makeHost([{ time: 9 }]), statusEl: makeStatus() });
    view.render(RULES);
    view.detach();
    assert.strictEqual(lwc.handles[0].detached, true);
    view.render(RULES);
    assert.strictEqual(lwc.handles.length, 2, "a rebuild gets a fresh handle");
  } finally { lwc.restore(); }
});

test("render is a no-op without a candle series (bell-only chart)", () => {
  const lwc = installLwc();
  try {
    const view = createMarkersView({ host: { getCandles: () => [], getCandleSeries: () => null }, statusEl: makeStatus() });
    assert.doesNotThrow(() => view.render(RULES));
    assert.strictEqual(lwc.handles.length, 0);
  } finally { lwc.restore(); }
});

test("flash shows a visible confirmation briefly without hiding the summary", () => {
  const lwc = installLwc();
  const prevTimer = globalThis.setTimeout;
  let scheduled = null;
  globalThis.setTimeout = (fn) => { scheduled = fn; return 1; };
  try {
    const status = makeStatus();
    const confirm = { textContent: "", hidden: true };
    const view = createMarkersView({
      host: makeHost([{ time: 9 }]), statusEl: status, confirmEl: confirm,
    });
    view.render(RULES);
    view.flash("Alert at 100.5 armed");
    assert.strictEqual(confirm.textContent, "Alert at 100.5 armed");
    assert.strictEqual(confirm.hidden, false, "revealed");
    assert.strictEqual(status.textContent, "2 alerts: 1 fired, 1 armed", "summary intact");
    assert.ok(scheduled, "a timer re-hides it");
    scheduled();
    assert.strictEqual(confirm.hidden, true);
    view.flash("");
    assert.strictEqual(confirm.textContent, "Alert at 100.5 armed", "empty text is ignored");
  } finally { globalThis.setTimeout = prevTimer; lwc.restore(); }
});
