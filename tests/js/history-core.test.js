// Pure history-core tests — node --test (no DOM, no chart lib, no network).
//
// The core owns a bounded LIFO stack of OPAQUE drawing operations
// ({op,id,before,after}); it NEVER inspects the entry fields. Undo/redo just
// move a reference between the two stacks, so a caller may mutate a returned
// entry in place (e.g. patch a re-minted id) and the stack sees the change.
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createHistory } from "../../web/market/templates/market/history-core.js";

const SRC = readFileSync(
  fileURLToPath(new URL("../../web/market/templates/market/history-core.js", import.meta.url)),
  "utf8",
);

// --- shape -------------------------------------------------------------------

test("a fresh history is empty", () => {
  const h = createHistory();
  assert.strictEqual(h.canUndo(), false);
  assert.strictEqual(h.canRedo(), false);
  assert.strictEqual(h.size(), 0);
});

test("undo and redo on an empty stack return null", () => {
  const h = createHistory();
  assert.strictEqual(h.undo(), null);
  assert.strictEqual(h.redo(), null);
});

// --- push / undo / redo round trip -------------------------------------------

test("push then undo then redo round-trips the same record", () => {
  const h = createHistory();
  const op = { op: "create", id: 1, after: { kind: "hline" } };
  h.push(op);

  assert.strictEqual(h.canUndo(), true);
  assert.strictEqual(h.canRedo(), false);
  assert.strictEqual(h.size(), 1);

  const undone = h.undo();
  assert.strictEqual(undone, op);
  assert.strictEqual(h.canUndo(), false);
  assert.strictEqual(h.canRedo(), true);
  assert.strictEqual(h.size(), 0);

  const redone = h.redo();
  assert.strictEqual(redone, op);
  assert.strictEqual(h.canUndo(), true);
  assert.strictEqual(h.canRedo(), false);
  assert.strictEqual(h.size(), 1);
});

test("undo/redo are LIFO", () => {
  const h = createHistory();
  const a = { op: "create", id: 1 };
  const b = { op: "move", id: 2 };
  const c = { op: "delete", id: 3 };
  h.push(a);
  h.push(b);
  h.push(c);

  assert.strictEqual(h.undo(), c);
  assert.strictEqual(h.undo(), b);
  assert.strictEqual(h.undo(), a);
  assert.strictEqual(h.undo(), null);

  assert.strictEqual(h.redo(), a);
  assert.strictEqual(h.redo(), b);
  assert.strictEqual(h.redo(), c);
  assert.strictEqual(h.redo(), null);
});

// --- redo-clear rule ---------------------------------------------------------

test("a new push clears the redo stack", () => {
  const h = createHistory();
  h.push({ op: "create", id: 1 });
  h.undo();
  assert.strictEqual(h.canRedo(), true);
  assert.strictEqual(h.size(), 0);

  h.push({ op: "move", id: 2 });
  assert.strictEqual(h.canRedo(), false);
  assert.strictEqual(h.size(), 1);
});

// --- bounded ----------------------------------------------------------------

test("default limit is 50 and drops the oldest", () => {
  const h = createHistory();
  for (let i = 1; i <= 51; i += 1) h.push({ op: "create", id: i });
  assert.strictEqual(h.size(), 50);
  // The oldest (id 1) was dropped: undo peels back to id 2, never id 1.
  let last = null;
  while (h.canUndo()) last = h.undo();
  assert.strictEqual(last.op, "create");
  assert.strictEqual(last.id, 2);
});

test("a custom limit bounds the stack", () => {
  const h = createHistory({ limit: 3 });
  for (let i = 1; i <= 4; i += 1) h.push({ op: "create", id: i });
  assert.strictEqual(h.size(), 3);
  assert.strictEqual(h.undo().id, 4);
  assert.strictEqual(h.undo().id, 3);
  assert.strictEqual(h.undo().id, 2);
  assert.strictEqual(h.undo(), null);
});

// --- clear / opaque / references --------------------------------------------

test("clear empties both stacks", () => {
  const h = createHistory();
  h.push({ op: "create", id: 1 });
  h.push({ op: "move", id: 2 });
  h.undo();
  h.clear();
  assert.strictEqual(h.size(), 0);
  assert.strictEqual(h.canUndo(), false);
  assert.strictEqual(h.canRedo(), false);
});

test("the core treats ops as opaque and never inspects fields", () => {
  const h = createHistory();
  const weird = { op: "x", id: 0, before: undefined, after: null, extra: [1, 2] };
  h.push(weird);
  assert.strictEqual(h.undo(), weird);
  assert.strictEqual(h.redo(), weird);
});

test("a returned entry's in-place id mutation survives redo", () => {
  const h = createHistory();
  const op = { op: "create", id: 1, after: { kind: "rect" } };
  h.push(op);

  const undone = h.undo();
  undone.id = 99; // caller re-mints the id while the entry sits on the redo stack
  const redone = h.redo();
  assert.strictEqual(redone.id, 99);
  assert.strictEqual(redone, op);
});

test("history-core is pure (no DOM, no imports)", () => {
  assert.ok(!/\bimport\b/.test(SRC), "no imports");
  assert.ok(!/document\.|window\.|fetch\(/.test(SRC), "no DOM / no window / no network");
});
