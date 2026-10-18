// object-tree-dom-core.js — DOM factories shared by the object-tree controller.
//
// Framework-free apart from ``document.createElement`` (no chart, no network, no
// state), imported in Node by the tests and in the browser by the tree. It keeps
// the row markup (``el``/``action``) and the eye/lock icon sync out of the
// controller so the tree stays under the R14 module ceiling.
import { EYE_ON, EYE_OFF, LOCK_ON, LOCK_OFF } from "./tool-icons-core.js";

export function el(tag, cls, attrs) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
  return node;
}

// A native per-row action button. ``icon`` is a CSP-clean SVG string (no event
// attribute); the accessible name rides aria-label. ``shortcut`` is the
// documented per-row key that activates it (R6: the row owns roving focus, so
// buttons stay tabindex=-1 and advertise their binding via aria-keyshortcuts).
export function action(cls, label, icon, onClick, shortcut) {
  const b = el("button", cls, {
    type: "button", "aria-label": label, tabindex: "-1",
  });
  if (shortcut) b.setAttribute("aria-keyshortcuts", shortcut);
  if (icon) b.innerHTML = icon;
  b.addEventListener("click", function (e) {
    e.stopPropagation();
    onClick(b);
  });
  return b;
}

// Sync a toggle button's icon + aria-pressed to a boolean (R6/R9: the icon swap
// keeps state not color-only). Eye and lock are the same shape.
export function syncBtn(btn, on, onIcon, offIcon) {
  btn.innerHTML = on ? onIcon : offIcon;
  btn.setAttribute("aria-pressed", on ? "true" : "false");
}

export const syncEye = (b, v) => syncBtn(b, v, EYE_ON, EYE_OFF);
export const syncLock = (b, l) => syncBtn(b, l, LOCK_ON, LOCK_OFF);
