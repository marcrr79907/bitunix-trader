// Pure drawing-tools-core tests — node --test (no DOM, no chart lib, no network).
//
// Spec chart-drawings R6 (per-kind geometry) / R10 (handles + drag) and the
// design "Descriptor-Map Contract": each F9 kind is a self-contained descriptor.
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  NEW_KINDS,
  TOOL_SPECS,
  clicksFor,
  defaultToolStyle,
  toolPath,
  toolHandles,
  toolBodyHit,
  toolDrag,
} from "../../web/market/templates/market/drawing-tools-core.js";

const SRC = readFileSync(
  fileURLToPath(new URL("../../web/market/templates/market/drawing-tools-core.js", import.meta.url)),
  "utf8",
);

// map: forward x/y; inverse time/price. ``right`` is the canvas right edge for ray.
const MAP = {
  x: (t) => t,
  y: (p) => p,
  time: (px) => px,
  price: (py) => py,
  right: 1000,
};

const COUNT = {
  ray: 2, vline: 1, channel: 3, price: 1,
  callout: 2, fib_ext: 3, fib_time: 2, fib_zone: 2,
};

test("NEW_KINDS exposes the eight F9 kinds in order", () => {
  assert.deepStrictEqual(NEW_KINDS, [
    "ray", "vline", "channel", "price", "callout", "fib_ext", "fib_time", "fib_zone",
  ]);
});

test("every kind has a complete descriptor (clicks/path/style/handles/bodyHit/drag)", () => {
  for (const k of NEW_KINDS) {
    const spec = TOOL_SPECS[k];
    assert.ok(spec, k + " spec");
    assert.strictEqual(spec.clicks, COUNT[k], k + " clicks");
    assert.strictEqual(typeof spec.path, "function", k + " path");
    assert.strictEqual(typeof spec.style, "object", k + " style");
    assert.strictEqual(typeof spec.handles, "function", k + " handles");
    assert.strictEqual(typeof spec.bodyHit, "function", k + " bodyHit");
    assert.strictEqual(typeof spec.drag, "function", k + " drag");
  }
});

test("clicksFor returns the per-kind click count", () => {
  for (const k of NEW_KINDS) assert.strictEqual(clicksFor(k), COUNT[k], k);
  assert.strictEqual(clicksFor("nope"), 0);
});

test("defaultToolStyle clones the kind style (never the same ref)", () => {
  const s = defaultToolStyle("ray");
  assert.strictEqual(typeof s.color, "string");
  assert.strictEqual(s.lineWidth, 1);
  assert.notStrictEqual(s, TOOL_SPECS.ray.style);
  // Unknown kind degrades to a neutral style, never throws.
  assert.strictEqual(typeof defaultToolStyle("nope").color, "string");
});

test("toolPath for ray projects b through p2 to the right edge", () => {
  const row = { kind: "ray", points: { p1: { time: 0, price: 0 }, p2: { time: 10, price: 10 } } };
  const p = toolPath("ray", row, MAP);
  assert.deepStrictEqual(p.a, { x: 0, y: 0 });
  assert.deepStrictEqual(p.b, { x: 1000, y: 1000 }); // slope 1 hits right edge at y=1000
});

test("toolPath for vline maps only the time to an x", () => {
  const row = { kind: "vline", points: { time: 42 } };
  assert.deepStrictEqual(toolPath("vline", row, MAP), { x: 42 });
});

test("toolPath for price maps only the price to a y and carries the label", () => {
  const row = { kind: "price", points: { price: 50 } };
  assert.deepStrictEqual(toolPath("price", row, MAP), { y: 50, price: 50 });
});

test("toolPath for channel returns a base a->b and a parallel c->d", () => {
  const row = {
    kind: "channel",
    points: { p1: { time: 0, price: 0 }, p2: { time: 10, price: 10 }, p3: { time: 0, price: 20 } },
  };
  const p = toolPath("channel", row, MAP);
  assert.deepStrictEqual(p.a, { x: 0, y: 0 });
  assert.deepStrictEqual(p.b, { x: 10, y: 10 });
  assert.deepStrictEqual(p.c, { x: 0, y: 20 });
  // d is p3 + (p2 - p1): the offset line is parallel by construction.
  assert.deepStrictEqual(p.d, { x: 10, y: 30 });
});

test("toolPath for fib_time returns per-ratio time levels", () => {
  const row = { kind: "fib_time", points: { p1: { time: 10 }, p2: { time: 20 } } };
  const p = toolPath("fib_time", row, MAP);
  assert.strictEqual(p.levels.length, 7);
  assert.strictEqual(p.levels[0].time, 10);
});

