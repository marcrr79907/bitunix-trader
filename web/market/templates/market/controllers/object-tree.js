// controllers/object-tree.js — unified Object Tree (F5 S3, R1-R5).
//
// DI factory (R14): ``createObjectTree({store, bus, config, onIndicatorSettings})``.
// LEAF module — never imports main. Renders ``role="tree"`` with grouped parent
// treeitems (Drawings, Indicators) wrapping ``role="group"`` lists. Drawings come
// from the ``drawings:changed`` payload; indicators are ACTIVE-ONLY (store
// membership), never the full registry (R1/D8). Per-row native buttons: eye
// (visibility), lock (drawings only), delete, settings (indicators), plus row
// select. Drawing actions REUSE existing bus events (D7); the indicator eye is
// the ONE new event ``indicator:visibility`` -> option-only host setter (#68).
import { TREE_GROUPS } from "../tool-icons-core.js";

const DRAWINGS = TREE_GROUPS[0].label; // "Drawings"
const INDICATORS = TREE_GROUPS[1].label; // "Indicators"

// Local CSP-clean control glyphs (inline SVG strings, NO event attribute, R5).
// Not color-only (R6/R9): the eye swaps filled/outline and the lock swaps
// closed/open alongside the aria-pressed state.
const SVG = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" '
  + 'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
  + 'stroke-linejoin="round" aria-hidden="true">';
const EYE_ON = `${SVG}<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12Z"/>`
  + '<circle cx="12" cy="12" r="3"/></svg>';
const EYE_OFF = `${SVG}<path d="M3 3l18 18"/>`
  + '<path d="M10.6 5.1A10.9 10.9 0 0 1 12 5c7 0 11 7 11 7a18 18 0 0 1-3.2 4.2"/>'
  + '<path d="M6.1 6.1A18 18 0 0 0 1 12s4 7 11 7a10.9 10.9 0 0 0 4.4-.9"/></svg>';
const LOCK_ON = `${SVG}<rect x="5" y="11" width="14" height="9" rx="1"/>`
  + '<path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';
const LOCK_OFF = `${SVG}<rect x="5" y="11" width="14" height="9" rx="1"/>`
  + '<path d="M8 11V8a4 4 0 0 1 7-2.6"/></svg>';
const TRASH = `${SVG}<path d="M4 7h16"/><path d="M9 7V5h6v2"/>`
  + '<path d="M6 7l1 13h10l1-13"/></svg>';
const GEAR = `${SVG}<circle cx="12" cy="12" r="3"/>`
  + '<path d="M12 2v3M12 19v3M2 12h3M19 12h3'
  + 'M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1"/></svg>';

