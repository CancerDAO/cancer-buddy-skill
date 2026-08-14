# Structured Output Schemas (Draft 2020-12)

These JSON Schemas define the structured outputs `cancer-buddy-organize` produces alongside `profile.json`. They are the contract that downstream consumers (vMTB, MTB-lite, trial-match, patient data export) rely on.

| File | Schema | What it carries |
|---|---|---|
| `patient_summary.json` | [patient_summary.schema.json](patient_summary.schema.json) | Demographics + diagnosis + current_status — single rollup |
| `timeline.json` | [timeline.schema.json](timeline.schema.json) | Chronological clinical events |
| `molecular.json` | [molecular.schema.json](molecular.schema.json) | NGS variants + IHC + MSI/MMR + TMB |
| `treatment_lines.json` | [treatment_lines.schema.json](treatment_lines.schema.json) | Chronological treatment episodes; line labels only when documented |
| `labs.json` | [labs.schema.json](labs.schema.json) | Lab panels with serial values |
| `comorbidities.json` | [comorbidities.schema.json](comorbidities.schema.json) | Conditions + long-term meds + allergies |
| `missing_items.json` | [missing_items.schema.json](missing_items.schema.json) | Existing-document inventory gaps; never a test recommendation |
| `source_inventory.json` | [source_inventory.schema.json](source_inventory.schema.json) | Native/deterministic extraction provenance, independent high-risk-field reread status, sidecar path, and protected `raw_path` |
| `high_risk_review.json` | [high_risk_review.schema.json](high_risk_review.schema.json) | Stable content-ID keyed independent reread results; the sidecar path is audit metadata, not identity |
| `readiness.json` | [readiness.schema.json](readiness.schema.json) | Documentation coverage plus source/faithfulness flags; never a clinical readiness score |
| `longitudinal_observations.json` | [longitudinal_observations.schema.json](longitudinal_observations.schema.json) | Neutral longitudinal observations; not a response trajectory |

## Anchor token contract

Every factual field carries source reference(s) and, where defined, a provenance layer and verification/dispute status. A conversation anchor supports only a patient/caregiver-reported statement; confirmation does not make it clinician/source truth. Structured JSON may use a safe bucket-relative path with or without a fragment; formal Markdown file refs must include a fragment:

```
JSON: <NN_bucket>/<…>/<file>.md
JSON: <NN_bucket>/<…>/<file>.md#L<start>-L<end>
Markdown: [[src:<NN_bucket>/<…>/<file>.md#section-anchor]]
conversation:<ISO8601>
```

File-anchor paths MUST begin with an `NN_` clinical-domain bucket prefix (`01_…` … `14_`, scheme_version 3) — the infrastructure vault `raw/` and quarantine `99_无关文件/` are never anchor targets, and the legacy `02_脱敏病历/` prefix is **retired**, and the transient central `ocr/` staging dir (live during a run, drained + deleted by Phase-2) is **not a valid anchor prefix** in final artifacts. Sidecars now live next to their image inside the clinical-domain bucket subdirectory. The full contract (regex included) is in [anchor-contract.md](anchor-contract.md).

In narrative artifacts (`timeline.md`, `case_text.md`, `review_summary.md`, and conditional `review_flags.md`), file anchors use `[[src:...#fragment]]` syntax. The deterministic validator rejects unsafe/escaping paths, missing targets, and path-only Markdown file refs — see [anchor-contract.md](anchor-contract.md).

## Validation

The synthesis worker validates each JSON it writes against its schema before saving. If validation fails, the file is NOT written and the error is surfaced into `readiness.json.warnings`.

A minimal validator is shipped in `scripts/validate_structured_outputs.py` (consumes `jsonschema>=4.18`). Its default mode validates artifacts that are present and tolerates missing in-progress outputs. Use `--require-complete` only at the final full-run/export boundary to enforce the complete lite artifact set and its documented conditional outputs.

### `--require-complete` lite artifact set

Always required: `profile.json`, `patient_summary.json`, `molecular.json`,
`treatment_lines.json`, `labs.json`, `comorbidities.json`, `timeline.json`,
`timeline.md`, `readiness.json`, `source_inventory.json`, `missing_items.json`,
`high_risk_review.json`,
`update_log.json`, `case_text.md`, `INDEX.md`, `review_summary.md`, `AGENTS.md`,
`.case_summary_data.json`, `病情简要总结.html`, `.semantic_pii_review.phase1.json`,
and the final clean `.semantic_pii_review.json`.

Conditional outputs are explicit:

- `review_flags.md` is required exactly when `readiness.json.review_flags[]` is non-empty.
- `longitudinal_observations.json` is required when an inventory row has
  `modality: timeseries`, `patient_summary.json` points to it, or one lab panel
  contains at least two values. Otherwise both files may be absent.

The validator is also an archive form gate. A final archive includes
`source_inventory.json`; every content unit points to a source-attributed sidecar and a protected original.
This structural check does not prove clinical correctness, authorization, anonymity, or minimum-necessary
sharing. Source-faithfulness and PII semantic review remain separate required gates.
