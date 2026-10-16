// controllers/preference.js — approval tests for the extracted preference
// helpers (F5 FIX-4). Pure DI factory, DOM + fetch only (a tiny shim, no jsdom),
// mirroring the object-tree test precedent. These capture the behavior that
// lived in main.js:184-237 byte-for-byte so the extraction is provably safe.
import test from "node:test";
import assert from "node:assert";
import { createPreference } from "../../web/market/templates/market/controllers/preference.js";

function installDom() {
  const prev = globalThis.document;
  globalThis.document = {
    querySelector: (sel) =>
      sel === 'meta[name="csrf-token"]' ? { content: "csrf-abc" } : null,
  };
  return () => { globalThis.document = prev; };
}

function installFetch(handler) {
  const prev = globalThis.fetch;
  const calls = [];
  globalThis.fetch = (url, opts) => {
    calls.push({ url, opts });
    return handler(url, opts);
  };
  return { calls, restore: () => { globalThis.fetch = prev; } };
}

test("csrfToken: reads the meta content; a missing meta yields empty string", () => {
  const restore = installDom();
  try {
    const pref = createPreference({ config: { urls: { preference: "/x" }, saveDelay: 0 } });
    assert.strictEqual(pref.csrfToken(), "csrf-abc");
    globalThis.document.querySelector = () => null;
    assert.strictEqual(pref.csrfToken(), "");
  } finally { restore(); }
});

test("loadPreference: maps the saved body fields to the boot shape", async () => {
  const restore = installDom();
  const f = installFetch(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve({
      interval: "5m", scale_mode: "log", chart_type: "heikin", theme: "dark",
      smc: { swings: false },
    }) }),
  );
  try {
    const pref = createPreference({ config: { urls: { preference: "/pref" }, saveDelay: 0 } });
    assert.deepStrictEqual(await pref.loadPreference(), {
      interval: "5m", scaleMode: "log", chartType: "heikin", theme: "dark",
      smc: { swings: false },
    });
  } finally { f.restore(); restore(); }
});

test("loadPreference: a failed fetch falls back to the frozen defaults", async () => {
  const restore = installDom();
  const f = installFetch(() => Promise.resolve({ ok: false, status: 500 }));
  try {
    const pref = createPreference({ config: { urls: { preference: "/pref" }, saveDelay: 0 } });
    assert.deepStrictEqual(await pref.loadPreference(), {
      interval: "1m", scaleMode: "linear", chartType: "candles", theme: "system", smc: {},
    });
  } finally { f.restore(); restore(); }
});

test("savePreference: debounces one PUT carrying the merged patch + CSRF", async () => {
  const restore = installDom();
  const f = installFetch(() => Promise.resolve({ ok: true }));
  try {
    const pref = createPreference({ config: { urls: { preference: "/pref" }, saveDelay: 20 } });
    pref.savePreference({ interval: "5m" });
    pref.savePreference({ scale_mode: "log" }); // coalesces into the pending body
    await new Promise((r) => setTimeout(r, 60));
    assert.strictEqual(f.calls.length, 1, "one debounced PUT");
    assert.strictEqual(f.calls[0].url, "/pref");
    assert.strictEqual(f.calls[0].opts.method, "PUT");
    assert.strictEqual(f.calls[0].opts.headers["X-CSRFToken"], "csrf-abc");
    assert.deepStrictEqual(JSON.parse(f.calls[0].opts.body), {
      interval: "5m", scale_mode: "log",
    });
  } finally { f.restore(); restore(); }
});

test("savePreference: a failed PUT is silent (never rejects)", async () => {
  const restore = installDom();
  const f = installFetch(() => Promise.reject(new Error("boom")));
  try {
    const pref = createPreference({ config: { urls: { preference: "/pref" }, saveDelay: 0 } });
    pref.savePreference({ theme: "dark" });
    await new Promise((r) => setTimeout(r, 30)); // must not throw
    assert.strictEqual(f.calls.length, 1);
  } finally { f.restore(); restore(); }
});
