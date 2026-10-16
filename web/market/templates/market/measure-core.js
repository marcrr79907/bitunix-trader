// measure-core.js — pure measure math for the market chart (issue #119, F6 R2).
//
// Framework-free (no DOM, no chart library, no network, no global state),
// mirroring chart-core.js and the project's "pure core at the center, adapters
// at the edges" rule. A native ESM module: imported in Node by the tests and in
// the browser by the measure controller.
//
// Bar/candle count reuses ``intervalSeconds`` from chart-core.js (single source)
// instead of re-deriving interval arithmetic, so the two never drift. The core
// NEVER throws: an off-value input degrades the affected field to null rather
// than raising (the readout shows an em dash).

import { intervalSeconds } from "./chart-core.js";

// A raw interval ("1m") or a seconds count -> seconds, or null when unusable.
function toSeconds(interval) {
  if (typeof interval === "number") return interval > 0 ? interval : null;
  if (typeof interval === "string" && interval) return intervalSeconds(interval);
  return null;
}

function num(v) {
  return typeof v === "number" && isFinite(v) ? v : null;
}

// Two points -> {priceDelta, pricePct, timeDelta, bars, candles}.
//
// a,b = {time:int|null, price:number|null}. Negative deltas are kept (direction
// is carried by the sign). timeDelta/bars/candles are null when either time is
// null (off-bar). candles === bars in v1 (one candle per bar); the key is kept
// for parity with the readout contract.
function measure(a, b, interval) {
  const out = { priceDelta: null, pricePct: null, timeDelta: null, bars: null, candles: null };
  const pa = a ? num(a.price) : null;
  const pb = b ? num(b.price) : null;
  if (pa !== null && pb !== null) {
    out.priceDelta = pb - pa;
    if (pa !== 0) out.pricePct = (out.priceDelta / pa) * 100;
  }
  const ta = a ? num(a.time) : null;
  const tb = b ? num(b.time) : null;
  const sec = toSeconds(interval);
  if (ta !== null && tb !== null && sec !== null) {
    out.timeDelta = tb - ta;
    out.bars = Math.round(out.timeDelta / sec);
    out.candles = out.bars;
  }
  return out;
}

// A measurement -> signed display strings for the DOM readout.
function formatMeasure(m) {
  const dash = "\u2014";
  const sign = (v) => (v >= 0 ? "+" : "");
  const price = (v) => (v === null || v === undefined ? dash : sign(v) + v.toFixed(2));
  const pct = (v) => (v === null || v === undefined ? dash : sign(v) + v.toFixed(2) + "%");
  const secs = (v) => (v === null || v === undefined ? dash : sign(v) + v + "s");
  const bars = (v) => (v === null || v === undefined ? dash : sign(v) + v);
  return {
    price: price(m ? m.priceDelta : null),
    pct: pct(m ? m.pricePct : null),
    time: secs(m ? m.timeDelta : null),
    bars: bars(m ? m.bars : null),
  };
}

export { measure, formatMeasure };
