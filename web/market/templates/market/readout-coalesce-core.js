// readout-coalesce-core.js — pure frame-coalescer for DOM readout writes (#192).
//
// Framework-free (no imports, no DOM, no state beyond the closure), mirroring
// the project's "pure core at the center, adapters at the edges" rule. A
// ``polite`` aria-live region rewritten on every pointer/drag frame is noise, so
// this coalesces high-frequency ``schedule`` calls to at most ONE write per
// animation frame, always carrying the LATEST payload. ``flush`` writes now and
// cancels any pending frame (the final value is never dropped); ``cancel`` drops
// a pending write with no write. rAF is read from the global at call time, so a
// headless/Node caller without one degrades to an immediate write.

function createCoalescer(write) {
  let frame = null;
  let pending = null;

  // Called by a scheduled frame OR the no-rAF immediate path: emit the latest
  // payload. A null payload is valid (it clears the readout).
  function run() {
    const p = pending;
    frame = null;
    pending = null;
    write(p);
  }

  function schedule(payload) {
    pending = payload;
    if (frame !== null) return;
    const raf = globalThis.requestAnimationFrame;
    if (typeof raf !== "function") {
      run();
      return;
    }
    frame = raf(run);
  }

  function cancel() {
    if (frame !== null && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(frame);
    }
    frame = null;
    pending = null;
  }

  function flush(payload) {
    cancel();
    write(payload);
  }

  return { schedule, flush, cancel };
}

export { createCoalescer };
