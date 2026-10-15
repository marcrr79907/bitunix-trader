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
//
// F8 (chart-scales): the stub also carries LineSeries/AreaSeries + a
// priceScale() surface. PriceScaleMode uses DELIBERATELY NON-STANDARD numeric
// values (70/71/72) so a magic-number implementation (0/1/2) fails — the host
// MUST use the library symbol.
function withChartStub(fn) {
  const prevLC = globalThis.LightweightCharts;
  const prevDoc = globalThis.document;
  const prevWin = globalThis.window;
  const created = [];
  const priceScales = [];
  // Captured createChart calls: {el, opts} — theme-core option assertions read
  // opts.layout. ColorType.Solid is DELIBERATELY NON-STANDARD (99) so a magic
  // number (0/1/2) fails, mirroring the PriceScaleMode discipline.
  const charts = [];
  function makeSeries() {
    const s = { optionsArgs: null, calls: [] };
    s.applyOptions = (o) => { s.style = { ...(s.style || {}), ...o }; };
    s.setData = (d) => { s.calls.push({ method: "setData", data: d }); };
    s.update = (d) => { s.calls.push({ method: "update", data: d }); };
    created.push(s);
    return s;
  }
  globalThis.LightweightCharts = {
    LineSeries: "line",
    AreaSeries: "area",
    HistogramSeries: "hist",
    CandlestickSeries: "candles",
    PriceScaleMode: { Normal: 70, Logarithmic: 71, Percentage: 72 },
    ColorType: { Solid: 99 },
    createChart: (el, opts) => {
      const chartObj = {};
      const ps = { id: null, applied: [] };
      chartObj.applied = [];
      Object.assign(chartObj, {
        addSeries: (Ctor, opts2) => { const s = makeSeries(); s.optionsArgs = opts2 || {}; s.ctor = Ctor; return s; },
        remove: () => {},
        timeScale: () => ({ subscribeVisibleLogicalRangeChange: () => {} }),
        applyOptions: (o) => chartObj.applied.push(o),
        priceScale: (id) => {
          ps.id = id;
          if (!priceScales.includes(ps)) priceScales.push(ps);
          return {
            applyOptions: (o) => ps.applied.push(o),
            options: () => Object.assign({}, ...ps.applied),
          };
        },
      });
      charts.push({ el, opts, chart: chartObj });
      return chartObj;
    },
  };
  globalThis.document = { getElementById: () => ({}) };
  globalThis.window = { marketChart: {} };
  try {
    return fn(created, priceScales, charts);
  } finally {
    globalThis.LightweightCharts = prevLC;
    globalThis.document = prevDoc;
    globalThis.window = prevWin;
  }
}

