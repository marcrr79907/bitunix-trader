// position-draft-core.js — the 3-click position draft state machine (F6 D6).
//
// Framework-free (no DOM, no chart library, no network, no global state, no
// imports), mirroring the project's "pure core at the center, adapters at the
// edges" rule. The drawings controller owns the fetch/POST; this core only
// accumulates the three clicks (entry time+price, stop price, take_profit
// price) and can CANCEL a half-collected draft (Escape, design-system R6).
//
// A draft is created lazily on the first click; ``collect`` returns the finished
// ``{entry, stop, take_profit}`` points on the third click (and resets), or null
// while the draft is incomplete. ``cancel`` drops it; ``active`` reports whether
// a draft is in flight (so the controller can show a draft indicator).

export function createDraft() {
  let draft = null;

  function collect(point) {
    if (!point) return null;
    if (draft === null) {
      draft = { entry: point };
      return null;
    }
    if (draft.stop === undefined) {
      draft.stop = point.price;
      return null;
    }
    draft.take_profit = point.price;
    const points = draft;
    draft = null;
    return points;
  }

  function cancel() {
    draft = null;
  }

  function active() {
    return draft !== null;
  }

  return { collect, cancel, active };
}
