# Cancer-type existing-document inventories

These YAML files are archive-routing hints only. They never determine that a test, biomarker, scan,
procedure, consent, or follow-up visit is clinically indicated.

## Runtime meaning

- `mode: existing_document_inventory_only` is load-bearing.
- A category means “if this record already exists and is relevant to the user's requested artifact, ask
  whether they want to add it.”
- Absence means `not_in_archive` or `unknown`, never “care gap,” “must do,” or “recommended test.”
- Do not map an unknown cancer to a “closest fit.” Use `cancer_type: unknown` and the generic categories.
- Do not infer stage context. Use a stage-specific inventory only when a clinician-authored source states
  the stage/context and the inventory's current primary source has been live-verified.
- Any decision about whether to order a test belongs to the treating team under the current guideline.

## Generic categories

1. diagnosis/pathology reports already issued;
2. imaging reports and image media already obtained;
3. treatment orders, administration records, radiation/surgery reports and discharge summaries;
4. laboratory reports already obtained;
5. molecular/genetic reports only if already performed;
6. medication list, allergies, comorbidity and clinician-recorded function;
7. referral, second-opinion or trial documents already issued;
8. patient goals, information preferences and questions, clearly marked patient-reported.

## Output

Use `missing_items.schema.json` compatibility filename, but emit `document_gaps[]` with
`gap_type: not_in_archive|unknown|requested_by_clinician`. Never emit P0/P1/P2 clinical priority.

Static YAML files contain no treatment or test claims and need no guideline version. If a future inventory
adds a cancer-specific item, it must follow root `clinical-content-governance.md`, include applicability,
direct primary source/version/expiry, and human specialty review before patient-facing use.
