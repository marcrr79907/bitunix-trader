// templates-core.js — pure mapping between a template entry list and the
// chart's store keys (F11-B, T4). Imports nothing: no DOM, no chart lib.
//
// A template stores the SAME shape a layout stores ({token, params?, style?,
// visible?}). Applying one is therefore a plain reshape into the four store
// keys the render path already consumes — no new write path, no new event.

// entries -> {indicators, params, styles, indicatorVisible}
// Unknown/legacy tokens are kept in ``indicators`` verbatim: the render path
// degrades (candles render, no series) rather than throwing, exactly like the
// layout loader does for a legacy token.
export function templateToStore(entries) {
  const list = Array.isArray(entries) ? entries : [];
  const indicators = [];
  const params = {};
  const styles = {};
  const indicatorVisible = {};

  list.forEach(function (entry) {
    if (!entry || typeof entry.token !== "string" || !entry.token) return;
    indicators.push(entry.token);
    if (entry.params && typeof entry.params === "object") {
      params[entry.token] = entry.params;
    }
    if (entry.style && typeof entry.style === "object") {
      styles[entry.token] = entry.style;
    }
    if (entry.visible === false) indicatorVisible[entry.token] = false;
  });

  return {
    indicators: indicators,
    params: params,
    styles: styles,
    indicatorVisible: indicatorVisible,
  };
}

// The inverse for the save path: reuse the SAME builder the layout save uses so
// a template and a layout can never disagree about shape.
export function storeToTemplate(buildIndicators, store) {
  const s = store || {};
  return buildIndicators(s.indicators, s.params, s.styles, s.indicatorVisible);
}
