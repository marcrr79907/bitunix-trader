// symbol-search-core.js — pure symbol filtering/ranking (F11 A-S4, R19).
//
// Imports NOTHING: no DOM, no chart lib, no network. The finder UI
// (controllers/symbol-picker.js) owns the DOM; this core owns the ranking so
// the behavior is unit-testable in Node and the controller stays small.
//
// Tiers: 0 = exact (case-insensitive), 1 = prefix, 2 = substring. Results sort
// by tier then alphabetically, and the cap is applied AFTER sorting so the
// best-ranked matches always survive. Total: never throws for any input.

export function filterSymbols(query, symbols, limit = 50) {
  if (!Array.isArray(symbols)) return [];
  // Clamp so a caller passing 0/negative/Infinity can never invert the slice.
  const cap = Math.max(0, Number.isFinite(limit) ? Math.floor(limit) : 50);
  const rows = symbols.filter(function (s) {
    return typeof s === "string" && s.length > 0;
  });

  const raw = typeof query === "string" ? query.trim().toUpperCase() : "";
  if (raw === "") {
    return rows.slice(0, cap);
  }

  const scored = [];
  rows.forEach(function (symbol) {
    const upper = symbol.toUpperCase();
    let tier;
    if (upper === raw) tier = 0;
    else if (upper.startsWith(raw)) tier = 1;
    else if (upper.includes(raw)) tier = 2;
    else return;
    scored.push({ symbol: symbol, tier: tier });
  });

  scored.sort(function (a, b) {
    if (a.tier !== b.tier) return a.tier - b.tier;
    return a.symbol < b.symbol ? -1 : a.symbol > b.symbol ? 1 : 0;
  });

  return scored.slice(0, cap).map(function (row) {
    return row.symbol;
  });
}
