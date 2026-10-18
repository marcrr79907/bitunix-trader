// controllers/alerts.js — the F10 alert layer over the chart (issue #123).
//
// DI factory (R14): ``createAlerts({store,bus,host,config})`` →
// ``{attach, refresh, clearForSwitch}``. LEAF module — never imports main.
//
// Owns a bell pinned to the crosshair, a native ``<dialog>`` seeded from that
// price, and ONE ``createSeriesMarkers`` handle for the caller's rules on the
// active pair. Markers are NOT series data: this controller never calls
// ``setData``/``update`` (#68). All mapping lives in the two pure cores
// (alert-condition-core, alert-markers-core); this file is DOM/fetch glue.
//
// Reuse, no new seam: the chart is recreated on every build, so the crosshair
// subscription is re-bound on the existing ``chart:built`` event (the
// legend.js precedent); no bus event, no store key, no 9th ``marketChart`` key.
// ``for_user`` is resolved server-side — the client never invents a rule.
import * as Cond from "../alert-condition-core.js";
import * as Markers from "../alert-markers-core.js";

// Interval eligibility mirrors the worker's persisted set (trading/candles.py
// CANDLE_INTERVALS): a rule on any other interval can never fire.
const EVALUABLE = ["5m", "15m", "1h", "2h", "4h", "1d", "1w", "1M"];
// Edit detection (D7): px distance to an existing price rule's level.
const NEAR_PX = 10;

function csrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : "";
}

function fmtPrice(v) {
  return typeof v === "number" && isFinite(v) ? String(Math.round(v * 1e6) / 1e6) : "–";
}

