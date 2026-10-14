// chart-host crosshair-seam tests — node --test.
//
// The host's chart is browser-only, so the delegation assertion lives in E2E.
// Here we lock the Node-testable contract: the seam is exported and is a
// null-guarded no-op before a chart exists (spec LC4 / R19).
import test from "node:test";
import assert from "node:assert";
import { createHost } from "../../web/market/templates/market/chart-host.js";

test("subscribeCrosshairMove is exported and mirrors subscribeClick", () => {
  const host = createHost();
  assert.strictEqual(typeof host.subscribeCrosshairMove, "function");
  assert.strictEqual(typeof host.subscribeClick, "function");
});

test("subscribeCrosshairMove is a null-guarded no-op with no chart", () => {
  const host = createHost();
  assert.doesNotThrow(() => host.subscribeCrosshairMove(() => {}));
});

// --- F2.5 host style apply ------------------------------------------------
//
// build() constructs every series through the sole addSeries site; here we stub
// the two browser globals build() touches so the color/lineWidth/priceFormat
// contract is node-testable.
function withChartStub(fn) {
  const prevLC = globalThis.LightweightCharts;
  const prevDoc = globalThis.document;
  const prevWin = globalThis.window;
  const created = [];
  function makeSeries() {
    const s = { options: { color: undefined, lineWidth: undefined }, optionsArgs: null };
    s.applyOptions = (o) => { s.style = { ...(s.style || {}), ...o }; };
    created.push(s);
    return s;
  }
  globalThis.LightweightCharts = {
    LineSeries: "line",
    HistogramSeries: "hist",
    CandlestickSeries: "candles",
    createChart: () => ({
      addSeries: (Ctor, opts) => { const s = makeSeries(); s.optionsArgs = opts || {}; s.ctor = Ctor; return s; },
      remove: () => {},
      timeScale: () => ({ subscribeVisibleLogicalRangeChange: () => {} }),
    }),
  };
  globalThis.document = { getElementById: () => ({}) };
  globalThis.window = { marketChart: {} };
  try {
    return fn(created);
  } finally {
    globalThis.LightweightCharts = prevLC;
    globalThis.document = prevDoc;
    globalThis.window = prevWin;
  }
}

test("build applies per-token style (color/lineWidth) and priceFormat precision", () => {
  withChartStub((created) => {
    const host = createHost();
    host.build({
      indicators: ["sma", "ema"],
      styles: { sma: { color: "#ff0000", lineWidth: 3, precision: 5 } },
    });
    const priceSeries = created.filter((s) => s.ctor === "candles" || s.ctor === "line");
    // sma: styled; ema: registry default.
    const sma = created.find((s) => s.optionsArgs.color === "#ff0000");
    assert.ok(sma, "styled sma series constructed with the style color");
    assert.strictEqual(sma.optionsArgs.lineWidth, 3);
    assert.deepStrictEqual(sma.style.priceFormat, { precision: 5, minMove: 0.00001 });
    // ema falls back to the REGISTRY color, width 1.
    const ema = created.find((s) => s.optionsArgs.color === "#ff6d00");
    assert.ok(ema, "ema falls back to the registry color");
    assert.strictEqual(ema.optionsArgs.lineWidth, 1);
    assert.ok(priceSeries.length >= 0);
  });
});
