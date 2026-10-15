// Pure core tests — node --test (no DOM, no chart lib, no network).
// theme-core.js: theme vocabulary + v5 option tables. Imports nothing,
// deterministic, never throws (CT1). The v5 ColorType.Solid is a SYMBOL read at
// call time — a magic number must fail.
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import * as core from "../../web/market/templates/market/theme-core.js";

// DELIBERATELY NON-STANDARD Solid (99, never 0/1/2) so a numeric impl fails.
function withColorTypeSymbol(fn) {
  const prev = globalThis.LightweightCharts;
  globalThis.LightweightCharts = { ColorType: { Solid: 99 } };
  try {
    return fn(99);
  } finally {
    if (prev === undefined) delete globalThis.LightweightCharts;
    else globalThis.LightweightCharts = prev;
  }
}

// WCAG 2.x relative-luminance contrast — pure test helper (design § Contrast).
function srgbChannel(c) {
  const v = c / 255;
  return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
}
function luminance(hex) {
  const h = hex.replace("#", "");
  return (
    0.2126 * srgbChannel(parseInt(h.slice(0, 2), 16)) +
    0.7152 * srgbChannel(parseInt(h.slice(2, 4), 16)) +
    0.0722 * srgbChannel(parseInt(h.slice(4, 6), 16))
  );
}
function contrastRatio(a, b) {
  const la = luminance(a);
  const lb = luminance(b);
  const hi = Math.max(la, lb);
  const lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}

// --- resolve ---------------------------------------------------------------

test("resolve: explicit values pass through regardless of the OS", () => {
  assert.strictEqual(core.resolve("light", true), "light");
  assert.strictEqual(core.resolve("light", false), "light");
  assert.strictEqual(core.resolve("dark", false), "dark");
  assert.strictEqual(core.resolve("dark", true), "dark");
});

test("resolve: system follows prefersDark", () => {
  assert.strictEqual(core.resolve("system", true), "dark");
  assert.strictEqual(core.resolve("system", false), "light");
});

test("resolve: unknown / missing degrades to system behavior, never throws", () => {
  assert.strictEqual(core.resolve("bogus", true), "dark");
  assert.strictEqual(core.resolve("bogus", false), "light");
  assert.strictEqual(core.resolve(null, undefined), "light");
  assert.strictEqual(core.resolve(undefined, undefined), "light");
  assert.strictEqual(core.resolve(undefined, true), "dark");
  assert.doesNotThrow(() => core.resolve({}, null));
});

// --- optionsFor ------------------------------------------------------------

test("optionsFor: exact v5 shape for both themes", () => {
  withColorTypeSymbol((solid) => {
    const groups = ["layout", "grid", "crosshair", "rightPriceScale", "timeScale"];
    for (const theme of ["dark", "light"]) {
      const o = core.optionsFor(theme);
      assert.deepStrictEqual(Object.keys(o), groups, theme);
      assert.deepStrictEqual(
        o.layout.background,
        { type: solid, color: o.layout.background.color },
        theme,
      );
      assert.strictEqual(typeof o.layout.textColor, "string", theme);
      assert.strictEqual(typeof o.grid.vertLines.color, "string", theme);
      assert.strictEqual(typeof o.grid.horzLines.color, "string", theme);
      assert.strictEqual(typeof o.crosshair.vertLine.color, "string", theme);
      assert.strictEqual(typeof o.crosshair.vertLine.labelBackgroundColor, "string", theme);
      assert.strictEqual(typeof o.crosshair.horzLine.color, "string", theme);
      assert.strictEqual(typeof o.rightPriceScale.borderColor, "string", theme);
      assert.strictEqual(typeof o.timeScale.borderColor, "string", theme);
    }
  });
});

