// draw-toolbar controller behaviour — node --test with a tiny DOM shim.
//
// The controller's chart/REST peers need a browser (E2E), but its toolbar
// contract is pure DOM + store: activating a tool writes store.tool (TASK 2.4)
// and aria-pressed follows store.subscribe. A hand-rolled shim (no jsdom) keeps
// the test framework-free, mirroring the project's no-new-dependency rule.
import test from "node:test";
import assert from "node:assert";

// --- minimal DOM shim -------------------------------------------------------
function makeEl(tag) {
  const el = {
    tagName: tag,
    children: [],
    attrs: {},
    dataset: {},
    _listeners: {},
    textContent: "",
    set innerHTML(v) { this._html = v; },
    get innerHTML() { return this._html || ""; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    appendChild(c) { this.children.push(c); return c; },
    addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
    click() { (this._listeners.click || []).forEach((fn) => fn({})); },
    keydown(key) { (this._listeners.keydown || []).forEach((fn) => fn({ key, preventDefault() {} })); },
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

const { createDrawToolbar } = await import(
  "../../web/market/templates/market/controllers/draw-toolbar.js"
);

function buttonsOf(mount) {
  // mount > toolbar > group > button*  -> flatten every .draw-tool
  const out = [];
  mount.children.forEach((toolbar) =>
    toolbar.children.forEach((group) =>
      group.children.forEach((b) => out.push(b)),
    ),
  );
  return out;
}

test("renders a vertical role=toolbar with one role=group per tool group", () => {
  const mount = makeEl("div");
  const restore = installDom(mount);
  try {
    createDrawToolbar({ store: makeStore({ tool: null }) });
    const toolbar = mount.children[0];
    assert.strictEqual(toolbar.getAttribute("role"), "toolbar");
    assert.strictEqual(toolbar.getAttribute("aria-orientation"), "vertical");
    assert.strictEqual(toolbar.getAttribute("aria-label"), "Drawing tools");
    assert.deepStrictEqual(
      toolbar.children.map((g) => g.getAttribute("aria-label")),
      ["Lines", "Fib", "Shapes", "Text"],
    );
    assert.strictEqual(buttonsOf(mount).length, 5);
  } finally { restore(); }
});

test("activating a tool writes store.tool and flips aria-pressed (R2)", () => {
  const mount = makeEl("div");
  const store = makeStore({ tool: null });
  const restore = installDom(mount);
  try {
    createDrawToolbar({ store });
    const fib = buttonsOf(mount).find((b) => b.dataset.kind === "fib");
    fib.click();
    assert.strictEqual(store.get().tool, "fib");
    assert.strictEqual(fib.getAttribute("aria-pressed"), "true");
    // Only one pressed.
    assert.strictEqual(buttonsOf(mount).filter((b) => b.getAttribute("aria-pressed") === "true").length, 1);
    // Clicking the active tool cancels (legacy toggle semantics).
    fib.click();
    assert.strictEqual(store.get().tool, null);
    assert.strictEqual(fib.getAttribute("aria-pressed"), "false");
  } finally { restore(); }
});

test("an external store.tool change syncs aria-pressed (R2 cancel path)", () => {
  const mount = makeEl("div");
  const store = makeStore({ tool: null });
  const restore = installDom(mount);
  try {
    createDrawToolbar({ store });
    const rect = buttonsOf(mount).find((b) => b.dataset.kind === "rect");
    rect.click();
    assert.strictEqual(rect.getAttribute("aria-pressed"), "true");
    store.set({ tool: null }); // e.g. clearForSwitch
    assert.strictEqual(buttonsOf(mount).every((b) => b.getAttribute("aria-pressed") === "false"), true);
  } finally { restore(); }
});

test("roving tabindex: exactly one 0, the rest -1; ArrowDown moves focus (R3)", () => {
  const mount = makeEl("div");
  const restore = installDom(mount);
  try {
    createDrawToolbar({ store: makeStore({ tool: null }) });
    const btns = buttonsOf(mount);
    assert.strictEqual(btns.filter((b) => b.getAttribute("tabindex") === "0").length, 1);
    assert.strictEqual(btns.filter((b) => b.getAttribute("tabindex") === "-1").length, 4);
    btns[0].focus();
    btns[0].keydown("ArrowDown");
    assert.strictEqual(globalThis.document.activeElement, btns[1]);
    btns[1].keydown("End");
    assert.strictEqual(globalThis.document.activeElement, btns[4]);
    btns[4].keydown("Home");
    assert.strictEqual(globalThis.document.activeElement, btns[0]);
  } finally { restore(); }
});
