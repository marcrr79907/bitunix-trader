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

// A single marker per armed/fired rule; inactive/none yield no marker.
// fired -> last_fired_at (epoch s), falling back to anchorTime when unusable;
// armed -> anchorTime. A missing anchor drops the rule (no synthetic time).
export function markersFor(rules, anchorTime) {
  if (!Array.isArray(rules)) return [];
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
    var time = state === "fired" ? num(rule.last_fired_at) : null;
    if (time === null) {
      if (anchor === null) continue;
      time = anchor;
    }
    var fired = state === "fired";
    out.push({
      time: time,
      position: fired ? "aboveBar" : "belowBar",
      shape: fired ? "arrowDown" : "circle",
      text: (fired ? "F " : "A ") + level,
      color: fired ? COLORS.fired : COLORS.armed,
    });
  }
  return out;
}
