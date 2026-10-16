// Interaction-controller pure helpers — node --test (DOM-free only).
//
// The interaction controller is a DI factory whose pointer/keyboard/dialog
// wiring needs a browser (covered by E2E). Its two pure helpers are unit-tested
// here, mirroring the chart-controllers.test.js discipline.
import test from "node:test";
import assert from "node:assert";
import {
  localPoint,
  mergeStyle,
  pointerRows,
} from "../../web/market/templates/market/controllers/drawing-interaction.js";

test("localPoint: client coords -> container-relative pixels", () => {
  assert.deepStrictEqual(localPoint({ left: 10, top: 20 }, 130, 220), {
    x: 120,
    y: 200,
  });
});

test("localPoint: a missing/zero rect is identity (never NaN)", () => {
  assert.deepStrictEqual(localPoint(null, 5, 7), { x: 5, y: 7 });
  assert.deepStrictEqual(localPoint({ left: 0, top: 0 }, -3, 4), { x: -3, y: 4 });
});

test("mergeStyle: string fields are coerced and merged over the base", () => {
  const out = mergeStyle(
    { color: "#111111", lineWidth: 1, fill: true },
    { color: "#ffffff", lineWidth: "3" },
  );
  assert.deepStrictEqual(out, { color: "#ffffff", lineWidth: 3, fill: true });
});

test("mergeStyle: invalid fields keep the base; the base is not mutated", () => {
  const base = { color: "#111111", lineWidth: 2 };
  const out = mergeStyle(base, { color: "", lineWidth: "x" });
  assert.deepStrictEqual(out, { color: "#111111", lineWidth: 2 });
  assert.deepStrictEqual(base, { color: "#111111", lineWidth: 2 }); // untouched
});

test("mergeStyle: a null base yields only the valid edited keys", () => {
  assert.deepStrictEqual(mergeStyle(null, { color: "#abcdef", lineWidth: "4" }), {
    color: "#abcdef",
    lineWidth: 4,
  });
  assert.deepStrictEqual(mergeStyle(null, { lineWidth: "0" }), {}); // <1 dropped
});

// --- pointerRows: the pointer hit-test row filter (R9) ------------------------
//
// R9: a locked OR hidden drawing MUST NOT be pointer-grabbable/openable. It stays
// tree-selectable (a bus emit), so the filter lives only on the pointer path.

test("pointerRows: a hidden row is excluded (R9 visible===false)", () => {
  const rows = [
    { id: 1, visible: true },
    { id: 2, visible: false },
  ];
  assert.deepStrictEqual(pointerRows(rows).map((r) => r.id), [1]);
});

test("pointerRows: absent visible flag stays (default visible)", () => {
  const rows = [{ id: 1 }, { id: 2, visible: false }];
  assert.deepStrictEqual(pointerRows(rows).map((r) => r.id), [1]);
});
