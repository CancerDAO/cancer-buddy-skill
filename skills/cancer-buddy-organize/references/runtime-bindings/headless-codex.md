# Runtime binding — headless Codex

This binding implements the same source-fidelity and authorization contract in a
single-process or platform-worker environment.

## Pipeline

For each uploaded source:

1. Create a stable `source_id`, hash the file, and store its bytes under an
   access-controlled, de-identified `raw/` filename. The organizer does not
   silently overwrite, transform, or delete it. Host retention policy controls
   later deletion or legal hold.
2. Prefer the file's native text/table layer when available. For scans, run an
   appropriate deterministic OCR/table/barcode extractor. Save engine, version,
   language, raw output, source spans, and adapter provenance.
3. Use Codex for layout reconstruction, candidate corrections, semantic labels,
   and PII semantic review. Preserve `raw_text` separately from any
   `proposed_text`; an LLM correction never overwrites the character source.
4. Independently reread names/identifiers, dates, drug names, dose/frequency,
   laboratory values/units/reference intervals, stage strings, variants/VAF, and
   accession numbers. Disagreement becomes `needs_human_review`.
5. Write a source-attributed sidecar. Unreadable content remains
   `unreadable/uncertain`; it is never guessed.

All sidecars must be complete before Phase 2 synthesis begins. Unsupported or
corrupt files receive an `[INGESTION_BLOCKED]` stub rather than being skipped.

## Locale and source language

The host forwards the current BCP-47 product locale when known. Locale controls
scaffold and explanations, not the source layer. Source clinical strings remain
unchanged; translation or normalization is an additive labeled field.

## Confirmation and truth layers

Headless confirmation is a product artifact:

1. Produce a diff with source/provenance and requested action.
2. The authenticated user confirms the administrative action in the UI.
3. Apply only the confirmed scoped change and append an audit event.

Patient confirmation can confirm what the patient reported; it cannot promote a
statement to `clinician_verified`, choose between conflicting clinician sources,
or create stage, ECOG, response, progression, or treatment-line truth. Silence
never authorizes deletion.

## Outputs and privacy gates

Phase 2 produces the canonical archive, source inventory, source-preserving JSON,
timeline, review flags, and derived HTML. PII review uses both an independent
semantic scan and deterministic shape checks. Failure or unavailability of either
layer blocks sharing.

`validate_structured_outputs.py` checks schemas, anchors, source-shape integrity,
inventory completeness, PII shapes, and HTML form. It does not decide whether a
clinical value is normal, severe, meaningful, or treatment-relevant. Phase 2.5
separately verifies that structured values can be reproduced from their sources.

The deterministic HTML path remains:

```bash
python3 skills/cancer-buddy-organize/scripts/render_html_template.py \
  --template skills/cancer-buddy-organize/references/templates/case-summary.template.html \
  --data <patient_dir>/.case_summary_data.json \
  --out <patient_dir>/病情简要总结.html

python3 skills/cancer-buddy-organize/scripts/validate_case_summary_html.py \
  --html <patient_dir>/病情简要总结.html \
  --template skills/cancer-buddy-organize/references/templates/case-summary.template.html
```

Any share action additionally requires host authentication, explicit confirmation
of recipient/scope/purpose/expiry, data minimization, residual-risk disclosure,
and an export that excludes `raw/`. A generated patient code or role file is not
authorization.