test("toolPath for unknown kind returns null (never throws)", () => {
  assert.strictEqual(toolPath("nope", { kind: "nope", points: {} }, MAP), null);
  assert.strictEqual(toolPath("ray", null, MAP), null);
});

test("toolHandles emits one handle per anchor; off-bar anchors are omitted", () => {
  const row = {
    kind: "channel",
    points: { p1: { time: 0, price: 0 }, p2: { time: 10, price: 10 }, p3: { time: 20, price: 20 } },
  };
  const h = toolHandles("channel", row.points, MAP);
  assert.deepStrictEqual(h, [
    { id: "p1", x: 0, y: 0 },
    { id: "p2", x: 10, y: 10 },
    { id: "p3", x: 20, y: 20 },
  ]);
  // An off-bar anchor drops out rather than becoming null.
  const off = toolHandles("channel", row.points, { ...MAP, x: (t) => (t === 20 ? null : t) });
  assert.deepStrictEqual(off.map((x) => x.id), ["p1", "p2"]);
});

test("toolHandles for vline/price use a single level handle", () => {
  assert.deepStrictEqual(toolHandles("vline", { time: 42 }, MAP), [{ id: "time", x: 42, y: 0 }]);
  assert.deepStrictEqual(toolHandles("price", { price: 50 }, MAP), [{ id: "price", x: 0, y: 50 }]);
});

test("toolBodyHit detects the ray body along its extended line", () => {
  const points = { p1: { time: 0, price: 0 }, p2: { time: 10, price: 10 } };
  assert.strictEqual(toolBodyHit("ray", points, 500, 500, MAP), true); // on the line
  assert.strictEqual(toolBodyHit("ray", points, 500, 600, MAP), false); // off it
});

test("toolBodyHit for price/vline is a single-axis proximity test", () => {
  assert.strictEqual(toolBodyHit("price", { price: 50 }, 999, 51, MAP), true);
  assert.strictEqual(toolBodyHit("price", { price: 50 }, 999, 90, MAP), false);
  assert.strictEqual(toolBodyHit("vline", { time: 42 }, 43, 999, MAP), true);
  assert.strictEqual(toolBodyHit("vline", { time: 42 }, 500, 999, MAP), false);
});

test("toolBodyHit never throws on an unknown kind or missing points", () => {
  assert.strictEqual(toolBodyHit("nope", {}, 0, 0, MAP), false);
  assert.strictEqual(toolBodyHit("ray", null, 0, 0, MAP), false);
});

test("toolDrag moving a ray handle updates only that anchor", () => {
  const points = { p1: { time: 0, price: 0 }, p2: { time: 10, price: 10 } };
  const out = toolDrag("ray", points, "p2", 5, 5, MAP);
  assert.deepStrictEqual(out.p1, { time: 0, price: 0 });
  assert.deepStrictEqual(out.p2, { time: 15, price: 15 });
});

test("toolDrag moving a channel body shifts every anchor", () => {
  const points = {
    p1: { time: 0, price: 0 },
    p2: { time: 10, price: 10 },
    p3: { time: 0, price: 20 },
  };
  const out = toolDrag("channel", points, "body", 2, 3, MAP);
  assert.deepStrictEqual(out.p1, { time: 2, price: 3 });
  assert.deepStrictEqual(out.p2, { time: 12, price: 13 });
  assert.deepStrictEqual(out.p3, { time: 2, price: 23 });
});

test("toolDrag for vline moves time only; price adds nothing", () => {
  const out = toolDrag("vline", { time: 42 }, "time", 5, 9, MAP);
  assert.deepStrictEqual(out, { time: 47 });
});

test("toolDrag for price moves price only; time adds nothing", () => {
  const out = toolDrag("price", { price: 50 }, "price", 7, 5, MAP);
  assert.deepStrictEqual(out, { price: 55 });
});

test("toolDrag never throws and returns fresh points on an unknown kind", () => {
  const points = { p1: { time: 0, price: 0 }, p2: { time: 1, price: 1 } };
  assert.deepStrictEqual(toolDrag("nope", points, "body", 1, 1, MAP), points);
  assert.deepStrictEqual(toolDrag("ray", null, "p1", 1, 1, MAP), {});
});

