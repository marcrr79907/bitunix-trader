// draft-preview controller helper — node --test, no DOM.
//
// The helper owns the ONE throwaway primitive drawn for a half-collected
// 1/2/3-click draft (R2 #222): it shapes the flow draft via previewRow, applies
// the caller's style resolver and attaches/detaches. It must NEVER POST and the
// primitive MUST stay out of the price autoscale (``preview: true``).
import test from "node:test";
import assert from "node:assert";

const { createDraftPreview } = await import(
  "../../web/market/templates/market/controllers/draft-preview.js"
);

function makeSeries() {
  const prims = [];
  return {
    prims,
    attachPrimitive(p) { prims.push(p); },
    detachPrimitive(p) {
      const i = prims.indexOf(p);
      if (i !== -1) prims.splice(i, 1);
    },
  };
}

function makeFlow(draft) {
  return { peek: () => draft };
}

function setup(draft) {
  const series = makeSeries();
  const created = [];
  const styled = [];
  const preview = createDraftPreview({
    host: { getCandleSeries: () => series },
    flow: makeFlow(draft),
    makePrimitive: (row, selection) => {
      const prim = { row, selection };
      created.push(prim);
      return prim;
    },
    styleFor: (kind, points) => {
      styled.push({ kind, points });
      return { color: "#abc", lineWidth: 2 };
    },
  });
  return { preview, series, created, styled };
}

test("no draft -> sync attaches nothing", () => {
  const f = setup(null);
  f.preview.sync();
  assert.strictEqual(f.series.prims.length, 0);
  assert.strictEqual(f.created.length, 0);
});

test("sync shapes the draft into one preview primitive with its style", () => {
  const clicks = [{ time: 1, price: 10 }];
  const f = setup({ kind: "channel", clicks: clicks });
  f.preview.sync();

  assert.strictEqual(f.created.length, 1);
  const prim = f.created[0];
  assert.strictEqual(prim.row.kind, "channel");
  assert.deepStrictEqual(prim.row.points, {
    p1: { time: 1, price: 10 }, p2: undefined, p3: undefined,
  });
  assert.deepStrictEqual(prim.row.style, { color: "#abc", lineWidth: 2 });
  assert.deepStrictEqual(f.styled, [{ kind: "channel", points: prim.row.points }]);
  assert.strictEqual(prim.selection.preview, true, "a preview never rescales");
  assert.strictEqual(prim.selection.isSelected(), true, "placed anchors stay visible");
  assert.deepStrictEqual(f.series.prims, [prim]);
});

test("repeated sync replaces the preview instead of stacking primitives", () => {
  const f = setup({ kind: "rect", clicks: [{ time: 1, price: 10 }] });
  f.preview.sync();
  const first = f.created[0];
  f.preview.sync();
  assert.strictEqual(f.created.length, 2);
  assert.deepStrictEqual(f.series.prims, [f.created[1]], "old preview detached");
  assert.ok(f.series.prims.indexOf(first) === -1);
});

test("attach re-attaches the draft to a rebuilt series", () => {
  const f = setup({ kind: "trendline", clicks: [{ time: 1, price: 10 }] });
  f.preview.sync();
  const rebuilt = makeSeries();
  f.preview.attach(rebuilt);
  assert.strictEqual(rebuilt.prims.length, 1, "re-attached after a rebuild");
  assert.strictEqual(rebuilt.prims[0].row.kind, "trendline");
});

test("clear detaches and a later attach draws nothing", () => {
  const f = setup({ kind: "hline", clicks: [{ time: 1, price: 10 }] });
  f.preview.sync();
  assert.strictEqual(f.series.prims.length, 1);
  f.preview.clear();
  assert.strictEqual(f.series.prims.length, 0);
  f.preview.attach(makeSeries());
  assert.strictEqual(f.created.length, 1, "no primitive rebuilt after clear");
});