export function createObjectTree({ store, bus, onIndicatorSettings }) {
  const mount = document.getElementById("object-tree");
  const state = store.get();
  if (!mount) return {};

  let drawingRows = []; // latest drawings:changed rows (shared refs)
  let selectedDrawingId = null;
  const expanded = { [DRAWINGS]: true, [INDICATORS]: true };

  mount.textContent = "";
  const tree = document.createElement("ul");
  tree.className = "object-tree";
  tree.setAttribute("role", "tree");
  tree.setAttribute("aria-label", "Chart objects");
  mount.appendChild(tree);

  // --- small DOM helpers ------------------------------------------------------

  function el(tag, cls, attrs) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    return node;
  }

  // A native per-row action button. ``icon`` is a CSP-clean SVG string (no
  // event attribute); the accessible name rides aria-label.
  function action(cls, label, icon, onClick) {
    const b = el("button", cls, {
      type: "button", "aria-label": label, tabindex: "-1",
    });
    if (icon) b.innerHTML = icon;
    b.addEventListener("click", function (e) {
      e.stopPropagation();
      onClick(b);
    });
    return b;
  }

  // --- group scaffold ---------------------------------------------------------

  function groupNode(label) {
    const li = el("li", "tree-group", {
      role: "treeitem", "aria-expanded": "true", tabindex: "-1",
    });
    const labelEl = el("span", "tree-group-label", {});
    labelEl.textContent = label;
    const toggle = el("button", "tree-toggle", { type: "button", tabindex: "-1" });
    toggle.textContent = "\u25be";
    toggle.addEventListener("click", function () { setExpanded(label); });
    li.appendChild(toggle);
    li.appendChild(labelEl);
    const ul = el("ul", "tree-group-children", { role: "group" });
    li.appendChild(ul);
    bindNav(li, label);
    return { li: li, ul: ul, toggle: toggle };
  }

  function setExpanded(label, next) {
    const want = next === undefined ? !expanded[label] : !!next;
    expanded[label] = want;
    const g = groups[label];
    g.li.setAttribute("aria-expanded", want ? "true" : "false");
    g.toggle.textContent = want ? "\u25be" : "\u25b8";
    g.ul.hidden = !want;
    roving();
  }

  const groups = {
    [DRAWINGS]: groupNode(DRAWINGS),
    [INDICATORS]: groupNode(INDICATORS),
  };
  tree.appendChild(groups[DRAWINGS].li);
  tree.appendChild(groups[INDICATORS].li);

  // --- rows -------------------------------------------------------------------

  function drawingRow(row) {
    const eye = action("row-eye", "Toggle " + row.kind + " visibility",
      "", function () {
        row.visible = !row.visible;
        syncEye(eye, row.visible !== false);
        bus.emit("drawing:changed", { id: row.id, visible: row.visible, persist: true });
      });
    syncEye(eye, row.visible !== false);

    const lock = action("row-lock", "Toggle " + row.kind + " lock", "", function () {
      row.locked = !row.locked;
      syncLock(lock, row.locked === true);
      bus.emit("drawing:changed", { id: row.id, locked: row.locked, persist: true });
    });
    syncLock(lock, row.locked === true);

    const del = action("row-delete", "Delete " + row.kind + " #" + row.id, TRASH, function () {
      bus.emit("drawing:delete", { id: row.id });
    });

    const li = el("li", "tree-row", { role: "treeitem", tabindex: "-1" });
    li.dataset.id = String(row.id);
    li.setAttribute("aria-selected", row.id === selectedDrawingId ? "true" : "false");
    const name = el("span", "tree-row-name", {});
    name.textContent = row.kind + " #" + row.id;
    li.appendChild(eye);
    li.appendChild(name);
    li.appendChild(lock);
    li.appendChild(del);
    li.addEventListener("click", function () { selectDrawing(row.id); });
    bindNav(li);
    li.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") selectDrawing(row.id);
    });
    return li;
  }

  function selectDrawing(id) {
    selectedDrawingId = id;
    bus.emit("drawing:selected", { id: id });
    drawingRows.forEach(function (r) { r._li.setAttribute("aria-selected", "false"); });
    const hit = drawingRows.find(function (r) { return r.id === id; });
    if (hit && hit._li) hit._li.setAttribute("aria-selected", "true");
    roving();
  }

  // Sync an eye button's icon + aria-pressed to a visible boolean (R6/R9).
  function syncEye(btn, visible) {
    btn.innerHTML = visible ? EYE_ON : EYE_OFF;
    btn.setAttribute("aria-pressed", visible ? "true" : "false");
  }

  function syncLock(btn, locked) {
    btn.innerHTML = locked ? LOCK_ON : LOCK_OFF;
    btn.setAttribute("aria-pressed", locked ? "true" : "false");
  }

  function indicatorRow(token) {
    const visible = !(state.indicatorVisible && state.indicatorVisible[token] === false);
    const eye = action("row-eye", "Toggle " + token + " visibility", "", function () {
      // next = the NEW visible value: a hidden row becomes visible, else hidden.
      const next = state.indicatorVisible && state.indicatorVisible[token] === false;
      const map = Object.assign({}, state.indicatorVisible);
      map[token] = next;
      store.set({ indicatorVisible: map });
      syncEye(eye, next);
      bus.emit("indicator:visibility", { token: token, visible: next });
    });
    syncEye(eye, visible);

    const settings = action("row-settings", token + " settings", GEAR,
      function () {
        if (typeof onIndicatorSettings === "function") onIndicatorSettings(token);
      });
    settings.dataset.token = token;
    settings.setAttribute("aria-haspopup", "dialog");

    const del = action("row-delete", "Remove " + token, TRASH, function () {
      const next = state.indicators.filter(function (t) { return t !== token; });
      const vis = Object.assign({}, state.indicatorVisible);
      delete vis[token];
      store.set({ indicators: next, indicatorVisible: vis });
      bus.emit("indicator:changed"); // membership change = rebuild (setData path)
    });

    const li = el("li", "tree-row", { role: "treeitem", tabindex: "-1" });
    li.dataset.token = token;
    const name = el("span", "tree-row-name", {});
    name.textContent = token;
    li.appendChild(eye);
    li.appendChild(name);
    li.appendChild(del);
    li.appendChild(settings);
    bindNav(li);
    return li;
  }

  // --- render -----------------------------------------------------------------

  function clearGroup(label, rows) {
    const ul = groups[label].ul;
    ul.textContent = "";
    rows.forEach(function (r) { ul.appendChild(r); });
  }

  function render() {
    const drawEls = drawingRows.map(drawingRow);
    drawingRows.forEach(function (r, i) { r._li = drawEls[i]; });
    clearGroup(DRAWINGS, drawEls);

    const tokens = (state.indicators || []);
    clearGroup(INDICATORS, tokens.map(indicatorRow));
    roving();
  }

  // --- roving tabindex + keyboard tree nav (R3) -------------------------------

  function focusables() {
    const out = [];
    [DRAWINGS, INDICATORS].forEach(function (label) {
      out.push(groups[label].li);
      if (expanded[label]) {
        // HTMLCollection has no forEach — copy to an array first.
        Array.prototype.forEach.call(groups[label].ul.children, function (r) {
          out.push(r);
        });
      }
    });
    return out;
  }

  function roving() {
    const items = focusables();
    const active = items.find(function (n) {
      return globalThis.document.activeElement === n;
    });
    const target = active || items[0];
    items.forEach(function (n) {
      n.setAttribute("tabindex", n === target ? "0" : "-1");
    });
  }

  // Per-node keydown (R3), guarded by ``e.target === node`` so a row event
  // bubbling to its group parent is handled once, never twice. Up/Down move
  // focus; Left/Right collapse/expand a group; Delete deletes; Enter selects.
  function bindNav(node, groupLabel) {
    node.addEventListener("keydown", function (e) {
      if (e.target && e.target !== node) return; // ignore bubbled child events
      const items = focusables();
      const i = items.indexOf(node);
      if (i === -1) return;
      if (e.key === "ArrowDown") {
        items[Math.min(i + 1, items.length - 1)].focus();
      } else if (e.key === "ArrowUp") {
        items[Math.max(i - 1, 0)].focus();
      } else if (e.key === "ArrowRight" && groupLabel) {
        setExpanded(groupLabel, true);
      } else if (e.key === "ArrowLeft" && groupLabel) {
        setExpanded(groupLabel, false);
      } else if (e.key === "Delete" && node.dataset.id !== undefined) {
        bus.emit("drawing:delete", { id: Number(node.dataset.id) });
      } else {
        return;
      }
      e.preventDefault();
      roving();
    });
  }

  // --- subscriptions ----------------------------------------------------------

  bus.on("drawings:changed", function (p) {
    drawingRows = ((p && p.rows) || []).slice();
    // A selected id MUST NOT linger after its row is gone (R14).
    if (selectedDrawingId !== null
      && !drawingRows.some(function (r) { return r.id === selectedDrawingId; })) {
      selectedDrawingId = null;
    }
    render();
  });
  bus.on("layout:loaded", render);
  store.subscribe(render);

  render();
  return {};
}
