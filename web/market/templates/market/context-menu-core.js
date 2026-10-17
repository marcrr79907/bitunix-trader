// context-menu-core.js — pure model + roving-focus math for the chart menu.
//
// Framework-free (no DOM, no chart library, no network, no global state, no
// imports at all), mirroring drawing-core.js / position-core.js and the
// project's "pure core at the center, adapters at the edges" rule. A native ESM
// module: imported in Node by the tests and in the browser by the context-menu
// controller (F7, issue #120).
//
// The core owns only the MODEL: given the hit-test result ({hit, row}) and the
// current scale mode it returns the ordered item list; given the item count and
// a roving index it returns the next wrapped / clamped index. Rendering,
// hit-testing and the focus trap live in the DOM controller. Every function is
// pure and NEVER throws; malformed input degrades to the empty-chart list or 0.

var RESET_SCALE = { id: "reset-scale", label: "Reset scale", keyshortcut: "" };
var ADD_INDICATOR = { id: "add-indicator", label: "Add indicator", keyshortcut: "" };
var DELETE_ITEM = { id: "delete", label: "Delete", keyshortcut: "Delete" };
var DUPLICATE_ITEM = { id: "duplicate", label: "Duplicate", keyshortcut: "" };

function nonLinear(scaleMode) {
  return scaleMode !== "linear";
}

// {hit, row, scaleMode} -> ordered items. The caller resolves `hit` into a
// `row`; a drawing under the cursor (a `row`) yields delete/duplicate
// (+ reset-scale when non-linear); anything else (empty chart, unknown hit) is
// the empty-chart list (reset-scale when non-linear + add-indicator).
function menuModel(input) {
  try {
    var row = input ? input.row : null;
    var scaleMode = input ? input.scaleMode : undefined;
    if (row) {
      var drawing = [DELETE_ITEM, DUPLICATE_ITEM];
      return nonLinear(scaleMode) ? drawing.concat([RESET_SCALE]) : drawing;
    }
    return nonLinear(scaleMode) ? [RESET_SCALE, ADD_INDICATOR] : [ADD_INDICATOR];
  } catch (e) {
    return [ADD_INDICATOR];
  }
}

// Roving-focus step: move `delta` items from `index`, wrapping. 0 when empty.
function nextIndex(count, index, delta) {
  if (!(count > 0)) return 0;
  var i = typeof index === "number" && isFinite(index) ? index : 0;
  var d = typeof delta === "number" && isFinite(delta) ? delta : 0;
  return (((i + d) % count) + count) % count;
}

// Clamp `index` into 0..count-1. 0 when empty.
function clampIndex(count, index) {
  if (!(count > 0)) return 0;
  var i = typeof index === "number" && isFinite(index) ? index : 0;
  return Math.max(0, Math.min(count - 1, i));
}

export { menuModel, nextIndex, clampIndex };
