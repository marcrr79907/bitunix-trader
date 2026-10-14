# Delta for per-user-isolation

Issue #115 (Fase F2). **No requirement changes.** The `style` field is stored
inside the existing `ChartLayout.indicators` JSON, so ownership is unchanged:
`ChartLayout` remains the owned model and every read/write still routes through
`ChartLayout.for_user(request.user)` (R14.2/R14.3). No owned model, no
`OWNED_MODELS` entry, and no migration is added. A ≠ B isolation for styles is
inherited verbatim from the `chart-config` layout isolation contract.

## Non-Applicable Domains

- **per-user-isolation**: N/A — ownership shape is unchanged; style rides inside
  `ChartLayout`. The A ≠ B style scenario is specified in
  `chart-indicator-settings` (F2.9) and `chart-config` (R1/R3).
