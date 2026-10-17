// drawing-click-flow-core.js — the ONE 1/2/3-click drawing state machine (F9 D6).
//
// Framework-free (no DOM, no chart library, no network, no global state),
// mirroring position-draft-core.js and the project's "pure core at the center,
// adapters at the edges" rule. Native ESM: imported in Node by the tests and in
// the browser by the drawings controller.
//
// It replaces the ad-hoc pendingAnchor / positionDraft pair in drawings.js with a
// single flow keyed by clicksFor(kind). ``collect`` accumulates clicks and returns
// the kind-shaped points on the final click; a tool switch, ``cancel`` or
// ``reset`` drops a half-collected draft. text/callout return a "dialog" status
// so the controller (not this core) owns the #text-dialog. Pure, never throws.
import { clicksFor } from "./drawing-tools-core.js";

// Existing kinds share the machine (D6) — the same counts the old controller used.
const BASE_CLICKS = { hline: 1, text: 1, trendline: 2, fib: 2, rect: 2, position: 3 };
const DIALOG_KINDS = ["text", "callout"];
// Price-only kinds accept a click with no bar under it; everything else needs
// a time anchor, so an off-bar click is ignored (mirrors the old controller).
const PRICE_ONLY = ["hline", "price"];

function countFor(kind) {
  return BASE_CLICKS[kind] !== undefined ? BASE_CLICKS[kind] : clicksFor(kind);
}

// The finished click list -> the kind-shaped points object (design Interfaces).
function shape(kind, pts) {
  const a = pts[0];
  const b = pts[1];
  const c = pts[2];
  if (kind === "position") return { entry: a, stop: b.price, take_profit: c.price };
  if (kind === "vline") return { time: a.time };
  if (kind === "price" || kind === "hline") return { price: a.price };
  if (kind === "text") return { time: a.time, price: a.price };
  if (kind === "channel" || kind === "fib_ext") return { p1: a, p2: b, p3: c };
  return { p1: a, p2: b };
}

export function createFlow() {
  let kind = null;
  let clicks = [];

  function collect(k, point) {
    if (!point) return null;
    const n = countFor(k);
    if (n <= 0) return null;
    if (PRICE_ONLY.indexOf(k) === -1 && (point.time === undefined || point.time === null)) {
      return null; // off-bar click: not an anchor
    }
    // A tool switch (or the first click) starts a fresh draft.
    if (k !== kind) { kind = k; clicks = []; }
    clicks.push(point);
    if (clicks.length < n) return { status: "pending" };
    const points = shape(kind, clicks);
    const dialog = DIALOG_KINDS.indexOf(kind) !== -1;
    cancel();
    return { status: dialog ? "dialog" : "ready", kind: k, points: points };
  }

  function cancel() {
    kind = null;
    clicks = [];
  }

  function active() {
    return clicks.length > 0;
  }

  function reset() {
    cancel();
  }

  return { collect, cancel, active, reset };
}
