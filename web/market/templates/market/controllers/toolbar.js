// controllers/toolbar.js — pair buttons + interval select + interval chips +
// sidebar collapse toggle.
//
// DI factory (R14): ``createToolbar({store, bus, config})``. LEAF module — never
// imports main. A pair/interval change is a command on the bus
// (``config:changed``); main owns the switch. Owns only the toolbar DOM
// listeners.
//
// The chips are DERIVED from the retained ``<select id="interval">`` options
// (single source: no 4th interval copy) and the select is clipped, never
// display:none, so the E2E ``select_option`` calls stay actionable.
export function createToolbar({ store, bus }) {
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

  return { setInterval };
}
