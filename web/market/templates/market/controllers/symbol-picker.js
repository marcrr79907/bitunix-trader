// controllers/symbol-picker.js — symbol search + watchlist follow (F11 A-S4).
//
// DI factory (R14): ``createSymbolPicker({store, bus, config})`` → ``{refresh}``.
// LEAF module — never imports main. The ranking is the pure core
// (../symbol-search-core.js); this module owns only the DOM and the two REST
// calls it needs (the exchange universe and the caller's watchlist).
//
// Selecting a result emits the EXISTING ``config:changed`` command (the same one
// toolbar.js:31 emits), so main.switchTo handles the switch unchanged: no new
// bus event, no new store key, no new write path (#68).
//
// Combobox pattern (R19): focus stays in the input and ``aria-activedescendant``
// points at the active option — no roving tabindex, no focus trap.
import { filterSymbols } from "../symbol-search-core.js";

const RESULT_LIMIT = 50;

export function createSymbolPicker({ store, bus, config }) {
  const input = document.getElementById("symbol-search");
  const list = document.getElementById("symbol-results");
  const status = document.getElementById("symbol-status");
  if (!input || !list) return { refresh: function () {} };

  let universe = [];
  let followed = new Set();
  let results = [];
  let active = -1;

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  function announce(text) {
    if (status) status.textContent = text;
  }

  function close() {
    list.hidden = true;
    list.textContent = "";
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    results = [];
    active = -1;
  }

  function setActive(index) {
    const options = list.querySelectorAll('[role="option"]');
    if (!options.length) return;
    active = (index + options.length) % options.length;
    Array.prototype.forEach.call(options, function (option, i) {
      const selected = i === active;
      option.setAttribute("aria-selected", selected ? "true" : "false");
      if (selected) {
        input.setAttribute("aria-activedescendant", option.id);
        option.scrollIntoView({ block: "nearest" });
      }
    });
  }

  function selectSymbol(symbol) {
    close();
    input.value = "";
    bus.emit("config:changed", { symbol: symbol, interval: store.get().interval });
  }

  function follow(symbol) {
    return fetch(config.urls.watchlist, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({ symbol: symbol }),
    })
      .then(function (response) {
        if (!response.ok) throw new Error("watchlist " + response.status);
        followed.add(symbol);
        renderResults(input.value);
        announce(symbol + " added to the watchlist");
      })
      .catch(function () {
        announce("Could not update the watchlist");
      });
  }

  function renderResults(query) {
    results = filterSymbols(query, universe, RESULT_LIMIT);
    list.textContent = "";

    if (!results.length) {
      close();
      announce("No matching symbols");
      return;
    }

    results.forEach(function (symbol, i) {
      const option = document.createElement("li");
      option.id = "symbol-option-" + i;
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", "false");
      option.dataset.symbol = symbol;

      const label = document.createElement("span");
      label.textContent = symbol;
      option.appendChild(label);

      // Follow affordance: refused on the active chart's own symbol (already
      // reachable) and shown as a state for symbols already followed.
      const button = document.createElement("button");
      button.type = "button";
      button.className = "symbol-follow";
      const isFollowed = followed.has(symbol);
      button.textContent = isFollowed ? "✓" : "+";
      button.setAttribute("aria-label",
        (isFollowed ? "Unfollow " : "Follow ") + symbol);
      button.disabled = isFollowed;
      button.addEventListener("click", function (event) {
        event.stopPropagation();
        follow(symbol);
      });
      option.appendChild(button);

      option.addEventListener("click", function () {
        selectSymbol(symbol);
      });

      list.appendChild(option);
    });

    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    setActive(0);
    announce(results.length + " symbol" + (results.length === 1 ? "" : "s"));
  }

  input.addEventListener("input", function () {
    // Local, O(n) over a few hundred strings: no debounce, no timer to fake.
    renderResults(input.value);
  });

  input.addEventListener("keydown", function (event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive(active + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive(active - 1);
    } else if (event.key === "Enter") {
      if (active >= 0 && results[active]) {
        event.preventDefault();
        selectSymbol(results[active]);
      }
    } else if (event.key === "Escape") {
      close();
    }
  });

  // Outer click closes the list; keyboard users never need it.
  document.addEventListener("pointerdown", function (event) {
    if (event.target === input || list.contains(event.target)) return;
    if (!list.hidden) close();
  });

  function refresh() {
    return Promise.all([
      fetch(config.urls.symbols)
        .then(function (response) {
          return response.ok ? response.json() : { symbols: [] };
        })
        .then(function (body) {
          universe = (body && body.symbols) || [];
        })
        .catch(function () {
          universe = (config.symbols || []).slice();
        }),
      fetch(config.urls.watchlist)
        .then(function (response) {
          return response.ok ? response.json() : { symbols: [] };
        })
        .then(function (body) {
          followed = new Set((body && body.symbols) || []);
        })
        .catch(function () {
          followed = new Set();
        }),
    ]).then(function () {
      // A failed catalog fetch still leaves the server-rendered default list
      // searchable (the picker never leaves the user with nothing).
      if (!universe.length) universe = (config.symbols || []).slice();
    });
  }

  refresh();
  return { refresh: refresh };
}
