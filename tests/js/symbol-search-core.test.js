// symbol-search-core.test.js — pure ranking contract (F11 A-S4, R19).
import test from "node:test";
import assert from "node:assert";
import { filterSymbols } from "../../web/market/templates/market/symbol-search-core.js";

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "WBTCUSDT", "DOGEUSDT"];

test("exact match ranks first", () => {
  assert.strictEqual(filterSymbols("BTCUSDT", SYMBOLS)[0], "BTCUSDT");
});

test("prefix outranks substring", () => {
  const out = filterSymbols("btc", SYMBOLS);
  assert.deepStrictEqual(out, ["BTCUSDT", "WBTCUSDT"]);
});

test("substring-only matches are included last", () => {
  const out = filterSymbols("usdt", ["BTCUSDT", "WBTCUSDT", "ETHUSDT"]);
  assert.deepStrictEqual(out, ["BTCUSDT", "ETHUSDT", "WBTCUSDT"]);
});

test("case-insensitive", () => {
  assert.deepStrictEqual(filterSymbols("BtC", SYMBOLS), filterSymbols("btc", SYMBOLS));
});

test("empty and whitespace queries return the capped full list", () => {
  assert.strictEqual(filterSymbols("", SYMBOLS).length, SYMBOLS.length);
  assert.strictEqual(filterSymbols("   ", SYMBOLS).length, SYMBOLS.length);
});

test("cap is applied after ranking so best matches survive", () => {
  const many = [];
  for (let i = 0; i < 300; i += 1) many.push("ZZZ" + String(i).padStart(3, "0") + "USDT");
  many.push("BTCUSDT");

  const out = filterSymbols("btc", many, 50);
  assert.deepStrictEqual(out, ["BTCUSDT"]);
  assert.strictEqual(filterSymbols("", many, 50).length, 50);
});

test("no match returns an empty array, not the whole list", () => {
  assert.deepStrictEqual(filterSymbols("zzzzz", SYMBOLS), []);
});

test("never throws on malformed input", () => {
  assert.deepStrictEqual(filterSymbols(null, null), []);
  assert.deepStrictEqual(filterSymbols(undefined, undefined), []);
  assert.deepStrictEqual(filterSymbols(42, SYMBOLS), filterSymbols("", SYMBOLS));
  assert.deepStrictEqual(filterSymbols("btc", [null, 1, {}, "BTCUSDT"]), ["BTCUSDT"]);
});

test("limit is clamped: 0 and negative return nothing, no inversion", () => {
  assert.deepStrictEqual(filterSymbols("", SYMBOLS, 0), []);
  assert.deepStrictEqual(filterSymbols("", SYMBOLS, -5), []);
  assert.deepStrictEqual(filterSymbols("btc", SYMBOLS, 1), ["BTCUSDT"]);
});
