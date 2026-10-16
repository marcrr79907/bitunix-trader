// controllers/drawings.js — drawing primitives, CRUD, tools, click.
// DI factory (R14): ``create({store, bus, host, config})``. LEAF module — never
// imports main. Drawings render on a series PRIMITIVE (own canvas layer) — never
// via setData/update — so #68 single-write-path stays intact. Geometry comes
// from the pure drawing-core.js; ``drawGen`` guards a stale drawings fetch.
import * as Draw from "../drawing-core.js";
import { makeDrawingPrimitive } from "../drawing-primitive.js";

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
  let pendingAnchor = null; // first click of a two-point drawing
  let pendingAnchorKind = state.tool; // tool the anchor was collected under
  let selectedId = null; // interaction selection (closure only; never a store key)
  const selection = { isSelected: function (row) { return row.id === selectedId; } };
  const enc = encodeURIComponent;

  // Re-attach every loaded drawing to the CURRENT candleSeries (after a rebuild
  // and after a load). Always rebuilds the primitive list (R7). Before the first
  // buildChart (candleSeries === null) it only publishes the seam + list.
  function attachAllDrawings() {
    const candleSeries = host.getCandleSeries();
    attached.forEach(function (p) {
      if (candleSeries) candleSeries.detachPrimitive(p.prim);
    });
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
  function loadDrawings(symbol) {
    const mine = ++drawGen;
    const url = config.urls.drawings + "?symbol=" + enc(symbol);
    return fetch(url)
      .then(function (r) {
        if (!r.ok) throw new Error("drawings " + r.status);
        return r.json();
      })
      .then(function (body) {
        if (mine !== drawGen) return;
        currentDrawings = (body.drawings || []).map(Draw.fromApi).filter(Boolean);
        attachAllDrawings();
      })
      .catch(function () {
        // A failed fetch is non-fatal: the chart renders with no drawings (R7).
        if (mine !== drawGen) return;
        currentDrawings = [];
        attachAllDrawings();
      });
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
    // NO re-publish on a flag change: the tree row that emitted it already synced
    // its own icon, and a rebuild would drop keyboard focus mid-interaction (R6).
  });

  // Keyboard delete (R11): same path as the panel list button.
  bus.on("drawing:delete", function (p) {
    if (p && p.id !== undefined) deleteDrawing(p.id);
  });

  // One write per gesture (D7/R2): PUT only the changed field(s). A failed save
  // is silent — the in-session shape is unaffected.
  function persistDrawing(id, body) {
    fetch(config.urls.drawings + "/" + id, {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify(body),
    }).catch(function () { /* non-fatal */ });
  }

  function createDrawing(kind, points, style) {
    const body = { symbol: state.symbol, kind: kind, points: points, style: style };
    fetch(config.urls.drawings, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify(body),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("drawings " + r.status);
        return r.json();
      })
      .then(function (saved) {
        const row = Draw.fromApi({
          id: saved.id, kind: saved.kind, points: saved.points, style: saved.style,
          visible: saved.visible, locked: saved.locked,
        });
        if (!row) return;
        currentDrawings.push(row);
        attachAllDrawings();
      })
      .catch(function () { /* in-session create failed; nothing to do */ });
  }

  function deleteDrawing(id) {
    fetch(config.urls.drawings + "/" + id, {
      method: "DELETE",
      headers: { "X-CSRFToken": csrfToken() },
    })
      .then(function () {
        currentDrawings = currentDrawings.filter(function (d) { return d.id !== id; });
        attachAllDrawings();
      })
      .catch(function () { /* keep the row on a failed delete */ });
  }

  // A chart click in tool mode -> create a shape. hline needs only a price;
  // two-point kinds collect an anchor then a second click; text opens a dialog.
  function onChartClick(param) {
    const candleSeries = host.getCandleSeries();
    if (!state.tool || !param || !param.point || !candleSeries) return;
    const price = candleSeries.coordinateToPrice(param.point.y);
    if (price === null || price === undefined) return;
    const kind = state.tool;
    if (kind === "hline") {
      createDrawing("hline", { price: price }, Draw.defaultStyle("hline"));
      return;
    }
    if (param.time === undefined || param.time === null) return; // off-bar anchor
    if (kind === "text") {
      pendingAnchor = { time: param.time, price: price };
      if (textDialog) {
        textDialogInput.value = "";
        textDialog.showModal();
      } else {
        createDrawing("text", { time: param.time, price: price, text: "note" }, textStyle());
        pendingAnchor = null;
      }
      return;
    }
    // trendline | fib | rect: first click sets the anchor, second finalizes.
    if (pendingAnchor === null) {
      pendingAnchor = { time: param.time, price: price };
      return;
    }
    createDrawing(kind, { p1: pendingAnchor, p2: { time: param.time, price: price } }, Draw.defaultStyle(kind));
    pendingAnchor = null;
  }

  // Tool selection now lives in controllers/draw-toolbar.js (F5 S2): it writes
  // ``store.tool`` (the SAME command the legacy buttons emitted). A tool change
  // only needs to drop a half-collected two-point anchor.
  store.subscribe(function () {
    if (state.tool !== pendingAnchorKind) {
      pendingAnchorKind = state.tool;
      pendingAnchor = null;
    }
  });

  if (textDialog) {
    textDialog.addEventListener("close", function () {
      const text = (textDialogInput.value || "").trim();
      if (textDialog.returnValue === "ok" && pendingAnchor && text) {
        createDrawing(
          "text",
          { time: pendingAnchor.time, price: pendingAnchor.price, text: text },
          textStyle(),
        );
      }
      pendingAnchor = null;
      textDialogInput.value = "";
    });
  }

  // Called by main on switchTo when the SYMBOL changed: clear shapes
  // immediately (they never cross symbols, R7) and invalidate any in-flight
  // fetch for the old symbol.
  function clearForSwitch() {
    // store.set (not a raw write) so the toolbar's subscriber clears aria-pressed.
    store.set({ tool: null });
    pendingAnchor = null;
    selectedId = null; // R14: a symbol switch clears selection with the drawings
    currentDrawings = [];
    drawGen++;
  }

  return { onChartClick, attachAllDrawings, refreshDrawings, clearForSwitch };
}
