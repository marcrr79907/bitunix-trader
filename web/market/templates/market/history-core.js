// history-core.js — pure bounded undo/redo stack for drawing operations.
//
// Framework-free (no DOM, no chart library, no network, no global state, no
// imports at all), mirroring drawing-core.js / position-core.js and the
// project's "pure core at the center, adapters at the edges" rule. A native ESM
// module: imported in Node by the tests and in the browser by the undo
// controller (F7, issue #120).
//
// The stack is OPAQUE: an entry is {op, id, before, after} but the core NEVER
// reads those fields — it only moves REFERENCES between the undo and redo
// stacks. A caller may therefore mutate a returned entry in place (e.g. patch a
// server re-minted id after an async restore) with no core `patch()` API.
//
// Bound: a LIFO capped at `limit` (default 50); over the cap the oldest entry is
// dropped. `push` clears the redo stack (the standard "new edit discards redo"
// rule). Undo/redo return the moved entry, or null when the source is empty.

var DEFAULT_LIMIT = 50;

function createHistory(options) {
  var limit =
    options && typeof options.limit === "number" && options.limit > 0
      ? options.limit
      : DEFAULT_LIMIT;
  var undoStack = [];
  var redoStack = [];

  return {
    // Record a new operation; a new edit invalidates any pending redo.
    push: function (op) {
      undoStack.push(op);
      redoStack.length = 0;
      while (undoStack.length > limit) undoStack.shift();
    },
    // Move the top of the undo stack to the redo stack; null when empty.
    undo: function () {
      if (undoStack.length === 0) return null;
      var entry = undoStack.pop();
      redoStack.push(entry);
      return entry;
    },
    // Move the top of the redo stack back to the undo stack; null when empty.
    redo: function () {
      if (redoStack.length === 0) return null;
      var entry = redoStack.pop();
      undoStack.push(entry);
      return entry;
    },
    canUndo: function () {
      return undoStack.length > 0;
    },
    canRedo: function () {
      return redoStack.length > 0;
    },
    clear: function () {
      undoStack.length = 0;
      redoStack.length = 0;
    },
    size: function () {
      return undoStack.length;
    },
  };
}

export { createHistory };
