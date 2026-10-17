// Undo controller + replay op matrix — node --test (no browser).
//
// The controller is a DI factory ``createUndo({store,bus,host,config})`` whose
// keydown router binds on ``document``. Its pure replay/op builder (``replayOps``)
// and the drag-coalescing / re-entrancy / id-re-mint contract are exercised here
// with a fake bus + a fake ``document`` capturing listeners, mirroring
// drawing-interaction-controller.test.js (no jsdom, framework-free).
import test from "node:test";
import assert from "node:assert";
import { createBus } from "../../web/market/templates/market/chart-bus.js";
import {
  createUndo,
  replayOps,
} from "../../web/market/templates/market/controllers/undo.js";

// --- replayOps: the op matrix (design Undo/Server Consistency) ---------------

test("replayOps: update undo PUTs the before points, redo the after", () => {
  const entry = {
    op: "update", id: 3,
    before: { points: { price: 100 } },
    after: { points: { price: 110 } },
  };
  assert.deepStrictEqual(replayOps(entry, "undo"), [
    { event: "drawing:changed", payload: { id: 3, persist: true, points: { price: 100 } } },
  ]);
  assert.deepStrictEqual(replayOps(entry, "redo"), [
    { event: "drawing:changed", payload: { id: 3, persist: true, points: { price: 110 } } },
  ]);
});

test("replayOps: a style update carries the style field, not points", () => {
  const entry = { op: "update", id: 4, before: { style: { color: "#111" } }, after: { style: { color: "#222" } } };
  assert.deepStrictEqual(replayOps(entry, "undo")[0].payload, {
    id: 4, persist: true, style: { color: "#111" },
  });
});

test("replayOps: create undo DELETEs, redo re-POSTs (restore)", () => {
  const after = { kind: "rect", points: { p1: { time: 1, price: 2 } }, style: { color: "#abc" } };
  const entry = { op: "create", id: 7, after: after };
  assert.deepStrictEqual(replayOps(entry, "undo"), [
    { event: "drawing:delete", payload: { id: 7 } },
  ]);
  assert.deepStrictEqual(replayOps(entry, "redo"), [
    { event: "drawing:restore", payload: { row: after } },
  ]);
});

test("replayOps: delete undo re-POSTs (restore), redo DELETEs", () => {
  const before = { kind: "hline", points: { price: 50 }, style: { color: "#111" } };
  const entry = { op: "delete", id: 9, before: before };
  assert.deepStrictEqual(replayOps(entry, "undo"), [
    { event: "drawing:restore", payload: { row: before } },
  ]);
  assert.deepStrictEqual(replayOps(entry, "redo"), [
    { event: "drawing:delete", payload: { id: 9 } },
  ]);
});

test("replayOps: duplicate is equivalent to create", () => {
  const after = { kind: "hline", points: { price: 1 }, style: {} };
  const dup = { op: "duplicate", id: 2, after: after };
  assert.deepStrictEqual(replayOps(dup, "undo"), [{ event: "drawing:delete", payload: { id: 2 } }]);
  assert.deepStrictEqual(replayOps(dup, "redo"), [
    { event: "drawing:restore", payload: { row: after } },
  ]);
});

test("replayOps: a null/unknown entry replays nothing", () => {
  assert.deepStrictEqual(replayOps(null, "undo"), []);
  assert.deepStrictEqual(replayOps({ op: "nope", id: 1 }, "undo"), []);
});

// --- controller wiring: coalescing, router, re-entrancy, id re-mint ----------

function makeDoc() {
  const listeners = {};
  return {
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    fire(type, ev) { (listeners[type] || []).forEach((fn) => fn(ev)); },
  };
}

function makeStore(initial) {
  const state = { ...initial };
  return { get: () => state, set: (p) => Object.assign(state, p), subscribe: () => {} };
}

function keyEvent(k, opts) {
  return Object.assign(
    { key: k, metaKey: false, ctrlKey: false, shiftKey: false, target: null, preventDefault() { this._pd = true; } },
    opts,
  );
}

function undoFixture() {
  const doc = makeDoc();
  const prevDoc = globalThis.document;
  globalThis.document = doc;
  const bus = createBus();
  const emitted = [];
  ["drawing:changed", "drawing:delete", "drawing:restore"].forEach((name) => {
    bus.on(name, (p) => emitted.push({ name, p }));
  });
  const store = makeStore({ symbol: "BTCUSDT", interval: "1m", tool: null });
  const undo = createUndo({ store, bus, host: {}, config: {} });
  return {
    doc, bus, emitted, undo,
    restore() { if (prevDoc === undefined) delete globalThis.document; else globalThis.document = prevDoc; },
  };
}

// A committed row is published on drawings:changed; a drag emits many
// persist:false frames then ONE persist:true at gesture end.
function commitRow(bus, row) { bus.emit("drawings:changed", { rows: [row] }); }

