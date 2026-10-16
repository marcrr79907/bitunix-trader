// tool-icons-core.js — pure grouped drawing-tool vocabulary + inline SVG icons
// (F5 S2, R1/R4). Framework-free: no DOM, no chart lib, no network, no global
// state. A native ESM module imported in Node by the tests and in the browser
// by controllers/draw-toolbar.js.
//
// Icons are plain STRINGS built here (design D9), injected with innerHTML on a
// native button. Each carries NO event attribute — an inline `on*` would be an
// inline handler under the market page's strict CSP. `currentColor` makes them
// follow the theme (R10).

// Grouped vocab (Fork 5): 5 kinds -> 2/1/1/1. Singleton groups are honest —
// TradingView ships thin groups too; padding a group with an invented shape
// would misrepresent the tool set.
export const TOOL_GROUPS = [
  { label: "Lines", kinds: ["hline", "trendline"] },
  { label: "Fib", kinds: ["fib"] },
  { label: "Shapes", kinds: ["rect"] },
  { label: "Text", kinds: ["text"] },
];

// Object-tree group vocab (S3 consumes these labels; kept here so the icon
// vocabulary is the single source for both sidebar idioms).
export const TREE_GROUPS = [
  { label: "Drawings", kinds: ["hline", "trendline", "fib", "rect", "text"] },
  { label: "Indicators", kinds: [] },
];

const SVG_OPEN = '<svg viewBox="0 0 24 24" width="18" height="18" '
  + 'fill="none" stroke="currentColor" stroke-width="1.6" '
  + 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">';

// kind -> inner path markup (the open/close wrapper is added by iconFor).
const ICON_BODIES = {
  hline: '<line x1="3" y1="12" x2="21" y2="12"/>',
  trendline: '<line x1="4" y1="18" x2="20" y2="6"/>',
  fib: '<line x1="4" y1="8" x2="20" y2="8"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="16" x2="20" y2="16"/>',
  rect: '<rect x="4" y="6" width="16" height="12" rx="1"/>',
  text: '<polyline points="5 7 12 7 12 18"/><line x1="8" y1="18" x2="16" y2="18"/><line x1="19" y1="7" x2="19" y2="14"/>',
};

// A kind -> a self-contained inline-SVG string (no event attribute), or "" for
// an unknown kind (the caller skips the icon; never throws).
export function iconFor(kind) {
  const body = ICON_BODIES[kind];
  return body ? SVG_OPEN + body + "</svg>" : "";
}

// The accessible group name for a group descriptor (role="group" aria-label).
export function groupLabel(group) {
  return group ? group.label : "";
}

// --- object-tree row-control glyphs (F5) ------------------------------------
// Inline SVG strings, NO event attribute (CSP-clean). Not color-only (R6/R9):
// eye swaps filled/outline, lock swaps closed/open, alongside aria-pressed.
export const EYE_ON = `${SVG_OPEN}<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12Z"/>`
  + '<circle cx="12" cy="12" r="3"/></svg>';
export const EYE_OFF = `${SVG_OPEN}<path d="M3 3l18 18"/>`
  + '<path d="M10.6 5.1A10.9 10.9 0 0 1 12 5c7 0 11 7 11 7a18 18 0 0 1-3.2 4.2"/>'
  + '<path d="M6.1 6.1A18 18 0 0 0 1 12s4 7 11 7a10.9 10.9 0 0 0 4.4-.9"/></svg>';
export const LOCK_ON = `${SVG_OPEN}<rect x="5" y="11" width="14" height="9" rx="1"/>`
  + '<path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';
export const LOCK_OFF = `${SVG_OPEN}<rect x="5" y="11" width="14" height="9" rx="1"/>`
  + '<path d="M8 11V8a4 4 0 0 1 7-2.6"/></svg>';
export const TRASH = `${SVG_OPEN}<path d="M4 7h16"/><path d="M9 7V5h6v2"/>`
  + '<path d="M6 7l1 13h10l1-13"/></svg>';
export const GEAR = `${SVG_OPEN}<circle cx="12" cy="12" r="3"/>`
  + '<path d="M12 2v3M12 19v3M2 12h3M19 12h3'
  + 'M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1"/></svg>';
