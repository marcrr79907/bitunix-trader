// controllers/drawing-interaction.js — pointer/keyboard gesture + selection.
//
// DI factory (R14): ``create({store, bus, host, config})`` → ``{attach,
// clearForSwitch}``. LEAF module — never imports main. Owns the ``#chart``
// pointer (down/move/up/cancel), the keydown (Delete/Backspace/Escape) and the
// double-click properties dialog. Selection state lives in this closure (NO
// store key, #68) and is published on the bus (``drawing:selected`` /
// ``drawing:changed``); drawing.js owns the rows, the primitive re-render and
// the persistence (one PUT per gesture). Geometry comes from the pure
// drawing-interaction-core.js; the brush never writes series data (#68).
import { grabHandle, applyDrag } from "../drawing-interaction-core.js";
import { riskReward } from "../position-core.js";
import { createCoalescer } from "../readout-coalesce-core.js";

// Container-relative pixel for a client coordinate (the ``#chart`` rect is the
// reference frame; a missing rect degrades to identity, never NaN).
export function localPoint(rect, clientX, clientY) {
  const left = (rect && rect.left) || 0;
  const top = (rect && rect.top) || 0;
  return { x: clientX - left, y: clientY - top };
}

// F5 (R9): rows the pointer may grab/open. A locked OR hidden drawing is NOT
// pointer-selectable/draggable, but stays selectable from the tree (a bus emit,
// not a pointer hit). Absent flags mean visible/unlocked. Pure (no closure) so
// both branches are unit-testable.
export function pointerRows(rows) {
  return (rows || []).filter(function (r) {
    return r.locked !== true && r.visible !== false;
  });
}

// Merge the dialog's edited color/lineWidth over a drawing's base style. Only
// valid edits apply (color non-empty, lineWidth integer >= 1); the base is
// never mutated. A null base yields only the valid edited keys.
export function mergeStyle(base, edited) {
  const out = Object.assign({}, base || {});
  const e = edited || {};
  if (typeof e.color === "string" && e.color) out.color = e.color;
  if (e.lineWidth !== undefined && e.lineWidth !== "") {
    const w = parseInt(e.lineWidth, 10);
    if (!isNaN(w) && w >= 1) out.lineWidth = w;
  }
  return out;
}

