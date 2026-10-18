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
