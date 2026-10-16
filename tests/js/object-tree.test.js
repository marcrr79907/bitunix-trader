// object-tree controller behaviour — node --test with a tiny DOM shim.
//
// The controller's chart/REST peers need a browser (E2E), but the tree contract
// is pure DOM + store + bus: grouping (drawings + active-only indicators),
// per-row eye/lock/delete/select emits, and roving-tabindex keyboard nav. A
// hand-rolled shim (no jsdom) keeps the test framework-free, mirroring the
// project's no-new-dependency rule and the draw-toolbar test precedent.
import test from "node:test";
import assert from "node:assert";
import { createBus } from "../../web/market/templates/market/chart-bus.js";

// --- minimal DOM shim -------------------------------------------------------
function makeEl(tag) {
  const el = {
    tagName: tag,
    children: [],
    attrs: {},
    dataset: {},
    _listeners: {},
    _text: "",
    hidden: false,
    className: "",
    set textContent(v) { this._text = String(v); this.children = []; },
    get textContent() { return this._text; },
    set innerHTML(v) { this._html = v; },
    get innerHTML() { return this._html || ""; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    appendChild(c) { this.children.push(c); return c; },
    addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
    click() { (this._listeners.click || []).forEach((fn) => fn({ stopPropagation() {} })); },
    keydown(key) {
      (this._listeners.keydown || []).forEach((fn) => fn({ key, preventDefault() {} }));
    },
    focus() { globalThis.document.activeElement = this; },
  };
  return el;
}

function installDom(mount) {
  const prev = globalThis.document;
  globalThis.document = {
    activeElement: null,
    getElementById: () => mount,
    createElement: makeEl,
  };
  return () => { globalThis.document = prev; };
}

function makeStore(initial) {
  const state = { ...initial };
  const listeners = [];
  return {
    get: () => state,
    set: (patch) => { Object.assign(state, patch); listeners.slice().forEach((fn) => fn(state)); },
    subscribe: (fn) => { listeners.push(fn); },
  };
}

function walk(el, out) {
  out = out || [];
  (el.children || []).forEach((c) => { out.push(c); walk(c, out); });
  return out;
}
const byClass = (root, cls) => walk(root).filter((e) => e.className === cls);
const rows = (root) => byClass(root, "tree-row");
const rowsWith = (root, prop) =>
  rows(root).filter((r) => r.dataset[prop] !== undefined);

const { createObjectTree } = await import(
  "../../web/market/templates/market/controllers/object-tree.js"
);

function setup(initial) {
  const mount = makeEl("div");
  const restore = installDom(mount);
  const bus = createBus();
  const store = makeStore(initial);
  createObjectTree({ store, bus, onIndicatorSettings: () => {} });
  return { mount, restore, bus, store };
}

const TWO_DRAWINGS = [
  { id: 1, kind: "hline", visible: true, locked: false },
  { id: 2, kind: "rect", visible: false, locked: true },
];

test("renders role=tree with Drawings + Indicators groups (active-only)", () => {
  const { mount, restore, bus } = setup({
    indicators: ["sma", "ema"],
    indicatorVisible: {},
    params: {},
  });
  try {
    bus.emit("drawings:changed", { rows: TWO_DRAWINGS.map((r) => ({ ...r })) });
    const tree = byClass(mount, "object-tree")[0];
    assert.ok(tree, "the tree root exists");
    assert.strictEqual(tree.getAttribute("role"), "tree");
    assert.strictEqual(tree.getAttribute("aria-label"), "Chart objects");

    const labels = byClass(mount, "tree-group-label").map((e) => e.textContent);
    assert.deepStrictEqual(labels, ["Drawings", "Indicators"]);
    // Group parents are treeitems with aria-expanded.
    byClass(mount, "tree-group").forEach((g) => {
      assert.strictEqual(g.getAttribute("role"), "treeitem");
      assert.strictEqual(g.getAttribute("aria-expanded"), "true");
    });

    const drawRows = rowsWith(mount, "id");
    const indRows = rowsWith(mount, "token");
    assert.strictEqual(drawRows.length, 2, "2 drawing rows");
    assert.strictEqual(indRows.length, 2, "exactly the 2 active tokens");
    const tokens = indRows.map((r) => r.dataset.token);
    assert.deepStrictEqual(tokens, ["sma", "ema"]);
    // No registry token is listed (active-only membership).
    assert.ok(!tokens.includes("rsi"));
    assert.ok(!tokens.includes("bollinger"));
  } finally { restore(); }
});

test("drawing eye emits drawing:changed {visible,persist} (R2)", () => {
  const { mount, restore, bus } = setup({
    indicators: [],
    indicatorVisible: {},
    params: {},
  });
  try {
    const emitted = [];
    bus.on("drawing:changed", (p) => emitted.push(p));
    bus.emit("drawings:changed", { rows: TWO_DRAWINGS.map((r) => ({ ...r })) });
    const row = rowsWith(mount, "id").find((r) => r.dataset.id == 1);
    byClass(row, "row-eye")[0].click();
    assert.deepStrictEqual(emitted, [{ id: 1, visible: false, persist: true }]);
    // The eye now reflects the new state without a reload.
    assert.strictEqual(byClass(row, "row-eye")[0].getAttribute("aria-pressed"), "false");
  } finally { restore(); }
});

test("drawing lock emits drawing:changed {locked,persist} (R2)", () => {
  const { mount, restore, bus } = setup({
    indicators: [],
    indicatorVisible: {},
    params: {},
  });
  try {
    const emitted = [];
    bus.on("drawing:changed", (p) => emitted.push(p));
    bus.emit("drawings:changed", { rows: TWO_DRAWINGS.map((r) => ({ ...r })) });
    const row = rowsWith(mount, "id").find((r) => r.dataset.id == 2);
    byClass(row, "row-lock")[0].click();
    assert.deepStrictEqual(emitted, [{ id: 2, locked: false, persist: true }]);
  } finally { restore(); }
});

test("a locked row is still tree-selectable (R9: bus emit, not pointer hit)", () => {
  // R9 (F5 FIX-1): lock blocks the POINTER path only. The tree must still emit
  // drawing:selected for a locked row — that is what the locked filter relies on.
  const { mount, restore, bus } = setup({
    indicators: [],
    indicatorVisible: {},
    params: {},
  });
  try {
    const emitted = [];
    bus.on("drawing:selected", (p) => emitted.push(p));
    bus.emit("drawings:changed", { rows: TWO_DRAWINGS.map((r) => ({ ...r })) });
    const locked = rowsWith(mount, "id").find((r) => r.dataset.id == 2); // locked
    locked.keydown("Enter");
    assert.deepStrictEqual(emitted, [{ id: 2 }]);
    assert.strictEqual(
      rowsWith(mount, "id").find((r) => r.dataset.id == 2)
        .getAttribute("aria-selected"),
      "true",
    );
  } finally { restore(); }
});

test("persisted flags render on first paint (R4)", () => {
  const { mount, restore, bus } = setup({
    indicators: [],
    indicatorVisible: {},
    params: {},
  });
  try {
    bus.emit("drawings:changed", { rows: TWO_DRAWINGS.map((r) => ({ ...r })) });
    const row = rowsWith(mount, "id").find((r) => r.dataset.id == 2);
    assert.strictEqual(byClass(row, "row-eye")[0].getAttribute("aria-pressed"), "false");
    assert.strictEqual(byClass(row, "row-lock")[0].getAttribute("aria-pressed"), "true");
  } finally { restore(); }
});

test("delete emits drawing:delete with the id (R2)", () => {
  const { mount, restore, bus } = setup({
    indicators: [],
    indicatorVisible: {},
    params: {},
  });
  try {
    const emitted = [];
    bus.on("drawing:delete", (p) => emitted.push(p));
    bus.emit("drawings:changed", { rows: TWO_DRAWINGS.map((r) => ({ ...r })) });
    const row = rowsWith(mount, "id").find((r) => r.dataset.id == 1);
    byClass(row, "row-delete")[0].click();
    assert.deepStrictEqual(emitted, [{ id: 1 }]);
  } finally { restore(); }
});

test("select emits drawing:selected and moves aria-selected (R2)", () => {
  const { mount, restore, bus } = setup({
    indicators: [],
    indicatorVisible: {},
    params: {},
  });
  try {
    const emitted = [];
    bus.on("drawing:selected", (p) => emitted.push(p));
    bus.emit("drawings:changed", { rows: TWO_DRAWINGS.map((r) => ({ ...r })) });
    const row = rowsWith(mount, "id").find((r) => r.dataset.id == 1);
    row.keydown("Enter");
    assert.deepStrictEqual(emitted, [{ id: 1 }]);
    assert.strictEqual(
      rowsWith(mount, "id").find((r) => r.dataset.id == 1).getAttribute("aria-selected"),
      "true",
    );
  } finally { restore(); }
});

test("indicator eye emits indicator:visibility + store slot, no rebuild (R2/R4)", () => {
  const { mount, restore, bus, store } = setup({
    indicators: ["sma", "ema"],
    indicatorVisible: {},
    params: {},
  });
  try {
    const vis = [];
    const rebuilds = [];
    bus.on("indicator:visibility", (p) => vis.push(p));
    bus.on("indicator:changed", () => rebuilds.push(1));
    const row = rowsWith(mount, "token").find((r) => r.dataset.token === "sma");
    byClass(row, "row-eye")[0].click();
    assert.deepStrictEqual(vis, [{ token: "sma", visible: false }]);
    assert.strictEqual(store.get().indicatorVisible.sma, false);
    assert.strictEqual(rebuilds.length, 0, "no indicator:changed / rebuild");
  } finally { restore(); }
});

test("indicators expose eye + delete + settings but no lock (R2)", () => {
  const { mount, restore, bus } = setup({
    indicators: ["sma"],
    indicatorVisible: {},
    params: {},
  });
  try {
    const row = rowsWith(mount, "token").find((r) => r.dataset.token === "sma");
    assert.strictEqual(byClass(row, "row-eye").length, 1);
    assert.strictEqual(byClass(row, "row-lock").length, 0);
    assert.strictEqual(byClass(row, "row-delete").length, 1);
    assert.strictEqual(byClass(row, "row-settings").length, 1);
    // Delete removes membership -> indicator:changed (rebuild path).
    const rebuilds = [];
    bus.on("indicator:changed", () => rebuilds.push(1));
    byClass(row, "row-delete")[0].click();
    assert.deepStrictEqual(rebuilds, [1]);
  } finally { restore(); }
});

test("roving tabindex: exactly one 0; ArrowDown moves focus between treeitems (R3)", () => {
  const { mount, restore, bus } = setup({
    indicators: ["sma"],
    indicatorVisible: {},
    params: {},
  });
  try {
    bus.emit("drawings:changed", { rows: TWO_DRAWINGS.map((r) => ({ ...r })) });
    const all = rows(mount).concat(byClass(mount, "tree-group"));
    assert.strictEqual(all.filter((e) => e.getAttribute("tabindex") === "0").length, 1);
    assert.strictEqual(all.filter((e) => e.getAttribute("tabindex") === "-1").length, all.length - 1);

    const first = rowsWith(mount, "id").find((r) => r.dataset.id == 1);
    first.focus();
    first.keydown("ArrowDown");
    const focused = globalThis.document.activeElement;
    assert.ok(focused, "focus moved");
    assert.notStrictEqual(focused, first);
    assert.strictEqual(focused.getAttribute("role"), "treeitem");
  } finally { restore(); }
});

test("drawing row: v toggles visibility, l toggles lock by keyboard (R6/R9)", () => {
  // R6/R9 (F5 FIX-3): the eye/lock buttons are mouse-only. A focused row MUST
  // expose documented key bindings that activate the same actions, without
  // moving the roving tabindex off the R3 row-based Up/Down model.
  const { mount, restore, bus } = setup({
    indicators: [],
    indicatorVisible: {},
    params: {},
  });
  try {
    const changed = [];
    bus.on("drawing:changed", (p) => changed.push(p));
    bus.emit("drawings:changed", { rows: TWO_DRAWINGS.map((r) => ({ ...r })) });
    const row = rowsWith(mount, "id").find((r) => r.dataset.id == 1);
    row.focus();
    row.keydown("v");
    assert.deepStrictEqual(changed[0], { id: 1, visible: false, persist: true });
    row.keydown("l");
    assert.deepStrictEqual(changed[1], { id: 1, locked: true, persist: true });
    assert.strictEqual(globalThis.document.activeElement, row);
  } finally { restore(); }
});

test("row action buttons advertise their key binding (R6)", () => {
  const { mount, restore, bus } = setup({
    indicators: ["sma"],
    indicatorVisible: {},
    params: {},
  });
  try {
    bus.emit("drawings:changed", { rows: TWO_DRAWINGS.map((r) => ({ ...r })) });
    const drawRow = rowsWith(mount, "id").find((r) => r.dataset.id == 1);
    assert.strictEqual(byClass(drawRow, "row-eye")[0].getAttribute("aria-keyshortcuts"), "v");
    assert.strictEqual(byClass(drawRow, "row-lock")[0].getAttribute("aria-keyshortcuts"), "l");
    const indRow = rowsWith(mount, "token").find((r) => r.dataset.token === "sma");
    assert.strictEqual(byClass(indRow, "row-eye")[0].getAttribute("aria-keyshortcuts"), "v");
    assert.strictEqual(byClass(indRow, "row-settings")[0].getAttribute("aria-keyshortcuts"), "s");
  } finally { restore(); }
});

test("indicator row: v hides, Delete removes, s opens settings (R6/R9)", () => {
  const mount = makeEl("div");
  const restore = installDom(mount);
  const bus = createBus();
  const store = makeStore({ indicators: ["sma"], indicatorVisible: {}, params: {} });
  const opened = [];
  createObjectTree({
    store,
    bus,
    onIndicatorSettings: (token) => opened.push(token),
  });
  try {
    const vis = [];
    const rebuilds = [];
    bus.on("indicator:visibility", (p) => vis.push(p));
    bus.on("indicator:changed", () => rebuilds.push(1));
    const row = rowsWith(mount, "token").find((r) => r.dataset.token === "sma");
    row.focus();
    row.keydown("v");
    assert.deepStrictEqual(vis, [{ token: "sma", visible: false }]);
    assert.strictEqual(store.get().indicatorVisible.sma, false);
    row.keydown("s");
    assert.deepStrictEqual(opened, ["sma"]);
    row.keydown("Delete");
    assert.deepStrictEqual(rebuilds, [1]);
  } finally { restore(); }
});

test("Left/Right collapse/expand a focused group parent (R3)", () => {
  const { mount, restore } = setup({
    indicators: ["sma"],
    indicatorVisible: {},
    params: {},
  });
  try {
    const group = byClass(mount, "tree-group")[0]; // Drawings
    group.focus();
    group.keydown("ArrowLeft");
    assert.strictEqual(group.getAttribute("aria-expanded"), "false");
    group.keydown("ArrowRight");
    assert.strictEqual(group.getAttribute("aria-expanded"), "true");
  } finally { restore(); }
});
