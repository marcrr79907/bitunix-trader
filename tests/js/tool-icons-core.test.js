// Pure core tests — node --test (no DOM, no chart lib, no network).
// tool-icons-core.js: grouped drawing-tool vocabulary + inline-SVG strings
// (F5 S2, R1/R4). Imports nothing; deterministic.
//
// CSP discipline (design D9): icons are plain strings built locally, carrying
// NO event attribute — an inline `on*` would be an inline handler under strict
// CSP, the exact thing the market page forbids.
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import * as core from "../../web/market/templates/market/tool-icons-core.js";
import { DRAWING_KINDS } from "../../web/market/templates/market/drawing-core.js";

test("TOOL_GROUPS: 5 kinds grouped 2/1/1/1 (Lines/Fib/Shapes/Text)", () => {
  const labels = core.TOOL_GROUPS.map((g) => g.label);
  assert.deepStrictEqual(labels, ["Lines", "Fib", "Shapes", "Text"]);
  assert.deepStrictEqual(
    core.TOOL_GROUPS.map((g) => g.kinds.length),
    [2, 1, 1, 1],
  );
  assert.deepStrictEqual(core.TOOL_GROUPS[0].kinds, ["hline", "trendline"]);
  assert.deepStrictEqual(core.TOOL_GROUPS[3].kinds, ["text"]);
});

test("TOOL_GROUPS covers exactly the drawing kinds (no gap, no duplicate)", () => {
  const grouped = core.TOOL_GROUPS.flatMap((g) => g.kinds);
  assert.strictEqual(grouped.length, 5);
  assert.deepStrictEqual([...grouped].sort(), [...DRAWING_KINDS].sort());
  assert.strictEqual(new Set(grouped).size, 5);
});

test("TREE_GROUPS: the object-tree group vocab (drawings + indicators)", () => {
  assert.deepStrictEqual(
    core.TREE_GROUPS.map((g) => g.label),
    ["Drawings", "Indicators"],
  );
});

test("groupLabel: returns the accessible group name", () => {
  assert.strictEqual(core.groupLabel(core.TOOL_GROUPS[0]), "Lines");
  assert.strictEqual(core.groupLabel(core.TOOL_GROUPS[2]), "Shapes");
  assert.strictEqual(core.groupLabel(core.TREE_GROUPS[1]), "Indicators");
});

test("iconFor: every drawing kind yields a valid, CSP-clean inline SVG", () => {
  DRAWING_KINDS.forEach((kind) => {
    const svg = core.iconFor(kind);
    assert.strictEqual(typeof svg, "string", kind);
    assert.match(svg, /^<svg\b/, kind);
    assert.match(svg, /<\/svg>$/, kind);
    assert.match(svg, /viewBox=/, kind);
    assert.match(svg, /currentColor/, kind); // follows the theme (R10)
    assert.match(svg, /aria-hidden="true"/, kind); // decorative: the button names it
    // The load-bearing CSP assertion: no event attribute anywhere.
    assert.doesNotMatch(svg, /\son[a-z]+\s*=/i, kind);
    assert.doesNotMatch(svg, /<script/i, kind);
  });
});

test("iconFor: distinct kinds yield distinct icons (no copy-paste stub)", () => {
  const icons = DRAWING_KINDS.map((k) => core.iconFor(k));
  assert.strictEqual(new Set(icons).size, DRAWING_KINDS.length);
});

test("iconFor: an unknown kind degrades to an empty string, never throws", () => {
  assert.strictEqual(core.iconFor("not-a-kind"), "");
  assert.strictEqual(core.iconFor(undefined), "");
});

test("row-control glyphs: every exported object-tree icon is CSP-clean SVG", () => {
  // F5 FIX-3 hoisted the eye/lock/delete/gear strings here (their proper home).
  ["EYE_ON", "EYE_OFF", "LOCK_ON", "LOCK_OFF", "TRASH", "GEAR"].forEach((name) => {
    const svg = core[name];
    assert.strictEqual(typeof svg, "string", name);
    assert.match(svg, /^<svg\b/, name);
    assert.match(svg, /<\/svg>$/, name);
    assert.match(svg, /currentColor/, name);
    assert.doesNotMatch(svg, /\son[a-z]+\s*=/i, name); // no inline handler
    assert.doesNotMatch(svg, /<script/i, name);
  });
  // The on/off pairs differ (state is not a single static glyph).
  assert.notStrictEqual(core.EYE_ON, core.EYE_OFF);
  assert.notStrictEqual(core.LOCK_ON, core.LOCK_OFF);
});

test("purity: the icon core imports nothing", () => {
  const src = readFileSync(
    fileURLToPath(
      new URL("../../web/market/templates/market/tool-icons-core.js", import.meta.url),
    ),
    "utf8",
  );
  assert.doesNotMatch(src, /^\s*import\b/m, "no ESM import");
  assert.doesNotMatch(src, /\brequire\s*\(/, "no CommonJS require");
});
