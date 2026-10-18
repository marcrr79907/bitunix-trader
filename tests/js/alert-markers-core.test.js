// Pure alert-markers-core tests — node --test (no DOM, no chart lib, no network).
//
// Spec chart-alerts R4 (armed/fired markers) + the frozen S4 precedence mirrored
// from market/views.py:104-116 (fired > armed > inactive > none). The core is
// pure and imports nothing; LWC v5 marker objects are plain data here.
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  COLORS,
  stateOf,
  markersFor,
  summaryOf,
} from "../../web/market/templates/market/alert-markers-core.js";

const SRC = readFileSync(
  fileURLToPath(new URL("../../web/market/templates/market/alert-markers-core.js", import.meta.url)),
  "utf8",
);

const ANCHOR = 1729300000;

// --- stateOf: the frozen S4 precedence --------------------------------------

test("stateOf: null rule -> none", () => {
  assert.strictEqual(stateOf(null), "none");
  assert.strictEqual(stateOf(undefined), "none");
});

test("stateOf: fired wins over armed", () => {
  assert.strictEqual(stateOf({ is_active: true, last_fired_at: 1 }), "fired");
  assert.strictEqual(stateOf({ is_active: false, last_fired_at: 1 }), "fired");
});

test("stateOf: active without last_fired_at -> armed", () => {
  assert.strictEqual(stateOf({ is_active: true, last_fired_at: null }), "armed");
});

test("stateOf: existing but inactive -> inactive", () => {
  assert.strictEqual(stateOf({ is_active: false, last_fired_at: null }), "inactive");
});

test("stateOf: a non-object rule never throws", () => {
  assert.doesNotThrow(() => stateOf("x"));
  assert.doesNotThrow(() => stateOf(42));
  assert.strictEqual(stateOf("x"), "inactive");
});

// --- markersFor: anchors, shape, text ---------------------------------------

test("markersFor: one marker per active rule, fired anchored at last_fired_at", () => {
  const rules = [{ condition: { level: 100.5 }, is_active: true, last_fired_at: 1729220400 }];
  assert.deepStrictEqual(markersFor(rules, ANCHOR), [
    {
      time: 1729220400,
      position: "aboveBar",
      shape: "arrowDown",
      text: "F 100.5",
      color: COLORS.fired,
    },
  ]);
});

test("markersFor: armed anchored at the newest candle, below the bar", () => {
  const rules = [{ condition: { level: 100.5 }, is_active: true, last_fired_at: null }];
  assert.deepStrictEqual(markersFor(rules, ANCHOR), [
    {
      time: ANCHOR,
      position: "belowBar",
      shape: "circle",
      text: "A 100.5",
      color: COLORS.armed,
    },
  ]);
});

test("markersFor: armed and fired differ by shape AND text AND position", () => {
  const [fired] = markersFor([{ condition: { level: 10 }, is_active: true, last_fired_at: 1 }], ANCHOR);
  const [armed] = markersFor([{ condition: { level: 10 }, is_active: true }], ANCHOR);
  assert.notStrictEqual(fired.shape, armed.shape);
  assert.notStrictEqual(fired.position, armed.position);
  assert.match(fired.text, /^F /);
  assert.match(armed.text, /^A /);
});

test("markersFor: inactive rules are omitted", () => {
  const rules = [{ condition: { level: 10 }, is_active: false, last_fired_at: null }];
  assert.deepStrictEqual(markersFor(rules, ANCHOR), []);
});

test("markersFor: a rule without a numeric level is skipped", () => {
  const rules = [
    { condition: { level: "10" }, is_active: true, last_fired_at: null },
    { condition: { level: null }, is_active: true, last_fired_at: null },
    { condition: null, is_active: true, last_fired_at: null },
    { condition: { level: 1 }, is_active: true, last_fired_at: null },
  ];
  const out = markersFor(rules, ANCHOR);
  assert.strictEqual(out.length, 1);
  assert.strictEqual(out[0].text, "A 1");
});

