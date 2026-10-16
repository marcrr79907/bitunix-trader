// Pure core tests — node --test (no DOM, no chart lib, no network).
// chart-registry-core.js: the static presentation registry moved out of
// chart-host.js (R14; F5 S1). Imports nothing, deterministic.
//
// LOAD-BEARING RENAME (tasks.md §Guard "TWO SCALE_MODES collision"):
// chart-types-core.js exports an ARRAY named ``SCALE_MODES``; the price-scale
// map moved here MUST be renamed ``PRICE_SCALE_MODES`` so both cores can be
// imported together without an export-name clash.
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import * as registry from "../../web/market/templates/market/chart-registry-core.js";
import * as types from "../../web/market/templates/market/chart-types-core.js";

test("REGISTRY: 9 tokens with place/series shape (moved verbatim)", () => {
  const tokens = Object.keys(registry.REGISTRY).sort();
  assert.deepStrictEqual(tokens, [
    "atr",
    "bollinger",
    "ema",
    "macd",
    "rsi",
    "sma",
    "stochastic",
    "volume",
    "vwap",
  ]);
  // Overlay vs pane placement + the pane name is real data, not a stub.
  assert.strictEqual(registry.REGISTRY.sma.place, "overlay");
  assert.strictEqual(registry.REGISTRY.ema.series[0].color, "#ff6d00");
  assert.strictEqual(registry.REGISTRY.rsi.place, "pane");
  assert.strictEqual(registry.REGISTRY.rsi.pane, "rsi");
  assert.strictEqual(registry.REGISTRY.macd.series.length, 3);
  assert.strictEqual(registry.REGISTRY.bollinger.series.length, 3);
  assert.strictEqual(registry.REGISTRY.volume.series[0].type, "histogram");
});

test("PANE_ORDER: the 5 pane tokens in fixed order", () => {
  assert.deepStrictEqual([...registry.PANE_ORDER], [
    "rsi",
    "macd",
    "stochastic",
    "atr",
    "volume",
  ]);
});

test("PRICE_SCALE_MODES: 3 vocab -> LightweightCharts symbol labels", () => {
  assert.deepStrictEqual(registry.PRICE_SCALE_MODES, {
    linear: "Normal",
    log: "Logarithmic",
    percentage: "Percentage",
  });
  assert.strictEqual(Object.keys(registry.PRICE_SCALE_MODES).length, 3);
});

test("no exported-name clash: the moved map is PRICE_SCALE_MODES, not SCALE_MODES", () => {
  // The registry core MUST NOT re-export the types-core array name.
  assert.strictEqual(registry.SCALE_MODES, undefined);
  assert.strictEqual(typeof registry.PRICE_SCALE_MODES, "object");
  // chart-types-core keeps its ARRAY under SCALE_MODES; the two coexist.
  assert.deepStrictEqual([...types.SCALE_MODES], ["linear", "log", "percentage"]);
  assert.notStrictEqual(registry.PRICE_SCALE_MODES, types.SCALE_MODES);
});

test("purity: the registry core imports nothing", () => {
  const src = readFileSync(
    fileURLToPath(
      new URL("../../web/market/templates/market/chart-registry-core.js", import.meta.url),
    ),
    "utf8",
  );
  assert.doesNotMatch(src, /^\s*import\b/m, "no ESM import");
  assert.doesNotMatch(src, /\brequire\s*\(/, "no CommonJS require");
});
