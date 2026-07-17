# Longitudinal observation selection

Cancer Buddy does not maintain a cancer-type table that automatically designates serum markers as
efficacy monitors. Cancer type alone is insufficient to choose a marker, and many markers are not valid
stand-alone response measures.

## Default

- Store every result exactly with date, unit, report-specific reference range, method when available, and
  source anchor.
- Do not place a tumor marker into a “Tier 1” or “treatment response” card by cancer type.
- Do not infer response, progression, recurrence, prognosis, or treatment success from direction or fold
  change.
- Do not replace imaging or clinician assessment with a biomarker trend.

## Patient-facing trend eligibility

A series may be graphed only when all are true:

1. the same analyte/method and compatible units are confirmed across at least two source reports;
2. each point has a specimen/report date and source anchor;
3. no unresolved OCR, unit, identity, or source conflict affects the points;
4. the user requests the graph or a clinician-authored plan explicitly identifies the analyte for follow-up;
5. the caption is descriptive only: value/date change, with no efficacy interpretation.

When methods, units, assay limits, treatment timing, biliary obstruction/inflammation, or other relevant
context differ, split the series or do not graph it. Do not harmonize units unless a deterministic,
validated conversion preserves the raw value and records the formula.

Examples of allowed captions: `CEA: 12.4 ng/mL (2026-01-01) → 8.1 ng/mL (2026-02-01)`.

Forbidden captions: `提示治疗有效`, `疾病进展`, `复发风险下降`, `反应较好`, or any RECIST category.
