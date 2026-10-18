// alert-ui-core — pure interval-eligibility + display helpers (F10).
// The eval-able set MUST mirror the server's CANDLE_INTERVALS.
import test from "node:test";
import assert from "node:assert";
import {
  EVALUABLE,
  eligible,
  reasonText,
  fmtPrice,
  lastClose,
  listUrl,
  writeRequest,
  nearestRule,
  paintBell,
} from "../../web/market/templates/market/alert-ui-core.js";

test("EVALUABLE mirrors the server CANDLE_INTERVALS (8 intervals, no 1m)", () => {
  assert.deepStrictEqual(EVALUABLE, ["5m", "15m", "1h", "2h", "4h", "1d", "1w", "1M"]);
  for (const bad of ["1m", "3d", "6h", "8h", "12h"]) {
    assert.strictEqual(eligible(bad), false, bad);
  }
  for (const ok of EVALUABLE) assert.strictEqual(eligible(ok), true, ok);
});

test("reasonText names the interval", () => {
  assert.match(reasonText("1m"), /1m/);
});

test("fmtPrice trims to 6 decimals and degrades a non-number to an en dash", () => {
  assert.strictEqual(fmtPrice(62431.2847391234), "62431.284739");
  assert.strictEqual(fmtPrice(100), "100");
  assert.strictEqual(fmtPrice(NaN), "\u2013");
  assert.strictEqual(fmtPrice("100"), "\u2013");
  assert.strictEqual(fmtPrice(null), "\u2013");
});

test("lastClose reads the newest bar's close, or null when unusable (#235)", () => {
  assert.strictEqual(lastClose([{ close: 1 }, { close: 137.25 }]), 137.25);
  for (const bad of [[], null, undefined, {}, [{ close: "9" }], [{ close: Infinity }]]) {
    assert.strictEqual(lastClose(bad), null, JSON.stringify(bad));
  }
});

test("listUrl scopes the GET to the active pair", () => {
  assert.strictEqual(
    listUrl("/market/api/alerts", "BTCUSDT", "1h"),
    "/market/api/alerts?symbol=BTCUSDT&interval=1h",
  );
  assert.strictEqual(
    listUrl("/a", "A B&c", "1m"),
    "/a?symbol=A%20B%26c&interval=1m",
  );
});

test("writeRequest edits a near rule in place, otherwise creates for the pair", () => {
  const pair = { symbol: "BTCUSDT", interval: "1h" };
  const cond = { type: "price", op: "above", level: 100 };
  assert.deepStrictEqual(writeRequest("/a", pair, cond, { id: 7 }), {
    url: "/a/7",
    body: { condition: cond },
  });
  assert.deepStrictEqual(writeRequest("/a", pair, cond, null), {
    url: "/a",
    body: { symbol: "BTCUSDT", interval: "1h", condition: cond, is_active: true },
  });
});

function fakeBell() {
  const attrs = {};
  return {
    hidden: false, disabled: false, style: {}, attrs,
    setAttribute(k, v) { attrs[k] = String(v); },
    removeAttribute(k) { delete attrs[k]; },
  };
}

test("paintBell hides without a cursor and anchors on its y", () => {
  const bell = fakeBell();
  paintBell(bell, null, "1h", false, null);
  assert.strictEqual(bell.hidden, true);
  paintBell(bell, { y: 42, price: 101.5 }, "1h", false, null);
  assert.strictEqual(bell.hidden, false);
  assert.strictEqual(bell.style.top, "42px");
  assert.match(bell.attrs["aria-label"], /101\.5/);
});

test("paintBell keeps a hovered bell visible and describes an ineligible interval", () => {
  const bell = fakeBell();
  const reason = { textContent: "" };
  paintBell(bell, null, "1h", true, reason);
  assert.strictEqual(bell.hidden, false, "hovering does not hide the bell");

  paintBell(bell, { y: 1, price: 5 }, "3d", false, reason);
  assert.strictEqual(bell.disabled, true);
  assert.strictEqual(bell.attrs["aria-describedby"], "alert-interval-reason");
  assert.match(reason.textContent, /3d/);
  paintBell(bell, { y: 1, price: 5 }, "1h", false, reason);
  assert.strictEqual(bell.disabled, false);
  assert.strictEqual(bell.attrs["aria-describedby"], undefined);
});

test("nearestRule picks the closest price rule within the px window", () => {
  const rules = [
    { id: 1, condition: { type: "price", level: 100 } },
    { id: 2, condition: { type: "price", level: 104 } },
    { id: 3, condition: { type: "rsi", level: 101 } },
  ];
  const coord = (level) => 200 - level; // y grows downward
  assert.strictEqual(nearestRule(rules, 98, 10, coord).id, 1); // |98-100| = 2
  assert.strictEqual(nearestRule(rules, 95, 10, coord).id, 2); // |95-96| = 1
  assert.strictEqual(nearestRule(rules, 50, 10, coord), null); // nothing near
  assert.strictEqual(nearestRule(null, 98, 10, coord), null);
  assert.strictEqual(nearestRule(rules, 98, 10, null), null);
});

// Parity guard: the client's eval-able set must equal the server's
// CANDLE_INTERVALS, or the bell could create an alert the worker never
// evaluates (it would never fire).
test("EVALUABLE matches the server CANDLE_INTERVALS exactly", async () => {
  const { readFileSync } = await import("node:fs");
  const { fileURLToPath } = await import("node:url");
  const src = readFileSync(
    fileURLToPath(new URL("../../web/trading/candles.py", import.meta.url)),
    "utf8",
  );
  const block = src.slice(src.indexOf("INTERVAL_SECONDS = {"), src.indexOf("}", src.indexOf("INTERVAL_SECONDS = {")));
  const keys = [...block.matchAll(/"([^"]+)":/g)].map((m) => m[1]);
  assert.deepStrictEqual(keys.slice().sort(), EVALUABLE.slice().sort());
});
