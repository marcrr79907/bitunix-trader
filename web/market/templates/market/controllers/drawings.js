// controllers/drawings.js — drawing primitives, CRUD, tools, click.
// DI factory (R14): ``create({store, bus, host, config})``. LEAF module — never
// imports main. Drawings render on a series PRIMITIVE (own canvas layer) — never
// via setData/update — so #68 single-write-path stays intact. Geometry comes
// from the pure drawing-core.js; ``drawGen`` guards a stale drawings fetch.
import * as Draw from "../drawing-core.js";

function csrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : "";
}

export function createDrawings({ store, bus, host, config }) {
  const state = store.get();
  const el = document.getElementById("chart");
  const drawToolButtons = Array.prototype.slice.call(document.querySelectorAll(".draw-tool"));
  const cancelToolButton = document.querySelector(".draw-cancel");
  const textDialog = document.getElementById("text-dialog");
  const textDialogInput = document.getElementById("text-dialog-input");
  const drawingListEl = document.getElementById("drawing-list");
  let currentDrawings = []; // rows loaded for the active (symbol, interval)
  let attached = []; // [{id, prim}] — the primitives currently on the series
  let drawGen = 0; // monotonic guard against a stale drawings fetch
  let pendingAnchor = null; // first click of a two-point drawing
  const enc = encodeURIComponent;

  // Price range so a full-width ray / rect is not clipped on pan/zoom (R6).
  function priceRangeFor(row) {
    const prices = [];
    if (typeof row.points.price === "number") prices.push(row.points.price);
    ["p1", "p2"].forEach(function (k) {
      const p = row.points[k];
      if (p && typeof p.price === "number") prices.push(p.price);
    });
    if (!prices.length) return null;
    return {
      priceRange: {
        minValue: Math.min.apply(null, prices),
        maxValue: Math.max.apply(null, prices),
      },
    };
  }

  // Pure canvas draws for one shape. ``map`` = {x(time), y(price)}; null means
  // off-bar / off-scale and the leg is skipped rather than thrown (R6).
  function renderShape(ctx, size, row, map) {
    const kind = row.kind;
    ctx.save();
    ctx.strokeStyle = ctx.fillStyle = row.style.color || "#2962ff";
    ctx.lineWidth = row.style.lineWidth || 1;
    if (kind === "hline") {
      const y = map.y(row.points.price);
      if (y !== null && y !== undefined) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(size.width, y); ctx.stroke();
      }
    } else if (kind === "trendline") {
      const t = Draw.trendlinePath(row, map);
      if (t.a && t.b) {
        ctx.beginPath(); ctx.moveTo(t.a.x, t.a.y); ctx.lineTo(t.b.x, t.b.y); ctx.stroke();
      }
    } else if (kind === "fib") {
      const f = Draw.fibPath(row, map, row.style.levels);
      ctx.font = "11px sans-serif";
      f.levels.forEach(function (l) {
        if (l.y === null || l.y === undefined) return;
        ctx.beginPath(); ctx.moveTo(f.x1, l.y); ctx.lineTo(f.x2, l.y); ctx.stroke();
        ctx.fillText(l.ratio + "  " + l.price, f.x1, l.y - 2);
      });
    } else if (kind === "rect") {
      const r = Draw.rectPath(row, map);
      if (r) {
        if (row.style.fill) {
          ctx.globalAlpha = 0.15;
          ctx.fillRect(r.left, r.top, r.width, r.height);
          ctx.globalAlpha = 1;
        }
        ctx.strokeRect(r.left, r.top, r.width, r.height);
      }
    } else if (kind === "text") {
      const tx = Draw.textPath(row, map);
      if (tx.x !== null && tx.x !== undefined && tx.y !== null && tx.y !== undefined) {
        ctx.font = (row.style.fontSize || 14) + "px sans-serif";
        ctx.fillText(tx.text, tx.x, tx.y);
      }
    }
    ctx.restore();
  }

  // One v5 ISeriesPrimitive per drawing (paneViews + autoscaleInfo + lifecycle).
  function makeDrawingPrimitive(row) {
    const c = { chart: null, series: null, requestUpdate: null };
    const map = {
      x: function (time) { return c.chart ? c.chart.timeScale().timeToCoordinate(time) : null; },
      y: function (price) { return c.series ? c.series.priceToCoordinate(price) : null; },
    };
    return {
      attached: function (p) { c.chart = p.chart; c.series = p.series; c.requestUpdate = p.requestUpdate; },
      detached: function () { c.chart = null; c.series = null; },
      paneViews: function () {
        return [{
          renderer: function () {
            return {
              draw: function (target) {
                target.useMediaCoordinateSpace(function (scope) {
                  renderShape(scope.context, scope.mediaSize, row, map);
                });
              },
            };
          },
        }];
      },
      autoscaleInfo: function () { return priceRangeFor(row); },
    };
  }

  function renderDrawingList() {
    if (!drawingListEl) return;
    drawingListEl.textContent = "";
    currentDrawings.forEach(function (row) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "drawing-del";
      btn.dataset.id = row.id;
      btn.textContent = "× " + row.kind + " #" + row.id;
      btn.addEventListener("click", function () { deleteDrawing(row.id); });
      li.appendChild(btn);
      drawingListEl.appendChild(li);
    });
  }

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
        const prim = makeDrawingPrimitive(row);
        candleSeries.attachPrimitive(prim);
        attached.push({ id: row.id, prim: prim });
      });
    }
    window.marketChart.drawings = currentDrawings.slice();
    renderDrawingList();
    bus.emit("drawings:changed", { rows: currentDrawings.slice() });
  }

  // Load the active key's drawings, then attach them to the CURRENT series
  // (called AFTER buildChart, per R7: layout -> build -> drawings -> attach).
  // A stale fetch (drawGen moved on) discards its result.
  function loadDrawings(symbol, interval) {
    const mine = ++drawGen;
    const url = config.urls.drawings + "?symbol=" + enc(symbol) + "&interval=" + enc(interval);
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
    return loadDrawings(state.symbol, state.interval);
  }

  function createDrawing(kind, points, style) {
    const body = {
      symbol: state.symbol, interval: state.interval, kind: kind, points: points, style: style,
    };
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
        const row = Draw.fromApi({ id: saved.id, kind: saved.kind, points: saved.points, style: saved.style });
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

  function syncToolButtons() {
    drawToolButtons.forEach(function (btn) {
      const on = btn.dataset.kind === state.tool;
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      btn.classList.toggle("active", on);
    });
    if (el) el.classList.toggle("drawing", !!state.tool);
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
        createDrawing("text", { time: param.time, price: price, text: "note" }, Draw.defaultStyle("text"));
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

  drawToolButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      const kind = btn.dataset.kind;
      state.tool = state.tool === kind ? null : kind;
      pendingAnchor = null;
      syncToolButtons();
    });
  });
  if (cancelToolButton) {
    cancelToolButton.addEventListener("click", function () {
      state.tool = null;
      pendingAnchor = null;
      syncToolButtons();
    });
  }
  if (textDialog) {
    textDialog.addEventListener("close", function () {
      const text = (textDialogInput.value || "").trim();
      if (textDialog.returnValue === "ok" && pendingAnchor && text) {
        createDrawing(
          "text",
          { time: pendingAnchor.time, price: pendingAnchor.price, text: text },
          Draw.defaultStyle("text"),
        );
      }
      pendingAnchor = null;
      textDialogInput.value = "";
    });
  }

  // Called by main on switchTo: clear shapes immediately (they never cross keys,
  // R7) and invalidate any in-flight fetch for the old key.
  function clearForSwitch() {
    state.tool = null;
    pendingAnchor = null;
    syncToolButtons();
    currentDrawings = [];
    drawGen++;
  }

  return { onChartClick, attachAllDrawings, refreshDrawings, clearForSwitch, syncToolButtons };
}
