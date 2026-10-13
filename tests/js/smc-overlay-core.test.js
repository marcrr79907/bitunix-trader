// Pure SMC overlay mapping tests — node --test (no DOM, no chart lib, no network).
import test from "node:test";
import assert from "node:assert";
import * as core from "../../web/market/templates/market/smc-overlay-core.js";

// A frozen-shape payload (mirrors the `/market/api/smc` response body).
const payload = {
  symbol: "BTCUSDT",
  interval: "1m",
  swings: [
    { kind: "low", time: 100, price: 10.0, label: null },
    { kind: "high", time: 200, price: 20.0, label: "HH" },
    { kind: "low", time: 300, price: 12.0, label: "HL" },
  ],
  structure: [
    { kind: "bos", time: 200, price: 20.0, direction: "bullish", trend: "up" },
    { kind: "choch", time: 300, price: 12.0, direction: "bearish", trend: "down" },
  ],
  order_blocks: [
    { kind: "bullish", time: 150, top: 21.0, bottom: 19.0, anchor_time: 200 },
  ],
  fvgs: [{ kind: "bearish", time: 250, top: 18.0, bottom: 17.0 }],
  range: { high: 25.0, low: 5.0, equilibrium: 15.0, time: 300 },
  setups: [
    {
      direction: "long",
      time: 200,
      entry: 19.5,
      stop: 18.0,
      take_profit: 24.0,
      rr: 3.0,
      score: 4,
    },
  ],
};

test("FAMILIES exposes the six element families in order", () => {
  assert.deepStrictEqual(core.FAMILIES, [
    "swings",
    "structure",
    "order_blocks",
    "fvg",
    "range",
    "setups",
  ]);
});

test("COLORS carries a palette per family", () => {
  for (const family of core.FAMILIES) {
    assert.notStrictEqual(core.COLORS[family], undefined);
  }
  assert.strictEqual(core.COLORS.swings.high, "#ef5350");
  assert.strictEqual(core.COLORS.swings.low, "#26a69a");
  assert.strictEqual(core.COLORS.structure.bullish, "#2962ff");
  assert.strictEqual(core.COLORS.range, "#7e57c2");
});

test("fromApi normalizes keys (order_blocks -> orderBlocks) and keeps data", () => {
  const n = core.fromApi(payload);
  assert.strictEqual(n.symbol, "BTCUSDT");
  assert.strictEqual(n.interval, "1m");
  assert.strictEqual(n.swings.length, 3);
  assert.strictEqual(n.structure.length, 2);
  assert.strictEqual(n.orderBlocks.length, 1);
  assert.strictEqual(n.orderBlocks[0].top, 21.0);
  assert.strictEqual(n.fvgs.length, 1);
  assert.strictEqual(n.range.equilibrium, 15.0);
  assert.strictEqual(n.setups.length, 1);
});

test("fromApi never throws and degrades null/garbage to the empty shape", () => {
  const empty = {
    symbol: null,
    interval: null,
    swings: [],
    structure: [],
    orderBlocks: [],
    fvgs: [],
    range: null,
    setups: [],
  };
  assert.deepStrictEqual(core.fromApi(null), empty);
  assert.deepStrictEqual(core.fromApi(undefined), empty);
  assert.deepStrictEqual(core.fromApi(42), empty);
  assert.deepStrictEqual(core.fromApi({ swings: "nope" }).swings, []);
});

test("fromApi drops unknown extra keys", () => {
  const n = core.fromApi(Object.assign({}, payload, { junk: 1 }));
  assert.strictEqual(n.junk, undefined);
});

test("visibleFamilies with absent/empty toggles means all ON", () => {
  assert.deepStrictEqual(core.visibleFamilies(), core.FAMILIES);
  assert.deepStrictEqual(core.visibleFamilies(null), core.FAMILIES);
  assert.deepStrictEqual(core.visibleFamilies({}), core.FAMILIES);
});

test("visibleFamilies filters only explicit false", () => {
  assert.deepStrictEqual(core.visibleFamilies({ swings: false, range: false }), [
    "structure",
    "order_blocks",
    "fvg",
    "setups",
  ]);
  assert.deepStrictEqual(core.visibleFamilies({ swings: true }), core.FAMILIES);
});

test("descriptors maps swings with kind/label/color and identity coords", () => {
  const d = core.descriptors(payload);
  assert.strictEqual(d.swings.length, 3);
  assert.deepStrictEqual(d.swings[0], {
    kind: "low",
    time: 100,
    price: 10.0,
    label: null,
    color: "#26a69a",
    x: 100,
    y: 10.0,
  });
  assert.deepStrictEqual(d.swings[1], {
    kind: "high",
    time: 200,
    price: 20.0,
    label: "HH",
    color: "#ef5350",
    x: 200,
    y: 20.0,
  });
});