export function createAlerts({ store, bus, host, config }) {
  const state = store.get();
  const container = document.getElementById("chart");
  const dialog = document.getElementById("alert-dialog");
  const opInput = document.getElementById("alert-op");
  const levelInput = document.getElementById("alert-level");
  const errorEl = document.getElementById("alert-error");
  const statusEl = document.getElementById("alert-status");
  const reasonEl = document.getElementById("alert-interval-reason");

  let bell = null; // the single #chart-alert-bell (JS-built, CSP-clean)
  let markers = null; // the LightweightCharts marker handle we own
  let rules = []; // rows for the active pair (server-shaped)
  let cursor = null; // {x, y, price} of the last crosshair point, or null
  let gen = 0; // invalidates an in-flight fetch after a switch
  let bound = false; // attach() runs once
  // Hovering the bell takes the pointer off the canvas (LWC clears the
  // crosshair), so the flag stops it vanishing just as it is reached.
  let hovering = false;

  function eligible() { return EVALUABLE.indexOf(state.interval) !== -1; }

  function reasonText() { return "Alerts cannot fire on the " + state.interval + " interval"; }

  // --- bell -----------------------------------------------------------------

  // JS-built (createElement/setAttribute) — CSP ``script-src 'self'`` forbids
  // an inline handler; the click listener is attached here.
  function buildBell() {
    if (!container || bell) return;
    bell = document.createElement("button");
    bell.type = "button";
    bell.id = "chart-alert-bell";
    bell.className = "chart-alert-bell";
    bell.setAttribute("aria-label", "Create price alert");
    bell.textContent = "+"; // the visible glyph; the bell is the aria-label
    bell.hidden = true;
    bell.addEventListener("click", openDialog);
    bell.addEventListener("pointerenter", setHovering);
    bell.addEventListener("pointerleave", setHovering);
    container.appendChild(bell);
  }

  function setHovering(e) { hovering = e.type === "pointerenter"; }

  // Move the crosshair on: the last price stays usable while the pointer is on
  // the bell (a leave with no point must not erase what the dialog will seed).
  function clearCursor() { if (!hovering) cursor = null; }

  // Show the bell at the crosshair, or hide it when the pointer leaves the plot
  // (mirrors legend.js onMove). The interval guard disables it with a reason.
  function placeBell() {
    if (!bell || hovering) return;
    bell.hidden = !cursor;
    if (!cursor) return;
    // Only the PRICE (vertical) comes from the crosshair. A fixed horizontal
    // anchor keeps the bell still: an x that tracked the cursor would move
    // under the pointer and no click could ever land (a moving target).
    bell.style.top = cursor.y + "px";
    bell.setAttribute("aria-label", "Create price alert at " + fmtPrice(cursor.price));
    bell.disabled = !eligible();
    if (eligible()) {
      bell.removeAttribute("aria-describedby");
      bell.removeAttribute("title");
      return;
    }
    bell.setAttribute("aria-describedby", "alert-interval-reason");
    bell.setAttribute("title", reasonText());
    if (reasonEl) reasonEl.textContent = reasonText();
  }

  // --- dialog ---------------------------------------------------------------

  function lastClosePrice() {
    const bars = host.getCandles();
    return Array.isArray(bars) && bars.length ? bars[bars.length - 1].close : null;
  }

  // Seed the dialog from the crosshair price; the op defaults off the last
  // close (opFor owns that rule, so the default cannot drift).
  function openDialog() {
    if (!dialog || !cursor || !eligible()) return;
    if (opInput) opInput.value = Cond.opFor(cursor.price, lastClosePrice());
    if (levelInput) levelInput.value = fmtPrice(cursor.price);
    if (errorEl) errorEl.hidden = true;
    dialog.showModal();
  }

  // The existing price rule whose level is nearest the cursor, within NEAR_PX
  // (zoom-aware px, not % — D7). No rule in range means "create".
  function nearRule() {
    const series = host.getCandleSeries();
    if (!series || !cursor) return null;
    let best = null;
    let bestDistance = NEAR_PX + 1;
    rules.forEach(function (rule) {
      const condition = rule && rule.condition;
      if (!condition || condition.type !== "price") return;
      const y = series.priceToCoordinate(condition.level);
      if (typeof y !== "number") return;
      const distance = Math.abs(y - cursor.y);
      if (distance <= NEAR_PX && distance < bestDistance) {
        best = rule;
        bestDistance = distance;
      }
    });
    return best;
  }

  function showError(text) {
    if (!errorEl) return;
    errorEl.textContent = text;
    errorEl.hidden = false;
  }

  // Apply writes ONE request through the pure condition core; a null condition
  // is the "do not POST" signal and re-opens the dialog with the reason.
  function apply() {
    const level = Cond.levelFromInput(levelInput ? levelInput.value : "");
    const condition = Cond.conditionFrom({ op: opInput ? opInput.value : "", level: level });
    if (!condition) {
      showError("Enter a price above 0");
      if (dialog) dialog.showModal();
      return;
    }
    const target = nearRule();
    const body = target
      ? { condition: condition }
      : { symbol: state.symbol, interval: state.interval, condition: condition, is_active: true };
    fetch(config.urls.alerts + (target ? "/" + target.id : ""), {
      method: target ? "PUT" : "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify(body),
    })
      .then(function (r) {
        return r.json().then(function (b) {
          if (!r.ok) return showError((b && b.error) || "Could not save the alert");
          return refresh();
        });
      })
      .catch(function () { showError("Network error — the alert was not saved"); });
  }

  if (dialog) {
    // Native <dialog>: Escape / Cancel close with an empty returnValue, so only
    // "ok" applies (drawings/indicators precedent). Focus goes back to #chart
    // per the spec, not to the (now hidden) bell.
    dialog.addEventListener("close", function () {
      const ok = dialog.returnValue === "ok";
      dialog.returnValue = "";
      if (ok) apply();
      if (container) container.focus();
    });
  }

  // --- markers + status -----------------------------------------------------
  // The accessible state: markers are canvas, so the count/fired/armed summary
  // lives in #alert-status[aria-live="polite"] (design-system R6).
  function announce() {
    if (!statusEl) return;
    let fired = 0, armed = 0;
    rules.forEach(function (rule) {
      const s = Markers.stateOf(rule);
      if (s === "fired") fired += 1;
      else if (s === "armed") armed += 1;
    });
    const total = fired + armed;
    if (!total) return void (statusEl.textContent = "No alerts on this chart");
    const noun = total === 1 ? " alert: " : " alerts: ";
    statusEl.textContent = total + noun + fired + " fired, " + armed + " armed";
  }

  // The newest loaded candle is the armed anchor (a marker time MUST be a real
  // data point). Re-projected after every history page — no synthetic bars.
  function renderMarkers() {
    const series = host.getCandleSeries();
    if (!series) return;
    const bars = host.getCandles();
    const anchor = Array.isArray(bars) && bars.length ? bars[bars.length - 1].time : null;
    const list = Markers.markersFor(rules, anchor);
    if (!markers) markers = LightweightCharts.createSeriesMarkers(series, list);
    else markers.setMarkers(list);
    announce();
  }

  // --- fetch ----------------------------------------------------------------

  // Refetch the ACTIVE pair's rules. A non-evaluable interval cannot have a
  // firing rule, so no request is issued there (the API would 400 anyway).
  function refresh() {
    if (!container || !eligible()) {
      rules = [];
      if (markers) markers.setMarkers([]);
      announce();
      return Promise.resolve();
    }
    const mine = ++gen;
    const enc = encodeURIComponent;
    const url = config.urls.alerts + "?symbol=" + enc(state.symbol) + "&interval=" + enc(state.interval);
    return fetch(url)
      .then(function (r) { if (!r.ok) throw new Error("alerts " + r.status); return r.json(); })
      .then(function (body) {
        if (mine !== gen) return;
        rules = Array.isArray(body.alerts) ? body.alerts : [];
        renderMarkers();
      })
      .catch(function () {
        if (mine !== gen) return;
        rules = [];
        if (markers) markers.setMarkers([]);
        announce();
      });
  }

  function onMove(param) {
    const point = param && param.point;
    if (!point) { clearCursor(); placeBell(); return; }
    const series = host.getCandleSeries();
    const price = series ? series.coordinateToPrice(point.y) : null;
    cursor = { x: point.x, y: point.y, price: price };
    placeBell();
  }

  // --- lifecycle ------------------------------------------------------------

  // The marker handle dies with its series: a rebuild must let it go, never
  // reuse it across charts (LWC throws on a detached handle).
  function detachMarkers() {
    if (markers) markers.detach();
    markers = null;
  }

  function attach() {
    if (bound) return;
    bound = true;
    buildBell();
    if (reasonEl) reasonEl.textContent = reasonText();
    // build() recreates the chart, so the handler is re-bound to the NEW chart
    // on every chart:built (its predecessor died with chart.remove()).
    bus.on("chart:built", function () {
      detachMarkers();
      host.subscribeCrosshairMove(onMove);
      cursor = null;
      placeBell();
      refresh();
    });
    // Armed markers anchor on the newest candle, which only exists after the
    // history page lands — re-project then (no refetch: the rules are current).
    bus.on("history:loaded", renderMarkers);
  }

  // Called by main on switchTo: the previous pair's markers must never cross
  // into the new chart (the marker handle dies with its series).
  function clearForSwitch() {
    gen += 1;
    rules = [];
    detachMarkers();
    cursor = null;
    placeBell();
    if (dialog && dialog.open) dialog.close("");
    announce();
  }

  return { attach: attach, refresh: refresh, clearForSwitch: clearForSwitch };
}
