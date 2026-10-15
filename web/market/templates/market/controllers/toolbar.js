// controllers/toolbar.js — pair buttons + interval select + interval chips +
// sidebar collapse toggle + F8 scale/type selects + theme control.
//
// DI factory (R14): ``createToolbar({store, bus, config, onTheme})``. LEAF module
// — never imports main. A pair/interval change is a command on the bus
// (``config:changed``); main owns the switch. Owns only the toolbar DOM
// listeners.
//
// The chips are DERIVED from the retained ``<select id="interval">`` options
// (single source: no 4th interval copy) and the select is clipped, never
// display:none, so the E2E ``select_option`` calls stay actionable.
//
// F8: the scale/type ``<select>``s are populated from the PURE core vocab
// (SCALE_MODES/CHART_TYPES — single source, no option copy in HTML). Scale
// emits the light ``scale:changed``; type reuses ``indicator:changed`` so main
// owns the rebuild (R26).
//
// theme (R27/CT2/CT3): the theme control is a native ``<select>`` in the SAME
// controller (no new controller, no new bus event). On change it resolves the
// preference against the OS media query, sets ``data-theme`` on the root to the
// RESOLVED value, and calls the ``main``-injected ``onTheme({resolved, pref})``
// callback (the option-only host flip + debounced save live in main).
import { SCALE_MODES, CHART_TYPES } from "../chart-types-core.js";
import { resolve as resolveTheme, prefersDark } from "../theme-core.js";

export function createToolbar({ store, bus, config, onTheme }) {
  const select = document.getElementById("interval");
  const state = store.get();

  document.querySelectorAll(".pair").forEach(function (btn) {
    btn.addEventListener("click", function () {
      bus.emit("config:changed", { symbol: btn.dataset.symbol, interval: state.interval });
    });
  });

  // --- interval chips (derived from the select options) -----------------------
  const chips = document.createElement("div");
  chips.className = "interval-chips";
  chips.setAttribute("role", "group");
  chips.setAttribute("aria-label", "Interval");

  const buttons = [];
  function setPressed(interval) {
    buttons.forEach(function (btn) {
      btn.setAttribute("aria-pressed", btn.dataset.interval === interval ? "true" : "false");
    });
  }

  function activate(interval) {
    select.value = interval;
    setPressed(interval);
    bus.emit("config:changed", { symbol: store.get().symbol, interval: interval });
  }

  Array.prototype.forEach.call(select.options, function (opt, i) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "interval-chip";
    btn.dataset.interval = opt.value;
    btn.textContent = opt.value;
    btn.setAttribute("aria-pressed", "false");
    btn.addEventListener("click", function () { activate(opt.value); });
    btn.addEventListener("keydown", function (e) {
      // Arrow keys move focus across the chip group (R22); Enter/Space are
      // native button activations.
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      e.preventDefault();
      const delta = e.key === "ArrowRight" ? 1 : -1;
      const next = buttons[(i + delta + buttons.length) % buttons.length];
      next.focus();
    });
    buttons.push(btn);
    chips.appendChild(btn);
  });

  select.insertAdjacentElement("afterend", chips);
  select.classList.add("visually-hidden");
  setPressed(select.value);

  select.addEventListener("change", function (e) {
    setPressed(e.target.value);
    bus.emit("config:changed", { symbol: store.get().symbol, interval: e.target.value });
  });

  // --- scale / chart-type selects (F8) ---------------------------------------

  // Populate an empty <select> from a core vocabulary (single source).
  function fillOptions(el, values) {
    values.forEach(function (value) {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = value;
      el.appendChild(opt);
    });
  }

  const scaleSelect = document.getElementById("scale-mode");
  const typeSelect = document.getElementById("chart-type");
  if (scaleSelect) {
    fillOptions(scaleSelect, SCALE_MODES);
    scaleSelect.value = store.get().scaleMode || "linear";
    scaleSelect.addEventListener("change", function (e) {
      store.set({ scaleMode: e.target.value });
      // Light event: host option only — no rebuild, no refetch (#68).
      bus.emit("scale:changed", { mode: e.target.value });
    });
  }
  if (typeSelect) {
    fillOptions(typeSelect, CHART_TYPES);
    typeSelect.value = store.get().chartType || "candles";
    typeSelect.addEventListener("change", function (e) {
      store.set({ chartType: e.target.value });
      // Reuse the existing rebuild command (main owns rebuild + refetch).
      bus.emit("indicator:changed");
    });
  }

  // --- theme control (R27) ----------------------------------------------------
  // One resolve site (CT2/CT3): the toolbar turns a preference into the
  // RESOLVED value, writes ``data-theme`` (never "system") and hands the value
  // to main's ``onTheme`` callback. NO bus event (R20). ``matchMedia`` change
  // re-applies only while the preference stays "system" (CT3).
  const themeSelect = document.getElementById("theme");
  const mql =
    typeof window !== "undefined" && window.matchMedia
      ? window.matchMedia("(prefers-color-scheme: dark)")
      : null;

  function applyTheme(pref) {
    const resolved = resolveTheme(pref, prefersDark());
    document.documentElement.dataset.theme = resolved;
    return resolved;
  }

  function notifyTheme(pref) {
    const resolved = applyTheme(pref);
    if (typeof onTheme === "function") onTheme({ resolved: resolved, pref: pref });
    return resolved;
  }

  if (themeSelect) {
    themeSelect.value = store.get().theme || "system";
    themeSelect.addEventListener("change", function (e) {
      notifyTheme(e.target.value);
    });
  }
  if (mql) {
    // Re-resolve on an OS flip, but only while the user chose "system" (CT3).
    mql.addEventListener("change", function () {
      if (themeSelect && themeSelect.value === "system") notifyTheme("system");
    });
  }

  // --- sidebar collapse toggle (≤820px) ---------------------------------------
  const toggle = document.querySelector(".panel-toggle");
  const layout = document.querySelector(".market-layout");
  if (toggle && layout) {
    toggle.addEventListener("click", function () {
      const collapsed = layout.classList.toggle("panel-collapsed");
      toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    });
  }

  // Reflect a store interval (called by main on boot/preference restore).
  function setInterval(interval) {
    select.value = interval;
    setPressed(interval);
  }

  // Reflect the restored scale/type on boot (Slice 3 persists; defaults now).
  function setScaleMode(mode) {
    if (scaleSelect && mode) scaleSelect.value = mode;
  }
  function setChartType(type) {
    if (typeSelect && type) typeSelect.value = type;
  }

  // Reflect + apply a restored theme preference on boot (CT6). Called by main
  // BEFORE the first build so the shell tokens start themed; it returns the
  // RESOLVED value for main to seed ``state.theme`` (no onTheme/save on boot).
  function setTheme(pref) {
    if (themeSelect && pref) themeSelect.value = pref;
    return applyTheme(pref || (themeSelect ? themeSelect.value : "system"));
  }

  return { setInterval, setScaleMode, setChartType, setTheme };
}
