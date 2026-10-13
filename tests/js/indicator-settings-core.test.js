// indicator-settings-core — node --test (pure ESM: no DOM, no chart lib,
// no network, no REGISTRY import). Locks F2.1/F2.2/F2.3: the field vocabulary,
// the derived defaults, the total (never-throw) normalize, and validate.
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  FIELDS,
  TOKENS,
  defaultsFor,
  normalize,
  validate,
} from "../../web/market/templates/market/indicator-settings-core.js";

const CORE_PATH = fileURLToPath(
  new URL(
    "../../web/market/templates/market/indicator-settings-core.js",
    import.meta.url,
  ),
);

// Registry shape mirrors chart-host.REGISTRY: token -> {series:[{color}]}.
const REGISTRY = {
  sma: { series: [{ color: "#2962ff" }] },
  ema: { series: [{ color: "#ff6d00" }] },
};
const DEFAULTS = { color: "#000000", lineWidth: 1, precision: 2 };

test("FIELDS freezes the style vocabulary (color/lineWidth 1..4/precision 0..8)", () => {
  assert.strictEqual(Object.isFrozen(FIELDS), true);
  assert.strictEqual(FIELDS.color.type, "color");
  assert.deepStrictEqual(
    [FIELDS.lineWidth.min, FIELDS.lineWidth.max],
    [1, 4],
  );
  assert.deepStrictEqual(
    [FIELDS.precision.min, FIELDS.precision.max],
    [0, 8],
  );
});

test("TOKENS is the render vocabulary (frozen, unique)", () => {
  assert.strictEqual(Object.isFrozen(TOKENS), true);
  assert.ok(TOKENS.includes("sma"));
  assert.ok(TOKENS.includes("volume"));
  assert.strictEqual(new Set(TOKENS).size, TOKENS.length);
});

test("defaultsFor derives the color from the injected registry", () => {
  assert.deepStrictEqual(defaultsFor(REGISTRY, "ema"), {
    color: "#ff6d00",
    lineWidth: 1,
    precision: 2,
  });
});

test("defaultsFor unknown token -> safe style, never throws", () => {
  let out;
  assert.doesNotThrow(() => {
    out = defaultsFor(REGISTRY, "notreal");
  });
  assert.strictEqual(out.lineWidth, 1);
  assert.strictEqual(out.precision, 2);
  assert.match(out.color, /^#[0-9a-fA-F]{6}$/);
});

test("normalize round-trips a full valid style", () => {
  assert.deepStrictEqual(
    normalize("sma", { color: "#ff0000", lineWidth: 2, precision: 4 }, DEFAULTS),
    { color: "#ff0000", lineWidth: 2, precision: 4 },
  );
});

test("normalize clamps out-of-range and drops unknown keys", () => {
  assert.deepStrictEqual(
    normalize("sma", { lineWidth: 99, precision: -3, foo: "bar" }, DEFAULTS),
    { color: "#000000", lineWidth: 4, precision: 0 },
  );
});

test("normalize falls back to defaults for omitted keys", () => {
  assert.deepStrictEqual(normalize("sma", {}, DEFAULTS), DEFAULTS);
  assert.deepStrictEqual(normalize("sma", { lineWidth: 3 }, DEFAULTS), {
    color: "#000000",
    lineWidth: 3,
    precision: 2,
  });
});

test("normalize never throws on hostile input and yields a valid style", () => {
  for (const raw of [null, undefined, "nope", 42, [], { color: "red" }]) {
    let out;
    assert.doesNotThrow(() => {
      out = normalize("sma", raw, DEFAULTS);
    });
    assert.match(out.color, /^#[0-9a-fA-F]{6}$/);
    assert.ok(out.lineWidth >= 1 && out.lineWidth <= 4);
    assert.ok(out.precision >= 0 && out.precision <= 8);
  }
  // Malformed color falls back to the default; unknown token still returns a style.
  assert.strictEqual(normalize("sma", { color: "red" }, DEFAULTS).color, "#000000");
  assert.doesNotThrow(() => normalize("notreal", {}, DEFAULTS));
});

test("normalize is deterministic", () => {
  const raw = { color: "#abcdef", lineWidth: 9, precision: -1 };
  assert.deepStrictEqual(
    normalize("sma", raw, DEFAULTS),
    normalize("sma", raw, DEFAULTS),
  );
});

test("validate accepts a valid style", () => {
  assert.deepStrictEqual(
    validate("sma", { color: "#2962ff", lineWidth: 1, precision: 2 }),
    { ok: true, errors: [] },
  );
  assert.deepStrictEqual(validate("sma", {}).ok, true);
});

test("validate names each offender", () => {
  const out = validate("sma", { color: "#zzz", lineWidth: 9, precision: 20 });
  assert.strictEqual(out.ok, false);
  const joined = out.errors.join(" | ");
  assert.match(joined, /color/);
  assert.match(joined, /lineWidth/);
  assert.match(joined, /precision/);
});

test("validate rejects unknown keys and unknown tokens without throwing", () => {
  let unknownKey;
  assert.doesNotThrow(() => {
    unknownKey = validate("sma", { foo: 1 });
  });
  assert.strictEqual(unknownKey.ok, false);
  assert.match(unknownKey.errors.join(" "), /foo/);

  assert.strictEqual(validate("notreal", {}).ok, false);
  assert.strictEqual(validate("sma", null).ok, false);
});

test("the core imports nothing (pure ESM)", () => {
  const src = readFileSync(CORE_PATH, "utf8");
  // Match a real import/export-from statement at line start (not the word in prose).
  assert.strictEqual(/^\s*(import|export\s+[^;]*\bfrom)\b/m.test(src), false);
});
