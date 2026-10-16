// add-indicator-core.js — the "＋ Add" affordance (F5 S5, issue #176).
//
// The Object Tree is ACTIVE-ONLY (chart-object-tree R1: "the registry's
// inactive tokens MUST NOT be listed"); this is the counterpart control that
// lists REGISTRY-minus-membership, TradingView-style. Keeping the whole
// affordance in this leaf helper leaves controllers/object-tree.js within the
// R14 ceiling and makes the "never duplicate an active token" rule testable
// without a browser.
//
// Leaf module: it never imports ``main``. The selection is pure; the affordance
// is a native <button> + a list of native item buttons (keyboard-operable, no
// inline handler — CSP-clean). No new bus event: an add emits the existing
// ``indicator:changed`` (rebuild/setData path, permitted; #68).
import { REGISTRY } from "./chart-registry-core.js";

// REGISTRY tokens NOT in the active membership, in registry order (stable).
// ``registry`` is the token->descriptor map; ``active`` the membership array.
export function inactiveTokens(registry, active) {
  const on = active || [];
  return Object.keys(registry).filter(function (token) {
    return on.indexOf(token) === -1;
  });
}

// Build the add control: a native button that toggles a list of the inactive
// registry tokens. Choosing a token appends it to the store membership and
// emits ``indicator:changed`` (rebuild) — the caller persists via saveLayout.
// When every token is active the control is aria-disabled with no candidates
// (R6). Subscribes to the store so it tracks membership without a re-render.
export function createAddIndicator({ store, bus }) {
  const wrap = document.createElement("div");
  wrap.className = "add-indicator";

  const btn = document.createElement("button");
  btn.setAttribute("type", "button");
  btn.setAttribute("aria-label", "Add indicator");
  btn.setAttribute("aria-expanded", "false");
  btn.className = "add-toggle";
  btn.textContent = "\uff0b Add";

  const list = document.createElement("ul");
  list.className = "add-menu";
  list.hidden = true;
  wrap.appendChild(btn);
  wrap.appendChild(list);

  const candidates = () => inactiveTokens(REGISTRY, store.get().indicators);

  function renderMenu() {
    list.textContent = "";
    const tokens = candidates();
    tokens.forEach(function (token) {
      const item = document.createElement("button");
      item.setAttribute("type", "button");
      item.className = "add-item";
      item.dataset.token = token;
      item.textContent = token;
      item.addEventListener("click", function () { add(token); });
      list.appendChild(item);
    });
    const empty = tokens.length === 0;
    btn.setAttribute("aria-disabled", empty ? "true" : "false");
    if (empty) {
      list.hidden = true;
      btn.setAttribute("aria-expanded", "false");
    }
  }

  function open(next) {
    if (candidates().length === 0) return; // R6: nothing to offer
    list.hidden = !next;
    btn.setAttribute("aria-expanded", next ? "true" : "false");
    if (next) renderMenu();
  }

  function add(token) {
    if (candidates().indexOf(token) === -1) return; // never duplicate an active token
    store.set({ indicators: (store.get().indicators || []).concat([token]) });
    bus.emit("indicator:changed"); // membership change = rebuild (setData path, #68)
    open(false);
  }

  btn.addEventListener("click", function () { open(list.hidden); });
  store.subscribe(renderMenu);
  renderMenu();
  return wrap;
}