test("one drag gesture yields exactly ONE entry (persist:true boundary)", () => {
  const f = undoFixture();
  try {
    commitRow(f.bus, { id: 1, kind: "hline", points: { price: 100 }, style: { color: "#111" } });
    // 200 live frames then the single persist boundary.
    for (let i = 0; i < 200; i += 1) {
      f.bus.emit("drawing:changed", { id: 1, points: { price: 100 + i }, persist: false });
    }
    f.emitted.length = 0; // the captured frames are the test's own input
    assert.deepStrictEqual(f.emitted, [], "per-frame drag never emits a replay");
    f.bus.emit("drawing:changed", { id: 1, points: { price: 130 }, persist: true });
    f.emitted.length = 0; // reset the input capture before reading controller output

    // Ctrl+Z undoes the ONE recorded entry, PUTing the PRE-drag points.
    const e = keyEvent("z", { ctrlKey: true });
    f.doc.fire("keydown", e);
    assert.strictEqual(e._pd, true, "Ctrl+Z prevents default");
    assert.strictEqual(f.emitted.length, 1);
    assert.strictEqual(f.emitted[0].name, "drawing:changed");
    assert.deepStrictEqual(f.emitted[0].p, { id: 1, persist: true, points: { price: 100 } });
  } finally { f.restore(); }
});

test("per-frame persistence is rejected (only persist:false -> no entry)", () => {
  const f = undoFixture();
  try {
    commitRow(f.bus, { id: 1, kind: "hline", points: { price: 100 }, style: {} });
    f.bus.emit("drawing:changed", { id: 1, points: { price: 101 }, persist: false });
    f.bus.emit("drawing:changed", { id: 1, points: { price: 102 }, persist: false });
    f.emitted.length = 0; // the captured frames are the test's own input
    f.doc.fire("keydown", keyEvent("z", { ctrlKey: true }));
    assert.deepStrictEqual(f.emitted, [], "no entry recorded, nothing to replay");
  } finally { f.restore(); }
});

test("a flag-only drawing:changed (visible/locked) is out of scope (no entry)", () => {
  const f = undoFixture();
  try {
    commitRow(f.bus, { id: 1, kind: "hline", points: { price: 100 }, style: {} });
    f.bus.emit("drawing:changed", { id: 1, visible: false, persist: true });
    f.emitted.length = 0; // the captured flag frame is the test's own input
    f.doc.fire("keydown", keyEvent("z", { ctrlKey: true }));
    assert.deepStrictEqual(f.emitted, []);
  } finally { f.restore(); }
});

test("a replay never re-records itself (replaying guard)", () => {
  const f = undoFixture();
  try {
    commitRow(f.bus, { id: 1, kind: "hline", points: { price: 100 }, style: {} });
    f.bus.emit("drawing:changed", { id: 1, points: { price: 130 }, persist: true });
    f.doc.fire("keydown", keyEvent("z", { ctrlKey: true })); // undo -> PUT before
    // If the replay's own drawing:changed were re-recorded, a second Ctrl+Z would
    // emit again. It must have nothing left to undo.
    f.emitted.length = 0;
    f.doc.fire("keydown", keyEvent("z", { ctrlKey: true }));
    assert.deepStrictEqual(f.emitted, [], "the replay did not push a new op");
  } finally { f.restore(); }
});

test("undo of a delete re-POSTs; redo DELETEs", () => {
  const f = undoFixture();
  try {
    commitRow(f.bus, { id: 5, kind: "hline", points: { price: 42 }, style: { color: "#111" } });
    f.bus.emit("drawing:delete", { id: 5 });
    f.emitted.length = 0; // the captured delete is the test's own input
    f.doc.fire("keydown", keyEvent("z", { ctrlKey: true })); // undo delete -> restore
    assert.strictEqual(f.emitted.length, 1);
    assert.deepStrictEqual(f.emitted[0], {
      name: "drawing:restore",
      p: { row: { kind: "hline", points: { price: 42 }, style: { color: "#111" } } },
    });
    f.emitted.length = 0;
    f.doc.fire("keydown", keyEvent("z", { ctrlKey: true, shiftKey: true })); // redo -> delete
    assert.deepStrictEqual(f.emitted, [{ name: "drawing:delete", p: { id: 5 } }]);
  } finally { f.restore(); }
});

