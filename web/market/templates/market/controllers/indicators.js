// controllers/indicators.js — indicator config state + layout REST.
//
// DI factory (R14): ``create({store, bus, host, config})``. This is a LEAF
// module — it never imports main. Commands travel the bus: a style/period
// change emits ``indicator:changed`` (main rebuilds); a loaded layout emits
// ``layout:loaded``. Owns the indicator settings dialog and the layout
// GET/PUT (debounced save, R5).
//
// F5 S3: the checkbox/param DOM readers are DELETED — the object tree is the
// sole indicator UI, so membership/params are sourced from the STORE
// (design data flow d). ``openSettings(token)`` opens the shared dialog for the
// tree's gear button.
import { defaultsFor, normalize } from "../indicator-settings-core.js";
import { REGISTRY } from "../chart-registry-core.js";

export const DEFAULT_INDICATORS = ["sma", "ema", "rsi"];

// Tokens with an editable period and the server param key it maps to. Only
// these show a Period control in the settings dialog (F2.6); every other token
// keeps its style-only dialog.
export const PERIOD_PARAMS = Object.freeze({ sma: "sma_len", ema: "ema_len" });

// Fallback period for an untouched param token (mirrors the server _INT_PARAMS
// defaults so the dialog opens on a sane value before any save).
const PARAM_DEFAULTS = Object.freeze({ sma_len: 20, ema_len: 20 });

// F5 S3: the store SEEDS these defaults (the checkbox inputs that used to carry
// them are gone), so the boot default set sends the same params as before and
// the legend labels (e.g. "SMA 20") are unchanged. Single source: PERIOD_PARAMS.
export const DEFAULT_PARAMS = Object.freeze(
  Object.keys(PERIOD_PARAMS).reduce(function (out, token) {
    out[token] = { [PERIOD_PARAMS[token]]: PARAM_DEFAULTS[PERIOD_PARAMS[token]] };
    return out;
  }, {}),
);

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

// indicators = ["sma",...]; params = {sma: {sma_len: 20}, ...}; styles =
// {sma: {color,lineWidth,precision}, ...}; visible = {sma: false, ...}. params/
// styles/visible only matter for tokens actually selected. style/visible are
// emitted only when meaningful (F2.7 payload shape): a style when one is set; a
// ``visible:false`` when hidden (absent = visible → minimal payload, R4).
export function buildIndicators(indicators, params, styles, visible) {
  return indicators.map(function (token) {
    const entry = { token: token };
    if (params && params[token]) entry.params = params[token];
    if (styles && styles[token]) entry.style = styles[token];
    if (visible && visible[token] === false) entry.visible = false;
    return entry;
  });
}

function csrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : "";
}

// Shallow-copy a token->object map so a store.set patch never mutates the
// reference a subscriber may still hold.
function copyMap(map) {
  const out = {};
  Object.keys(map || {}).forEach(function (k) { out[k] = map[k]; });
  return out;
}

export function createIndicators({ store, bus, config }) {
  const state = store.get();
  const dialog = document.getElementById("indicator-settings-dialog");
  const colorInput = document.getElementById("is-color");
  const widthInput = document.getElementById("is-width");
  const periodLabel = dialog && dialog.querySelector(".is-period-label");
  const periodInput = document.getElementById("is-period");
  const precisionInput = document.getElementById("is-precision");
  let dialogToken = null; // token the open dialog is editing

  // Fetch and apply the saved layout for ``symbol``/``interval``; fall back to
  // the default set on any failure (never a blank chart). Resolves either way.
  // Membership/params/styles/visibility are written STRAIGHT into the store —
  // the object tree re-renders from them (data flow c/d).
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
        // Seed the param defaults UNDER the saved params for params-capable
        // tokens (parity with the pre-S3 DOM inputs whose markup default was
        // 20): a token the layout omits keeps its default length.
        const params = {};
        Object.keys(DEFAULT_PARAMS).forEach(function (t) {
          params[t] = Object.assign({}, DEFAULT_PARAMS[t]);
        });
        const styles = {};
        const visible = {};
        body.indicators.forEach(function (i) {
          if (i.params) params[i.token] = i.params;
          // Style/visibility ride the layout entry's optional keys (F2.7); keep
          // them in dedicated top-level slots, never under params (no kline leak).
          if (i.style) styles[i.token] = i.style;
          if (i.visible === false) visible[i.token] = false;
        });
        state.params = params;
        state.styles = styles;
        state.indicatorVisible = visible;
        bus.emit("layout:loaded", { indicators: body.indicators, params: state.params });
      })
      .catch(function () {
        // Fall back to the default set (member-sourced from the store now that
        // the checkbox DOM is gone), including the seed params so the legend
        // labels and kline query match the pre-S3 default set.
        state.indicators = DEFAULT_INDICATORS.slice();
        state.params = DEFAULT_PARAMS;
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
        indicators: buildIndicators(
          state.indicators, state.params, state.styles, state.indicatorVisible,
        ),
      };
      fetch(config.urls.layout, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify(payload),
      }).catch(function () { /* in-session chart unaffected */ });
    }, config.saveDelay);
  }

  // Store -> state (used by main's rebuild): the store IS the source of truth.
  function readState() {
    return { indicators: state.indicators, params: state.params };
  }

  // Current style for ``token``: the stored style normalized over the registry
  // default (single color source). Never throws for a partial/absent style.
  function styleFor(token) {
    const stored = state.styles && state.styles[token];
    return normalize(token, stored, defaultsFor(REGISTRY, token));
  }

  // Populate the shared dialog for ``token`` from styles[token] + params[token]
  // (F2.6). The Period control is hidden for tokens without an editable param.
  // Called by the object tree's gear button (``onIndicatorSettings``).
  function openSettings(token) {
    if (!dialog || !token) return;
    dialogToken = token;
    const style = styleFor(token);
    colorInput.value = style.color;
    widthInput.value = style.lineWidth;
    precisionInput.value = style.precision;
    const param = PERIOD_PARAMS[token];
    if (param) {
      const stored = (state.params && state.params[token]) || {};
      periodLabel.hidden = false;
      periodInput.hidden = false;
      periodInput.value = stored[param] || PARAM_DEFAULTS[param] || 20;
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
    const styles = copyMap(state.styles);
    styles[token] = out.style;
    store.set({ styles: styles });
    // Period persists in params (unchanged channel, D3): params is store-sourced
    // now that the checkbox DOM is gone.
    if (out.period !== null) {
      const param = PERIOD_PARAMS[token];
      const params = copyMap(state.params);
      params[token] = Object.assign({}, params[token] || {}, { [param]: out.period });
      store.set({ params: params });
    }
    bus.emit("indicator:changed");
  }

  if (dialog) {
    // Native <dialog> closes on Esc / cancel with an empty returnValue: only
    // "ok" applies (drawings precedent). Focus returns to the opener natively.
    dialog.addEventListener("close", function () {
      if (dialog.returnValue === "ok") applyDialog();
      dialogToken = null;
      dialog.returnValue = "";
    });
  }

  return { loadLayout, saveLayout, readState, openSettings };
}