test("descriptors maps structure with BOS/CHoCH label and direction color", () => {
  const d = core.descriptors(payload);
  assert.deepStrictEqual(d.structure, [
    {
      kind: "bos",
      time: 200,
      price: 20.0,
      direction: "bullish",
      trend: "up",
      label: "BOS",
      color: "#2962ff",
      x: 200,
      y: 20.0,
    },
    {
      kind: "choch",
      time: 300,
      price: 12.0,
      direction: "bearish",
      trend: "down",
      label: "CHoCH",
      color: "#ff6d00",
      x: 300,
      y: 12.0,
    },
  ]);
});

test("descriptors maps order blocks with resolved anchorTime + box edges", () => {
  const d = core.descriptors(payload);
  assert.deepStrictEqual(d.order_blocks, [
    {
      kind: "bullish",
      time: 150,
      anchorTime: 200,
      top: 21.0,
      bottom: 19.0,
      color: "#26a69a",
      x1: 150,
      x2: 200,
      yTop: 21.0,
      yBottom: 19.0,
    },
  ]);
});

test("descriptors maps FVGs and the range bands", () => {
  const d = core.descriptors(payload);
  assert.deepStrictEqual(d.fvg, [
    {
      kind: "bearish",
      time: 250,
      top: 18.0,
      bottom: 17.0,
      color: "#ef5350",
      x: 250,
      yTop: 18.0,
      yBottom: 17.0,
    },
  ]);
  assert.deepStrictEqual(d.range, {
    high: 25.0,
    low: 5.0,
    equilibrium: 15.0,
    time: 300,
    color: "#7e57c2",
    yHigh: 25.0,
    yLow: 5.0,
    yEquilibrium: 15.0,
  });
});

test("descriptors respects toggles (family off -> empty / null range)", () => {
  const d = core.descriptors(payload, { swings: false, range: false });
  assert.deepStrictEqual(d.swings, []);
  assert.strictEqual(d.range, null);
  assert.strictEqual(d.structure.length, 2);
});

test("descriptors with a coord map drops off-series legs without throwing", () => {
  const coords = {
    x: (t) => (t === 200 ? null : t),
    y: (p) => p,
  };
  const d = core.descriptors(payload, null, coords);
  // The swing/structure at time 200 has no bar -> dropped, not thrown.
  assert.deepStrictEqual(d.swings.map((s) => s.time), [100, 300]);
  assert.deepStrictEqual(d.structure.map((s) => s.time), [300]);
  // The OB spans 150 -> anchor 200 (off-series) -> dropped whole.
  assert.deepStrictEqual(d.order_blocks, []);
  assert.deepStrictEqual(d.fvg.map((f) => f.time), [250]);
  assert.notStrictEqual(d.range, null);
});

test("descriptors drops the range when a band price is off-scale", () => {
  const d = core.descriptors(payload, null, {
    x: (t) => t,
    y: (p) => (p === 15.0 ? null : p),
  });
  assert.strictEqual(d.range, null);
});

test("descriptors on null/empty payload yields empty arrays + null range", () => {
  const d = core.descriptors(null);
  assert.deepStrictEqual(d.swings, []);
  assert.deepStrictEqual(d.structure, []);
  assert.deepStrictEqual(d.order_blocks, []);
  assert.deepStrictEqual(d.fvg, []);
  assert.strictEqual(d.range, null);
});

test("setupMarkers maps a long setup to a belowBar arrow with L score text", () => {
  assert.deepStrictEqual(core.setupMarkers(payload), [
    {
      time: 200,
      position: "belowBar",
      color: "#26a69a",
      shape: "arrowUp",
      text: "L 4/4",
    },
  ]);
});

test("setupMarkers maps a short setup to an aboveBar arrow with S score text", () => {
  const short = Object.assign({}, payload, {
    setups: [
      {
        direction: "short",
        time: 5,
        entry: 1.0,
        stop: 2.0,
        take_profit: 0.5,
        rr: 2.0,
        score: 3,
      },
    ],
  });
  assert.deepStrictEqual(core.setupMarkers(short), [
    {
      time: 5,
      position: "aboveBar",
      color: "#ef5350",
      shape: "arrowDown",
      text: "S 3/4",
    },
  ]);
});

test("setupMarkers honors toggles and the empty payload", () => {
  assert.deepStrictEqual(core.setupMarkers(payload, { setups: false }), []);
  assert.deepStrictEqual(core.setupMarkers(null), []);
});

test("counts parity matches descriptor lengths per family", () => {
  assert.deepStrictEqual(core.counts(payload), {
    swings: 3,
    structure: 2,
    order_blocks: 1,
    fvg: 1,
    range: 1,
    setups: 1,
  });
  assert.deepStrictEqual(
    core.counts(payload, { swings: false, setups: false, range: false }),
    { swings: 0, structure: 2, order_blocks: 1, fvg: 1, range: 0, setups: 0 },
  );
  assert.deepStrictEqual(core.counts(null), {
    swings: 0,
    structure: 0,
    order_blocks: 0,
    fvg: 0,
    range: 0,
    setups: 0,
  });
});
