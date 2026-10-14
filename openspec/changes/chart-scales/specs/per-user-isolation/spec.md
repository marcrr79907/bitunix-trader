# Delta for per-user-isolation

Issue #121 (Fase F8). **No requirement changes.** The two new fields
(`scale_mode`, `chart_type`) are columns on the existing owned `ChartPreference`
model, so ownership is unchanged: `ChartPreference` remains the owned model, is
already in `OWNED_MODELS` (R14.3), and every read/write still routes through
`ChartPreference.for_user(request.user)` (R14.2/R14.3). No owned model, no
`OWNED_MODELS` entry, and no new isolation path is added. A ≠ B isolation for the
new fields is inherited verbatim from the `chart-config` R11/R12 contract.

## Non-Applicable Domains

- **per-user-isolation**: N/A — ownership shape is unchanged; `scale_mode`/
  `chart_type` ride on `ChartPreference`, already owned and already scoped through
  `for_user`. The A ≠ B scenario is specified in `chart-config` (R12).