test("drawing-tools-core imports only pure cores + the DOM-guarded token read", () => {
  assert.ok(/from "\.\/fib-tools-core\.js"/.test(SRC), "imports fib-tools-core");
  // #221: theme-core.token is the one DOM-touching import, guarded to a fallback.
  assert.ok(/from "\.\/theme-core\.js"/.test(SRC), "imports theme-core token()");
  assert.ok(!/from "(?!\.\/(drawing-core|fib-tools-core|theme-core)\.js)/.test(SRC),
    "no other imports");
  assert.ok(!/document\.|window\.|fetch\(/.test(SRC), "no DOM / no network");
});

// --- F9 #221: per-kind palette resolves theme tokens -------------------------

// DOM shim: theme-core.token reads getComputedStyle on the document element.
function withTokens(values, fn) {
  const prevDoc = globalThis.document;
  const prevGcs = globalThis.getComputedStyle;
  globalThis.document = { documentElement: {} };
  globalThis.getComputedStyle = () => ({ getPropertyValue: (n) => values[n] || "" });
  try {
    return fn();
  } finally {
    if (prevDoc === undefined) delete globalThis.document;
    else globalThis.document = prevDoc;
    if (prevGcs === undefined) delete globalThis.getComputedStyle;
    else globalThis.getComputedStyle = prevGcs;
  }
}

const TOKEN_OF = {
  ray: "--draw-ray", vline: "--draw-vline", channel: "--draw-channel",
  price: "--draw-price", callout: "--draw-callout", fib_ext: "--draw-fib-ext",
  fib_time: "--draw-fib-time", fib_zone: "--draw-fib-zone",
};

test("defaultToolStyle resolves each kind's --draw-* token, not the literal (#221)", () => {
  // Deliberately NON-palette values so a hard-coded literal fails.
  const stub = {};
  Object.keys(TOKEN_OF).forEach((k, i) => { stub[TOKEN_OF[k]] = `#00000${i}`; });
  withTokens(stub, () => {
    Object.keys(TOKEN_OF).forEach((k) => {
      assert.strictEqual(defaultToolStyle(k).color, stub[TOKEN_OF[k]], k);
    });
  });
});

test("defaultToolStyle falls back to a per-kind literal without a DOM (#221)", () => {
  Object.keys(TOKEN_OF).forEach((k) => {
    const c = defaultToolStyle(k).color;
    assert.match(c, /^#[0-9a-f]{6}$/i, k + " literal fallback");
  });
  // Every kind seeds a DISTINCT colour (ray != trendline, vline != hline, fibs differ).
  const all = NEW_KINDS.map((k) => defaultToolStyle(k).color);
  assert.strictEqual(new Set(all).size, NEW_KINDS.length, "distinct per kind: " + all);
});

// F9 #221: the LIGHT theme drawing tokens must be legible on the white canvas.
// WCAG 2.x relative luminance (same helper as theme-core.test.js).
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
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

// Parse the two theme.css blocks into {dark, light} token maps.
function themeTokens() {
  const css = readFileSync(
    fileURLToPath(new URL(
      "../../web/accounts/templates/registration/theme.css", import.meta.url)),
    "utf8",
  );
  const block = (sel) => {
    const m = css.match(new RegExp(sel + "\\{([^}]*)\\}"));
    const out = {};
    if (m) {
      m[1].replace(/\/\*[\s\S]*?\*\//g, "").split(";").forEach((decl) => {
        const i = decl.indexOf(":");
        if (i > 0) out[decl.slice(0, i).trim()] = decl.slice(i + 1).trim();
      });
    }
    return out;
  };
  return { dark: block(":root"), light: block('\\[data-theme="light"\\]') };
}

test("every --draw-* token exists in BOTH theme sets (#221)", () => {
  const { dark, light } = themeTokens();
  const names = Object.values(TOKEN_OF);
  names.forEach((n) => {
    assert.ok(dark[n], `${n} missing from :root`);
    assert.ok(light[n], `${n} missing from [data-theme="light"]`);
  });
});

test("light --draw-* tokens meet WCAG contrast on the white canvas (#221)", () => {
  const { light } = themeTokens();
  const CANVAS = "#ffffff";
  Object.keys(TOKEN_OF).forEach((kind) => {
    const v = light[TOKEN_OF[kind]];
    const ratio = contrastRatio(v, CANVAS);
    // 11px canvas labels (fib ratios, price tags) need 4.5:1; strokes 3:1.
    const min = ["fib_ext", "fib_time", "fib_zone", "price", "callout"].includes(kind)
      ? 4.5 : 3;
    assert.ok(ratio >= min, `${kind} ${v} on ${CANVAS} = ${ratio.toFixed(2)}:1 < ${min}`);
  });
});

test("dark --draw-* tokens are legible on the dark canvas (#221)", () => {
  const { dark } = themeTokens();
  const CANVAS = "#0e1117";
  Object.keys(TOKEN_OF).forEach((kind) => {
    const ratio = contrastRatio(dark[TOKEN_OF[kind]], CANVAS);
    const min = ["fib_ext", "fib_time", "fib_zone", "price", "callout"].includes(kind)
      ? 4.5 : 3;
    assert.ok(ratio >= min, `${kind} ${dark[TOKEN_OF[kind]]} = ${ratio.toFixed(2)}:1 < ${min}`);
  });
});
