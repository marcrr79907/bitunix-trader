// alert-ui-core.js — small pure helpers shared by the alerts controller.
//
// Extracted from controllers/alerts.js to keep that module comfortably under
// the 300-line ceiling. No DOM, no chart library, no network: only the
// interval-eligibility vocabulary and the two display formatters the bell and
// dialog need (csrfToken stays in the controller — it reads the DOM).
//
// The eval-able set MUST match the server's CANDLE_INTERVALS
// (trading/candles.py): a rule on any other interval can never fire.

export const EVALUABLE = ["5m", "15m", "1h", "2h", "4h", "1d", "1w", "1M"];

// A rule on an interval the worker never evaluates can never fire.
export function eligible(interval) {
  return EVALUABLE.indexOf(interval) !== -1;
}

export function reasonText(interval) {
  return "Alerts cannot fire on the " + interval + " interval";
}

// A price with at most 6 decimals; a missing/NaN value degrades to an en dash.
export function fmtPrice(v) {
  return typeof v === "number" && isFinite(v) ? String(Math.round(v * 1e6) / 1e6) : "\u2013";
}
