// alert-markers-view.js — the LWC/DOM adapter for alert markers + the live summary.
//
// Extracted from controllers/alerts.js to hold the 300-line R14 ceiling: it owns
// the ONE ``createSeriesMarkers`` handle (never series data, #68), resolves the
// shell tokens at render time (#232), and writes the aria-live summary (#234).
// The mapping itself stays in the pure alert-markers-core; this file is glue.
import * as Markers from "./alert-markers-core.js";
import { token } from "./theme-core.js";

// How long the visible Apply confirmation stays up (#234). The same node is the
// screen-reader live region, so it is only revealed, never replaced.
const FLASH_MS = 4000;

export function createMarkersView({ host, statusEl, confirmEl }) {
  let markers = null; // the handle we own; dies with its series

  // The newest loaded candle is the armed anchor (a marker time MUST be a real
  // data point). The core drops armed rules when there is no usable anchor.
  function render(rules) {
    const series = host.getCandleSeries();
    if (!series) return;
    const bars = host.getCandles();
    const anchor = Array.isArray(bars) && bars.length ? bars[bars.length - 1].time : null;
    const colors = {
      armed: token("--alert-armed", Markers.COLORS.armed),
      fired: token("--dn", Markers.COLORS.fired),
    };
    const list = Markers.markersFor(rules, anchor, colors);
    if (markers) markers.setMarkers(list);
    else markers = LightweightCharts.createSeriesMarkers(series, list);
    announce(rules);
  }

  // The accessible state: markers are canvas, so the count/fired/armed summary
  // lives in #alert-status[aria-live="polite"] (design-system R6).
  function announce(rules) {
    if (!statusEl) return;
    statusEl.textContent = Markers.summaryOf(rules) || "No alerts on this chart";
  }

  // Visible confirmation after a successful Apply (#234): the dialog is closed
  // by then, so a short toast says what landed. It is a SEPARATE node from the
  // summary live region — overwriting #alert-status would hide the count from
  // assistive tech and the E2E contract.
  let timer = null;
  function flash(text) {
    if (!text || !confirmEl) return;
    confirmEl.textContent = text;
    confirmEl.hidden = false;
    if (timer) clearTimeout(timer);
    timer = setTimeout(function () {
      timer = null;
      confirmEl.hidden = true;
    }, FLASH_MS);
  }

  // The marker handle dies with its series: a rebuild must let it go, never
  // reuse it across charts (LWC throws on a detached handle).
  function detach() {
    if (markers) markers.detach();
    markers = null;
  }

  // Empty the markers (an ineligible interval or a pair switch) and re-announce.
  function clear() {
    if (markers) markers.setMarkers([]);
    announce([]);
  }

  return { render, clear, detach, flash };
}
