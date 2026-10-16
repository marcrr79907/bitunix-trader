// add-indicator-core.js — pure helper (F5 S5, issue #176).
//
// The Object Tree is ACTIVE-ONLY (chart-object-tree R1); its counterpart ADD
// affordance lists REGISTRY-minus-membership. This core owns the pure selection
// (inactiveTokens) so the tree stays within the R14 ceiling and the rule is
// tested without a browser. node --test, no deps.
import test from "node:test";
import assert from "node:assert";
import { REGISTRY } from "../../web/market/templates/market/chart-registry-core.js";

const { inactiveTokens } = await import(
  "../../web/market/templates/market/add-indicator-core.js"
);

test("inactiveTokens: registry order minus the active membership (R1)", () => {
  const out = inactiveTokens(REGISTRY, ["sma", "ema", "rsi"]);
  assert.deepStrictEqual(out, [
    "bollinger",
    "vwap",
    "macd",
    "stochastic",
    "atr",
    "volume",
  ]);
});

test("inactiveTokens: never duplicates an active token (R1)", () => {
  const out = inactiveTokens(REGISTRY, Object.keys(REGISTRY));
  assert.deepStrictEqual(out, []);
});

test("inactiveTokens: absent/empty membership offers every token", () => {
  assert.deepStrictEqual(inactiveTokens(REGISTRY, []).length, 9);
  assert.deepStrictEqual(inactiveTokens(REGISTRY, undefined).length, 9);
});
