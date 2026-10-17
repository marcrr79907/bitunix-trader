// controllers/undo.js — in-session undo/redo for drawing OPERATIONS (F7).
//
// DI factory (R14): ``createUndo({store,bus,host,config})`` → ``{clearForSwitch}``.
// LEAF module — never imports main. Owns the pure ``history-core`` stack and a
// ``document`` keydown router (Ctrl/Cmd+Z / Shift+Z / Y). It records ONLY at the
// persist:true gesture boundary (one entry per drag, D3) and replays through the
// EXISTING bus commands (drawing:changed/delete/restore); drawings.js keeps the
// single write path (#68) — undo never patches rows or series data locally.
import { createHistory } from "../history-core.js";

function copy(v) {
  return v === undefined ? undefined : JSON.parse(JSON.stringify(v));
}

// The ordered bus ops a recorded entry replays for a direction. PURE — the
// controller test imports it directly (op matrix, design Undo/Server
// Consistency). Returns ``[{event, payload}]``, or ``[]`` for a null/unknown
// entry. ``update`` PUTs the before/after side; ``create`` (incl. duplicate)
// undo DELETEs, redo re-POSTs; ``delete`` mirrors it.
export function replayOps(entry, dir) {
  if (!entry || !entry.op) return [];
  const undo = dir === "undo";
  if (entry.op === "update") {
    const side = undo ? entry.before : entry.after;
    if (!side) return [];
    const payload = { id: entry.id, persist: true };
    if (side.points !== undefined) payload.points = side.points;
    if (side.style !== undefined) payload.style = side.style;
    return [{ event: "drawing:changed", payload: payload }];
  }
  if (entry.op === "create" || entry.op === "duplicate") {
    if (undo) return [{ event: "drawing:delete", payload: { id: entry.id } }];
    if (!entry.after) return [];
    return [{ event: "drawing:restore", payload: { row: entry.after } }];
  }
  if (entry.op === "delete") {
    if (undo) {
      if (!entry.before) return [];
      return [{ event: "drawing:restore", payload: { row: entry.before } }];
    }
    return [{ event: "drawing:delete", payload: { id: entry.id } }];
  }
  return [];
}

export function createUndo({ store, bus, host, config }) {
  const history = createHistory({ limit: 50 });
  const committed = {}; // id -> {kind,points,style}; add/update only, never removed
  let replaying = null; // the entry a replay is emitting (re-entrancy guard)
  // F7 UI #205: a polite announcement ("Undo"/"Redo") so a keyboard/SR user gets
  // feedback — and knows the feature exists. One write per op, no coalescing.
  const status = globalThis.document ? globalThis.document.getElementById("history-status") : null;

  // The last-committed shape per id feeds the update ``before`` snapshot and a
  // deleted row's ``before`` re-POST. Published by drawings.attachAllDrawings.
  bus.on("drawings:changed", function (p) {
    if (!p || !p.rows) return;
    p.rows.forEach(function (row) {
      committed[row.id] = { kind: row.kind, points: copy(row.points), style: copy(row.style) };
    });
  });

  // Record ONLY at the gesture boundary (persist:true, D3); a flag-only change
  // (visible/locked) is out of scope (D2). ``before`` is the committed cache.
  // The cache is updated on EVERY real change (including a replay's), so an undo
  // leaves ``committed`` at the REVERTED value — a following gesture records the
  // right ``before`` (#200). Only the op push is suppressed during a replay.
  bus.on("drawing:changed", function (p) {
    if (!p || p.persist !== true) return;
    const c = committed[p.id];
    if (!c) return;
    if (!p.points && !p.style) return;
    if (replaying) {
      // A replay's own change: sync the cache to the reverted state, no op push.
      if (p.points) c.points = copy(p.points);
      if (p.style) c.style = copy(p.style);
      return;
    }
    const before = {};
    const after = {};
    if (p.points) { before.points = copy(c.points); after.points = copy(p.points); }
    if (p.style) { before.style = copy(c.style); after.style = copy(p.style); }
    history.push({ op: "update", id: p.id, before: before, after: after });
    if (p.points) c.points = copy(p.points);
    if (p.style) c.style = copy(p.style);
  });

  // A delete records the last-committed shape for the undo re-POST.
  bus.on("drawing:delete", function (p) {
    if (!p || p.id === undefined || replaying) return;
    const c = committed[p.id];
    if (!c) return;
    history.push({
      op: "delete", id: p.id,
      before: { kind: c.kind, points: copy(c.points), style: copy(c.style) },
    });
  });

  // A create (tool draw / duplicate) is known only when the POST resolves. While
  // replaying, this is the restore's completion → patch the re-minted id.
  bus.on("drawing:created", function (p) {
    if (!p) return;
    if (replaying) { replaying.id = p.id; replaying = null; return; }
    history.push({
      op: "create", id: p.id,
      after: { kind: p.kind, points: copy(p.points), style: copy(p.style) },
    });
  });

  // A restore whose POST failed (#201): clear the guard so undo is not wedged
  // for the rest of the session. ``drawings.js`` emits this from the catch.
  bus.on("drawing:create-failed", function () {
    replaying = null;
  });

  function replay(entry, dir) {
    const ops = replayOps(entry, dir);
    if (!ops.length) return;
    // A restore is async (drawing:created re-mints the id); keep the guard until
    // then. update/delete replay synchronously, so the guard clears right away.
    const waits = ops.some(function (o) { return o.event === "drawing:restore"; });
    replaying = entry;
    ops.forEach(function (o) { bus.emit(o.event, o.payload); });
    if (!waits) replaying = null;
  }

  // #209: a replay in flight owns the stack (an async restore is awaiting its
  // drawing:created to re-mint the id). A second undo/redo would mutate the
  // stack and overwrite the guard's entry → ignore the press until it settles.
  function undo() {
    if (replaying) return;
    const entry = history.undo();
    if (!entry) return;
    replay(entry, "undo");
    if (status) status.textContent = "Undo";
  }

  function redo() {
    if (replaying) return;
    const entry = history.redo();
    if (!entry) return;
    replay(entry, "redo");
    if (status) status.textContent = "Redo";
  }

  // Router (R5): Ctrl/Cmd+Z undoes; Ctrl/Cmd+Shift+Z or Ctrl/Cmd+Y redoes. A
  // focused text field keeps its native edit behaviour; Escape/Delete are owned
  // by the #chart handler and left untouched.
  function onDocKey(e) {
    if (!(e.metaKey || e.ctrlKey)) return;
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA"
        || t.tagName === "SELECT" || t.isContentEditable)) return;
    const k = (e.key || "").toLowerCase();
    if (k === "z" && !e.shiftKey) { undo(); e.preventDefault(); }
    else if ((k === "z" && e.shiftKey) || k === "y") { redo(); e.preventDefault(); }
  }

  const doc = globalThis.document;
  if (doc) doc.addEventListener("keydown", onDocKey);

  // R14: a symbol switch clears the stack AND the cache — no op keyed to a gone
  // id may replay after the switch.
  function clearForSwitch() {
    history.clear();
    Object.keys(committed).forEach(function (k) { delete committed[k]; });
  }

  return { clearForSwitch: clearForSwitch };
}
