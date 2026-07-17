# Source-grounded trend selection — manual E2E

This manual test verifies that a trend chart is a faithful display of reported
measurements, not a cancer-specific interpretation engine.

## Fixtures

Create two synthetic cases:

1. Multiple repeated measurements, each with date, value, unit, laboratory
   reference interval, report flag, source file, and page.
2. Only one measurement for each analyte, with one report carrying an explicit
   flag and another carrying no flag.

Do not add a cancer-to-marker priority table or universal normal ranges.

## Run

Execute the same summary pipeline used by the integration test:

```text
compute_version_delta.py
compute_sparklines.py
render_html_template.py
validate_case_summary_html.py
```

## Pass criteria

- Every plotted point is traceable to a source measurement with the same date,
  value, and unit.
- Repeated values with incompatible units are not silently combined or
  converted without a documented conversion source.
- A trend requires at least two comparable source points; otherwise the output
  states that no trend can be shown.
- The archive retains the laboratory's own flag and reference interval for each
  result. It does not calculate a new H/L/critical/severity label.
- Chart selection is driven by the documented user task and available source
  data, not a static cancer-type marker hierarchy.
- The chart does not label response, progression, recurrence, prognosis, or
  treatment effectiveness.
- Missing or contradictory measurements remain visible and are not imputed.
- The deterministic renderer may draw zero or more supplied series, but it does
  not perform clinical interpretation.

The automated renderer regression remains:

```bash
bash tests/integration/case-summary-trend-e2e.sh
```
