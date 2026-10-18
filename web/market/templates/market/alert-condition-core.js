// alert-condition-core.js — pure price-condition mapping for the alert dialog.
//
// Framework-free (no DOM, no chart library, no network, no imports at all).
// The op strings MUST equal the server engine's `_OPS` (src/alert_rules.py:27,
// `("above", "below")`): the server re-validates through `parse_condition`, so a
// mismatch is a runtime 400. Every function is pure and NEVER throws.

var OPS = ["above", "below"];

function num(v) {
  return typeof v === "number" && isFinite(v) ? v : null;
}

function positive(v) {
  var n = num(v);
  return n !== null && n > 0 ? n : null;
}

// {op, level} -> fresh {type:"price", op, level} or null (the "do not POST" signal).
export function conditionFrom(fields) {
  if (!fields || typeof fields !== "object") return null;
  if (OPS.indexOf(fields.op) === -1) return null;
  var level = positive(fields.level);
  if (level === null) return null;
  return { type: "price", op: fields.op, level: level };
}

// Dialog text input -> positive number or null. Accepts "," as decimal separator.
export function levelFromInput(raw) {
  if (typeof raw !== "string") return null;
  var text = raw.trim().replace(",", ".");
  if (text === "") return null;
  var n = Number(text);
  return positive(n);
}

// Default op: above when the level is at/above the last close, else below.
// An unknown/non-finite close defaults to "above".
export function opFor(level, lastClose) {
  var lv = num(level);
  var close = num(lastClose);
  if (lv === null || close === null) return "above";
  return lv >= close ? "above" : "below";
}
