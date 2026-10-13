// chart-store.js — observable UI/config STATE ONLY.
//
// #68 hard boundary: the store holds configuration + UI state and NEVER candle
// data. Candle data lives exclusively in chart-host.js (the single write path).
// The state keys are frozen to the design vocabulary; any other key in a patch
// (e.g. ``candles``) is silently dropped.
//
//   state = { symbol, interval, indicators, params, smc, tool }
//
// API: get() -> state (same reference) | set(patch) -> merge + emit |
//      subscribe(fn) -> unsubscribe.
export const STORE_KEYS = ["symbol", "interval", "indicators", "params", "smc", "tool"];

export function createStore(initial) {
  const state = {};
  STORE_KEYS.forEach(function (key) {
    state[key] = initial ? initial[key] : undefined;
  });

  const listeners = [];

  function get() {
    return state;
  }

  function set(patch) {
    if (patch) {
      STORE_KEYS.forEach(function (key) {
        if (key in patch) state[key] = patch[key];
      });
    }
    listeners.slice().forEach(function (fn) {
      fn(state);
    });
  }

  function subscribe(fn) {
    listeners.push(fn);
    return function unsubscribe() {
      const i = listeners.indexOf(fn);
      if (i !== -1) listeners.splice(i, 1);
    };
  }

  return { get, set, subscribe };
}
