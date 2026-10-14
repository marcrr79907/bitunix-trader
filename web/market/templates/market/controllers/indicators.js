// controllers/indicators.js — indicator panel DOM <-> config state + layout REST.
//
// DI factory (R14): ``create({store, bus, host, config})``. This is a LEAF
// module — it never imports main. Commands travel the bus: a toggle/param
// change emits ``indicator:changed`` (main rebuilds); a loaded layout emits
// ``layout:loaded``. Owns the indicator checkbox/param DOM and the layout
// GET/PUT (debounced save, R5).
import { defaultsFor, normalize } from "../indicator-settings-core.js";
import { REGISTRY } from "../chart-host.js";

export const DEFAULT_INDICATORS = ["sma", "ema", "rsi"];

// Tokens with an editable period and the server param key it maps to. Only
// these show a Period control in the settings dialog (F2.6); every other token
// keeps its style-only dialog.
export const PERIOD_PARAMS = Object.freeze({ sma: "sma_len", ema: "ema_len" });

// Dialog controls -> {style, period}. Pure: string inputs from the form are
// coerced, then normalized (clamped/dropped/defaulted) into the frozen style
// shape. ``period`` is the integer length for a PERIOD_PARAMS token (>= 1) or
// null. Never throws; malformed input degrades to ``defaults``.
export function settingsFromFields(token, fields, defaults) {
  const f = fields || {};
  const raw = {
    color: f.color,
    lineWidth: parseInt(f.lineWidth, 10),
    precision: parseInt(f.precision, 10),
  };
  const style = normalize(token, raw, defaults);
  const param = PERIOD_PARAMS[token];
  const n = parseInt(f.period, 10);
  const period = param && !isNaN(n) && n >= 1 ? n : null;
  return { style: style, period: period };
}

// DOM -> {token: {param: number}} for the checked, param-capable overlays.
export function readParams() {
  const out = {};
  document.querySelectorAll(".indicator-param").forEach(function (el) {
    const token = el.dataset.token;
    const n = parseInt(el.value, 10);
    if (!token || isNaN(n) || n < 1) return;
    (out[token] = out[token] || {})[el.dataset.param] = n;
  });
  return out;
}

// DOM -> ["sma", ...] for the checked indicator toggles.
export function readIndicators() {
  const toggles = document.querySelectorAll(".indicator-toggle");
  if (!toggles.length) return DEFAULT_INDICATORS.slice();
  return Array.prototype.slice
    .call(toggles)
    .filter(function (t) { return t.checked; })
    .map(function (t) { return t.value; });
}

// indicators = ["sma",...]; params = {sma: {sma_len: 20}, ...}; styles =
// {sma: {color,lineWidth,precision}, ...}. params/styles only matter for tokens
// actually selected. style is emitted only when one is set (F2.7 payload shape).
export function buildIndicators(indicators, params, styles) {
  return indicators.map(function (token) {
    const entry = { token: token };
    if (params && params[token]) entry.params = params[token];
    if (styles && styles[token]) entry.style = styles[token];
    return entry;
  });
}

function csrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : "";
}

