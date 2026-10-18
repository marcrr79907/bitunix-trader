// controllers/alerts.js — the F10 alert layer over the chart (issue #123).
//
// DI factory (R14): ``createAlerts({store,bus,host,config})`` →
// ``{attach, refresh, clearForSwitch}``. LEAF module — never imports main.
//
// Owns a bell pinned to the crosshair, a native ``<dialog>`` seeded from that
// price, and the marker view (alert-markers-view) for the active pair's rules.
// Markers are NOT series data: this controller never calls
// ``setData``/``update`` (#68). All mapping lives in the pure cores
// (alert-condition-core, alert-markers-core, alert-ui-core); this file is
// DOM/fetch glue.
//
// Reuse, no new seam: the chart is recreated on every build, so the crosshair
// subscription is re-bound on the existing ``chart:built`` event (the
// legend.js precedent); no bus event, no store key, no 9th ``marketChart`` key.
// ``for_user`` is resolved server-side — the client never invents a rule.
import * as Cond from "../alert-condition-core.js";
import { createMarkersView } from "../alert-markers-view.js";
import { createBellView } from "../alert-bell-view.js";
import {
  eligible,
  reasonText,
  fmtPrice,
  lastClose,
  listUrl,
  writeRequest,
  nearestRule,
  editCueText,
  successText,
} from "../alert-ui-core.js";

// Edit detection (D7): px distance to an existing price rule's level.
const NEAR_PX = 10;

function csrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : "";
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
  const cueEl = document.getElementById("alert-cue");
  const confirmEl = document.getElementById("alert-confirm");

  const markers = createMarkersView({ host, statusEl, confirmEl });
  const bellView = createBellView({ container, host, onOpen: openDialog });
  let rules = []; // rows for the active pair (server-shaped)
  let cursor = null; // {x, y, price} of the last crosshair point, or null
  let target = null; // the near rule the open dialog would PUT, or null
  let gen = 0; // invalidates an in-flight fetch after a switch
  let bound = false; // attach() runs once
  // Hovering the bell takes the pointer off the canvas (LWC clears the
  // crosshair), so the flag stops it vanishing just as it is reached.
  let hovering = false;
  // The crosshair cleared while the pointer was on the bell; the point was kept
  // for the dialog, but leaving must not leave a bell with no cursor behind.
  let stale = false;

  function isEligible() { return eligible(state.interval); }

  // --- bell -----------------------------------------------------------------

  // Leaving a bell whose crosshair point is gone must hide it (F10 UI #234):
  // the flag suppressed the clear while hovered, so the deferred clear lands
  // here and the bell is re-placed for the now-empty state.
  function setHovering(e) {
    hovering = e.type === "pointerenter";
    if (hovering) return;
    if (stale) cursor = null;
    stale = false;
    placeBell();
  }

  // Move the crosshair on: the last price stays usable while the pointer is on
  // the bell (a leave with no point must not erase what the dialog will seed).
  function clearCursor() {
    if (hovering) { stale = true; return; }
    cursor = null;
  }

  // Show the bell at the crosshair, or hide it when the pointer leaves the plot
  // (mirrors legend.js onMove). The interval guard marks it inert with a reason.
  function placeBell() {
    bellView.render(cursor, state.interval, hovering, reasonEl);
  }

  // --- dialog ---------------------------------------------------------------

  function lastClosePrice() {
    return lastClose(host.getCandles());
  }

  // The existing price rule whose level is nearest the cursor, within NEAR_PX
  // (zoom-aware px, not % — D7). No rule in range means "create". The mapping is
  // the pure core's; this only supplies the price->coordinate function.
  function nearRule() {
    const series = host.getCandleSeries();
    if (!series || !cursor) return null;
    return nearestRule(rules, cursor.y, NEAR_PX, function (level) {
      return series.priceToCoordinate(level);
    });
  }

  // A silent PUT is a silent edit (F10 UI #234): the dialog says what it will
  // do, and Apply's outcome is named in the visible confirmation.
  function paintCue() {
    if (!cueEl) return;
    const text = editCueText(target);
    cueEl.textContent = text || "";
    cueEl.hidden = !text;
  }

  // Seed the dialog from the crosshair price; the op defaults off the last
  // close (opFor owns that rule, so the default cannot drift).
  function seedAt(price) {
    if (!dialog || !isEligible()) return false;
    target = nearRule();
    if (opInput) opInput.value = Cond.opFor(price, lastClosePrice());
    if (levelInput) levelInput.value = fmtPrice(price);
    if (errorEl) errorEl.hidden = true;
    paintCue();
    dialog.showModal();
    return true;
  }

  function openDialog() {
    if (!cursor || !isEligible()) return; // aria-disabled: skip the action
    seedAt(cursor.price);
  }

  // F10 UI #235: the keyboard path. The bell needs a pointer-produced crosshair
  // point, which Tab never makes, so the context menu's "Add alert" opens the
  // dialog seeded from the newest close instead.
  function openFromLastClose() {
    const close = lastClosePrice();
    if (close === null) return false;
    cursor = null; // no cursor: the dialog is a create from the last close
    return seedAt(close);
  }

  // Apply runs inside the dialog's ``close`` handler, so the dialog is already
  // shut when the response lands. An error written into a closed dialog is zero
  // feedback (#233): every failure RE-OPENS it. The typed level is untouched.
  function fail(text) {
    if (errorEl) {
      errorEl.textContent = text;
      errorEl.hidden = false;
    }
    if (dialog) dialog.showModal();
    if (levelInput) levelInput.focus();
  }

  // Apply writes ONE request through the pure condition core; a null condition
  // is the "do not POST" signal and re-opens the dialog with the reason.
  function apply() {
    const level = Cond.levelFromInput(levelInput ? levelInput.value : "");
    const condition = Cond.conditionFrom({ op: opInput ? opInput.value : "", level: level });
    if (!condition) {
      fail("Enter a price above 0");
      return;
    }
    const edit = target;
    const req = writeRequest(config.urls.alerts, state, condition, edit);
    fetch(req.url, {
      method: edit ? "PUT" : "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify(req.body),
    })
      .then(function (r) {
        return r.json().then(function (b) {
          if (!r.ok) return fail((b && b.error) || "Could not save the alert");
          markers.flash(successText(condition, edit));
          return refresh();
        });
      })
      .catch(function () { fail("Network error — the alert was not saved"); });
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

  // --- fetch ----------------------------------------------------------------

  // Refetch the ACTIVE pair's rules. A non-evaluable interval cannot have a
  // firing rule, so no request is issued there (the API would 400 anyway).
  function refresh() {
    if (!container || !isEligible()) {
      rules = [];
      markers.clear();
      return Promise.resolve();
    }
    const mine = ++gen;
    return fetch(listUrl(config.urls.alerts, state.symbol, state.interval))
      .then(function (r) { if (!r.ok) throw new Error("alerts " + r.status); return r.json(); })
      .then(function (body) {
        if (mine !== gen) return;
        rules = Array.isArray(body.alerts) ? body.alerts : [];
        markers.render(rules);
      })
      .catch(function () {
        if (mine !== gen) return;
        rules = [];
        markers.clear();
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

  function attach() {
    if (bound) return;
    bound = true;
    bellView.build();
    bellView.onPointer(setHovering);
    if (reasonEl) reasonEl.textContent = reasonText(state.interval);
    // build() recreates the chart, so the handler is re-bound to the NEW chart
    // on every chart:built (its predecessor died with chart.remove()).
    bus.on("chart:built", function () {
      markers.detach();
      host.subscribeCrosshairMove(onMove);
      cursor = null;
      bellView.build();
      bellView.placeRight();
      placeBell();
      refresh();
    });
    // Armed markers anchor on the newest candle, which only exists after the
    // history page lands — re-project then (no refetch: the rules are current).
    bus.on("history:loaded", function () { markers.render(rules); });
    // A closed candle becomes the new newest bar, so the anchor must move with
    // it (F10 UI #234). Same no-refetch rule: the rule rows did not change.
    bus.on("candle:closed", function () { markers.render(rules); });
  }

  // Called by main on switchTo: the previous pair's markers must never cross
  // into the new chart (the marker handle dies with its series).
  function clearForSwitch() {
    gen += 1;
    rules = [];
    markers.detach();
    cursor = null;
    placeBell();
    if (dialog && dialog.open) dialog.close("");
    markers.clear();
  }

  return {
    attach: attach,
    refresh: refresh,
    clearForSwitch: clearForSwitch,
    openFromLastClose: openFromLastClose,
    refreshTheme: function () { markers.render(rules); },
  };
}
