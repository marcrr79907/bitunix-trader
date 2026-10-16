# Delta for smc-overlay

SMC family toggles become **persisted** user-global preferences (issue #124, Ola
3). R7 **inverts**: the toggles MUST survive a reload and MUST NOT reset on an
interval switch. The endpoint, payload, render contract, and single-source rules
(R1–R6, R8–R11) are unchanged.

## MODIFIED Requirements

### Requirement: R7 — Per-element toggles persist per user

The page MUST expose one show/hide checkbox per family
(`swings|structure|order_blocks|fvg|range|setups`), all ON by default. Toggling a
family MUST re-render the SMC layer WITHOUT refetching. Toggle state MUST be
persisted **user-global** on `ChartPreference` (a `smc` `JSONField`); it MUST be
loaded at boot and applied to the checkboxes, and it MUST NOT reset on an interval
switch (it is not per-chart). A change MUST debounce-save through the existing
partial-PUT `/market/api/preference`. A failed fetch or save MUST be non-fatal
(defaults to all-ON; in-session toggles keep working).
(Previously: session-only — toggle state MUST NOT be persisted, no model field.)

#### Scenario: Toggle hides a family without refetch

- GIVEN the SMC layer rendered and a request count of N
- WHEN a family checkbox is unchecked
- THEN that family's primitive/markers are hidden and request count stays N

#### Scenario: Toggle survives reload

- GIVEN a family toggled off and the preference saved
- WHEN the page is reloaded
- THEN that family is off again (restored from `ChartPreference`)

#### Scenario: Toggles do not reset on interval switch

- GIVEN `range` toggled off on `BTCUSDT 1m`
- WHEN `switchTo("BTCUSDT", "1h")` runs
- THEN `range` stays off (the toggle is user-global, not per-chart)

#### Scenario: Failed fetch is non-fatal

- GIVEN the preference fetch fails at boot
- WHEN the page boots
- THEN all families are ON and the SMC layer still renders
