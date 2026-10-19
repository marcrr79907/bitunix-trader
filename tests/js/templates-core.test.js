// templates-core.test.js — pure template <-> store mapping (F11-B, T4).
import test from "node:test";
import assert from "node:assert";
import {
  templateToStore,
  storeToTemplate,
} from "../../web/market/templates/market/templates-core.js";
import { buildIndicators } from "../../web/market/templates/market/controllers/indicators.js";

test("templateToStore splits entries into the four store keys", () => {
  const out = templateToStore([
    { token: "sma", params: { sma_len: 50 }, style: { color: "#ff0000" } },
    { token: "rsi", visible: false },
  ]);

  assert.deepStrictEqual(out.indicators, ["sma", "rsi"]);
  assert.deepStrictEqual(out.params, { sma: { sma_len: 50 } });
  assert.deepStrictEqual(out.styles, { sma: { color: "#ff0000" } });
  assert.deepStrictEqual(out.indicatorVisible, { rsi: false });
});

test("templateToStore keeps a legacy token verbatim (degraded render, no throw)", () => {
  const out = templateToStore([{ token: "sma20" }]);

  assert.deepStrictEqual(out.indicators, ["sma20"]);
  assert.deepStrictEqual(out.params, {});
});

test("templateToStore is total for malformed input", () => {
  assert.deepStrictEqual(templateToStore(null).indicators, []);
  assert.deepStrictEqual(templateToStore("nope").indicators, []);
  assert.deepStrictEqual(templateToStore([null, {}, { token: "" }]).indicators, []);
});

test("storeToTemplate reuses buildIndicators so the shapes cannot drift", () => {
  const entries = storeToTemplate(buildIndicators, {
    indicators: ["sma"],
    params: { sma: { sma_len: 20 } },
    styles: { sma: { color: "#00ff00" } },
    indicatorVisible: {},
  });

  assert.deepStrictEqual(entries, [
    { token: "sma", params: { sma_len: 20 }, style: { color: "#00ff00" } },
  ]);
});

test("round-trip: store -> template -> store preserves the selection", () => {
  const store = {
    indicators: ["sma", "rsi"],
    params: { sma: { sma_len: 30 } },
    styles: {},
    indicatorVisible: { rsi: false },
  };
  const back = templateToStore(storeToTemplate(buildIndicators, store));

  assert.deepStrictEqual(back.indicators, store.indicators);
  assert.deepStrictEqual(back.params, store.params);
  assert.deepStrictEqual(back.indicatorVisible, store.indicatorVisible);
});
