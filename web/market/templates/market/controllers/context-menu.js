// controllers/context-menu.js — right-click menu over the chart (F7 S3).
//
// DI factory (R14): ``createContextMenu({store,bus,host,config})`` →
// ``{attach, clearForSwitch}``. LEAF module — never imports main. Binds ONE
// ``contextmenu`` listener on ``#chart`` (mirroring drawing-interaction.attach),
// hit-tests with the REUSED pure ``grabHandle(pointerRows(rows),…)`` and renders
// a JS-built ``role="menu"`` (CSP ``script-src 'self'`` — no inline handler).
// Actions reuse existing seams (#68): delete/duplicate emit bus commands,
// reset-scale routes the F8 ``scale:changed`` option-only path, add-indicator
// reuses the F5 ``add-indicator-core`` (single source). No setData/update.
import { menuModel, nextIndex, clampIndex } from "../context-menu-core.js";
import { localPoint, pointerRows } from "./drawing-interaction.js";
import { grabHandle } from "../drawing-interaction-core.js";
import { inactiveTokens } from "../add-indicator-core.js";
import { REGISTRY } from "../chart-registry-core.js";

export function createContextMenu({ store, bus, host, config }) {
  const el = document.getElementById("chart");
  let rows = []; // the latest ``drawings:changed`` rows (shared refs)
  let menu = null; // the open role="menu" node, or null
  let items = []; // the item buttons (roving focus)
  let bound = false;

  bus.on("drawings:changed", function (p) {
    rows = (p && p.rows) || [];
  });

  // Data<->pixel map for the reused core (mirrors drawing-interaction.map).
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

  function close(returnFocus) {
    if (!menu) return;
    menu.remove();
    menu = null;
    items = [];
    document.removeEventListener("pointerdown", onOutside, true);
    if (returnFocus !== false && el) el.focus();
  }

  // An outside pointerdown dismisses the menu (the menu's own clicks stay).
  function onOutside(e) {
    if (menu && e && e.target && menu.contains && menu.contains(e.target)) return;
    close(true);
  }

  // The ordered action per item id (design §c / §R4). Each reuses a shipped
  // seam — no new endpoint, no series-data write (#68).
  const ACTION = {
    delete: function (row) { bus.emit("drawing:delete", { id: row.id }); },
    duplicate: function (row) { bus.emit("drawing:duplicate", { id: row.id }); },
    "reset-scale": function () {
      store.set({ scaleMode: "linear" });
      bus.emit("scale:changed", { mode: "linear" }); // F8 option-only path
    },
    "add-indicator": function () {
      // F5 single source: REGISTRY minus the active membership.
      const token = inactiveTokens(REGISTRY, store.get().indicators)[0];
      if (!token) return;
      store.set({ indicators: (store.get().indicators || []).concat([token]) });
      bus.emit("indicator:changed"); // membership change = rebuild (setData path, #68)
    },
  };

  function activate(item, row) {
    const fn = ACTION[item.id];
    if (fn) fn(row);
    close(true);
  }

  function moveFocus(delta) {
    if (!items.length) return;
    const i = items.indexOf(document.activeElement);
    const next = nextIndex(items.length, i === -1 ? 0 : i, delta);
    items.forEach(function (b, j) { b.setAttribute("tabindex", j === next ? "0" : "-1"); });
    items[next].focus();
  }

  function jumpFocus(which) {
    if (!items.length) return;
    const next = which === "End" ? clampIndex(items.length, items.length) : 0;
    items.forEach(function (b, j) { b.setAttribute("tabindex", j === next ? "0" : "-1"); });
    items[next].focus();
  }

  function onMenuKey(e) {
    if (e.key === "ArrowDown") { e.preventDefault(); moveFocus(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); moveFocus(-1); }
    else if (e.key === "Home" || e.key === "End") { e.preventDefault(); jumpFocus(e.key); }
    else if (e.key === "Escape") { e.preventDefault(); close(true); }
  }

  function open(model, row, clientX, clientY) {
    close(false); // replace any open menu without stealing focus
    menu = document.createElement("div");
    menu.className = "chart-context-menu";
    menu.setAttribute("role", "menu");
    menu.setAttribute("aria-label", "Chart actions");
    menu.addEventListener("keydown", onMenuKey);
    items = [];
    model.forEach(function (item, i) {
      const b = document.createElement("button");
      b.type = "button";
      b.setAttribute("role", "menuitem");
      b.setAttribute("tabindex", i === 0 ? "0" : "-1");
      b.setAttribute("aria-keyshortcuts", item.keyshortcut || "");
      b.textContent = item.label;
      b.addEventListener("click", function () { activate(item, row); });
      items.push(b);
      menu.appendChild(b);
    });
    document.body.appendChild(menu);
    place(menu, clientX, clientY);
    // Roving focus: the first item is focused on open (native activation keys).
    if (items[0]) items[0].focus();
    document.addEventListener("pointerdown", onOutside, true);
  }

  // Fixed at the cursor, clamped so a right/bottom overflow stays on-screen.
  function place(node, x, y) {
    node.style.position = "fixed";
    node.style.left = x + "px";
    node.style.top = y + "px";
    const rect = node.getBoundingClientRect ? node.getBoundingClientRect() : null;
    const vw = globalThis.innerWidth;
    const vh = globalThis.innerHeight;
    if (rect && vw && rect.right > vw) node.style.left = Math.max(0, x - rect.width) + "px";
    if (rect && vh && rect.bottom > vh) node.style.top = Math.max(0, y - rect.height) + "px";
  }

  function onContextMenu(e) {
    if (!el) return;
    e.preventDefault(); // a JS-built menu replaces the native one (CSP-clean)
    const p = localPoint(el.getBoundingClientRect(), e.clientX, e.clientY);
    const hit = grabHandle(pointerRows(rows), p.x, p.y, map());
    const row = hit ? rows.find(function (r) { return r.id === hit.id; }) || null : null;
    bus.emit("drawing:selected", { id: hit ? hit.id : null });
    open(menuModel({ hit: hit, row: row, scaleMode: store.get().scaleMode }),
      row, e.clientX, e.clientY);
  }

  // The ``#chart`` container survives a rebuild; bind ONCE. main calls attach()
  // after every buildChart (mirror drawing-interaction.attach).
  function attach() {
    if (bound) return;
    if (el) el.addEventListener("contextmenu", onContextMenu);
    bound = true;
  }

  // Symbol switch: close any open menu (R14 — a gone id must not be acted on).
  function clearForSwitch() {
    close(false);
  }

  return { attach: attach, clearForSwitch: clearForSwitch };
}
