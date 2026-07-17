# Cancer Buddy Organize Contract

This contract separates source preservation, extraction, organization, and patient-facing rendering. It
does not authorize clinical interpretation.

## Pipeline

1. **Ingest**: retain authorized originals, hash bytes, create immutable source IDs, classify modality.
2. **Extract**: deterministic OCR/parser first where available; LLM-assisted layout/semantics second;
   independent verification for high-risk fields.
3. **Synthesize**: write schema v2 with provenance layer and verification status; preserve conflicts.
4. **Confirm archive actions**: confirmation allows a patient-reported note or explicit deletion; it does
   not establish clinical truth.
5. **Faithfulness gate**: verify every patient-visible value against source spans.
6. **Render**: deterministic templates only; no treatment path, response, stage, ECOG, severity, or
   prognosis inference.
7. **Validate/export**: schema, anchors, hashes, PII, conflict preservation, and share-policy gates.

## Clinical truth invariants

- `source_reported`, `patient_reported`, `caregiver_reported`, and `system_normalized` never overwrite
  each other.
- Source strings remain available. Validated normalization and translation are additive.
- Stage, ECOG, response, treatment line, laboratory values, molecular results, and clinician plan are
  copied only from attributable sources.
- Conflicts remain `disputed`; patient confirmation cannot clear them.
- Existing-document inventories do not recommend tests.
- Longitudinal observations are not response trajectories.
- Missing/failed extraction yields null and review flags, never a plausible value.

## Irreversible actions

No file is deleted on silence or model confidence. Quarantine and preview first; delete only after explicit,
item-specific confirmation and append an irreversible audit event. Corrections and superseded clinical
records remain versioned with immutable anchors.

## Canonical meaning

“Canonical file” means the current storage/contract location, not that its clinical content is correct.
Clinical validity is represented separately by source, provenance layer, verification status, and dispute
state.

## Output set

The patient directory contains the source inventory, raw vault, clinical-domain sidecars, schema-v2 JSON,
timeline, neutral record summary, review flags, document gaps, update log, and deterministic HTML. All
artifacts share one patient directory; `patient_code` is a locator, not authentication.

## Host responsibilities

The host authenticates actors, enforces consent/authorization and revocation, handles concurrent writes,
encrypts storage/transport, manages retention, and prevents the skill from overriding platform safety.
Runtime bindings may differ in mechanism but must satisfy these invariants.
