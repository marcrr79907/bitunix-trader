// controllers/draw-toolbar.js — vertical grouped icon toolbar (F5 S2, R1-R5).
//
// DI factory (R14): ``createDrawToolbar({store, bus, config})``. LEAF module —
// never imports main. Renders from the PURE tool-icons-core (grouped vocab +
// inline-SVG strings) and owns ONLY the toolbar DOM. Activating a tool writes
// ``store.tool`` — the SAME command the legacy ``.draw-tool`` buttons emitted
// (design D3); NO new bus event. Active state is reflected through
// ``store.subscribe`` so an external change (cancel/switch) syncs the toolbar.
//
// CSP: icons are strings built by tool-icons-core and injected with innerHTML on
// a native button — no inline handler, no inline script. Keyboard: a single
// roving ``tabindex`` with Up/Down/Home/End, mirroring the interval chips
// (toolbar.js:63-71); Enter/Space activate the native button.
import { TOOL_GROUPS, iconFor, groupLabel } from "../tool-icons-core.js";

// F7 (R1 delta): the per-tool shortcut letter each button ADVERTISES via
// ``aria-keyshortcuts``. Advisory only — no global letter router is bound (D8);
// the object tree owns ``v``/``l``/``s`` (object-tree.js). A short label is the
// accessible-name sibling of the icon.
export const TOOL_KEYS = {
  hline: "H",
  trendline: "T",
  fib: "F",
  rect: "R",
  text: "X",
  measure: "M",
  position: "P",
};

// Accessible name per kind (the SVG is aria-hidden, so the button carries it).
const TOOL_LABELS = {
  hline: "Horizontal line",
  trendline: "Trend line",
  fib: "Fibonacci retracement",
  rect: "Rectangle",
  text: "Text",
  measure: "Measure",
  position: "Position",
};

export function createDrawToolbar({ store }) {
  const mount = document.getElementById("draw-tools");
  const state = store.get();
  if (!mount) return {};

  mount.textContent = "";
  const toolbar = document.createElement("div");
  toolbar.className = "draw-tools";
  toolbar.setAttribute("role", "toolbar");
  toolbar.setAttribute("aria-label", "Drawing tools");
  toolbar.setAttribute("aria-orientation", "vertical");

  const buttons = [];

  // Toggle semantics of the legacy wiring: clicking the active tool cancels it.
  function activate(kind) {
    store.set({ tool: state.tool === kind ? null : kind });
  }

  // Single roving tabindex: the active tool (or the first when none is active).
  function roving() {
    const active = buttons.find(function (b) { return b.dataset.kind === state.tool; });
    const target = active || buttons[0];
    buttons.forEach(function (b) {
      b.setAttribute("tabindex", b === target ? "0" : "-1");
    });
  }

  function sync() {
    buttons.forEach(function (b) {
      b.setAttribute("aria-pressed", b.dataset.kind === state.tool ? "true" : "false");
    });
    roving();
  }

  function moveFocus(from, key) {
    const i = buttons.indexOf(from);
    if (key === "Home") return buttons[0].focus();
    if (key === "End") return buttons[buttons.length - 1].focus();
    const delta = key === "ArrowDown" ? 1 : -1;
    buttons[(i + delta + buttons.length) % buttons.length].focus();
  }

  TOOL_GROUPS.forEach(function (group) {
    const g = document.createElement("div");
    g.setAttribute("role", "group");
    g.setAttribute("aria-label", groupLabel(group));
    group.kinds.forEach(function (kind) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "draw-tool";
      btn.dataset.kind = kind;
      btn.setAttribute("aria-pressed", "false");
      btn.setAttribute("aria-label", TOOL_LABELS[kind] || kind);
      // F7 (R1 delta): advertise the per-tool letter (no router — D8).
      if (TOOL_KEYS[kind]) btn.setAttribute("aria-keyshortcuts", TOOL_KEYS[kind]);
      const icon = iconFor(kind);
      if (icon) btn.innerHTML = icon;
      btn.addEventListener("click", function () { activate(kind); });
      btn.addEventListener("keydown", function (e) {
        if (e.key !== "ArrowDown" && e.key !== "ArrowUp"
          && e.key !== "Home" && e.key !== "End") return;
        e.preventDefault();
        moveFocus(btn, e.key);
      });
      buttons.push(btn);
      g.appendChild(btn);
    });
    toolbar.appendChild(g);
  });

  mount.appendChild(toolbar);
  sync();
  store.subscribe(sync);

  return {};
}
