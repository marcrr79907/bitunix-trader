// controllers/draft-preview.js — the transient preview of a half-collected draft.
//
// R2 #222: a 2/3-click draft used to draw nothing until the final click. This
// helper owns ONE throwaway primitive over the partial row: client-side only,
// never POSTed and never in the drawings list (#68) — so #68's single write
// path is untouched. DI factory: the caller injects the flow, the primitive
// factory and the style resolver; the helper owns ``previewRowData``/``previewPrim``.
import { previewRow } from "../drawing-click-flow-core.js";

export function createDraftPreview({ host, flow, makePrimitive, styleFor }) {
  let previewRowData = null;
  let previewPrim = null;

  // Detach the current preview and (re)attach it to ``candleSeries`` — the
  // CURRENT series, which changes after a rebuild.
  function attach(candleSeries) {
    const series = candleSeries || host.getCandleSeries();
    if (previewPrim) {
      if (series) series.detachPrimitive(previewPrim);
      previewPrim = null;
    }
    if (!previewRowData || !series || !series.attachPrimitive) return;
    // ``isSelected`` draws the anchor HANDLES so placed clicks are visible;
    // ``preview`` keeps a draft out of autoscale (no axis jump).
    previewPrim = makePrimitive(previewRowData, { isSelected: () => true, preview: true });
    series.attachPrimitive(previewPrim);
  }

  // Derive the preview from the flow draft and (re)attach it; no draft -> detach.
  function sync() {
    const p = flow.peek();
    previewRowData = p ? previewRow(p.kind, p.clicks) : null;
    if (previewRowData) previewRowData.style = styleFor(previewRowData.kind, previewRowData.points);
    attach();
  }

  // Drop the draft preview (ready / dialog / Escape / tool or symbol switch).
  function clear() {
    previewRowData = null;
    attach();
  }

  return { sync, attach, clear };
}
