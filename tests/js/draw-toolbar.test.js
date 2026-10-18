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

function installDom(mount, chart) {
  const prev = globalThis.document;
  globalThis.document = {
    activeElement: null,
    getElementById: (id) => (id === "chart" ? chart : mount),
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

const { createDrawToolbar, TOOL_KEYS } = await import(
  "../../web/market/templates/market/controllers/draw-toolbar.js"
);
const { TOOL_GROUPS } = await import(
  "../../web/market/templates/market/tool-icons-core.js"
);

function buttonsOf(mount) {
  // mount > toolbar > group > button*  -> flatten every .draw-tool
  const out = [];
  // A group also carries its caption span, so filter to the buttons.
  mount.children.forEach((toolbar) =>
    toolbar.children.forEach((group) =>
      group.children.filter((c) => c.className === "draw-tool").forEach((b) => out.push(b)),
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
      ["Lines", "Fib", "Shapes", "Text", "Measure", "Positions"],
    );
    assert.strictEqual(buttonsOf(mount).length, 15);
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

test("TOOL_KEYS advertises one letter per kind (R1 delta, F7)", () => {
  // Every grouped kind has a documented shortcut letter — the aria-keyshortcuts
  // vocabulary the buttons advertise. No global router (D8).
  const kinds = TOOL_GROUPS.flatMap((g) => g.kinds);
  assert.deepStrictEqual(Object.keys(TOOL_KEYS).sort(), kinds.slice().sort());
  for (const kind of kinds) {
    assert.strictEqual(typeof TOOL_KEYS[kind], "string");
    assert.ok(TOOL_KEYS[kind].length >= 1, kind);
  }
});

test("each tool button carries an aria-keyshortcuts value (R1 delta, F7)", () => {
  const mount = makeEl("div");
  const restore = installDom(mount);
  try {
    createDrawToolbar({ store: makeStore({ tool: null }) });
    const btns = buttonsOf(mount);
    assert.strictEqual(btns.length, 15);
    for (const b of btns) {
      assert.strictEqual(
        b.getAttribute("aria-keyshortcuts"),
        TOOL_KEYS[b.dataset.kind],
        b.dataset.kind,
      );
    }
  } finally { restore(); }
});

test("each tool button shows its letter visibly in a .tool-key span (F7 UI #206)", () => {
  // The aria-keyshortcuts letter is only honest if sighted users can see it too;
  // a muted <span class="tool-key"> surfaces it on every button.
  const mount = makeEl("div");
  const restore = installDom(mount);
  try {
    createDrawToolbar({ store: makeStore({ tool: null }) });
    const btns = buttonsOf(mount);
    for (const b of btns) {
      const key = toolKeyOf(b);
      assert.ok(key, `${b.dataset.kind} has a .tool-key span`);
      assert.strictEqual(key.textContent, TOOL_KEYS[b.dataset.kind], b.dataset.kind);
    }
  } finally { restore(); }
});

function toolKeyOf(btn) {
  return (btn.children || []).find((c) => c.className === "tool-key") || null;
}

test("roving tabindex: exactly one 0, the rest -1; ArrowDown moves focus (R3)", () => {
  const mount = makeEl("div");
  const restore = installDom(mount);
  try {
    createDrawToolbar({ store: makeStore({ tool: null }) });
    const btns = buttonsOf(mount);
    assert.strictEqual(btns.filter((b) => b.getAttribute("tabindex") === "0").length, 1);
    assert.strictEqual(btns.filter((b) => b.getAttribute("tabindex") === "-1").length, 14);
    btns[0].focus();
    btns[0].keydown("ArrowDown");
    assert.strictEqual(globalThis.document.activeElement, btns[1]);
    btns[1].keydown("End");
    assert.strictEqual(globalThis.document.activeElement, btns[14]);
    btns[14].keydown("Home");
    assert.strictEqual(globalThis.document.activeElement, btns[0]);
  } finally { restore(); }
});

test("a tool letter fires inside #chart (R3, F7)", () => {
  const mount = makeEl("div");
  const chart = makeEl("section");
  const store = makeStore({ tool: null });
  const restore = installDom(mount, chart);
  try {
    createDrawToolbar({ store });
    chart.keydown("H"); // TOOL_KEYS.hline
    assert.strictEqual(store.get().tool, "hline", "the letter activates the tool");
    const t = keyEventish("T");
    (chart._listeners.keydown || []).forEach((fn) => fn(t));
    assert.strictEqual(store.get().tool, "trendline");
    assert.strictEqual(t._pd, true, "the letter is consumed (preventDefault)");
  } finally { restore(); }
});

test("a tool letter outside #chart does nothing (chart-scoped only, R3)", () => {
  const mount = makeEl("div");
  const chart = makeEl("section");
  const store = makeStore({ tool: null });
  const restore = installDom(mount, chart);
  try {
    createDrawToolbar({ store });
    // The toolbar button's keydown handler only moves roving focus (Arrow/Home/
    // End); a letter must NOT activate a tool there (letters are #chart-scoped).
    const btn = buttonsOf(mount)[0];
    const e = keyEventish("H");
    (btn._listeners.keydown || []).forEach((fn) => fn(e));
    assert.strictEqual(store.get().tool, null, "the toolbar button never activates on a letter");
    assert.notStrictEqual(e._pd, true, "the letter is not consumed outside #chart");
  } finally { restore(); }
});

test("a letter typed in a text field inside #chart is ignored (R3)", () => {
  const mount = makeEl("div");
  const chart = makeEl("section");
  const store = makeStore({ tool: null });
  const restore = installDom(mount, chart);
  try {
    createDrawToolbar({ store });
    const e = keyEventish("H");
    e.target = { tagName: "INPUT" };
    (chart._listeners.keydown || []).forEach((fn) => fn(e));
    assert.strictEqual(store.get().tool, null, "an input keeps native typing");
    assert.notStrictEqual(e._pd, true);
  } finally { restore(); }
});

function keyEventish(key) {
  return { key, _pd: false, preventDefault() { this._pd = true; } };
}

// --- F9 letters (F9 S3 R1/R3) -------------------------------------------------

test("TOOL_KEYS gains the eight F9 letters with no collision (R1 delta)", () => {
  assert.deepStrictEqual(
    {
      ray: TOOL_KEYS.ray, vline: TOOL_KEYS.vline, channel: TOOL_KEYS.channel,
      price: TOOL_KEYS.price, callout: TOOL_KEYS.callout, fib_ext: TOOL_KEYS.fib_ext,
      fib_time: TOOL_KEYS.fib_time, fib_zone: TOOL_KEYS.fib_zone,
    },
    { ray: "A", vline: "I", channel: "C", price: "U",
      callout: "O", fib_ext: "E", fib_time: "W", fib_zone: "Z" },
  );
  // No collision with the pre-F9 letters H/T/F/R/X/M/P or the tree's v/l/s.
  const letters = Object.values(TOOL_KEYS).map((s) => s.toLowerCase());
  assert.strictEqual(new Set(letters).size, letters.length);
  ["h", "t", "f", "r", "x", "m", "p", "v", "l", "s"].forEach((treeLetter) => {
    const f9 = ["a", "i", "c", "u", "o", "e", "w", "z"];
    assert.ok(!f9.includes(treeLetter), treeLetter);
  });
});

test("an F9 letter fires inside #chart and activates its tool (R3)", () => {
  const mount = makeEl("div");
  const chart = makeEl("section");
  const store = makeStore({ tool: null });
  const restore = installDom(mount, chart);
  try {
    createDrawToolbar({ store });
    chart.keydown("c"); // TOOL_KEYS.channel
    assert.strictEqual(store.get().tool, "channel");
    chart.keydown("z"); // TOOL_KEYS.fib_zone
    assert.strictEqual(store.get().tool, "fib_zone");
  } finally { restore(); }
});

test("every F9 tool button shows its own letter (R1)", () => {
  const mount = makeEl("div");
  const restore = installDom(mount);
  try {
    createDrawToolbar({ store: makeStore({ tool: null }) });
    const f9 = ["ray", "vline", "channel", "price", "callout", "fib_ext", "fib_time", "fib_zone"];
    for (const kind of f9) {
      const b = buttonsOf(mount).find((x) => x.dataset.kind === kind);
      assert.ok(b, `${kind} button`);
      assert.strictEqual(b.getAttribute("aria-keyshortcuts"), TOOL_KEYS[kind], kind);
      assert.strictEqual(toolKeyOf(b).textContent, TOOL_KEYS[kind], kind);
    }
  } finally { restore(); }
});

// --- F9 R2 (#223): hover names + group captions ------------------------------

test("every tool button carries a title (hover name) equal to its aria-label", () => {
  const mount = makeEl("div");
  const restore = installDom(mount);
  try {
    createDrawToolbar({ store: makeStore({ tool: null }) });
    for (const b of buttonsOf(mount)) {
      assert.strictEqual(b.getAttribute("title"), b.getAttribute("aria-label"), b.dataset.kind);
    }
    // #223: fib_zone is named "bands", not a homonym of fib_time.
    const zone = buttonsOf(mount).find((b) => b.dataset.kind === "fib_zone");
    assert.strictEqual(zone.getAttribute("title"), "Fibonacci bands");
  } finally { restore(); }
});

test("each role=group carries a visible muted caption with its label", () => {
  const mount = makeEl("div");
  const restore = installDom(mount);
  try {
    createDrawToolbar({ store: makeStore({ tool: null }) });
    const toolbar = mount.children[0];
    toolbar.children.forEach((group) => {
      const caption = group.children.find((c) => c.className === "tool-group-label");
      assert.ok(caption, "every group has a caption");
      assert.strictEqual(caption.textContent, group.getAttribute("aria-label"));
    });
  } finally { restore(); }
});
