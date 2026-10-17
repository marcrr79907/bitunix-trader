// Pure context-menu-core tests — node --test (no DOM, no chart lib, no network).
//
// The core owns the menu MODEL ({hit,row,scaleMode} -> item list) and the roving
// focus index math (nextIndex/clampIndex). Rendering, hit-testing and the focus
// trap live in the DOM controller; this core is pure and never throws.
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { menuModel, nextIndex, clampIndex } from "../../web/market/templates/market/context-menu-core.js";

const SRC = readFileSync(
  fileURLToPath(new URL("../../web/market/templates/market/context-menu-core.js", import.meta.url)),
  "utf8",
);

const row = { id: 7, kind: "trendline", points: { p1: { time: 1, price: 2 } } };

// --- menuModel: a drawing row ------------------------------------------------

test("a drawing row yields delete then duplicate", () => {
  const items = menuModel({ hit: { id: 7 }, row, scaleMode: "linear" });
  assert.deepStrictEqual(items, [
    { id: "delete", label: "Delete", keyshortcut: "Delete" },
    { id: "duplicate", label: "Duplicate", keyshortcut: "" },
  ]);
});

test("a drawing row adds reset-scale only when non-linear", () => {
  const nonLinear = menuModel({ hit: { id: 7 }, row, scaleMode: "log" });
  assert.deepStrictEqual(nonLinear.map((i) => i.id), ["delete", "duplicate", "reset-scale"]);
  const linear = menuModel({ hit: { id: 7 }, row, scaleMode: "linear" });
  assert.deepStrictEqual(linear.map((i) => i.id), ["delete", "duplicate"]);
});

// --- menuModel: empty chart --------------------------------------------------

test("an empty chart yields reset-scale then add-indicator when non-linear", () => {
  assert.deepStrictEqual(menuModel({ hit: null, row: null, scaleMode: "log" }), [
    { id: "reset-scale", label: "Reset scale", keyshortcut: "" },
    { id: "add-indicator", label: "Add indicator", keyshortcut: "" },
  ]);
});

test("an empty chart drops reset-scale when linear", () => {
  assert.deepStrictEqual(menuModel({ hit: null, row: null, scaleMode: "linear" }), [
    { id: "add-indicator", label: "Add indicator", keyshortcut: "" },
  ]);
});

test("an unknown hit falls back to the empty-chart list", () => {
  const unknown = menuModel({ hit: { id: 999 }, row: null, scaleMode: "log" });
  assert.deepStrictEqual(unknown, menuModel({ hit: null, row: null, scaleMode: "log" }));
});

// --- menuModel: never throws -------------------------------------------------

test("menuModel never throws on garbage input", () => {
  assert.doesNotThrow(() => menuModel());
  assert.doesNotThrow(() => menuModel({}));
  assert.doesNotThrow(() => menuModel(null));
  assert.doesNotThrow(() => menuModel({ hit: "x", row: 42, scaleMode: undefined }));
  assert.doesNotThrow(() => menuModel({ hit: {}, row: {}, scaleMode: {} }));
});

// --- nextIndex (wrap) --------------------------------------------------------

test("nextIndex wraps forward and backward", () => {
  assert.strictEqual(nextIndex(3, 0, 1), 1);
  assert.strictEqual(nextIndex(3, 2, 1), 0);
  assert.strictEqual(nextIndex(3, 0, -1), 2);
});

test("nextIndex is 0 when there are no items", () => {
  assert.strictEqual(nextIndex(0, 0, 1), 0);
  assert.strictEqual(nextIndex(-1, 5, 2), 0);
});

// --- clampIndex --------------------------------------------------------------

test("clampIndex stays within 0..count-1", () => {
  assert.strictEqual(clampIndex(3, 1), 1);
  assert.strictEqual(clampIndex(3, -1), 0);
  assert.strictEqual(clampIndex(3, 9), 2);
});

test("clampIndex is 0 when there are no items", () => {
  assert.strictEqual(clampIndex(0, 4), 0);
  assert.strictEqual(clampIndex(-2, 4), 0);
});

test("context-menu-core is pure (no DOM, no imports)", () => {
  assert.ok(!/\bimport\b/.test(SRC), "no imports");
  assert.ok(!/document\.|window\.|fetch\(/.test(SRC), "no DOM / no window / no network");
});