export function createIndicators({ store, bus, config }) {
  const state = store.get();
  const toggles = Array.prototype.slice.call(
    document.querySelectorAll(".indicator-toggle"),
  );
  const paramInputs = Array.prototype.slice.call(
    document.querySelectorAll(".indicator-param"),
  );
  const gearButtons = Array.prototype.slice.call(
    document.querySelectorAll(".indicator-settings"),
  );
  const dialog = document.getElementById("indicator-settings-dialog");
  const colorInput = document.getElementById("is-color");
  const widthInput = document.getElementById("is-width");
  const periodLabel = dialog && dialog.querySelector(".is-period-label");
  const periodInput = document.getElementById("is-period");
  const precisionInput = document.getElementById("is-precision");
  let dialogToken = null; // token the open dialog is editing

  // Sync the panel DOM from a layout so a saved set wins over the markup.
  function applyLayout(indicators) {
    const tokens = indicators.map(function (i) { return i.token; });
    toggles.forEach(function (t) {
      t.checked = tokens.indexOf(t.value) !== -1;
    });
    const params = {};
    indicators.forEach(function (i) {
      if (i.params) params[i.token] = i.params;
    });
    paramInputs.forEach(function (el) {
      const token = el.dataset.token;
      if (params[token] && params[token][el.dataset.param] !== undefined) {
        el.value = params[token][el.dataset.param];
      }
    });
  }

  // Fetch and apply the saved layout for ``symbol``/``interval``; fall back to
  // the DOM defaults on any failure (never a blank chart). Resolves either way.
  function loadLayout(symbol, interval) {
    const url = config.urls.layout + "?symbol=" + encodeURIComponent(symbol)
      + "&interval=" + encodeURIComponent(interval);
    return fetch(url)
      .then(function (r) {
        if (!r.ok) throw new Error("layout " + r.status);
        return r.json();
      })
      .then(function (body) {
        if (!body || !body.indicators) return;
        state.indicators = body.indicators.map(function (i) { return i.token; });
        state.params = readParams();
        applyLayout(body.indicators);
        state.params = readParams();
        // Style rides the layout entry's optional ``style`` (F2.7); keep it in
        // the dedicated top-level slot, never under params (kline-leak guard).
        const styles = {};
        body.indicators.forEach(function (i) {
          if (i.style) styles[i.token] = i.style;
        });
        state.styles = styles;
        bus.emit("layout:loaded", { indicators: body.indicators, params: state.params });
      })
      .catch(function () {
        // Fall back to the DOM defaults already reflected in state.
        state.indicators = readIndicators();
        state.params = readParams();
      });
  }

  // Debounced PUT; the symbol/interval are captured at change time so a racing
  // switch cannot mis-save (R5). A failed save is silent (non-fatal).
  let saveTimer = null;
  function saveLayout() {
    if (saveTimer) clearTimeout(saveTimer);
    const symbol = state.symbol;
    const interval = state.interval;
    saveTimer = setTimeout(function () {
      saveTimer = null;
      const payload = {
        symbol: symbol,
        interval: interval,
        indicators: buildIndicators(state.indicators, state.params, state.styles),
      };
      fetch(config.urls.layout, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify(payload),
      }).catch(function () { /* in-session chart unaffected */ });
    }, config.saveDelay);
  }

  // Panel -> state (used by main's rebuild): reads the current DOM selection.
  function readState() {
    return { indicators: readIndicators(), params: readParams() };
  }

  // Current style for ``token``: the stored style normalized over the registry
  // default (single color source). Never throws for a partial/absent style.
  function styleFor(token) {
    const stored = state.styles && state.styles[token];
    return normalize(token, stored, defaultsFor(REGISTRY, token));
  }

  // The visible param input for ``token`` (e.g. the sma_len number), if any.
  function paramInputFor(token) {
    const param = PERIOD_PARAMS[token];
    if (!param) return null;
    return (
      paramInputs.find(function (el) {
        return el.dataset.token === token && el.dataset.param === param;
      }) || null
    );
  }

  // Populate the shared dialog for ``token`` from styles[token] + params[token]
  // (F2.6). The Period control is hidden for tokens without an editable param.
  function openDialog(token) {
    if (!dialog) return;
    dialogToken = token;
    const style = styleFor(token);
    colorInput.value = style.color;
    widthInput.value = style.lineWidth;
    precisionInput.value = style.precision;
    const param = PERIOD_PARAMS[token];
    const paramEl = paramInputFor(token);
    if (param && paramEl) {
      periodLabel.hidden = false;
      periodInput.hidden = false;
      periodInput.value = paramEl.value;
    } else {
      periodLabel.hidden = true;
      periodInput.hidden = true;
      periodInput.value = "";
    }
    dialog.showModal();
  }

  // Apply on confirm only (F2.6): write styles[token] + period into params, then
  // one ``indicator:changed`` (main rebuilds once, #68) + a debounced save.
  function applyDialog() {
    const token = dialogToken;
    if (!token) return;
    const out = settingsFromFields(
      token,
      {
        color: colorInput.value,
        lineWidth: widthInput.value,
        precision: precisionInput.value,
        period: PERIOD_PARAMS[token] ? periodInput.value : "",
      },
      defaultsFor(REGISTRY, token),
    );
    const styles = {};
    Object.keys(state.styles || {}).forEach(function (k) { styles[k] = state.styles[k]; });
    styles[token] = out.style;
    store.set({ styles: styles });
    // Period persists in params (unchanged channel, D3); readParams() reads the
    // DOM input, so writing the input value is the write.
    if (out.period !== null) {
      const paramEl = paramInputFor(token);
      if (paramEl) paramEl.value = out.period;
    }
    bus.emit("indicator:changed");
  }

  // Toggle = config change -> main rebuilds (setData path).
  toggles.forEach(function (t) {
    t.addEventListener("change", function () { bus.emit("indicator:changed"); });
  });
  paramInputs.forEach(function (el) {
    el.addEventListener("change", function () { bus.emit("indicator:changed"); });
  });
  gearButtons.forEach(function (btn) {
    btn.addEventListener("click", function () { openDialog(btn.dataset.token); });
  });
  if (dialog) {
    // Native <dialog> closes on Esc / cancel with an empty returnValue: only
    // "ok" applies (drawings precedent). Focus returns to the opener natively.
    dialog.addEventListener("close", function () {
      if (dialog.returnValue === "ok") applyDialog();
      dialogToken = null;
      dialog.returnValue = "";
    });
  }

  return { loadLayout, saveLayout, readState };
}
