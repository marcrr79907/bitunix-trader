// controllers/preference.js — preference PUT/GET helpers (F5 FIX-4, D11).
//
// DI factory (R14): ``create({config})`` → ``{csrfToken, savePreference,
// loadPreference}``. LEAF module — never imports main. Extracted verbatim from
// main.js (csrfToken/savePreference/loadPreference) so the orchestrator keeps
// real margin under the 300-line ceiling. No behavior change: the debounced
// PUT merges only its patch, a failed save is silent, and loadPreference falls
// back to the frozen defaults on a miss/failure (R10/CS6).

export function createPreference({ config }) {
  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  // Debounced preference PUT (R10/CS6), mirroring saveLayout. Each call merges
  // only its patch into the pending body, so two quick changes coalesce into one
  // PUT. A failed save is silent — the in-session chart is unaffected.
  let savePrefTimer = null;
  let savePrefPending = null;
  function savePreference(patch) {
    savePrefPending = Object.assign(savePrefPending || {}, patch);
    if (savePrefTimer) clearTimeout(savePrefTimer);
    savePrefTimer = setTimeout(function () {
      savePrefTimer = null;
      const body = savePrefPending;
      savePrefPending = null;
      fetch(config.urls.preference, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify(body),
      }).catch(function () { /* non-fatal */ });
    }, config.saveDelay);
  }

  // Fetch the saved preference before boot; a failure (or a miss) falls back to
  // the defaults so the chart is never blank and boot is never blocked (R10/CS6).
  function loadPreference() {
    return fetch(config.urls.preference)
      .then(function (r) {
        if (!r.ok) throw new Error("preference " + r.status);
        return r.json();
      })
      .then(function (body) {
        return {
          interval: (body && body.interval) || "1m",
          scaleMode: (body && body.scale_mode) || "linear",
          chartType: (body && body.chart_type) || "candles",
          theme: (body && body.theme) || "system",
          smc: (body && body.smc) || {}, // R7: persisted family toggles
        };
      })
      .catch(function () {
        return {
          interval: "1m",
          scaleMode: "linear",
          chartType: "candles",
          theme: "system",
          smc: {},
        };
      });
  }

  return { csrfToken, savePreference, loadPreference };
}
