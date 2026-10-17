// theme-core.js — pure theme core (CT1). Imports nothing, deterministic,
// never throws.
//
// Owns the single source of the v5.2.0 option tables for each resolved theme so
// chart-host.js stays under the ~300-line ceiling (R14). The shell token layer
// mirrors these literals via [data-theme] (theme.css); this core is the canvas
// source. The v5 ColorType.Solid member is read at call time as a SYMBOL (never
// a magic number), mirroring the PriceScaleMode discipline in chart-host.js.

// Frozen vocab: the preference value; "system" follows the media query.
const THEMES = Object.freeze(["light", "dark", "system"]);

// Frozen v5 option tables. Alpha is never used; every value is a full literal
// (v5 applyOptions must never receive undefined). Colors per design.md.
const TABLES = Object.freeze({
  dark: Object.freeze({
    layout: Object.freeze({
      background: Object.freeze({ type: "solid", color: "#0e1117" }),
      textColor: "#e6edf3",
    }),
    grid: Object.freeze({
      vertLines: Object.freeze({ color: "#5a6a80" }),
      horzLines: Object.freeze({ color: "#5a6a80" }),
    }),
    crosshair: Object.freeze({
      vertLine: Object.freeze({ color: "#8b949e", labelBackgroundColor: "#1c2230" }),
      horzLine: Object.freeze({ color: "#8b949e", labelBackgroundColor: "#1c2230" }),
    }),
    rightPriceScale: Object.freeze({ borderColor: "#5a6a80" }),
    timeScale: Object.freeze({ borderColor: "#5a6a80" }),
  }),
  light: Object.freeze({
    layout: Object.freeze({
      background: Object.freeze({ type: "solid", color: "#ffffff" }),
      textColor: "#1f2328",
    }),
    grid: Object.freeze({
      vertLines: Object.freeze({ color: "#7d8794" }),
      horzLines: Object.freeze({ color: "#7d8794" }),
    }),
    crosshair: Object.freeze({
      vertLine: Object.freeze({ color: "#57606a", labelBackgroundColor: "#eaeef2" }),
      horzLine: Object.freeze({ color: "#57606a", labelBackgroundColor: "#eaeef2" }),
    }),
    rightPriceScale: Object.freeze({ borderColor: "#7d8794" }),
    timeScale: Object.freeze({ borderColor: "#7d8794" }),
  }),
});

// Resolve the ColorType.Solid member at call time. Falls back to the string
// "solid" when the lib/global is absent so the pure core stays testable and
// never throws (unknown -> dark set still carries a usable background).
function solidColorType() {
  try {
    const ct = globalThis.LightweightCharts && globalThis.LightweightCharts.ColorType;
    if (ct && ct.Solid !== undefined) return ct.Solid;
  } catch (_e) {
    /* never throw */
  }
  return "solid";
}

// F6 UI #193 (R9): resolve a shell design token (e.g. "--up") to its computed
// value, so canvas paint follows the light/dark palette instead of a literal.
// Falls back to ``fallback`` when the DOM or the var is absent, so Node tests
// without a DOM (and an unthemed shell) keep the byte-identical literal.
export function token(name, fallback) {
  try {
    const v = getComputedStyle(document.documentElement)
      .getPropertyValue(name)
      .trim();
    return v || fallback;
  } catch (_e) {
    return fallback;
  }
}

// OS dark preference (for "system"). Reads the global like solidColorType;
// never throws (absent matchMedia -> light).
export function prefersDark() {
  try {
    return !!(
      globalThis.matchMedia &&
      globalThis.matchMedia("(prefers-color-scheme: dark)").matches
    );
  } catch (_e) {
    return false;
  }
}

// Resolve a preference + OS flag to exactly "light" | "dark". Unknown, missing
// or non-string preference -> system behavior. A non-true prefersDark -> light.
export function resolve(theme, prefersDark) {
  if (theme === "light" || theme === "dark") return theme;
  if (theme === "system" || !THEMES.includes(theme)) {
    return prefersDark === true ? "dark" : "light";
  }
  return prefersDark === true ? "dark" : "light";
}

// Return the v5 option set for a RESOLVED value ("light"/"dark"). Unknown ->
// the dark set. Never throws. The background type is the live ColorType.Solid
// symbol, re-resolved on every call.
export function optionsFor(resolved) {
  const table = resolved === "light" ? TABLES.light : TABLES.dark;
  return {
    layout: {
      background: { type: solidColorType(), color: table.layout.background.color },
      textColor: table.layout.textColor,
    },
    grid: {
      vertLines: { color: table.grid.vertLines.color },
      horzLines: { color: table.grid.horzLines.color },
    },
    crosshair: {
      vertLine: {
        color: table.crosshair.vertLine.color,
        labelBackgroundColor: table.crosshair.vertLine.labelBackgroundColor,
      },
      horzLine: {
        color: table.crosshair.horzLine.color,
        labelBackgroundColor: table.crosshair.horzLine.labelBackgroundColor,
      },
    },
    rightPriceScale: { borderColor: table.rightPriceScale.borderColor },
    timeScale: { borderColor: table.timeScale.borderColor },
  };
}
