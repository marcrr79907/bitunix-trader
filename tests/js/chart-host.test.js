// chart-host crosshair-seam tests — node --test.
//
// The host's chart is browser-only, so the delegation assertion lives in E2E.
// Here we lock the Node-testable contract: the seam is exported and is a
// null-guarded no-op before a chart exists (spec LC4 / R19).
import test from "node:test";
import assert from "node:assert";
import { createHost } from "../../web/market/templates/market/chart-host.js";

test("subscribeCrosshairMove is exported and mirrors subscribeClick", () => {
  const host = createHost();
  assert.strictEqual(typeof host.subscribeCrosshairMove, "function");
  assert.strictEqual(typeof host.subscribeClick, "function");
});

test("subscribeCrosshairMove is a null-guarded no-op with no chart", () => {
  const host = createHost();
  assert.doesNotThrow(() => host.subscribeCrosshairMove(() => {}));
});
