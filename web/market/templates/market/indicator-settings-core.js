// indicator-settings-core.js — pure per-indicator STYLE schema (F2.1–F2.3).
//
// PURE ESM: imports nothing (no DOM, chart lib, network, or REGISTRY). Manual
// inspection of the source is a spec scenario, so keep this file import-free and
// free of indicator math. Deterministic and total: no input ever throws.
//
// Vocabulary: color (#rrggbb), lineWidth (int 1..4), precision (int 0..8). The
// default COLOR is derived from the host REGISTRY passed by the caller (single
// color source); this core hardcodes no color.

export const FIELDS = Object.freeze({
  color: Object.freeze({ type: "color" }),
  lineWidth: Object.freeze({ type: "int", min: 1, max: 4 }),
  precision: Object.freeze({ type: "int", min: 0, max: 8 }),
});

// Render vocabulary — mirrors chart-host REGISTRY keys (data, not an import).
export const TOKENS = Object.freeze([
  "sma",
  "ema",
  "bollinger",
  "vwap",
  "rsi",
  "macd",
  "stochastic",
  "atr",
  "volume",
]);

const NEUTRAL = "#888888";
const HEX = /^#[0-9a-fA-F]{6}$/;

// Internal only (spec: export exactly FIELDS/TOKENS/validate/normalize/defaultsFor).
function clamp(n, lo, hi, fallback) {
  const v = typeof n === "number" && isFinite(n) ? Math.trunc(n) : fallback;
  return Math.min(hi, Math.max(lo, v));
}

function registryColor(registry, token) {
  const entry = registry && registry[token];
  const series = entry && entry.series;
  const color = series && series[0] && series[0].color;
  return HEX.test(color) ? color : NEUTRAL;
}

// Default style for ``token``: color from the registry (single source), width 1,
// precision 2. Unknown token → neutral color, never throws.
export function defaultsFor(registry, token) {
  return { color: registryColor(registry, token), lineWidth: 1, precision: 2 };
}

// Total normalizer: known fields only, clamped; omitted/malformed → default.
export function normalize(token, raw, defaults) {
  const defs = defaults || { color: NEUTRAL, lineWidth: 1, precision: 2 };
  const input = raw && typeof raw === "object" ? raw : {};
  const color = HEX.test(input.color) ? input.color : defs.color;
  return {
    color: HEX.test(color) ? color : NEUTRAL,
    lineWidth: clamp(input.lineWidth, 1, 4, defs.lineWidth),
    precision: clamp(input.precision, 0, 8, defs.precision),
  };
}

// Strict validator (no clamping): {ok, errors}. Never throws.
export function validate(token, raw) {
  const errors = [];
  if (TOKENS.indexOf(token) === -1) errors.push("unknown token: " + token);
  if (raw === null || raw === undefined) return { ok: false, errors: errors.concat("style required") };
  if (typeof raw !== "object" || Array.isArray(raw)) {
    return { ok: false, errors: errors.concat("style must be an object") };
  }
  Object.keys(raw).forEach(function (key) {
    if (key === "color") {
      if (!HEX.test(raw.color)) errors.push("invalid color");
    } else if (key === "lineWidth") {
      const v = raw.lineWidth;
      if (!Number.isInteger(v) || v < 1 || v > 4) errors.push("invalid lineWidth");
    } else if (key === "precision") {
      const v = raw.precision;
      if (!Number.isInteger(v) || v < 0 || v > 8) errors.push("invalid precision");
    } else {
      errors.push("unknown key: " + key);
    }
  });
  return { ok: errors.length === 0, errors };
}