test("markersFor: an off-series or non-finite last_fired_at drops the marker (R4)", () => {
  // Spec chart-alerts R4: a marker time that is not on the series MUST be
  // dropped. Faking the newest-candle time would misplace it (and LWC v5 would
  // discard it anyway); the fired state stays visible on /signals/.
  const rules = [{ condition: { level: 10 }, is_active: true, last_fired_at: "nope" }];
  assert.deepStrictEqual(markersFor(rules, ANCHOR), []);
  const offSeries = [{ condition: { level: 10 }, is_active: true, last_fired_at: Infinity }];
  assert.deepStrictEqual(markersFor(offSeries, ANCHOR), []);
});

test("markersFor: a missing/non-finite anchor drops armed rules", () => {
  const rules = [{ condition: { level: 10 }, is_active: true, last_fired_at: null }];
  assert.deepStrictEqual(markersFor(rules, null), []);
  assert.deepStrictEqual(markersFor(rules, NaN), []);
  assert.deepStrictEqual(markersFor(rules, Infinity), []);
});

test("markersFor: a non-array rules input -> []", () => {
  assert.deepStrictEqual(markersFor(null, ANCHOR), []);
  assert.deepStrictEqual(markersFor({}, ANCHOR), []);
});

test("markersFor: never throws and never mutates the input", () => {
  const rules = [{ condition: { level: 10 }, is_active: true, last_fired_at: null }];
  const snapshot = JSON.parse(JSON.stringify(rules));
  assert.doesNotThrow(() => markersFor([null, 42, "x", ...rules], ANCHOR));
  assert.deepStrictEqual(rules, snapshot);
});

// --- colors are injected (F10 UI #232) ---------------------------------------
//
// The core stays pure and import-free: the controller resolves the shell tokens
// and passes them in. Without an override the literals stay (the fallback map),
// so a DOM-less caller and the initial render keep working.

test("markersFor: injected colors override the fallback literals", () => {
  const rules = [
    { condition: { level: 10 }, is_active: true, last_fired_at: 1 },
    { condition: { level: 20 }, is_active: true, last_fired_at: null },
  ];
  const [fired, armed] = markersFor(rules, ANCHOR, { armed: "#111111", fired: "#222222" });
  assert.strictEqual(fired.color, "#222222");
  assert.strictEqual(armed.color, "#111111");
});

test("markersFor: a partial/invalid color map falls back per state", () => {
  const rules = [
    { condition: { level: 10 }, is_active: true, last_fired_at: 1 },
    { condition: { level: 20 }, is_active: true, last_fired_at: null },
  ];
  const [fired, armed] = markersFor(rules, ANCHOR, { fired: "#222222" });
  assert.strictEqual(fired.color, "#222222");
  assert.strictEqual(armed.color, COLORS.armed);
  const [fired2, armed2] = markersFor(rules, ANCHOR, { armed: 7, fired: "" });
  assert.strictEqual(fired2.color, COLORS.fired);
  assert.strictEqual(armed2.color, COLORS.armed);
});

test("summaryOf counts fired/armed and returns the aria-live sentence", () => {
  assert.strictEqual(summaryOf([]), "");
  assert.strictEqual(summaryOf(null), "");
  const one = [{ condition: { level: 1 }, is_active: true, last_fired_at: null }];
  assert.strictEqual(summaryOf(one), "1 alert: 0 fired, 1 armed");
  const three = [
    { condition: { level: 1 }, is_active: true, last_fired_at: 5 },
    { condition: { level: 2 }, is_active: true, last_fired_at: null },
    { condition: { level: 3 }, is_active: true, last_fired_at: null },
    { condition: { level: 4 }, is_active: false, last_fired_at: null },
  ];
  assert.strictEqual(summaryOf(three), "3 alerts: 1 fired, 2 armed");
});

// --- purity ------------------------------------------------------------------

test("alert-markers-core is pure: no imports, no DOM, no network, no globals", () => {
  assert.ok(!/\bimport\b/.test(SRC), "no imports");
  assert.ok(!/\bexport\s+\{[^}]+\}\s+from\b/.test(SRC), "no re-exports");
  assert.ok(!/document\.|window\.|fetch\(|XMLHttpRequest/.test(SRC), "no DOM / no network");
});
