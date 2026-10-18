// alert-bell-view.js — the crosshair bell element (create, place, paint).
//
// Extracted from controllers/alerts.js to hold the R14 ceiling. It owns exactly
// one JS-built <button> in #chart and its geometry: CSP forbids an inline
// handler, so the click listener is bound here. The crosshair state and the
// dialog stay in the controller; this file is the element adapter.
import { paintBell, bellRight } from "./alert-ui-core.js";

export function createBellView({ container, host, onOpen }) {
  let bell = null;

  // The right price scale owns the crosshair price tag and a drag strip; the
  // bell is pushed left of it by the axis width (measured once per build).
  function placeRight() {
    if (!bell) return;
    const chart = host.getChart ? host.getChart() : null;
    const scale = chart && chart.priceScale ? chart.priceScale("right") : null;
    const offset = scale && scale.width ? bellRight(scale.width()) : null;
    if (offset) bell.style.right = offset;
  }

  function build() {
    if (!container || bell) return;
    bell = document.createElement("button");
    bell.type = "button";
    bell.id = "chart-alert-bell";
    bell.className = "chart-alert-bell";
    bell.setAttribute("aria-label", "Create price alert");
    bell.textContent = "+"; // the visible glyph; the bell is the aria-label
    bell.hidden = true;
    bell.addEventListener("click", onOpen);
    container.appendChild(bell);
    placeRight();
  }

  // Paint for the current crosshair state (pure core does the mapping).
  function render(cursor, interval, hovering, reasonEl) {
    paintBell(bell, cursor, interval, hovering, reasonEl);
  }

  // Pointer enter/leave plumbing lives with the element it belongs to.
  function onPointer(fn) {
    if (!bell) return;
    bell.addEventListener("pointerenter", fn);
    bell.addEventListener("pointerleave", fn);
  }

  return { build, placeRight, render, onPointer };
}
