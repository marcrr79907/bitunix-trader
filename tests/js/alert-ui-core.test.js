// alert-ui-core — pure interval-eligibility + display helpers (F10).
// The eval-able set MUST mirror the server's CANDLE_INTERVALS.
import test from "node:test";
import assert from "node:assert";
import { EVALUABLE, eligible, reasonText, fmtPrice } from "../../web/market/templates/market/alert-ui-core.js";

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
