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

test("TOOL_GROUPS: F9 groups the 15 instruments 6/4/1/2/1/1", () => {
  const labels = core.TOOL_GROUPS.map((g) => g.label);
  assert.deepStrictEqual(labels, ["Lines", "Fib", "Shapes", "Text", "Measure", "Positions"]);
  assert.deepStrictEqual(
    core.TOOL_GROUPS.map((g) => g.kinds.length),
    [6, 4, 1, 2, 1, 1],
  );
  assert.deepStrictEqual(
    core.TOOL_GROUPS[0].kinds,
    ["hline", "trendline", "ray", "vline", "channel", "price"],
  );
  assert.deepStrictEqual(
    core.TOOL_GROUPS[1].kinds,
    ["fib", "fib_ext", "fib_time", "fib_zone"],
  );
  assert.deepStrictEqual(core.TOOL_GROUPS[2].kinds, ["rect"]);
  assert.deepStrictEqual(core.TOOL_GROUPS[3].kinds, ["text", "callout"]);
  assert.deepStrictEqual(core.TOOL_GROUPS[4], { label: "Measure", kinds: ["measure"] });
  assert.deepStrictEqual(core.TOOL_GROUPS[5], { label: "Positions", kinds: ["position"] });
});

test("TOOL_GROUPS covers the drawing kinds + measure (no gap, no duplicate)", () => {
  const grouped = core.TOOL_GROUPS.flatMap((g) => g.kinds);
  assert.strictEqual(grouped.length, 15);
  // Every persisted drawing kind is grouped (no gap)...
  DRAWING_KINDS.forEach((kind) => assert.ok(grouped.includes(kind), kind));
  // ...plus the ephemeral ``measure`` tool and the ``position`` group.
  assert.ok(grouped.includes("measure"));
  assert.ok(grouped.includes("position"));
  assert.strictEqual(new Set(grouped).size, grouped.length); // no duplicate
});

test("F9 icons: the eight new tools yield valid, CSP-clean inline SVGs (R1)", () => {
  const F9 = ["ray", "vline", "channel", "price", "callout", "fib_ext", "fib_time", "fib_zone"];
  const svgs = F9.map((kind) => core.iconFor(kind));
  F9.forEach((kind, i) => {
    const svg = svgs[i];
    assert.strictEqual(typeof svg, "string", kind);
    assert.match(svg, /^<svg\b/, kind);
    assert.match(svg, /<\/svg>$/, kind);
    assert.match(svg, /currentColor/, kind);
    assert.doesNotMatch(svg, /\son[a-z]+\s*=/i, kind); // no inline handler (CSP)
    assert.doesNotMatch(svg, /<script/i, kind);
  });
  // All eight are distinct (each tool has its own glyph).
  assert.strictEqual(new Set(svgs).size, F9.length);
});

test("F6 icons: measure + position yield distinct, CSP-clean inline SVGs (R1)", () => {
  ["measure", "position"].forEach((kind) => {
    const svg = core.iconFor(kind);
    assert.match(svg, /^<svg\b/, kind);
    assert.match(svg, /currentColor/, kind);
    assert.doesNotMatch(svg, /\son[a-z]+\s*=/i, kind);
  });
  assert.notStrictEqual(core.iconFor("measure"), core.iconFor("position"));
});

test("TREE_GROUPS: the object-tree group vocab (drawings + indicators)", () => {
  assert.deepStrictEqual(
    core.TREE_GROUPS.map((g) => g.label),
    ["Drawings", "Indicators"],
  );
  // F9 S3: the tree's Drawings group lists every drawing kind.
  DRAWING_KINDS.forEach((kind) =>
    assert.ok(core.TREE_GROUPS[0].kinds.includes(kind), kind));
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

// --- F9 R2 (#223): human labels shared by the toolbar + the object tree ------

test("TOOL_LABELS covers every drawing kind + measure with a human name", () => {
  const kinds = core.TOOL_GROUPS.flatMap((g) => g.kinds);
  assert.deepStrictEqual(Object.keys(core.TOOL_LABELS).sort(), kinds.slice().sort());
  kinds.forEach((kind) => {
    assert.strictEqual(typeof core.TOOL_LABELS[kind], "string", kind);
    assert.ok(core.TOOL_LABELS[kind].length > 2, kind);
  });
  // #223: fib_zone reads as bands, distinct from fib_time.
  assert.strictEqual(core.TOOL_LABELS.fib_zone, "Fibonacci bands");
  assert.notStrictEqual(core.TOOL_LABELS.fib_zone, core.TOOL_LABELS.fib_time);
});

test("labelFor: a known kind -> its human label; unknown/none -> the kind", () => {
  assert.strictEqual(core.labelFor("fib_ext"), "Fibonacci extension");
  assert.strictEqual(core.labelFor("fib_zone"), "Fibonacci bands");
  assert.strictEqual(core.labelFor("nope"), "nope");
  assert.strictEqual(core.labelFor(undefined), "");
});

// --- F9 R2 (#223): icon clarity at 18px --------------------------------------

// The widest RELATIVE leg in a path's ``d`` after its opening move — the
// arrowhead's real size (absolute coords would pass on the viewBox alone).
function headDelta(d) {
  const rel = d.replace(/^[Mm][^A-Za-z]*/, "");
  const nums = (rel.match(/-?\d+(?:\.\d+)?/g) || []).map(Number);
  return nums.length ? Math.max(...nums.map(Math.abs)) : 0;
}

test("ray's arrowhead spans >= 5 units, so it reads at 18px (#223)", () => {
  const ray = core.iconFor("ray");
  const heads = (ray.match(/<path d="([^"]+)"/g) || []).map((h) => h.match(/d="([^"]+)"/)[1]);
  assert.ok(heads.length >= 1, "ray has an arrowhead path");
  const span = Math.max(...heads.map(headDelta));
  assert.ok(span >= 5, `arrowhead too small to read: delta ${span}`);
});

test("fib_ext shows its extension beyond the 0/1 pair via a dashed leg (#223)", () => {
  const svg = core.iconFor("fib_ext");
  assert.match(svg, /stroke-dasharray/, "the projection leg is dashed");
});

test("fib_zone shows a diagonal band, distinct from the fib line stack (#223)", () => {
  const svg = core.iconFor("fib_zone");
  const diagonals = (svg.match(/<line [^>]*>/g) || [])
    .map((l) => ["x1", "y1", "x2", "y2"].map((k) => Number((l.match(new RegExp(k + '="(\\d+)"')) || [])[1])))
    .filter((c) => c.every((n) => !Number.isNaN(n)) && c[0] !== c[2] && c[1] !== c[3]);
  assert.ok(diagonals.length >= 1, "a diagonal hatch marks the band");
});
