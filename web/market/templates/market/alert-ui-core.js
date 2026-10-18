// alert-ui-core.js — small pure helpers shared by the alerts controller.
//
// Extracted from controllers/alerts.js to keep that module comfortably under
// the 300-line ceiling. No DOM, no chart library, no network: only the
// interval-eligibility vocabulary and the two display formatters the bell and
// dialog need (csrfToken stays in the controller — it reads the DOM).
//
// The eval-able set MUST match the server's CANDLE_INTERVALS
// (trading/candles.py): a rule on any other interval can never fire.

export const EVALUABLE = ["5m", "15m", "1h", "2h", "4h", "1d", "1w", "1M"];

// A rule on an interval the worker never evaluates can never fire.
export function eligible(interval) {
  return EVALUABLE.indexOf(interval) !== -1;
}

export function reasonText(interval) {
  return "Alerts cannot fire on the " + interval + " interval";
}

// A price with at most 6 decimals; a missing/NaN value degrades to an en dash.
export function fmtPrice(v) {
  return typeof v === "number" && isFinite(v) ? String(Math.round(v * 1e6) / 1e6) : "\u2013";
}

// The newest loaded candle's close, or null. The dialog's "no crosshair" seed
// (F10 UI #235) and the op default both read this.
export function lastClose(bars) {
  if (!Array.isArray(bars) || !bars.length) return null;
  const close = bars[bars.length - 1].close;
  return typeof close === "number" && isFinite(close) ? close : null;
}

// GET url for the ACTIVE pair's rules.
export function listUrl(base, symbol, interval) {
  const enc = encodeURIComponent;
  return base + "?symbol=" + enc(symbol) + "&interval=" + enc(interval);
}

// Paint the bell for the current crosshair state. No globals: the caller passes
// the elements, so this stays testable and keeps the controller thin. A fixed
// horizontal anchor (not the cursor x) keeps the target still — an x that
// tracked the pointer would move under it and no click could land.
export function paintBell(bell, cursor, interval, hovering, reasonEl) {
  if (!bell || hovering) return;
  bell.hidden = !cursor;
  if (!cursor) return;
  bell.style.top = cursor.y + "px";
  bell.setAttribute("aria-label", "Create price alert at " + fmtPrice(cursor.price));
  bell.disabled = !eligible(interval);
  if (eligible(interval)) {
    bell.removeAttribute("aria-describedby");
    bell.removeAttribute("title");
    return;
  }
  bell.setAttribute("aria-describedby", "alert-interval-reason");
  bell.setAttribute("title", reasonText(interval));
  if (reasonEl) reasonEl.textContent = reasonText(interval);
}

// The existing price rule whose level is nearest ``pxY`` within ``nearPx``
// (zoom-aware pixels, not % — design D7), or null. ``coordOf`` maps a level to a
// y coordinate; a non-number skips the rule. Pure: the caller supplies the map.
export function nearestRule(rules, pxY, nearPx, coordOf) {
  if (!Array.isArray(rules) || typeof coordOf !== "function") return null;
  let best = null;
  let bestDistance = nearPx + 1;
  rules.forEach(function (rule) {
    const condition = rule && rule.condition;
    if (!condition || condition.type !== "price") return;
    const y = coordOf(condition.level);
    if (typeof y !== "number" || !isFinite(y)) return;
    const distance = Math.abs(y - pxY);
    if (distance <= nearPx && distance < bestDistance) {
      best = rule;
      bestDistance = distance;
    }
  });
  return best;
}

// {url, body} for ONE alert write: a near rule is edited in place (PUT), else a
// new rule for the pair is created (POST). Pure so the request shape is testable
// without fetch.
export function writeRequest(base, pair, condition, target) {
  if (target) return { url: base + "/" + target.id, body: { condition: condition } };
  return {
    url: base,
    body: {
      symbol: pair.symbol,
      interval: pair.interval,
      condition: condition,
      is_active: true,
    },
  };
}
