// readout-coalesce-core.js — pure frame-coalescer (F6 UI #192). node --test.
//
// A ``polite`` aria-live region rewritten on every pointer/drag frame is noise.
// This pure core coalesces high-frequency writes to at most ONE per animation
// frame and keeps the LATEST payload, so the final value is never lost. rAF is
// read from the global at call time; with no rAF (headless/Node) it writes
// immediately. Framework-free: no imports, deterministic, never throws.
import test from "node:test";
import assert from "node:assert";
import { createCoalescer } from "../../web/market/templates/market/readout-coalesce-core.js";

function withRaf(fn) {
  const prev = globalThis.requestAnimationFrame;
  const prevCancel = globalThis.cancelAnimationFrame;
  const queued = [];
  globalThis.requestAnimationFrame = (cb) => { queued.push(cb); return cb; };
  globalThis.cancelAnimationFrame = (cb) => {
    const i = queued.indexOf(cb);
    if (i !== -1) queued.splice(i, 1);
  };
  try {
    return fn(() => { queued.splice(0).forEach((cb) => cb()); });
  } finally {
    if (prev === undefined) delete globalThis.requestAnimationFrame;
    else globalThis.requestAnimationFrame = prev;
    if (prevCancel === undefined) delete globalThis.cancelAnimationFrame;
    else globalThis.cancelAnimationFrame = prevCancel;
  }
}

test("N schedule calls inside one frame coalesce to ONE write (#192)", () => {
  const seen = [];
  withRaf((flush) => {
    const c = createCoalescer((p) => seen.push(p));
    for (let i = 0; i < 25; i++) c.schedule(i);
    assert.strictEqual(seen.length, 0, "no write before the frame");
    flush();
    assert.deepStrictEqual(seen, [24], "one write, carrying the LATEST payload");
  });
});

test("a schedule after the frame writes again (trailing edge) (#192)", () => {
  const seen = [];
  withRaf((flush) => {
    const c = createCoalescer((p) => seen.push(p));
    c.schedule("a");
    flush();
    c.schedule("b");
    flush();
    assert.deepStrictEqual(seen, ["a", "b"]);
  });
});

test("flush writes immediately and cancels the pending frame (#192)", () => {
  const seen = [];
  withRaf((flush) => {
    const c = createCoalescer((p) => seen.push(p));
    c.schedule("stale");
    c.flush("final");
    flush(); // a stale frame must NOT resurrect the old payload
    assert.deepStrictEqual(seen, ["final"]);
  });
});

test("with no rAF the schedule writes immediately (headless) (#192)", () => {
  const prev = globalThis.requestAnimationFrame;
  delete globalThis.requestAnimationFrame;
  try {
    const seen = [];
    const c = createCoalescer((p) => seen.push(p));
    c.schedule("x");
    assert.deepStrictEqual(seen, ["x"]);
  } finally {
    if (prev !== undefined) globalThis.requestAnimationFrame = prev;
  }
});

test("cancel drops a pending write; the next schedule still writes (#192)", () => {
  const seen = [];
  withRaf((flush) => {
    const c = createCoalescer((p) => seen.push(p));
    c.schedule("gone");
    c.cancel();
    flush();
    assert.deepStrictEqual(seen, [], "a cancelled frame writes nothing");
    c.schedule("after");
    flush();
    assert.deepStrictEqual(seen, ["after"]);
  });
});
