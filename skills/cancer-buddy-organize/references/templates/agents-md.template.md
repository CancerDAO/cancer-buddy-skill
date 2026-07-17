# Patient archive pointer: {{patient_code}}

Summary label: {{one_line_condition}}

This file is a retrieval pointer, not a clinical summary and not authorization to access the archive.

## Read order

1. Authenticate/authorize the actor in the host.
2. Read `profile.json` only as an index; inspect provenance layer and verification status.
3. Read the relevant domain JSON and follow `source_refs` to the exact sidecar span.
4. Use `source_inventory.json` to locate the immutable raw source when authorized.
5. Check `readiness.json.review_flags` and unresolved `disputed` fields before using any value.

## Domain map

| Need | File | Safety condition |
|---|---|---|
| diagnosis/stage records | `patient_summary.json` | copy source wording; do not restage |
| molecular records | `molecular.json` | inspect report/sample/method/quality; do not match drugs |
| treatment history | `treatment_lines.json` | chronological episodes; line labels only if documented |
| labs | `labs.json` | use each result's unit/range/date/source; no universal grading |
| symptoms/observations | `longitudinal_observations.json` | preserve patient/device/clinical layers; not response |
| document gaps | `missing_items.json` | existing-document inventory only; never order tests |

## Non-negotiable rules

- Do not infer diagnosis, stage, ECOG, response, progression, treatment line, prognosis, or eligibility.
- Patient/caregiver confirmation can archive a reported statement but cannot overwrite clinician/source facts.
- Conflicts remain disputed until a formal amendment or authorized clinician attestation.
- Preserve source text; normalization/translation is additive and validated.
- Every factual statement needs a resolvable source anchor. Missing source means omit or label unknown.
- Follow root `references/clinical-content-governance.md` and `references/safety-guardrails.md`.
