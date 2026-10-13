// controllers/toolbar.js — pair buttons + interval select.
//
// DI factory (R14): ``create({store, bus, config})``. LEAF module — never imports
// main. A pair/interval change is a command on the bus (``config:changed``);
// main owns the switch. Owns only the toolbar DOM listeners.
export function createToolbar({ store, bus }) {
  const state = store.get();

  document.querySelectorAll(".pair").forEach(function (btn) {
    btn.addEventListener("click", function () {
      bus.emit("config:changed", { symbol: btn.dataset.symbol, interval: state.interval });
    });
  });
  document.getElementById("interval").addEventListener("change", function (e) {
    bus.emit("config:changed", { symbol: state.symbol, interval: e.target.value });
  });

  return {};
}
