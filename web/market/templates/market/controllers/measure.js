// controllers/measure.js — ephemeral measure tool controller (F6 S3).
//
// DI factory (R14): ``createMeasure({store,bus,host,config})`` →
// ``{attach, clearForSwitch}``. LEAF module — never imports main (S3 wires it
// there). The gesture owns its own ``#chart`` pointer listeners guarded by
// ``state.tool === "measure"`` and renders through its own ISeriesPrimitive
// with ``autoscaleInfo`` null (D1/D4, R6). The measure is EPHEMERAL: no store
// key, no bus event, no seam key, no persistence. Bar/candle math comes from
// the pure measure-core.js; the numbers live in the ``#measure-readout``
// aria-live DOM node (D8).
import { measure, formatMeasure } from "../measure-core.js";

export function createMeasure({ store, bus, host, config }) {
  const el = document.getElementById("chart");
  const readout = document.getElementById("measure-readout");
  const state = store.get();
  let a = null; // start point {time, price}
  let b = null; // current point {time, price}
  let drawing = false; // a press-drag is in progress
  let prim = null; // the ONE attached primitive (while a measurement exists)
  let primSeries = null; // the series ``prim`` is currently attached to
  let bound = false;
  const c = { chart: null, series: null, requestUpdate: null };

  const map = {
    x: function (time) { return c.chart ? c.chart.timeScale().timeToCoordinate(time) : null; },
    y: function (price) { return c.series ? c.series.priceToCoordinate(price) : null; },
  };

  // One v5 ISeriesPrimitive draws the two-point span + readout. autoscaleInfo is
  // ALWAYS null (a measure must never move the price scale, R3). Redraw only via
  // requestUpdate (#68) — never setData/update on the series.
  function makePrimitive() {
    return {
      attached: function (params) {
        c.chart = params.chart;
        c.series = params.series;
        c.requestUpdate = params.requestUpdate;
      },
      detached: function () { c.chart = null; c.series = null; c.requestUpdate = null; },
      requestUpdate: function () { if (c.requestUpdate) c.requestUpdate(); },
      paneViews: function () {
        return [{
          renderer: function () {
            return {
              draw: function (target) {
                target.useMediaCoordinateSpace(function (scope) {
                  drawMeasure(scope.context, scope.mediaSize);
                });
              },
            };
          },
        }];
      },
      autoscaleInfo: function () { return null; },
    };
  }

  function drawMeasure(ctx, size) {
    if (!a || !b) return;
    const x1 = map.x(a.time);
    const y1 = map.y(a.price);
    const x2 = map.x(b.time);
    const y2 = map.y(b.price);
    if (x1 === null || y1 === null || x2 === null || y2 === null) return;
    ctx.save();
    ctx.strokeStyle = ctx.fillStyle = "#2962ff";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x1, y2);
    ctx.moveTo(x1, y2);
    ctx.lineTo(x2, y2);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 0.12;
    ctx.fillRect(x1, Math.min(y1, y2), x2 - x1, Math.abs(y2 - y1));
    ctx.globalAlpha = 1;
    const m = measure(a, b, state.interval);
    const f = formatMeasure(m);
    ctx.font = "12px sans-serif";
    ctx.fillText(f.price + "  " + f.pct + "  " + f.time + "  " + f.bars + " bars", x1 + 4, y2 - 4);
    ctx.restore();
  }

  // Ensure ``prim`` sits on the CURRENT candle series. A chart rebuild (e.g. an
  // interval-only switch) recreates the series, so re-attach there (#188): the
  // primitive would otherwise stay glued to the destroyed series (readout alive,
  // canvas dead). Idempotent while the series is unchanged.
  function bindPrim() {
    const series = host.getCandleSeries();
    if (!series || !prim) return;
    if (primSeries === series) return;
    if (primSeries) primSeries.detachPrimitive(prim);
    series.attachPrimitive(prim);
    primSeries = series;
  }

  // Attach the primitive once (idempotent) and push the readout to the DOM.
  function ensurePrimitive() {
    const series = host.getCandleSeries();
    if (!series) return;
    if (!prim) prim = makePrimitive();
    bindPrim();
    writeReadout();
    if (prim.requestUpdate) prim.requestUpdate();
  }

  function writeReadout() {
    if (!readout) return;
    const f = formatMeasure(measure(a, b, state.interval));
    readout.textContent = f.price + " " + f.pct + " | " + f.time + " | " + f.bars + " bars";
  }

  function clear() {
    drawing = false;
    a = null;
    b = null;
    if (prim) {
      const series = primSeries || host.getCandleSeries();
      if (series) series.detachPrimitive(prim);
      prim = null;
      primSeries = null;
    }
    if (readout) readout.textContent = "";
  }

  // --- pointer gesture --------------------------------------------------------

  function local(e) {
    const rect = el.getBoundingClientRect();
    return { px: e.clientX - (rect.left || 0), py: e.clientY - (rect.top || 0) };
  }

  function pointAt(e) {
    const series = host.getCandleSeries();
    const chart = host.getChart();
    if (!series || !chart) return null;
    const p = local(e);
    const time = chart.timeScale().coordinateToTime(p.px);
    const price = series.coordinateToPrice(p.py);
    if (time === null || time === undefined || price === null || price === undefined) return null;
    return { time: time, price: price };
  }

  function onPointerDown(e) {
    if (state.tool !== "measure") return;
    if (e.button !== undefined && e.button !== 0) return;
    const p = pointAt(e);
    if (!p) return;
    a = p;
    b = p;
    drawing = true;
    ensurePrimitive();
    e.preventDefault();
    e.stopPropagation();
  }

  function onPointerMove(e) {
    if (!drawing || !a) return;
    const p = pointAt(e);
    if (!p) return;
    b = p;
    ensurePrimitive();
  }

  function onPointerUp() {
    drawing = false; // the measurement stays readable (no clear on release)
  }

  function onKeyDown(e) {
    if (e.key === "Escape" && (a || prim)) {
      clear();
      e.preventDefault();
    }
  }

  // Tool change away from "measure" cancels (R4); a symbol switch is handled by
  // main calling clearForSwitch (R4).
  store.subscribe(function () {
    if (state.tool !== "measure" && (a || prim)) clear();
  });

  // The ``#chart`` container survives a rebuild, so listeners bind ONCE. main
  // calls attach() after every build — which also RE-BINDS an existing
  // measurement's primitive to the new series (#188).
  function attach() {
    bindPrim();
    if (!el || bound) return;
    el.addEventListener("pointerdown", onPointerDown, true);
    el.addEventListener("pointermove", onPointerMove, true);
    el.addEventListener("pointerup", onPointerUp, true);
    el.addEventListener("pointercancel", onPointerUp, true);
    el.addEventListener("keydown", onKeyDown);
    bound = true;
  }

  function clearForSwitch() {
    clear();
  }

  return { attach, clearForSwitch };
}