function candleSeriesOf(created) {
  return created.find((s) => s.ctor === "candles" || s.ctor === "line" || s.ctor === "area");
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

// --- F8 chart-scales: Ctor map / scale option / HA live --------------------

const HA_B0 = { time: 100, open: 10, high: 12, low: 9, close: 11 };
const HA_B1 = { time: 200, open: 11, high: 13, low: 10, close: 12 };
const HA_B2 = { time: 300, open: 12, high: 14, low: 11, close: 13 };

test("build selects the candle Ctor from state.chartType (CS3 / R21)", () => {
  const expected = {
    candles: "candles",
    "heikin-ashi": "candles",
    line: "line",
    area: "area",
  };
  Object.keys(expected).forEach((type) => {
    withChartStub((created) => {
      const host = createHost();
      host.build({ chartType: type, indicators: [] });
      const cs = candleSeriesOf(created);
      assert.deepStrictEqual(cs.ctor, expected[type], type);
    });
  });
});

test("unknown chartType degrades to the CandlestickSeries Ctor (CS3)", () => {
  withChartStub((created) => {
    const host = createHost();
    host.build({ chartType: "notreal", indicators: [] });
    assert.strictEqual(candleSeriesOf(created).ctor, "candles");
  });
});

test("setScaleMode is option-only and uses the PriceScaleMode symbol (CS2)", () => {
  withChartStub((created, priceScales) => {
    const host = createHost();
    host.build({ scaleMode: "linear", indicators: [] });
    const cs = candleSeriesOf(created);
    const before = cs.calls.length;
    const appliedBefore = priceScales[0].applied.length;

    host.setScaleMode("log");
    assert.strictEqual(priceScales[0].id, "right", "right price scale");
    const logApplied = priceScales[0].applied.slice(appliedBefore);
    assert.deepStrictEqual(logApplied, [{ mode: 71 }]);
    // The SYMBOL, not a magic number (stub uses 71, never 1).
    assert.strictEqual(
      logApplied[0].mode,
      globalThis.LightweightCharts.PriceScaleMode.Logarithmic,
    );
    // No data write on a scale change (#68).
    assert.strictEqual(cs.calls.length, before);

    host.setScaleMode("percentage");
    assert.deepStrictEqual(priceScales[0].applied.slice(-1), [{ mode: 72 }]);
  });
});

test("unknown scale falls back to Normal without throwing (CS2)", () => {
  withChartStub((created, priceScales) => {
    const host = createHost();
    host.build({ indicators: [] });
    assert.doesNotThrow(() => host.setScaleMode("bogus"));
    assert.deepStrictEqual(priceScales[0].applied.pop(), { mode: 70 });
  });
});

test("build re-applies the scale mode after createChart (CS2)", () => {
  withChartStub((created, priceScales) => {
    const host = createHost();
    host.build({ scaleMode: "percentage", indicators: [] });
    assert.deepStrictEqual(priceScales[0].applied, [{ mode: 72 }]);
  });
});

test("heikin-ashi history is transformed and written via setData (CS4)", () => {
  withChartStub((created) => {
    const host = createHost();
    host.build({ chartType: "heikin-ashi", indicators: [] });
    const cs = candleSeriesOf(created);
    host.setCandles([HA_B0, HA_B1]);
    assert.deepStrictEqual(cs.calls.slice(-1)[0], {
      method: "setData",
      data: [
        { time: 100, open: 10.5, high: 12, low: 9, close: 10.5 },
        { time: 200, open: 10.5, high: 13, low: 10, close: 11.5 },
      ],
    });
    // Raw candles stay raw in the host (pagination/lastBucket read them).
    assert.deepStrictEqual(host.getCandles(), [HA_B0, HA_B1]);
  });
});

test("candles history is written verbatim, no transform (CS4)", () => {
  withChartStub((created) => {
    const host = createHost();
    host.build({ chartType: "candles", indicators: [] });
    const cs = candleSeriesOf(created);
    host.setCandles([HA_B0]);
    assert.deepStrictEqual(cs.calls.slice(-1)[0].data, [HA_B0]);
  });
});

test("HA live new bar chains state and matches a full recompute via update() only (CS4)", () => {
  withChartStub((created) => {
    const host = createHost();
    host.build({ chartType: "heikin-ashi", indicators: [] });
    const cs = candleSeriesOf(created);
    host.setCandles([HA_B0, HA_B1]);
    const setDataCalls = cs.calls.filter((c) => c.method === "setData").length;

    host.updateCandle(HA_B2); // new bar
    assert.strictEqual(
      cs.calls.slice(-1)[0].method,
      "update",
      "live write is update() only",
    );
    assert.deepStrictEqual(cs.calls.slice(-1)[0].data, {
      time: 300,
      open: 11, // (prevHaOpen 10.5 + prevHaClose 11.5) / 2
      high: 14,
      low: 11,
      close: 12.5,
    });
    // No full-series setData during the live path (#68).
    assert.strictEqual(
      cs.calls.filter((c) => c.method === "setData").length,
      setDataCalls,
    );
  });
});

test("HA live same-bucket forming bar re-transforms from the prior HA state (CS4)", () => {
  withChartStub((created) => {
    const host = createHost();
    host.build({ chartType: "heikin-ashi", indicators: [] });
    const cs = candleSeriesOf(created);
    host.setCandles([HA_B0, HA_B1]);
    host.updateCandle(HA_B2); // lastHa advances to HA(B2) = {open:11, close:12.5}
    const setDataCalls = cs.calls.filter((c) => c.method === "setData").length;
    // Forming bar update: chains from the prior CLOSED bar's HA (stable while
    // forming), update() only.
    host.updateCandle({ time: 300, open: 12, high: 15, low: 11, close: 14 });
    assert.strictEqual(cs.calls.slice(-1)[0].method, "update");
    assert.deepStrictEqual(cs.calls.slice(-1)[0].data, {
      time: 300,
      open: 11, // (prevClosedHaOpen 10.5 + prevClosedHaClose 11.5) / 2
      high: 15,
      low: 11,
      close: 13, // (12+15+11+14)/4
    });
    assert.strictEqual(
      cs.calls.filter((c) => c.method === "setData").length,
      setDataCalls,
    );
  });
});

test("HA live is stable across MULTIPLE same-bucket ticks (C1 regression)", () => {
  // Regression for the drift where repeated same-bucket pushes chained the
  // forming bar onto an old version of ITSELF (prevHa advanced every tick
  // instead of only on a bar close), cascading the next bucket. Every tick of
  // the SAME forming bar MUST reuse the prior CLOSED bar's HA → identical haOpen.
  withChartStub((created) => {
    const host = createHost();
    host.build({ chartType: "heikin-ashi", indicators: [] });
    const cs = candleSeriesOf(created);
    host.setCandles([HA_B0, HA_B1]);
    host.updateCandle(HA_B2); // HA(B2) = {open:11, close:12.5} (closed)

    const baseOpen = 11; // (prevClosedHaOpen 10.5 + prevClosedHaClose 11.5) / 2
    // Three ticks of the SAME forming bar (time 300) with a moving close.
    const ticks = [
      { time: 300, open: 12, high: 15, low: 11, close: 14 },
      { time: 300, open: 12, high: 16, low: 11, close: 15.5625 },
      { time: 300, open: 12, high: 16, low: 11, close: 16 },
    ];
    const opens = ticks.map((b) => {
      host.updateCandle(b);
      return cs.calls.slice(-1)[0].data.open;
    });
    // haOpen must NOT drift across repeated same-bucket ticks.
    assert.deepStrictEqual(opens, [baseOpen, baseOpen, baseOpen]);

    // A NEW bucket then chains from the FINAL forming bar's HA, not a stale one.
    host.updateCandle({ time: 400, open: 16, high: 18, low: 15, close: 17 });
    const last = cs.calls.slice(-1)[0].data;
    // haOpen = (prevHaOpen 11 + prevHaClose 13.75) / 2 = 12.375
    assert.strictEqual(last.open, 12.375);
  });
});

// --- theme host contract (R22 / CT4 / CT5) ---------------------------------
//
// The chart is BORN themed: build() merges optionsFor(state.theme) into the sole
// createChart call. A live flip is OPTION-ONLY (#68): setTheme -> applyOptions,
// never setData/update. ColorType.Solid is a SYMBOL (stub = 99, never a number).

test("build is born themed: createChart carries the themed layout (R22)", () => {
  withChartStub((created, priceScales, charts) => {
    const host = createHost();
    host.build({ theme: "light", indicators: [] });
    const opts = charts[0].opts;
    assert.strictEqual(opts.layout.background.color, "#ffffff");
    assert.strictEqual(opts.layout.textColor, "#1f2328");
    assert.strictEqual(opts.layout.background.type, 99);
    // The pre-existing host options survive the merge.
    assert.strictEqual(opts.autoSize, true);
    assert.strictEqual(opts.timeScale.timeVisible, true);
  });
});

test("build defaults to the system-resolved theme when state.theme is absent", () => {
  withChartStub((created, priceScales, charts) => {
    const host = createHost();
    host.build({ indicators: [] });
    // No prefersDark in the Node env -> resolves to light.
    assert.strictEqual(charts[0].opts.layout.background.color, "#ffffff");
  });
});

test("build keeps the ColorType.Solid symbol, never a magic number (R22)", () => {
  withChartStub((created, priceScales, charts) => {
    const host = createHost();
    host.build({ theme: "dark", indicators: [] });
    assert.strictEqual(charts[0].opts.layout.background.type, 99);
    assert.notStrictEqual(charts[0].opts.layout.background.type, 0);
  });
});

test("setTheme is option-only: applyOptions, no setData/update (#68)", () => {
  withChartStub((created, priceScales, charts) => {
    const host = createHost();
    host.build({ theme: "dark", indicators: [] });
    const cs = candleSeriesOf(created);
    const dataCallsBefore = cs.calls.length;
    const appliedBefore = charts[0].chart.applied.length;

    host.setTheme("light");

    const applied = charts[0].chart.applied.slice(appliedBefore);
    assert.strictEqual(applied.length, 1, "one applyOptions call");
    assert.strictEqual(applied[0].layout.background.color, "#ffffff");
    assert.strictEqual(applied[0].layout.textColor, "#1f2328");
    assert.strictEqual(applied[0].layout.background.type, 99);
    // No data write on a live theme flip (#68).
    assert.strictEqual(cs.calls.length, dataCallsBefore);
    assert.strictEqual(cs.calls.filter((c) => c.method === "setData").length, 0);
    assert.strictEqual(cs.calls.filter((c) => c.method === "update").length, 0);
  });
});

test("setTheme before a chart is a null-guarded no-op", () => {
  withChartStub(() => {
    const host = createHost();
    assert.doesNotThrow(() => host.setTheme("dark"));
  });
});

test("setCandles resets the HA state from the new first bar (CS4)", () => {
  withChartStub((created) => {
    const host = createHost();
    host.build({ chartType: "heikin-ashi", indicators: [] });
    const cs = candleSeriesOf(created);
    host.setCandles([HA_B0, HA_B1]);
    host.setCandles([HA_B2]); // fresh page -> state reset (single bar = first-branch)
    host.updateCandle({ time: 400, open: 13, high: 15, low: 12, close: 14 });
    // HA(B2) as a lone bar = {open:(12+13)/2=12.5, close:(12+14+11+13)/4=12.5};
    // the new bar chains its haOpen from that state.
    assert.deepStrictEqual(cs.calls.slice(-1)[0].data, {
      time: 400,
      open: 12.5, // (12.5 + 12.5) / 2
      high: 15,
      low: 12,
      close: 13.5, // (13+15+12+14)/4
    });
  });
});
