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
