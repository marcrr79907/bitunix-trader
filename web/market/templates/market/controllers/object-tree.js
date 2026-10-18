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
import {
  TREE_GROUPS,
  labelFor,
  TRASH,
  GEAR,
} from "../tool-icons-core.js";
import { el, action, syncEye, syncLock } from "../object-tree-dom-core.js";
import { createAddIndicator } from "../add-indicator-core.js";

const DRAWINGS = TREE_GROUPS[0].label; // "Drawings"
const INDICATORS = TREE_GROUPS[1].label; // "Indicators"

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

  // --- group scaffold ---------------------------------------------------------

  function groupNode(label) {
    const li = el("li", "tree-group", {
      role: "treeitem", "aria-expanded": "true", tabindex: "-1",
    });
    const labelEl = el("span", "tree-group-label", {});
    labelEl.textContent = label;
    const toggle = el("button", "tree-toggle", { type: "button", tabindex: "-1", "aria-label": "Toggle " + label + " group" });
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
  groups[INDICATORS].li.appendChild(createAddIndicator({ store, bus }));

  // --- rows -------------------------------------------------------------------

  function drawingRow(row) {
    const label = labelFor(row.kind); // R2 #223: a human name, never the slug
    const eye = action("row-eye", "Toggle " + label + " visibility",
      "", function () {
        row.visible = !row.visible;
        syncEye(eye, row.visible !== false);
        bus.emit("drawing:changed", { id: row.id, visible: row.visible, persist: true });
      }, "v");
    syncEye(eye, row.visible !== false);

    const lock = action("row-lock", "Toggle " + label + " lock", "", function () {
      row.locked = !row.locked;
      syncLock(lock, row.locked === true);
      bus.emit("drawing:changed", { id: row.id, locked: row.locked, persist: true });
    }, "l");
    syncLock(lock, row.locked === true);

    const del = action("row-delete", "Delete " + label + " #" + row.id, TRASH, function () {
      bus.emit("drawing:delete", { id: row.id });
    }, "Delete");

    const li = el("li", "tree-row", { role: "treeitem", tabindex: "-1" });
    li.dataset.id = String(row.id);
    li.setAttribute("aria-selected", row.id === selectedDrawingId ? "true" : "false");
    const name = el("span", "tree-row-name", {});
    name.textContent = label + " #" + row.id;
    li.appendChild(eye);
    li.appendChild(name);
    li.appendChild(lock);
    li.appendChild(del);
    li.addEventListener("click", function () { selectDrawing(row.id); });
    // R6: documented row keys mirror the mouse-only eye/lock; Enter/space select.
    bindNav(li, null, {
      Enter: function () { selectDrawing(row.id); },
      " ": function () { selectDrawing(row.id); },
      v: function () { eye.click(); },
      l: function () { lock.click(); },
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
    }, "v");
    syncEye(eye, visible);

    const settings = action("row-settings", token + " settings", GEAR,
      function () {
        if (typeof onIndicatorSettings === "function") onIndicatorSettings(token);
      }, "s");
    settings.dataset.token = token;
    settings.setAttribute("aria-haspopup", "dialog");

    const del = action("row-delete", "Remove " + token, TRASH, function () {
      const next = state.indicators.filter(function (t) { return t !== token; });
      const vis = Object.assign({}, state.indicatorVisible);
      delete vis[token];
      store.set({ indicators: next, indicatorVisible: vis });
      bus.emit("indicator:changed"); // membership change = rebuild (setData path)
    }, "Delete");

    const li = el("li", "tree-row", { role: "treeitem", tabindex: "-1" });
    li.dataset.token = token;
    const name = el("span", "tree-row-name", {});
    name.textContent = token;
    li.appendChild(eye);
    li.appendChild(name);
    li.appendChild(del);
    li.appendChild(settings);
    // R6: documented row keys mirror eye/delete/settings. No new bus event (R20).
    bindNav(li, null, {
      v: function () { eye.click(); },
      s: function () { settings.click(); },
      Delete: function () { del.click(); },
    });
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

  // Per-node keydown (R3 + R6 row actions), guarded by ``e.target === node`` so
  // a row event bubbling to its group parent is handled once, never twice.
  // ``keys`` maps a row's documented action keys to their handlers (R6 a11y);
  // Up/Down move focus; Left/Right collapse/expand a group.
  function bindNav(node, groupLabel, keys) {
    node.addEventListener("keydown", function (e) {
      if (e.target && e.target !== node) return; // ignore bubbled child events
      if (keys && keys[e.key]) { keys[e.key](); return; }
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
