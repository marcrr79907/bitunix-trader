// alert-markers-core.js — pure state + LWC v5 marker projection for alert rules.
//
// Framework-free (no DOM, no chart library, no network, no global state, no
// imports at all), mirroring position-core.js and the project's "pure core at
// the center, adapters at the edges" rule. A native ESM module: imported in
// Node by the tests and in the browser by controllers/alerts.js (S3).
//
// `stateOf` reproduces the frozen S4 precedence (market/views.py:104-116) per
// rule: fired (last_fired_at) > armed (is_active) > inactive. `markersFor` maps
// rules to LWC series markers; a marker's `time` MUST be a real data point, so
// armed rules anchor to the newest loaded candle supplied by the caller.
// Every function is pure and NEVER throws; off-value input degrades to []/none.

export const COLORS = { armed: "#2962ff", fired: "#ef5350" };

function num(v) {
  return typeof v === "number" && isFinite(v) ? v : null;
}

// A usable injected color, else the state's fallback literal (F10 UI #232: the
// shell tokens are resolved by the controller; the core stays pure and keeps
// these literals so a DOM-less caller still paints something).
function colorOf(override, fallback) {
  return typeof override === "string" && override ? override : fallback;
}

// rule -> "fired" | "armed" | "inactive" | "none".
// null/undefined -> "none"; any other non-object -> "inactive" (a rule exists).
export function stateOf(rule) {
  if (rule === null || rule === undefined) return "none";
  if (typeof rule !== "object") return "inactive";
  // Mirrors views.py `last_fired_at is not None` exactly: any non-null value is
  // fired; a non-finite one still gets the anchor fallback in markersFor.
  if (rule.last_fired_at !== null && rule.last_fired_at !== undefined) return "fired";
  if (rule.is_active === true) return "armed";
  return "inactive";
}

// Accessible count summary for ``#alert-status`` (design-system R6): markers are
// canvas, so the fired/armed tally is the only announced state. Pure: returns
// the already-formatted sentence, or "" when there is nothing to announce.
export function summaryOf(rules) {
  if (!Array.isArray(rules)) return "";
  var fired = 0;
  var armed = 0;
  for (var i = 0; i < rules.length; i++) {
    var state = stateOf(rules[i]);
    if (state === "fired") fired += 1;
    else if (state === "armed") armed += 1;
  }
  var total = fired + armed;
  if (!total) return "";
  var noun = total === 1 ? " alert: " : " alerts: ";
  return total + noun + fired + " fired, " + armed + " armed";
}

// A single marker per armed/fired rule; inactive/none yield no marker.
// fired -> last_fired_at (epoch s); armed -> anchorTime. A marker whose time is
// not a real data point MUST be dropped (spec chart-alerts R4): a fired rule
// whose last_fired_at is off-series or unusable yields no marker — LWC v5 would
// discard it anyway, and faking the newest-candle time would misplace it. The
// fired state stays visible on the /signals/ pair badge.
// `colors` ({armed, fired}) is optional: the controller passes the shell tokens
// it resolved at render time; a missing/invalid entry falls back to COLORS.
export function markersFor(rules, anchorTime, colors) {
  if (!Array.isArray(rules)) return [];
  var map = colors && typeof colors === "object" ? colors : {};
  var firedColor = colorOf(map.fired, COLORS.fired);
  var armedColor = colorOf(map.armed, COLORS.armed);
  var anchor = num(anchorTime);
  var out = [];
  for (var i = 0; i < rules.length; i++) {
    var rule = rules[i];
    if (!rule || typeof rule !== "object") continue;
    var state = stateOf(rule);
    if (state !== "fired" && state !== "armed") continue;
    var condition = rule.condition;
    var level = condition && typeof condition === "object" ? num(condition.level) : null;
    if (level === null) continue;
    var fired = state === "fired";
    var time = fired ? num(rule.last_fired_at) : anchor;
    if (time === null) continue; // off-series / missing anchor -> drop
    out.push({
      time: time,
      position: fired ? "aboveBar" : "belowBar",
      shape: fired ? "arrowDown" : "circle",
      text: (fired ? "F " : "A ") + level,
      color: fired ? firedColor : armedColor,
    });
  }
  return out;
}