export function createDrawingInteraction({ store, bus, host, config }) {
  const state = store.get();
  const el = document.getElementById("chart");
  const dialog = document.getElementById("drawing-settings-dialog");
  const colorInput = document.getElementById("ds-color");
  const widthInput = document.getElementById("ds-width");
  const positionReadout = document.getElementById("position-readout");
  let rows = []; // the latest ``drawings:changed`` rows (shared refs with drawings.js)
  let selectedId = null;
  let readoutId = null; // the id the R:R readout currently announces (bus-driven)
  // F6 UI #192: coalesce drag-frame readout writes to one per animation frame.
  const readoutCoalescer = createCoalescer(function (p) {
    writePositionReadout(p ? p.id : null, p ? p.points : null);
  });
  let drag = null; // {id, target, lastX, lastY, moved}
  let dialogId = null;
  let bound = false;

  // Rows arrive from the drawings controller (single source of truth). A stale
  // selected id MUST NEVER linger after its row is gone (R14).
  bus.on("drawings:changed", function (p) {
    rows = (p && p.rows) || [];
    if (selectedId !== null && !rowById(selectedId)) selectedId = null;
    writePositionReadout(readoutId, null);
  });

  function rowById(id) {
    return rows.find(function (r) { return r.id === id; }) || null;
  }

  // F6 (design-system R6): the selected position's R:R lives in an ``aria-live``
  // DOM node (the canvas text stays as visual reinforcement). ``id`` is the
  // announced selection; a non-position or absent selection clears the node.
  // R:R comes from the pure position-core (single source); a degenerate rr
  // (null) clears it. ``pointsOverride`` lets a live drag refresh immediately.
  function writePositionReadout(id, pointsOverride) {
    readoutId = id === undefined ? null : id;
    if (!positionReadout) return;
    const row = readoutId === null ? null : rowById(readoutId);
    if (!row || row.kind !== "position") {
      positionReadout.textContent = "";
      return;
    }
    const p = pointsOverride || row.points || {};
    const rr = riskReward(p.entry && p.entry.price, p.stop, p.take_profit).rr;
    positionReadout.textContent = rr === null ? "" : "R:R " + rr.toFixed(2);
  }

  // F6 UI #192: a drag frame at 60fps must not churn the polite region. Coalesce
  // a live drag refresh to one write per animation frame; a selection / drag-end
  // write goes through immediately (the announcement is never dropped).
  function schedulePositionReadout(id, pointsOverride) {
    readoutId = id;
    readoutCoalescer.schedule({ id: id, points: pointsOverride });
  }

  function flushPositionReadout(id, pointsOverride) {
    readoutId = id;
    readoutCoalescer.flush({ id: id, points: pointsOverride });
  }

  // Any selection source (pointer, tree, keyboard) announces on the bus, so the
  // readout follows the ONE announcement rather than a second selection copy.
  // Mirror the announcement into ``selectedId`` so a tree-select keeps the
  // pointer hit-test in sync (a later canvas miss must clear it, not early-return).
  bus.on("drawing:selected", function (p) {
    selectedId = p ? p.id : null;
    writePositionReadout(p ? p.id : null, null);
  });

  // A live row change (drag/style) refreshes the R:R when it touches the
  // announced position; drawings.js already applied the new points to the row.
  // F6 UI #192: a live drag frame (persist !== true) coalesces per frame; the
  // drag-end write (persist === true) flushes immediately.
  bus.on("drawing:changed", function (p) {
    if (!p || p.id !== readoutId) return;
    const points = p.points;
    if (p.persist === true) flushPositionReadout(readoutId, points);
    else schedulePositionReadout(readoutId, points);
  });

  // Data<->pixel map for the core. All four functions may return null with no
  // chart/series or off-bar; the core keeps the old component on a null inverse.
  function map() {
    const chart = host.getChart();
    const series = host.getCandleSeries();
    return {
      x: function (t) { return chart ? chart.timeScale().timeToCoordinate(t) : null; },
      y: function (p) { return series ? series.priceToCoordinate(p) : null; },
      time: function (px) { return chart ? chart.timeScale().coordinateToTime(px) : null; },
      price: function (py) { return series ? series.coordinateToPrice(py) : null; },
    };
  }

  function setSelection(id) {
    if (selectedId === id) return;
    selectedId = id;
    // The ``drawing:selected`` emit drives the R:R readout (one announcement).
    bus.emit("drawing:selected", { id: id });
  }

  function pointFromEvent(e) {
    return localPoint(el.getBoundingClientRect(), e.clientX, e.clientY);
  }

  // --- pointer gesture --------------------------------------------------------

  function onPointerDown(e) {
    if (!el || state.tool) return; // a drawing tool owns the click in tool mode
    if (e.button !== undefined && e.button !== 0) return;
    const p = pointFromEvent(e);
    const hit = grabHandle(pointerRows(rows), p.x, p.y, map());
    if (!hit) {
      setSelection(null); // R9: a miss clears any current selection
      return;
    }
    setSelection(hit.id);
    drag = { id: hit.id, target: hit.target, lastX: p.x, lastY: p.y, moved: false };
    // D4: capture keeps the gesture when the pointer leaves #chart.
    try { el.setPointerCapture(e.pointerId); } catch (err) { /* unsupported */ }
    e.preventDefault();
    e.stopPropagation(); // keep the chart from panning under our drag
  }

  function onPointerMove(e) {
    if (!drag) return;
    const p = pointFromEvent(e);
    const dx = p.x - drag.lastX;
    const dy = p.y - drag.lastY;
    if (dx === 0 && dy === 0) return;
    drag.lastX = p.x;
    drag.lastY = p.y;
    drag.moved = true;
    const row = rowById(drag.id);
    if (!row) return;
    const points = applyDrag(row, drag.target, dx, dy, map());
    // F6 (R6): refresh the R:R readout live for a dragged position.
    if (drag.id === readoutId) writePositionReadout(readoutId, points);
    // D6: live render via the primitive requestUpdate in drawings.js, no PUT.
    bus.emit("drawing:changed", { id: drag.id, points: points, persist: false });
  }

  function endDrag(e) {
    if (!drag) return;
    const d = drag;
    drag = null;
    try {
      if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
    } catch (err) { /* unsupported */ }
    if (d.moved) {
      // D7: a single PUT after the gesture. Rows are shared refs (drawings.js
      // already applied each move), so the row holds the final points.
      const row = rowById(d.id);
      if (row) bus.emit("drawing:changed", { id: d.id, points: row.points, persist: true });
    }
    e.preventDefault();
    e.stopPropagation();
  }

  function onPointerCancel() {
    drag = null;
  }

  // --- keyboard (R11) ---------------------------------------------------------

  function onKeyDown(e) {
    if (e.key === "Escape") {
      drag = null;
      if (selectedId !== null) {
        setSelection(null);
        e.preventDefault();
      }
      return;
    }
    if (e.key === "Delete" || e.key === "Backspace") {
      if (selectedId !== null) {
        const id = selectedId;
        setSelection(null);
        // Same delete path as the panel list (drawings.js owns the DELETE).
        bus.emit("drawing:delete", { id: id });
      }
      e.preventDefault(); // R11: Backspace must not trigger browser back
    }
  }

  // --- properties dialog (R12) ------------------------------------------------

  function onDblClick(e) {
    if (!el || state.tool) return;
    const p = pointFromEvent(e);
    const hit = grabHandle(pointerRows(rows), p.x, p.y, map());
    if (!hit) return; // R13: double-click with nothing under it is a no-op
    const row = rowById(hit.id);
    if (!row || !dialog) return;
    dialogId = hit.id;
    const style = row.style || {};
    if (colorInput) colorInput.value = style.color || "#2962ff";
    if (widthInput) widthInput.value = style.lineWidth || 1;
    dialog.showModal();
  }

  if (dialog) {
    dialog.addEventListener("close", function () {
      const id = dialogId;
      dialogId = null;
      if (dialog.returnValue === "ok" && id !== null) {
        const row = rowById(id);
        const style = mergeStyle(row && row.style, {
          color: colorInput && colorInput.value,
          lineWidth: widthInput && widthInput.value,
        });
        // Only style changes (R13): kind/points untouched; drawings.js PUTs it.
        bus.emit("drawing:changed", { id: id, style: style, persist: true });
      }
      dialog.returnValue = "";
    });
  }

  // --- lifecycle --------------------------------------------------------------

  // The ``#chart`` container persists across builds (only the canvases are
  // recreated), so listeners bind ONCE. main calls attach() after every build.
  function attach() {
    if (!el) return;
    if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "0");
    if (bound) return;
    el.addEventListener("pointerdown", onPointerDown, true);
    el.addEventListener("pointermove", onPointerMove, true);
    el.addEventListener("pointerup", endDrag, true);
    el.addEventListener("pointercancel", onPointerCancel, true);
    el.addEventListener("keydown", onKeyDown);
    el.addEventListener("dblclick", onDblClick);
    bound = true;
  }

  // Symbol switch: clear selection with the drawings (R14). An interval-only
  // switch never calls this, so the selection survives.
  function clearForSwitch() {
    drag = null;
    setSelection(null);
  }

  return { attach, clearForSwitch };
}
