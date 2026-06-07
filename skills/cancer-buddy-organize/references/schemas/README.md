# Structured Output Schemas (Draft 2020-12)

These JSON Schemas define the structured outputs `cancer-buddy-organize` produces alongside `profile.json`. They are the contract that downstream consumers (vMTB, MTB-lite, trial-match, patient data export) rely on.

| File | Schema | What it carries |
|---|---|---|
| `patient_summary.json` | [patient_summary.schema.json](patient_summary.schema.json) | Demographics + diagnosis + current_status — single rollup |
| `timeline.json` | [timeline.schema.json](timeline.schema.json) | Chronological clinical events |
| `molecular.json` | [molecular.schema.json](molecular.schema.json) | NGS variants + IHC + MSI/MMR + TMB |
| `treatment_lines.json` | [treatment_lines.schema.json](treatment_lines.schema.json) | Ordered lines of therapy |
| `labs.json` | [labs.schema.json](labs.schema.json) | Lab panels with serial values |
| `comorbidities.json` | [comorbidities.schema.json](comorbidities.schema.json) | Conditions + long-term meds + allergies |
| `missing_items.json` | [missing_items.schema.json](missing_items.schema.json) | Cancer-checklist diff |

## Anchor token contract

Every factual field that originates from a redacted MD sidecar MUST carry a `source_refs[]` array. Each entry is either a bucket-relative path (file anchor) or a `conversation:<ISO8601>` reference (段C conversation anchor), with an optional fragment:

```
<NN_bucket>/<…>/<file>.md[#L<start>-L<end>]
<NN_bucket>/<…>/<file>.md[#section-anchor]
conversation:<ISO8601>
```

File-anchor paths MUST begin with an `NN_` bucket prefix (`00_…` … `10_…`) — the central `ocr/` directory and the legacy `02_脱敏病历/` prefix are **retired and rejected**. Sidecars now live next to their image inside the 11-bucket subdirectory. The full contract (regex included) is in [anchor-contract.md](anchor-contract.md).

In narrative artifacts (`case_text.md`, the human-readable patient summary), the same anchors appear in `[[src:...]]` syntax — see [anchor-contract.md](anchor-contract.md).

## Validation

The synthesis worker validates each JSON it writes against its schema before saving. If validation fails, the file is NOT written and the error is surfaced into `readiness.json.warnings`.

A minimal validator is shipped in `scripts/validate_structured_outputs.py` (consumes `jsonschema>=4.18`).