test("a restore's async drawing:created patches the re-minted id onto the entry", () => {
  const f = undoFixture();
  try {
    // A user create (tool draw / duplicate) -> drawing:created records op:create.
    f.bus.emit("drawing:created", {
      id: 5, kind: "rect", points: { p1: { time: 1, price: 2 } }, style: { color: "#abc" },
    });
    f.doc.fire("keydown", keyEvent("z", { ctrlKey: true })); // undo create -> DELETE 5
    assert.deepStrictEqual(f.emitted, [{ name: "drawing:delete", p: { id: 5 } }]);
    f.emitted.length = 0;

    f.doc.fire("keydown", keyEvent("z", { ctrlKey: true, shiftKey: true })); // redo -> restore
    assert.strictEqual(f.emitted.length, 1);
    assert.strictEqual(f.emitted[0].name, "drawing:restore");
    f.emitted.length = 0;

    // The POST resolves -> drawing:created with a NEW id; the entry is patched.
    f.bus.emit("drawing:created", {
      id: 9, kind: "rect", points: { p1: { time: 1, price: 2 } }, style: { color: "#abc" },
    });
    assert.deepStrictEqual(f.emitted, [], "the completion is not re-recorded as a new create");

    f.doc.fire("keydown", keyEvent("z", { ctrlKey: true })); // undo again -> DELETE 9
    assert.deepStrictEqual(f.emitted, [{ name: "drawing:delete", p: { id: 9 } }],
      "the entry carries the re-minted id");
  } finally { f.restore(); }
});

test("Ctrl+Y redoes (Windows); a bare key is ignored; preventDefault only on a hit", () => {
  const f = undoFixture();
  try {
    commitRow(f.bus, { id: 1, kind: "hline", points: { price: 100 }, style: {} });
    f.bus.emit("drawing:changed", { id: 1, points: { price: 130 }, persist: true });
    f.doc.fire("keydown", keyEvent("z", { ctrlKey: true })); // undone -> redo available
    f.emitted.length = 0;
    const y = keyEvent("y", { ctrlKey: true });
    f.doc.fire("keydown", y);
    assert.strictEqual(y._pd, true);
    assert.deepStrictEqual(f.emitted, [
      { name: "drawing:changed", p: { id: 1, persist: true, points: { price: 130 } } },
    ]);
    // A non-modifier key does nothing.
    const plain = keyEvent("z");
    f.doc.fire("keydown", plain);
    assert.notStrictEqual(plain._pd, true);
    assert.deepStrictEqual(f.emitted.length, 1);
  } finally { f.restore(); }
});

test("Escape and Delete are left to the #chart handler (router ignores them)", () => {
  const f = undoFixture();
  try {
    const esc = keyEvent("Escape", { ctrlKey: true });
    const del = keyEvent("Delete", { ctrlKey: true });
    f.doc.fire("keydown", esc);
    f.doc.fire("keydown", del);
    assert.notStrictEqual(esc._pd, true);
    assert.notStrictEqual(del._pd, true);
    assert.deepStrictEqual(f.emitted, []);
  } finally { f.restore(); }
});

test("a text input is exempt from the router", () => {
  const f = undoFixture();
  try {
    commitRow(f.bus, { id: 1, kind: "hline", points: { price: 100 }, style: {} });
    f.bus.emit("drawing:changed", { id: 1, points: { price: 130 }, persist: true });
    f.emitted.length = 0; // the captured drag is the test's own input
    const e = keyEvent("z", { ctrlKey: true, target: { tagName: "INPUT" } });
    f.doc.fire("keydown", e);
    assert.notStrictEqual(e._pd, true, "native edit behaviour preserved");
    assert.deepStrictEqual(f.emitted, []);
  } finally { f.restore(); }
});

test("a contenteditable target is exempt too", () => {
  const f = undoFixture();
  try {
    commitRow(f.bus, { id: 1, kind: "hline", points: { price: 100 }, style: {} });
    f.bus.emit("drawing:changed", { id: 1, points: { price: 130 }, persist: true });
    const e = keyEvent("z", { ctrlKey: true, metaKey: true, target: { tagName: "DIV", isContentEditable: true } });
    f.doc.fire("keydown", e);
    assert.notStrictEqual(e._pd, true);
  } finally { f.restore(); }
});

test("clearForSwitch empties the stack and the committed cache", () => {
  const f = undoFixture();
  try {
    commitRow(f.bus, { id: 1, kind: "hline", points: { price: 100 }, style: {} });
    f.bus.emit("drawing:changed", { id: 1, points: { price: 130 }, persist: true });
    f.emitted.length = 0; // the captured drag is the test's own input
    f.undo.clearForSwitch();
    f.doc.fire("keydown", keyEvent("z", { ctrlKey: true }));
    assert.deepStrictEqual(f.emitted, [], "the stack is empty after a switch");
    // The committed cache is gone too: a stale delete records nothing.
    f.bus.emit("drawing:delete", { id: 1 });
    f.emitted.length = 0; // the captured delete is the test's own input
    f.doc.fire("keydown", keyEvent("z", { ctrlKey: true }));
    assert.deepStrictEqual(f.emitted, []);
  } finally { f.restore(); }
});