test("optionsFor: frozen color sets (contrast-checked per theme)", () => {
  withColorTypeSymbol(() => {
    const dark = core.optionsFor("dark");
    assert.strictEqual(dark.layout.background.color, "#0e1117");
    assert.strictEqual(dark.layout.textColor, "#e6edf3");
    assert.strictEqual(dark.grid.vertLines.color, "#5a6a80");
    assert.strictEqual(dark.grid.horzLines.color, "#5a6a80");
    assert.strictEqual(dark.crosshair.vertLine.color, "#8b949e");
    assert.strictEqual(dark.crosshair.vertLine.labelBackgroundColor, "#1c2230");
    assert.strictEqual(dark.crosshair.horzLine.labelBackgroundColor, "#1c2230");
    assert.strictEqual(dark.rightPriceScale.borderColor, "#5a6a80");
    assert.strictEqual(dark.timeScale.borderColor, "#5a6a80");

    const light = core.optionsFor("light");
    assert.strictEqual(light.layout.background.color, "#ffffff");
    assert.strictEqual(light.layout.textColor, "#1f2328");
    assert.strictEqual(light.grid.vertLines.color, "#7d8794");
    assert.strictEqual(light.crosshair.vertLine.color, "#57606a");
    assert.strictEqual(light.crosshair.vertLine.labelBackgroundColor, "#eaeef2");
    assert.strictEqual(light.rightPriceScale.borderColor, "#7d8794");
    assert.strictEqual(light.timeScale.borderColor, "#7d8794");
  });
});

test("optionsFor: the background type is the SYMBOL, never a magic number", () => {
  withColorTypeSymbol((solid) => {
    assert.strictEqual(core.optionsFor("dark").layout.background.type, solid);
    assert.strictEqual(core.optionsFor("light").layout.background.type, solid);
    assert.notStrictEqual(core.optionsFor("dark").layout.background.type, 0);
  });
});

test("optionsFor: unknown / missing falls back to the dark set, never throws", () => {
  withColorTypeSymbol(() => {
    const dark = core.optionsFor("dark");
    assert.deepStrictEqual(core.optionsFor("bogus"), dark);
    assert.deepStrictEqual(core.optionsFor(undefined), dark);
    assert.deepStrictEqual(core.optionsFor(null), dark);
    assert.deepStrictEqual(core.optionsFor("system"), dark);
    assert.doesNotThrow(() => core.optionsFor({}));
  });
});

test("optionsFor: no ColorType global still yields a usable solid type", () => {
  const prev = globalThis.LightweightCharts;
  delete globalThis.LightweightCharts;
  try {
    const o = core.optionsFor("dark");
    assert.ok(o.layout.background.type);
    assert.doesNotThrow(() => core.optionsFor("light"));
  } finally {
    if (prev !== undefined) globalThis.LightweightCharts = prev;
  }
});

// --- contrast / determinism / purity ---------------------------------------

test("contrast: axis text vs background >= 4.5:1 in both themes", () => {
  withColorTypeSymbol(() => {
    for (const theme of ["dark", "light"]) {
      const o = core.optionsFor(theme);
      const ratio = contrastRatio(o.layout.textColor, o.layout.background.color);
      assert.ok(ratio >= 4.5, `${theme} text contrast ${ratio}`);
    }
  });
});

test("contrast: grid / border / crosshair >= 3:1 (non-text floor)", () => {
  withColorTypeSymbol(() => {
    for (const theme of ["dark", "light"]) {
      const o = core.optionsFor(theme);
      const bg = o.layout.background.color;
      for (const hex of [
        o.grid.vertLines.color,
        o.rightPriceScale.borderColor,
        o.timeScale.borderColor,
      ]) {
        assert.ok(contrastRatio(hex, bg) >= 3, `${theme} ${hex}`);
      }
    }
  });
});

test("determinism: identical inputs -> identical output", () => {
  withColorTypeSymbol(() => {
    assert.deepStrictEqual(core.optionsFor("dark"), core.optionsFor("dark"));
    assert.strictEqual(core.resolve("system", true), core.resolve("system", true));
  });
});

test("purity: the module imports nothing", () => {
  const src = readFileSync(
    fileURLToPath(new URL("../../web/market/templates/market/theme-core.js", import.meta.url)),
    "utf8",
  );
  assert.doesNotMatch(src, /^\s*import\b/m, "no ESM import");
  assert.doesNotMatch(src, /\brequire\s*\(/, "no CommonJS require");
});
