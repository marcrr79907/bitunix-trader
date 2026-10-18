// Pure alert-condition-core tests — node --test (no DOM, no chart lib, no network).
//
// Spec chart-alerts R2 (condition dialog -> price condition). The op strings MUST
// equal the server engine's `_OPS` (src/alert_rules.py:27) — a mismatch would be a
// runtime 400 from `parse_condition`. The core imports nothing, never throws.
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  conditionFrom,
  levelFromInput,
  opFor,
} from "../../web/market/templates/market/alert-condition-core.js";

const SRC = readFileSync(
  fileURLToPath(new URL("../../web/market/templates/market/alert-condition-core.js", import.meta.url)),
  "utf8",
);

// Mirrors src/alert_rules.py `_OPS = ("above", "below")` — the server re-validates.
const ENGINE_OPS = ["above", "below"];

// --- conditionFrom -----------------------------------------------------------

test("conditionFrom accepts every engine op", () => {
  for (const op of ENGINE_OPS) {
    assert.deepStrictEqual(conditionFrom({ op, level: 50000 }), {
      type: "price",
      op,
      level: 50000,
    });
  }
});

test("conditionFrom returns a fresh object (no input mutation)", () => {
  const fields = { op: "above", level: 10 };
  const out = conditionFrom(fields);
  assert.notStrictEqual(out, fields);
  assert.deepStrictEqual(fields, { op: "above", level: 10 });
});

test("conditionFrom rejects an unknown op", () => {
  assert.strictEqual(conditionFrom({ op: "crosses", level: 10 }), null);
  assert.strictEqual(conditionFrom({ op: "ABOVE", level: 10 }), null);
  assert.strictEqual(conditionFrom({ op: "", level: 10 }), null);
  assert.strictEqual(conditionFrom({ level: 10 }), null);
});

test("conditionFrom rejects non-numeric, non-positive, NaN and Infinity levels", () => {
  for (const level of ["10", null, undefined, NaN, Infinity, -Infinity, 0, -1]) {
    assert.strictEqual(conditionFrom({ op: "above", level }), null, String(level));
  }
});

test("conditionFrom never throws on junk input", () => {
  for (const input of [null, undefined, 42, "x", {}, []]) {
    assert.doesNotThrow(() => conditionFrom(input));
    assert.strictEqual(conditionFrom(input), null);
  }
});

// --- levelFromInput ----------------------------------------------------------

test("levelFromInput accepts a plain positive number string", () => {
  assert.strictEqual(levelFromInput("50000"), 50000);
  assert.strictEqual(levelFromInput(" 50000 "), 50000);
  assert.strictEqual(levelFromInput("100.5"), 100.5);
});

test("levelFromInput accepts a comma decimal separator", () => {
  assert.strictEqual(levelFromInput("50000,5"), 50000.5);
});

test("levelFromInput rejects empty, junk, zero, negative, non-finite", () => {
  for (const raw of ["", "   ", "abc", "0", "-1", "Infinity", "NaN", null, undefined]) {
    assert.strictEqual(levelFromInput(raw), null, String(raw));
  }
});

test("levelFromInput never throws", () => {
  for (const raw of [Symbol("s"), {}, [], true]) {
    assert.doesNotThrow(() => levelFromInput(raw));
    assert.strictEqual(levelFromInput(raw), null);
  }
});

// --- opFor -------------------------------------------------------------------

test("opFor: above the last close -> above", () => {
  assert.strictEqual(opFor(100, 90), "above");
  assert.strictEqual(opFor(90, 90), "above");
});

test("opFor: below the last close -> below", () => {
  assert.strictEqual(opFor(80, 90), "below");
});

test("opFor: unknown/invalid reference defaults to above", () => {
  assert.strictEqual(opFor(100, null), "above");
  assert.strictEqual(opFor(100, NaN), "above");
  assert.strictEqual(opFor(100, Infinity), "above");
  assert.strictEqual(opFor(null, 90), "above");
});

// --- purity ------------------------------------------------------------------

test("alert-condition-core is pure: no imports, no DOM, no network", () => {
  assert.ok(!/\bimport\b/.test(SRC), "no imports");
  assert.ok(!/document\.|window\.|fetch\(|XMLHttpRequest/.test(SRC), "no DOM / no network");
});
