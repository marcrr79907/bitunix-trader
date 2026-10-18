// object-tree DOM helpers — node --test with the same tiny shim as the tree.
//
// Extracted from the object-tree controller so it stays under the R14 module
// ceiling: the row markup factory (el/action) and the eye/lock toggle sync.
import test from "node:test";
import assert from "node:assert";

import {
  el,
  action,
  syncEye,
  syncLock,
} from "../../web/market/templates/market/object-tree-dom-core.js";
import {
  EYE_ON,
  EYE_OFF,
  LOCK_ON,
  LOCK_OFF,
} from "../../web/market/templates/market/tool-icons-core.js";

function makeEl(tag) {
  return {
    tagName: tag,
    children: [],
    attrs: {},
    dataset: {},
    _listeners: {},
    _text: "",
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
  };
}

function installDom() {
  const prev = globalThis.document;
  globalThis.document = { createElement: makeEl };
  return () => { globalThis.document = prev; };
}

test("el builds a node with class and attributes", () => {
  const restore = installDom();
  try {
    const node = el("li", "tree-row", { role: "treeitem", tabindex: "-1" });
    assert.strictEqual(node.tagName, "li");
    assert.strictEqual(node.className, "tree-row");
    assert.strictEqual(node.getAttribute("role"), "treeitem");
    assert.strictEqual(node.getAttribute("tabindex"), "-1");
    assert.strictEqual(el("span").className, "", "no class is optional");
  } finally { restore(); }
});

test("action builds a tabindex=-1 button that stops propagation and calls back", () => {
  const restore = installDom();
  try {
    const seen = [];
    const btn = action("row-eye", "Toggle hline visibility", "<svg/>", (b) => seen.push(b), "v");
    assert.strictEqual(btn.tagName, "button");
    assert.strictEqual(btn.className, "row-eye");
    assert.strictEqual(btn.getAttribute("type"), "button");
    assert.strictEqual(btn.getAttribute("aria-label"), "Toggle hline visibility");
    assert.strictEqual(btn.getAttribute("tabindex"), "-1");
    assert.strictEqual(btn.getAttribute("aria-keyshortcuts"), "v");
    assert.strictEqual(btn.innerHTML, "<svg/>");
    btn.click();
    assert.deepStrictEqual(seen, [btn]);
  } finally { restore(); }
});

test("syncEye/syncLock swap icon and aria-pressed", () => {
  const restore = installDom();
  try {
    const eye = makeEl("button");
    syncEye(eye, true);
    assert.strictEqual(eye.innerHTML, EYE_ON);
    assert.strictEqual(eye.getAttribute("aria-pressed"), "true");
    syncEye(eye, false);
    assert.strictEqual(eye.innerHTML, EYE_OFF);
    assert.strictEqual(eye.getAttribute("aria-pressed"), "false");

    const lock = makeEl("button");
    syncLock(lock, true);
    assert.strictEqual(lock.innerHTML, LOCK_ON);
    syncLock(lock, false);
    assert.strictEqual(lock.innerHTML, LOCK_OFF);
    assert.strictEqual(lock.getAttribute("aria-pressed"), "false");
  } finally { restore(); }
});
