// controllers/drawings.js — drawing primitives, CRUD, tools, click.
// DI factory (R14): ``create({store, bus, host, config})``. LEAF module — never
// imports main. Drawings render on a series PRIMITIVE (own canvas layer) — never
// via setData/update — so #68 single-write-path stays intact. Geometry comes
// from the pure drawing-core.js; ``drawGen`` guards a stale drawings fetch.
import * as Draw from "../drawing-core.js";
import { makeDrawingPrimitive } from "../drawing-primitive.js";
import { defaultPositionStyle } from "../position-core.js";
import { createFlow } from "../drawing-click-flow-core.js";

function csrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : "";
}
// D5: new text drawings adopt --chart-text (persisted rows keep their color).
const textStyle = () => { const b = Draw.defaultStyle("text"); try { return { ...b, color: getComputedStyle(document.documentElement).getPropertyValue("--chart-text").trim() || b.color }; } catch { return b; } };

export function createDrawings({ store, bus, host, config }) {
  const state = store.get();
  const textDialog = document.getElementById("text-dialog");
  const textDialogInput = document.getElementById("text-dialog-input");
  let currentDrawings = []; // rows loaded for the active SYMBOL
  let attached = []; // [{id, prim}] — the primitives currently on the series
  let drawGen = 0; // monotonic guard against a stale drawings fetch
  // F9 (D6): ONE 1/2/3-click machine lives in the pure click-flow core; this
  // controller only owns the dialog and the POST. ``flowTool`` tracks the tool
  // the draft belongs to so a switch drops it (the core also resets on a miss).
  const flow = createFlow();
  let flowTool = state.tool;
  let pendingDialog = null; // {kind, points} awaiting the #text-dialog
  let selectedId = null; // interaction selection (closure only; never a store key)
  const selection = { isSelected: function (row) { return row.id === selectedId; } };
  const enc = encodeURIComponent;

  // Re-attach every loaded drawing to the CURRENT candleSeries (after a rebuild
  // and a load); before the first buildChart it only publishes the seam + list.
  function attachAllDrawings() {
    const candleSeries = host.getCandleSeries();
    attached.forEach(function (p) { if (candleSeries) candleSeries.detachPrimitive(p.prim); });
    attached = [];
    if (candleSeries) {
      currentDrawings.forEach(function (row) {
        const prim = makeDrawingPrimitive(row, selection);
        candleSeries.attachPrimitive(prim);
        attached.push({ id: row.id, prim: prim });
      });
    }
    window.marketChart.drawings = currentDrawings.slice();
    bus.emit("drawings:changed", { rows: currentDrawings.slice() });
  }

  // Load the active SYMBOL's drawings, then attach them to the CURRENT series
  // (called AFTER buildChart, per R7: layout -> build -> drawings -> attach).
  // Per SYMBOL (R1): an interval-only switch does NOT reload. A stale fetch
  // (drawGen moved on) discards its result.
  async function loadDrawings(symbol) {
    const mine = ++drawGen;
    let rows = [];
    try {
      const r = await fetch(config.urls.drawings + "?symbol=" + enc(symbol));
      if (!r.ok) throw new Error("drawings " + r.status);
      rows = ((await r.json()).drawings || []).map(Draw.fromApi).filter(Boolean);
    } catch (e) {
      rows = []; // a failed fetch is non-fatal: render with no drawings (R7)
    }
    if (mine !== drawGen) return; // a stale fetch discards its result
    currentDrawings = rows;
    attachAllDrawings();
  }

  function refreshDrawings() {
    return loadDrawings(state.symbol);
  }

  // The primitive currently attached for ``id`` (undefined before a build).
  function primFor(id) {
    const hit = attached.find(function (a) { return a.id === id; });
    return hit && hit.prim;
  }

  // Selection highlight (R9): mark + redraw via the primitive requestUpdate only.
  bus.on("drawing:selected", function (p) {
    selectedId = p ? p.id : null;
    attached.forEach(function (a) { if (a.prim.requestUpdate) a.prim.requestUpdate(); });
  });

  // Live drag / style edit (R10/R12): replace the row in place, redraw via
  // requestUpdate (#68), refresh the seam. ``persist`` → one PUT (D7), sending
  // ONLY the field(s) this gesture changed (partial body, R2).
  bus.on("drawing:changed", function (p) {
    if (!p) return;
    const row = currentDrawings.find(function (d) { return d.id === p.id; });
    if (!row) return;
    if (p.points) row.points = p.points;
    if (p.style) row.style = p.style;
    // F5 S3 (R2/R9): the tree toggles visible/locked; the primitive re-renders
    // live each frame (visible===false -> blank), so a requestUpdate reveals or
    // parks without a re-attach (#68).
    if (p.visible !== undefined) row.visible = p.visible;
    if (p.locked !== undefined) row.locked = p.locked;
    const prim = primFor(p.id);
    if (prim && prim.requestUpdate) prim.requestUpdate();
    window.marketChart.drawings = currentDrawings.slice();
    // The tree re-renders from this event (rows carry the flags).
    if (!p.persist) return;
    const body = {};
    if (p.points) body.points = row.points;
    if (p.style) body.style = row.style;
    if (p.visible !== undefined) body.visible = row.visible;
    if (p.locked !== undefined) body.locked = row.locked;
    persistDrawing(row.id, body);
    // NO re-publish on a flag change: the tree row already synced its own icon,
    // and a rebuild would drop keyboard focus mid-interaction (R6).
  });

  // Keyboard delete (R11): same path as the panel list button.
  bus.on("drawing:delete", function (p) {
    if (p && p.id !== undefined) deleteDrawing(p.id);
  });

  // F7 (D6): duplicate/restore reuse the ONE create path (#68) — never a new
  // endpoint. Duplicate clones kind/points/style verbatim (Q4: no offset); undo
  // of a delete re-POSTs the committed ``before`` row (minting a NEW id).
  function clone(v) { return v === undefined ? undefined : JSON.parse(JSON.stringify(v)); }
  function recreate(row) {
    if (row && row.kind) createDrawing(row.kind, clone(row.points), clone(row.style));
  }
  bus.on("drawing:duplicate", function (p) {
    recreate(p && currentDrawings.find(function (d) { return d.id === p.id; }));
  });
  bus.on("drawing:restore", function (p) { recreate(p && p.row); });

  // One write per gesture (D7/R2): PUT only the changed field(s); failures are silent.
  function persistDrawing(id, body) {
    fetch(config.urls.drawings + "/" + id, {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify(body),
    }).catch(function () { /* non-fatal */ });
  }

  async function createDrawing(kind, points, style) {
    const body = { symbol: state.symbol, kind: kind, points: points, style: style };
    try {
      const r = await fetch(config.urls.drawings, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error("drawings " + r.status);
      const row = Draw.fromApi(await r.json());
      if (!row) return;
      currentDrawings.push(row);
      attachAllDrawings();
      // F7: the create signal (undo records / repatches the re-minted id),
      // emitted AFTER attach so a listener reading the seam sees the row.
      bus.emit("drawing:created", { id: row.id, kind: row.kind, points: row.points, style: row.style });
    } catch (e) {
      bus.emit("drawing:create-failed", {});
    }
  }

  async function deleteDrawing(id) {
    try {
      await fetch(config.urls.drawings + "/" + id, {
        method: "DELETE",
        headers: { "X-CSRFToken": csrfToken() },
      });
      currentDrawings = currentDrawings.filter(function (d) { return d.id !== id; });
      attachAllDrawings();
    } catch (e) { /* keep the row on a failed delete */ }
  }

  // A chart click in tool mode -> the pure flow decides pending / ready /
  // dialog; a ready shape is POSTed once via the ONE create path (#68).
  function onChartClick(param) {
    const candleSeries = host.getCandleSeries();
    if (!state.tool || !param || !param.point || !candleSeries) return;
    if (state.tool === "measure") return; // ephemeral: measure owns its own listeners
    const price = candleSeries.coordinateToPrice(param.point.y);
    if (price === null || price === undefined) return;
    const out = flow.collect(state.tool, { time: param.time, price: price });
    if (!out) return;
    if (out.status === "dialog") { openTextDialog(out); return; }
    if (out.status === "ready") createDrawing(out.kind, out.points, styleFor(out.kind, out.points));
  }

  // Per-kind style seed: position derives its direction colour, text reads the
  // --chart-text token, everything else uses the core default.
  function styleFor(kind, points) {
    if (kind === "position") return defaultPositionStyle(points);
    return kind === "text" ? textStyle() : Draw.defaultStyle(kind);
  }

  // text/callout need the typed label: remember the shape and let the dialog's
  // close handler merge the text and POST (a missing dialog degrades to "note").
  function openTextDialog(out) {
    if (textDialog) {
      pendingDialog = out;
      textDialogInput.value = "";
      textDialog.showModal();
      return;
    }
    const p = Object.assign({}, out.points, { text: "note" });
    createDrawing(out.kind, p, styleFor(out.kind, p));
  }

  // F6 (D5/R15): position-seed copies a setup's levels VERBATIM and hands the
  // shaped points here — the client never recomputes SMC levels, only persists.
  function seedPosition(points) {
    if (!points) return;
    createDrawing("position", points, defaultPositionStyle(points));
  }

  // Tool selection now lives in controllers/draw-toolbar.js (F5 S2): it writes
  // ``store.tool`` (the SAME command the legacy buttons emitted). A tool change
  // drops a half-collected draft (the flow keys its draft by kind).
  store.subscribe(function () {
    if (state.tool === flowTool) return;
    flowTool = state.tool;
    flow.cancel(); // a tool switch drops the half-collected draft
  });

  // Escape (design-system R6): cancel a half-collected draft (the measure
  // cancels itself in measure.js). Bound once on the #chart container, which
  // survives a rebuild.
  const chartEl = document.getElementById("chart");
  if (chartEl) {
    chartEl.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && flow.active()) {
        flow.cancel();
        e.preventDefault();
      }
    });
  }

  if (textDialog) {
    textDialog.addEventListener("close", function () {
      const text = (textDialogInput.value || "").trim();
      const pending = pendingDialog;
      pendingDialog = null;
      textDialogInput.value = "";
      if (textDialog.returnValue !== "ok" || !pending || !text) return;
      const points = Object.assign({}, pending.points, { text: text });
      createDrawing(pending.kind, points, styleFor(pending.kind, pending.points));
    });
  }

  // Called by main on switchTo when the SYMBOL changed: clear shapes
  // immediately (they never cross symbols, R7) and invalidate any in-flight
  // fetch for the old symbol.
  function clearForSwitch() {
    // store.set (not a raw write) so the toolbar's subscriber clears aria-pressed.
    store.set({ tool: null });
    flowTool = state.tool;
    flow.reset();
    pendingDialog = null;
    selectedId = null; // R14: selection clears with the drawings
    currentDrawings = [];
    drawGen++;
  }

  return { onChartClick, attachAllDrawings, refreshDrawings, clearForSwitch, seedPosition };
}
