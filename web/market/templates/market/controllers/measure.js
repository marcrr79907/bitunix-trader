// controllers/measure.js — ephemeral measure tool controller (F6 S3).
//
// DI factory (R14): ``createMeasure({store,bus,host,config})`` →
// ``{attach, clearForSwitch}``. LEAF module — never imports main (S3 wires it
// there). The gesture owns its own ``#chart`` pointer listeners guarded by
// ``state.tool === "measure"`` and renders through its own ISeriesPrimitive
// with ``autoscaleInfo`` null (D1/D4, R6). The measure is EPHEMERAL: no store
// key, no bus event, no seam key, no persistence.
//
// ponytail: S2 ships the served module + DI shape so the allowlist route
// resolves (a missing route 404s the import and blanks the chart); the gesture
// body lands in S3 (task 3.6).

export function createMeasure({ store, bus, host, config }) {
  function attach() {}
  function clearForSwitch() {}

  return { attach, clearForSwitch };
}
