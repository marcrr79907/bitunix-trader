// chart-bus.js — tiny event bus (no lib).
//
// Commands main subscribes to: config:changed {symbol,interval}, indicator:changed,
// scale:changed {mode}, indicator:visibility {token,visible}. Notifications:
// layout:loaded, chart:built, history:loaded, candle:closed, drawings:changed,
// smc:loaded, smc:toggles, ready.
//
// API: on(name, fn) -> unsubscribe | off(name, fn) | emit(name, payload).
export const EVENTS = Object.freeze({
  configChanged: "config:changed",
  indicatorChanged: "indicator:changed",
  scaleChanged: "scale:changed",
  // F5 S3 (R20): the ONE new event. Routed by main to the option-only
  // setSeriesVisible (#68) — never the indicator:changed rebuild/setData path.
  indicatorVisibility: "indicator:visibility",
  layoutLoaded: "layout:loaded",
  chartBuilt: "chart:built",
  historyLoaded: "history:loaded",
  candleClosed: "candle:closed",
  drawingsChanged: "drawings:changed",
  smcLoaded: "smc:loaded",
  smcToggles: "smc:toggles",
  ready: "ready",
});

export function createBus() {
  const listeners = new Map();

  function on(event, fn) {
    if (!listeners.has(event)) listeners.set(event, []);
    listeners.get(event).push(fn);
    return function unsubscribe() {
      off(event, fn);
    };
  }

  function off(event, fn) {
    const arr = listeners.get(event);
    if (!arr) return;
    const i = arr.indexOf(fn);
    if (i !== -1) arr.splice(i, 1);
  }

  function emit(event, payload) {
    const arr = listeners.get(event);
    if (!arr || !arr.length) return;
    // Snapshot: a listener may subscribe/unsubscribe during the emit.
    arr.slice().forEach(function (fn) {
      fn(payload);
    });
  }

  return { on, off, emit };
}
