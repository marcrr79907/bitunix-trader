// controllers/position-seed.js — the "Position from setup" affordance (F6 #194).
//
// DI factory ``createPositionSeed({bus, onSeed})``. LEAF module — never imports
// main. Owns the SMC setups cache and the ``#position-seed`` button state: the
// button is DISABLED until ``smc:loaded`` provides at least one setup (an empty
// payload re-disables it), so a click can never silently no-op. On click it
// copies the most recent setup's levels VERBATIM (single source; the client
// never recomputes SMC levels) into ``onSeed(points)``. Extracted from
// drawings.js to keep that module under the 300-line ceiling (R14).
export function createPositionSeed({ bus, onSeed }) {
  let setups = []; // F6 (D5): SMC setups cached from ``smc:loaded`` (verbatim)
  const button = document.getElementById("position-seed");

  function render() {
    if (button) button.disabled = setups.length === 0;
  }

  bus.on("smc:loaded", function (p) {
    setups = (p && p.payload && p.payload.setups) || [];
    render();
  });

  function seedMostRecent() {
    const setup = setups[setups.length - 1];
    if (!setup) return; // no setup -> no-op (belt and braces; the button is disabled)
    onSeed({
      entry: { time: setup.time, price: setup.entry },
      stop: setup.stop,
      take_profit: setup.take_profit,
    });
  }

  if (button) button.addEventListener("click", seedMostRecent);

  // Initial state: disabled until a setup arrives.
  render();

  return { seedMostRecent };
}
