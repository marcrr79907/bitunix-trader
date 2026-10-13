# Delta for market-chart

Issue #116 (Fase F3). The full-height change is a **construction-option change
inside the host** (R14: "chart-host.js owns chart/series/panes/scales"). R14–R19
are behavior-preserving and remain in force unmodified; this delta only pins that
the shell work does not breach them.

## ADDED Requirements

### Requirement: R20 — Shell change stays inside the frozen host/seam envelope

The `autoSize: true` host option and the `#chart` markup change MUST stay within
R14 (host owns construction) and MUST NOT add a bus event, a module, or a
`window.marketChart` key. `window.marketChart` MUST keep exactly its 8 frozen
keys `{chart, candleSeries, panes, ready, drawings, smc, smcCounts, smcToggles}`
and `window.SmcOverlayCore` MUST be untouched. The E2E seam shape and timing
(R18) and the single-write-path invariants (R17) MUST be preserved; the existing
E2E assertions MUST stay green with NO edits.

#### Scenario: Seam stays 8 keys

- GIVEN a booted chart after the shell change
- WHEN `window.marketChart` is read
- THEN exactly the 8 frozen keys exist and `SmcOverlayCore` is reachable

#### Scenario: No new bus event or module

- GIVEN the shell change
- WHEN the module inventory and bus events are inspected
- THEN no module was added and the interval change reuses the existing `config:changed`

#### Scenario: Existing E2E stays green unedited

- GIVEN the 15 `select_option("#interval", …)` calls
- WHEN the suite runs after the shell change
- THEN they pass with no assertion edits
